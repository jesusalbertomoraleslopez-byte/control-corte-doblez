"""
=============================================================================
SISTEMA DE CONTROL DE CORTE Y DOBLEZ - INDUSTRIA SIGRAMA S.A. DE C.V.
Módulo de Sincronización con Google Cloud Storage (Cloud Run & Local Storage)
=============================================================================
"""

import os
import io
import json
import threading
import datetime
from pathlib import Path
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
EXCEL_DB_NAME = "sigrama_database.xlsx"
LOCAL_EXCEL_PATH = BASE_DIR / EXCEL_DB_NAME
TEMP_DB_PATH = BASE_DIR / "sigrama_temp.db"

# Bucket oficial de Google Cloud Storage
_raw_bucket = os.environ.get("GCS_BUCKET", "sigrama-corte-doblez-storage").strip()
# Si por error de despliegue viene acompañado de otros parámetros (ej. 'sigrama-corte-doblez-storage PYTHONUNBUFFERED=1')
GCS_BUCKET_NAME = _raw_bucket.split()[0] if _raw_bucket else "sigrama-corte-doblez-storage"

_storage_client = None
_bucket_obj = None
_gcs_initialized = False

def get_bucket():
    """Obtiene el objeto Bucket de GCS si las credenciales están disponibles."""
    global _storage_client, _bucket_obj, _gcs_initialized
    if _bucket_obj is not None:
        return _bucket_obj
    try:
        from google.cloud import storage
        _storage_client = storage.Client()
        _bucket_obj = _storage_client.bucket(GCS_BUCKET_NAME)
        _gcs_initialized = True
        return _bucket_obj
    except Exception as e:
        print(f"[GCS_SYNC] Aviso: No se pudo conectar a GCS ({GCS_BUCKET_NAME}): {e}")
        return None

def is_gcs_available() -> bool:
    """Verifica si el bucket está accesible."""
    b = get_bucket()
    if b is None:
        return False
    try:
        if b.exists():
            return True
    except Exception:
        pass
    try:
        # Fallback si no tiene permiso storage.buckets.get a nivel proyecto
        blobs_sample = list(b.list_blobs(max_results=1))
        return True
    except Exception:
        return False

# =============================================================================
# SINCRONIZACIÓN DE BASE DE DATOS (sigrama_database.xlsx)
# =============================================================================

def sync_db_from_gcs(force: bool = False) -> bool:
    """
    Descarga la base de datos de producción desde GCS (gs://sigrama-corte-doblez-storage/database/sigrama_database.xlsx).
    Si force=True o si la versión en GCS es más reciente que el archivo local, la descarga
    y sincroniza automáticamente a SQLite.
    """
    b = get_bucket()
    if not b:
        return False
    try:
        blob = b.blob(f"database/{EXCEL_DB_NAME}")
        if not blob.exists():
            print(f"[GCS_SYNC] No existe base de datos previa en gs://{GCS_BUCKET_NAME}/database/{EXCEL_DB_NAME}")
            return False

        blob.reload()
        gcs_size = blob.size or 0
        if gcs_size < 5000:
            print(f"[GCS_SYNC] Archivo en GCS demasiado pequeño ({gcs_size} bytes), ignorando.")
            return False

        descargar = force
        if not LOCAL_EXCEL_PATH.exists():
            descargar = True
        elif not force:
            local_size = LOCAL_EXCEL_PATH.stat().st_size
            if local_size < 5000:
                descargar = True
            elif blob.updated:
                # Si el archivo en GCS tiene fecha posterior al local
                try:
                    gcs_mtime = blob.updated.timestamp()
                    local_mtime = LOCAL_EXCEL_PATH.stat().st_mtime
                    if gcs_mtime > (local_mtime + 5):
                        descargar = True
                except Exception:
                    pass

        if descargar:
            print(f"[GCS_SYNC] Descargando {EXCEL_DB_NAME} desde GCS ({gcs_size} bytes)...")
            content = blob.download_as_bytes()
            # Validar integridad antes de escribir
            try:
                _test = pd.ExcelFile(io.BytesIO(content))
                if 'ordenes' in _test.sheet_names:
                    with open(LOCAL_EXCEL_PATH, "wb") as f:
                        f.write(content)
                    print(f"[GCS_SYNC] Base de datos descargada y verificada exitosamente.")
                    
                    # Refrescar base de datos SQLite activa
                    try:
                        from utils.database import sync_excel_to_sqlite
                        sync_excel_to_sqlite()
                        print(f"[GCS_SYNC] Base SQLite local refrescada con datos de GCS.")
                    except Exception as edb:
                        print(f"[GCS_SYNC] Aviso al sincronizar SQLite: {edb}")
                    return True
            except Exception as ev:
                print(f"[GCS_SYNC] Error de integridad al verificar Excel desde GCS: {ev}")
                return False
        return True
    except Exception as e:
        print(f"[GCS_SYNC] Error en sync_db_from_gcs: {e}")
        return False

