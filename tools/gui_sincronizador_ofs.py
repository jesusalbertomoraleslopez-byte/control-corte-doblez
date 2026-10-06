# -*- coding: utf-8 -*-
"""
=============================================================================
INDUSTRIA SIGRAMA S.A. DE C.V.
Aplicación de Escritorio: Sincronizador de Órdenes de Fabricación ProNest a GCS
Control de Corte y Doblez — Industria 4.0
=============================================================================
"""

import os
import sys
import time
import json
import threading
import webbrowser
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
from pathlib import Path

# Configurar encoding UTF-8 en Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))

Z_PATH = r"Z:\14 - ORDENES DE FABRICACION"
BUCKET_NAME = "sigrama-corte-doblez-storage"
LOCAL_URL = "http://localhost:8501"

class SigramaOFSynchronizerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("SIGRAMA METALES — Sincronizador de Órdenes de Fabricación a GCS")
        self.root.geometry("820x680")
        self.root.minsize(740, 600)
        self.root.configure(bg="#0F172A")

        self.is_running = False

        self._build_ui()
        self._refresh_status()

    def _build_ui(self):
        # ── 1. CABECERA CORPORATIVA ──
        header_frame = tk.Frame(self.root, bg="#1E293B", height=85)
        header_frame.pack(fill="x", side="top")

        red_bar = tk.Frame(header_frame, bg="#EC2024", width=7)
        red_bar.pack(side="left", fill="y")

        title_container = tk.Frame(header_frame, bg="#1E293B", padx=18, pady=12)
        title_container.pack(side="left", fill="both", expand=True)

        lbl_company = tk.Label(
            title_container,
            text="INDUSTRIA SIGRAMA S.A. DE C.V.",
            font=("Montserrat", 13, "bold"),
            fg="#EC2024",
            bg="#1E293B"
        )
        lbl_company.pack(anchor="w")

        lbl_subtitle = tk.Label(
            title_container,
            text="Sincronizador de Órdenes de Fabricación ProNest (Z:\\ ➔ Google Cloud Storage)",
            font=("Segoe UI", 9),
            fg="#94A3B8",
            bg="#1E293B"
        )
        lbl_subtitle.pack(anchor="w")

        # ── 2. TARJETA DE ESTADO Y RUTAS ──
        info_card = tk.LabelFrame(
            self.root,
            text="  Estado de Red, Almacenamiento en la Nube y Base de Datos  ",
            font=("Segoe UI", 9, "bold"),
            fg="#F8FAFC",
            bg="#1E293B",
            padx=14,
            pady=10,
            relief="groove"
        )
        info_card.pack(fill="x", padx=18, pady=10)

        # Fila 1: Origen
        row1 = tk.Frame(info_card, bg="#1E293B")
        row1.pack(fill="x", pady=2)
        tk.Label(row1, text="📁 Origen en Red:", font=("Segoe UI", 9, "bold"), fg="#94A3B8", bg="#1E293B", width=18, anchor="w").pack(side="left")
        self.lbl_network_path = tk.Label(row1, text=Z_PATH, font=("Consolas", 9), fg="#38BDF8", bg="#1E293B")
        self.lbl_network_path.pack(side="left")

        # Fila 2: Bucket
        row2 = tk.Frame(info_card, bg="#1E293B")
        row2.pack(fill="x", pady=2)
        tk.Label(row2, text="☁️ Bucket Destino:", font=("Segoe UI", 9, "bold"), fg="#94A3B8", bg="#1E293B", width=18, anchor="w").pack(side="left")
        tk.Label(row2, text=f"gs://{BUCKET_NAME}/ordenes_fabricacion/ | Incremental (Omite duplicados)", font=("Consolas", 9), fg="#34D399", bg="#1E293B").pack(side="left")

        # Fila 3: Conteo en vivo
        row3 = tk.Frame(info_card, bg="#1E293B")
        row3.pack(fill="x", pady=4)
        tk.Label(row3, text="📊 Detección:", font=("Segoe UI", 9, "bold"), fg="#94A3B8", bg="#1E293B", width=18, anchor="w").pack(side="left")
        self.lbl_counter = tk.Label(row3, text="Inspeccionando carpetas en red local y catálogo...", font=("Segoe UI", 9, "bold"), fg="#FCD34D", bg="#1E293B")
        self.lbl_counter.pack(side="left")

        btn_refresh = tk.Button(
            row3,
            text="🔄 Refrescar",
            font=("Segoe UI", 8, "bold"),
            bg="#334155",
            fg="#FFFFFF",
            relief="flat",
            command=self._refresh_status,
            padx=8,
            pady=2,
            cursor="hand2"
        )
        btn_refresh.pack(side="right")

        # Fila 4: Garantía de transferencia incremental
        row4 = tk.Frame(info_card, bg="#1E293B")
        row4.pack(fill="x", pady=2)
        tk.Label(
            row4,
            text="🛡️ Eficiencia Total: Solo sube PDFs, NIFs y Excels nuevos o modificados. Si ya existen, se omiten al instante.",
            font=("Segoe UI", 8, "italic"),
            fg="#FDE047",
            bg="#1E293B"
        ).pack(anchor="w")

        # ── 3. BOTONES DE ACCIÓN PRINCIPALES ──
        actions_frame = tk.Frame(self.root, bg="#0F172A", padx=18, pady=4)
        actions_frame.pack(fill="x")

        self.btn_sync = tk.Button(
            actions_frame,
            text="⚡ SUBIR ÓRDENES DE FABRICACIÓN A GOOGLE CLOUD",
            font=("Montserrat", 10, "bold"),
            bg="#EC2024",
            fg="#FFFFFF",
            activebackground="#C62828",
            activeforeground="#FFFFFF",
            relief="flat",
            padx=20,
            pady=11,
            cursor="hand2",
            command=self._start_sync_thread
        )
        self.btn_sync.pack(side="left", fill="x", expand=True, padx=(0, 8))

        btn_open_web = tk.Button(
            actions_frame,
            text="🌐 Abrir App Web ↗",
            font=("Segoe UI", 10, "bold"),
            bg="#2563EB",
            fg="#FFFFFF",
            activebackground="#1D4ED8",
            activeforeground="#FFFFFF",
            relief="flat",
            padx=16,
            pady=11,
            cursor="hand2",
            command=lambda: webbrowser.open(LOCAL_URL)
        )
        btn_open_web.pack(side="right")

        # ── 4. BARRA DE PROGRESO ──
        prog_frame = tk.Frame(self.root, bg="#0F172A", padx=18, pady=4)
        prog_frame.pack(fill="x")

        self.lbl_progress_status = tk.Label(
            prog_frame,
            text="Listo para sincronizar.",
            font=("Segoe UI", 9),
            fg="#94A3B8",
            bg="#0F172A"
        )
        self.lbl_progress_status.pack(anchor="w", pady=(0, 3))

        self.progress_bar = ttk.Progressbar(prog_frame, orient="horizontal", mode="determinate")
        self.progress_bar.pack(fill="x")

        # ── 5. TERMINAL DE EVENTOS / LOG ──
        log_frame = tk.LabelFrame(
            self.root,
            text="  Registro de Transferencia e Inspección de Archivos  ",
            font=("Segoe UI", 9, "bold"),
            fg="#94A3B8",
            bg="#0B132B",
            padx=8,
            pady=8,
            relief="groove"
        )
        log_frame.pack(fill="both", expand=True, padx=18, pady=(4, 14))

        self.txt_log = scrolledtext.ScrolledText(
            log_frame,
            bg="#050C1A",
            fg="#38BDF8",
            insertbackground="#FFFFFF",
            font=("Consolas", 9),
            relief="flat",
            wrap="word"
        )
        self.txt_log.pack(fill="both", expand=True)

    def _log(self, msg):
        timestamp = time.strftime("[%H:%M:%S] ")
        self.txt_log.insert(tk.END, timestamp + msg + "\n")
        self.txt_log.see(tk.END)
        self.root.update_idletasks()

    def _update_progress(self, val, status_text=None):
        self.progress_bar["value"] = val
        if status_text:
            self.lbl_progress_status.config(text=status_text)
        else:
            self.lbl_progress_status.config(text=f"Sincronizando: {val:.1f}% completado...")
        self.root.update_idletasks()

    def _refresh_status(self):
        def _task():
            if not os.path.exists(Z_PATH):
                self.lbl_counter.config(text="❌ Unidad de red Z:\\ no accesible. Conecte su red o VPN.", fg="#EF4444")
                self._log("⚠️ Advertencia: No se puede acceder a Z:\\14 - ORDENES DE FABRICACION.")
                return

            try:
                carpetas = [d for d in os.listdir(Z_PATH) if os.path.isdir(os.path.join(Z_PATH, d))]
                
                # Consultar BD activa de producción
                from utils.database import get_all_ofs
                ofs_en_db = get_all_ofs()
                total_db = len(ofs_en_db)

                status_txt = f"{len(carpetas)} carpetas en Z:\\ | {total_db} OFs en Producción Activa"
                self.lbl_counter.config(text=status_txt, fg="#34D399")
                self._log(f"Inventario: {len(carpetas)} carpetas en red Z:\\, {total_db} órdenes en BD de producción.")
            except Exception as e:
                self.lbl_counter.config(text=f"Error al inspeccionar catálogo: {e}", fg="#FCD34D")

        threading.Thread(target=_task, daemon=True).start()

    def _start_sync_thread(self):
        if self.is_running:
            messagebox.showwarning("Proceso en curso", "Ya hay una sincronización en ejecución.")
            return

        self.is_running = True
        self.btn_sync.config(state="disabled", bg="#64748B", text="⏳ SINCRONIZANDO CON GOOGLE CLOUD...")
        self.progress_bar["value"] = 0

        t = threading.Thread(target=self._run_sync, daemon=True)
        t.start()

    def _run_sync(self):
        t0 = time.time()
        self._log("🚀 Iniciando proceso de sincronización con Google Cloud...")

        if not os.path.exists(Z_PATH):
            self._log("❌ ERROR: La unidad Z:\\ no está disponible.")
            self._finish_sync(False, "Unidad Z:\\ no disponible.")
            return

        try:
            from google.cloud import storage
            client = storage.Client()
            bucket = client.bucket(BUCKET_NAME)
            if not bucket.exists():
                self._log(f"❌ ERROR: El bucket gs://{BUCKET_NAME} no existe o no tiene permisos.")
                self._finish_sync(False, "Bucket no accesible.")
                return
        except Exception as e:
            self._log(f"❌ Error conectando a Google Cloud: {e}")
            if "billing" in str(e).lower() or "disabled" in str(e).lower():
                self._log("💡 NOTA: La cuenta de facturación de GCP requiere ser reactivada en Google Cloud Console.")
            self._finish_sync(False, f"Error de conexión con GCP: {e}")
            return

        self._log("✅ Conexión con Google Cloud Storage verificada exitosamente.")

        # 1. Respaldo de Base de Datos local
        excel_db = APP_DIR / "sigrama_database.xlsx"
        if excel_db.exists() and excel_db.stat().st_size > 5000:
            self._log(f"📦 Respaldando base de datos ({excel_db.name}) a GCS...")
            try:
                blob = bucket.blob(f"database/{excel_db.name}")
                blob.upload_from_filename(str(excel_db))
                self._log(f"   ✅ Base de datos respaldada en gs://{BUCKET_NAME}/database/{excel_db.name}")
            except Exception as edb:
                self._log(f"   ⚠️ Aviso: Falló el respaldo de BD: {edb}")

        # 2. Obtener lista de blobs existentes en GCS
        self._log("🔍 Inspeccionando catálogo existente en GCS...")
        blobs_existentes = {}
        try:
            for b in bucket.list_blobs(prefix="ordenes_fabricacion/"):
                blobs_existentes[b.name] = b.size
            self._log(f"   Encontrados {len(blobs_existentes)} archivos previos en la nube.")
        except Exception as e:
            self._log(f"   ⚠️ Error listando blobs: {e}")

        # 3. Escaneo y sincronización de carpetas
        carpetas = sorted([d for d in os.listdir(Z_PATH) if os.path.isdir(os.path.join(Z_PATH, d))])
        total_carpetas = len(carpetas)
        self._log(f"📂 Iniciando escaneo de {total_carpetas} carpetas...")

        subidos = 0
        omitidos = 0
        errores = 0
        manifest_ofs = []

        for idx, carpeta in enumerate(carpetas, 1):
            c_path = os.path.join(Z_PATH, carpeta)
            
            # Detectar archivos
            archivos_a_subir = []
            diag = {"resumen": None, "nido": None, "pieza": None, "nif": None, "excel": None}

            try:
                for f in os.listdir(c_path):
                    fp = os.path.join(c_path, f)
                    if not os.path.isfile(fp):
                        continue
                    fl = f.lower()
                    if fl.endswith(".pdf"):
                        if "resumen" in fl:
                            diag["resumen"] = f
                            archivos_a_subir.append(fp)
                        elif "cabezal" in fl or "nido" in fl:
                            diag["nido"] = f
                            archivos_a_subir.append(fp)
                        elif "pieza" in fl:
                            diag["pieza"] = f
                            archivos_a_subir.append(fp)
                        else:
                            archivos_a_subir.append(fp)
                    elif fl.endswith(".nif"):
                        diag["nif"] = f
                        archivos_a_subir.append(fp)
                    elif fl.endswith(".xlsx") and not fl.startswith("~$"):
                        diag["excel"] = f
                        archivos_a_subir.append(fp)
            except Exception:
                pass

            completo = bool(diag["resumen"] and diag["nido"] and diag["pieza"])
            manifest_ofs.append({
                "of_nombre": carpeta,
                "resumen_pdf": diag["resumen"],
                "nido_pdf": diag["nido"],
                "pieza_pdf": diag["pieza"],
                "excel_existente": diag["excel"],
                "completo": completo
            })

            # Subir archivos
            for fpath in archivos_a_subir:
                fname = os.path.basename(fpath)
                blob_name = f"ordenes_fabricacion/{carpeta}/{fname}"
                local_sz = os.path.getsize(fpath)

                if blob_name in blobs_existentes and blobs_existentes[blob_name] == local_sz:
                    omitidos += 1
                    continue

                try:
                    bl = bucket.blob(blob_name)
                    bl.upload_from_filename(fpath)
                    blobs_existentes[blob_name] = local_sz
                    subidos += 1
                    self._log(f"   ⬆️ Subido: {carpeta} / {fname} ({local_sz:,} B)")
                except Exception as eup:
                    errores += 1
                    self._log(f"   ❌ Error subiendo {fname}: {eup}")

            # Actualizar barra de progreso
            pct = (idx / total_carpetas) * 100
            self._update_progress(pct, f"Procesando {idx}/{total_carpetas}: {carpeta[:35]}...")

        # 4. Guardar Manifiesto
        self._log("📝 Actualizando manifest_ofs.json en la nube...")
        try:
            m_payload = {
                "version": "1.0",
                "fecha": time.strftime("%Y-%m-%d %H:%M:%S"),
                "total_carpetas": len(manifest_ofs),
                "completas": sum(1 for o in manifest_ofs if o["completo"]),
                "ordenes": manifest_ofs
            }
            mblob = bucket.blob("ordenes_fabricacion/manifest_ofs.json")
            mblob.upload_from_string(json.dumps(m_payload, indent=2, ensure_ascii=False), content_type="application/json")
            self._log("   ✅ Manifiesto maestro actualizado en Google Cloud.")
        except Exception as em:
            self._log(f"   ⚠️ No se pudo guardar manifiesto en GCS: {em}")

        # Guardar copia local de respaldo
        try:
            local_m = APP_DIR / "pronest_files" / "manifest_ofs.json"
            local_m.parent.mkdir(parents=True, exist_ok=True)
            with open(local_m, "w", encoding="utf-8") as f:
                json.dump(m_payload, f, indent=2, ensure_ascii=False)
            self._log(f"   ✅ Manifiesto local respaldado en: {local_m.name}")
        except Exception:
            pass

        duracion = time.time() - t0
        resumen = f"Finalizado en {duracion:.1f}s | Subidos: {subidos} | Ya existentes: {omitidos} | Errores: {errores}"
        self._log(f"🏁 {resumen}")
        self._finish_sync(True, resumen)

    def _finish_sync(self, exito, mensaje):
        self.is_running = False
        self.btn_sync.config(state="normal", bg="#EC2024", text="⚡ SUBIR ÓRDENES DE FABRICACIÓN A GOOGLE CLOUD")
        self.progress_bar["value"] = 100 if exito else 0
        self.lbl_progress_status.config(text="Sincronización finalizada." if exito else "Sincronización interrumpida.")

        if exito:
            messagebox.showinfo("Sincronización Exitosa", f"¡Órdenes sincronizadas con éxito hacia Google Cloud!\n\n{mensaje}")
        else:
            messagebox.showwarning("Aviso de Sincronización", f"El proceso finalizó con observaciones:\n\n{mensaje}")

def main():
    root = tk.Tk()
    app = SigramaOFSynchronizerApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
