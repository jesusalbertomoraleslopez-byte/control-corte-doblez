"""
=============================================================================
SIGRAMA - HERRAMIENTA LOCAL DE SINCRONIZACIÓN Z:\\ -> GOOGLE CLOUD STORAGE
Sincroniza carpetas de Órdenes de Fabricación (PDFs, NIFs, Excel, DXFs)
desde Z:\\14 - ORDENES DE FABRICACION al Bucket de GCS para Cloud Run.
=============================================================================
"""

import os
import sys
import io
import time
import json
import hashlib
from pathlib import Path
from datetime import datetime

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

try:
    from google.cloud import storage
except ImportError:
    print("❌ Error: google-cloud-storage no está instalado en el entorno.")
    print("Ejecute: pip install google-cloud-storage")
    sys.exit(1)

BUCKET_NAME = os.environ.get("GCS_BUCKET", "sigrama-corte-doblez-storage").strip()
Z_DRIVE_PATH = os.environ.get("Z_DRIVE_PATH", r"Z:\14 - ORDENES DE FABRICACION")
EXCEL_DB_LOCAL = APP_DIR / "sigrama_database.xlsx"

def calcular_md5(filepath):
    """Calcula el hash MD5 local para evitar subir archivos duplicados."""
    h = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

def analizar_archivos_carpeta(folder_path):
    """Detecta reportes PDF y archivos clave de ProNest en una carpeta."""
    res = {
        "resumen": None,
        "nido": None,
        "pieza": None,
        "nif": None,
        "excel": None,
        "otros": []
    }
    if not os.path.exists(folder_path):
        return res

    for f in os.listdir(folder_path):
        fp = os.path.join(folder_path, f)
        if not os.path.isfile(fp):
            continue
        fl = f.lower()
        if fl.endswith(".pdf"):
            if "resumen" in fl:
                res["resumen"] = f
            elif "cabezal" in fl or "nido" in fl:
                res["nido"] = f
            elif "pieza" in fl:
                res["pieza"] = f
            else:
                res["otros"].append(f)
        elif fl.endswith(".nif"):
            res["nif"] = f
        elif fl.endswith(".xlsx") and not fl.startswith("~$"):
            res["excel"] = f
        elif fl.endswith(".dxf"):
            res["otros"].append(f)

    return res