def pull_data_from_gcp() -> tuple[bool, str]:
    """
    Fuerza la descarga de la base de datos oficial y manifiesto desde GCP.
    Retorna (éxito, mensaje).
    """
    ok = sync_db_from_gcs(force=True)
    if ok:
        return True, "Base de datos y órdenes actualizadas exitosamente desde GCP."
    return False, "No se pudo descargar la información de GCP. Verifique su conexión a Internet o credenciales."

def push_db_to_gcs() -> bool:
    """Sube el archivo sigrama_database.xlsx actual a GCS."""
    b = get_bucket()
    if not b or not LOCAL_EXCEL_PATH.exists():
        return False
    try:
        # Validar integridad antes de subir
        _test = pd.ExcelFile(str(LOCAL_EXCEL_PATH))
        if 'ordenes' not in _test.sheet_names:
            print("[GCS_SYNC] El archivo local no tiene la hoja 'ordenes'. No se sube.")
            return False

        blob = b.blob(f"database/{EXCEL_DB_NAME}")
        blob.upload_from_filename(str(LOCAL_EXCEL_PATH))
        print(f"[GCS_SYNC] Base de datos respaldada con éxito en gs://{GCS_BUCKET_NAME}/database/{EXCEL_DB_NAME}")
        return True
    except Exception as e:
        print(f"[GCS_SYNC] Error al subir base de datos a GCS: {e}")
        return False

def push_db_to_gcs_async():
    """Ejecuta push_db_to_gcs en segundo plano sin bloquear la interfaz."""
    t = threading.Thread(target=push_db_to_gcs, daemon=True)
    t.start()

# =============================================================================
# MANIFIESTO Y CONSULTA DE ÓRDENES DE FABRICACIÓN EN GCS
# =============================================================================

MANIFEST_BLOB_NAME = "ordenes_fabricacion/manifest_ofs.json"

def get_gcs_manifest() -> list:
    """Descarga el catálogo/manifiesto de OFs almacenadas en GCS."""
    b = get_bucket()
    if not b:
        return []
    try:
        blob = b.blob(MANIFEST_BLOB_NAME)
        if blob.exists():
            data = json.loads(blob.download_as_text(encoding="utf-8"))
            return data.get("ordenes", [])
    except Exception as e:
        print(f"[GCS_SYNC] Error al leer manifiesto GCS: {e}")
    return []

def save_gcs_manifest(ordenes_list: list) -> bool:
    """Guarda el catálogo/manifiesto de OFs en GCS."""
    b = get_bucket()
    if not b:
        return False
    try:
        blob = b.blob(MANIFEST_BLOB_NAME)
        payload = {
            "version": "1.0",
            "last_updated": datetime.datetime.now().isoformat(),
            "total_ofs": len(ordenes_list),
            "ordenes": ordenes_list
        }
        blob.upload_from_string(json.dumps(payload, indent=2, ensure_ascii=False), content_type="application/json")
        return True
    except Exception as e:
        print(f"[GCS_SYNC] Error al guardar manifiesto GCS: {e}")
        return False