def sincronizar_z_hacia_gcs(max_ofs=None, solo_recientes=False):
    print("=" * 75)
    print(" 🚀 SIGRAMA - SINCRONIZADOR DE ÓRDENES DE FABRICACIÓN Z:\\ ➔ GCS")
    print(f" 📅 Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f" 📂 Origen: {Z_DRIVE_PATH}")
    print(f" ☁️ Destino: gs://{BUCKET_NAME}/ordenes_fabricacion/")
    print("=" * 75)

    if not os.path.exists(Z_DRIVE_PATH):
        print(f"\n❌ ERROR: La unidad de red '{Z_DRIVE_PATH}' no está disponible.")
        print("   Por favor verifique que su conexión de red o VPN esté activa.")
        return False

    print("\n⏳ Conectando con Google Cloud Storage...")
    try:
        client = storage.Client()
        bucket = client.bucket(BUCKET_NAME)
        if not bucket.exists():
            print(f"❌ ERROR: El bucket gs://{BUCKET_NAME} no existe o no se tiene acceso.")
            return False
    except Exception as e:
        print(f"❌ ERROR de autenticación en Google Cloud: {e}")
        return False
    print("✅ Conexión con Bucket GCS exitosa.\n")

    # 1. Respaldo de Base de Datos local a GCS
    if EXCEL_DB_LOCAL.exists() and EXCEL_DB_LOCAL.stat().st_size > 5000:
        print(f"📦 Respaldando base de datos activa ({EXCEL_DB_LOCAL.name})...")
        try:
            db_blob = bucket.blob(f"database/{EXCEL_DB_LOCAL.name}")
            db_blob.upload_from_filename(str(EXCEL_DB_LOCAL))
            print(f"   ✅ Base de datos subida a gs://{BUCKET_NAME}/database/{EXCEL_DB_LOCAL.name}")
        except Exception as edb:
            print(f"   ⚠️ Aviso: No se pudo respaldar la base de datos: {edb}")

    # 2. Obtener lista de blobs existentes en GCS para comparación rápida
    print("🔍 Inspeccionando catálogo actual en GCS...")
    blobs_existentes = {}
    for b in bucket.list_blobs(prefix="ordenes_fabricacion/"):
        blobs_existentes[b.name] = b.size
    print(f"   Encontrados {len(blobs_existentes)} archivos previos en GCS.")

    # 3. Escaneo de carpetas en Z:\
    print(f"\n📂 Escaneando carpetas en {Z_DRIVE_PATH}...")
    carpetas = sorted([d for d in os.listdir(Z_DRIVE_PATH) if os.path.isdir(os.path.join(Z_DRIVE_PATH, d))])
    print(f"   Se encontraron {len(carpetas)} carpetas en total.")

    subidos_count = 0
    omitidos_count = 0
    errores_count = 0
    ofs_manifest = []

    for idx, carpeta in enumerate(carpetas, 1):
        if max_ofs and idx > max_ofs:
            break

        c_path = os.path.join(Z_DRIVE_PATH, carpeta)
        diag = analizar_archivos_carpeta(c_path)
        completo = bool(diag["resumen"] and diag["nido"] and diag["pieza"])

        # Registro para manifiesto
        of_info = {
            "of_nombre": carpeta,
            "etiqueta": carpeta,
            "subcarpeta": "",
            "resumen_pdf": diag["resumen"],
            "nido_pdf": diag["nido"],
            "pieza_pdf": diag["pieza"],
            "nif": diag["nif"],
            "excel_existente": diag["excel"],
            "completo": completo,
            "tiene_excel": bool(diag["excel"]),
            "ultima_sync": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        ofs_manifest.append(of_info)

        # Archivos a sincronizar prioritarios: los 3 PDFs, el Excel y el NIF
        archivos_a_subir = []
        for clave in ["resumen", "nido", "pieza", "nif", "excel"]:
            fn = diag.get(clave)
            if fn:
                archivos_a_subir.append(os.path.join(c_path, fn))

        # También sincronizar PDFs adicionales si existen
        for extra in diag.get("otros", []):
            archivos_a_subir.append(os.path.join(c_path, extra))

        status_icono = "🟢" if completo else ("🟡" if (diag["resumen"] or diag["nido"] or diag["pieza"]) else "⚪")
        print(f"[{idx:03d}/{len(carpetas):03d}] {status_icono} {carpeta} ({len(archivos_a_subir)} archivos)")

        for filepath in archivos_a_subir:
            filename = os.path.basename(filepath)
            gcs_blob_name = f"ordenes_fabricacion/{carpeta}/{filename}"
            local_size = os.path.getsize(filepath)

            # Verificar si ya existe con el mismo tamaño en GCS
            if gcs_blob_name in blobs_existentes and blobs_existentes[gcs_blob_name] == local_size:
                omitidos_count += 1
                continue

            # Subir a GCS
            try:
                blob = bucket.blob(gcs_blob_name)
                blob.upload_from_filename(filepath)
                blobs_existentes[gcs_blob_name] = local_size
                subidos_count += 1
                print(f"      ⬆️ Subido: {filename} ({local_size:,} bytes)")
            except Exception as e:
                errores_count += 1
                print(f"      ❌ Error subiendo {filename}: {e}")

    # 4. Guardar manifiesto en GCS y localmente
    print("\n📝 Generando y guardando manifest_ofs.json...")
    manifest_payload = {
        "version": "1.0",
        "ultima_actualizacion": datetime.now().isoformat(),
        "total_carpetas": len(ofs_manifest),
        "total_completas": sum(1 for o in ofs_manifest if o["completo"]),
        "ordenes": ofs_manifest
    }
    
    # Guardar en GCS
    try:
        m_blob = bucket.blob("ordenes_fabricacion/manifest_ofs.json")
        m_blob.upload_from_string(
            json.dumps(manifest_payload, indent=2, ensure_ascii=False),
            content_type="application/json"
        )
        print("   ✅ Manifiesto actualizado en GCS (ordenes_fabricacion/manifest_ofs.json)")
    except Exception as em:
        print(f"   ⚠️ Error guardando manifiesto en GCS: {em}")

    # Guardar copia local en scratch/pronest_files
    try:
        local_m = APP_DIR / "pronest_files" / "manifest_ofs.json"
        local_m.parent.mkdir(parents=True, exist_ok=True)
        with open(local_m, "w", encoding="utf-8") as f:
            json.dump(manifest_payload, f, indent=2, ensure_ascii=False)
        print(f"   ✅ Copia local del manifiesto guardada en: {local_m}")
    except Exception:
        pass

    print("\n" + "=" * 75)
    print(" 🏁 RESUMEN DE SINCRONIZACIÓN Z:\\ ➔ GCS")
    print(f" • OFs analizadas: {len(ofs_manifest)}")
    print(f" • OFs con 3 PDFs completos: {sum(1 for o in ofs_manifest if o['completo'])}")
    print(f" • Archivos subidos: {subidos_count}")
    print(f" • Archivos ya al día (omitidos): {omitidos_count}")
    print(f" • Errores de transferencia: {errores_count}")
    print("=" * 75)
    return True

if __name__ == "__main__":
    t0 = time.time()
    sincronizar_z_hacia_gcs()
    print(f"⏱️ Tiempo total: {time.time() - t0:.1f} segundos.\n")