def list_ofs_in_gcs() -> list:
    """
    Obtiene la lista completa de OFs disponibles en el bucket GCS.
    Primero consulta el manifiesto; si está vacío, escanea los blobs.
    """
    manifest = get_gcs_manifest()
    if manifest:
        return manifest

    # Fallback: escanear prefijos en el bucket
    b = get_bucket()
    if not b:
        return []
    try:
        blobs = list(b.list_blobs(prefix="ordenes_fabricacion/"))
        ofs_dict = {}
        for blob in blobs:
            parts = blob.name.split("/")
            if len(parts) >= 3 and parts[0] == "ordenes_fabricacion":
                of_folder = parts[1]
                filename = parts[-1]
                if of_folder not in ofs_dict:
                    ofs_dict[of_folder] = {
                        "of_nombre": of_folder,
                        "archivos": [],
                        "resumen_pdf": None,
                        "nido_pdf": None,
                        "pieza_pdf": None,
                        "excel_existente": None
                    }
                ofs_dict[of_folder]["archivos"].append(filename)
                fn_lower = filename.lower()
                if fn_lower.endswith(".pdf"):
                    if "resumen" in fn_lower:
                        ofs_dict[of_folder]["resumen_pdf"] = filename
                    elif "cabezal" in fn_lower or "nido" in fn_lower:
                        ofs_dict[of_folder]["nido_pdf"] = filename
                    elif "pieza" in fn_lower:
                        ofs_dict[of_folder]["pieza_pdf"] = filename
                elif fn_lower.endswith(".xlsx") and not fn_lower.startswith("~$"):
                    ofs_dict[of_folder]["excel_existente"] = filename

        result = []
        for of_f, data in sorted(ofs_dict.items()):
            completo = bool(data["resumen_pdf"] and data["nido_pdf"] and data["pieza_pdf"])
            result.append({
                "of_nombre": of_f,
                "etiqueta": of_f,
                "subcarpeta": "",
                "resumen_pdf": data["resumen_pdf"],
                "nido_pdf": data["nido_pdf"],
                "pieza_pdf": data["pieza_pdf"],
                "excel_existente": data["excel_existente"],
                "completo": completo,
                "tiene_excel": bool(data["excel_existente"])
            })
        return result
    except Exception as e:
        print(f"[GCS_SYNC] Error escaneando GCS: {e}")
        return []

def download_of_pdfs_from_gcs(of_folder_name: str, target_dir: str) -> dict:
    """
    Descarga los 3 reportes PDF de una OF desde GCS a una carpeta local/temporal.
    Retorna un diccionario con las rutas locales de {resumen, nido, pieza}.
    """
    b = get_bucket()
    if not b:
        raise RuntimeError("No hay conexión con el bucket de GCS.")

    dest_path = Path(target_dir)
    dest_path.mkdir(parents=True, exist_ok=True)

    prefix = f"ordenes_fabricacion/{of_folder_name}/"
    blobs = list(b.list_blobs(prefix=prefix))
    
    downloaded = {
        "resumen": None,
        "nido": None,
        "pieza": None,
        "excel": None
    }

    for blob in blobs:
        filename = blob.name.split("/")[-1]
        fn_lower = filename.lower()
        if not fn_lower.endswith(".pdf") and not fn_lower.endswith(".xlsx"):
            continue

        local_file = dest_path / filename
        blob.download_to_filename(str(local_file))

        if fn_lower.endswith(".pdf"):
            if "resumen" in fn_lower:
                downloaded["resumen"] = str(local_file)
            elif "cabezal" in fn_lower or "nido" in fn_lower:
                downloaded["nido"] = str(local_file)
            elif "pieza" in fn_lower:
                downloaded["pieza"] = str(local_file)
        elif fn_lower.endswith(".xlsx"):
            downloaded["excel"] = str(local_file)

    return downloaded

def upload_of_excel_to_gcs(of_folder_name: str, local_excel_path: str) -> bool:
    """Sube el archivo Excel generado a la carpeta de la OF en GCS."""
    b = get_bucket()
    if not b or not os.path.exists(local_excel_path):
        return False
    try:
        filename = os.path.basename(local_excel_path)
        blob_name = f"ordenes_fabricacion/{of_folder_name}/{filename}"
        blob = b.blob(blob_name)
        blob.upload_from_filename(local_excel_path)
        print(f"[GCS_SYNC] Excel subido a GCS: {blob_name}")
        return True
    except Exception as e:
        print(f"[GCS_SYNC] Error al subir Excel a GCS: {e}")
        return False
