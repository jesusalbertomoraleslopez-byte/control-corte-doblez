"""
=============================================================================
SISTEMA DE CONTROL DE CORTE Y DOBLEZ - INDUSTRIA SIGRAMA S.A. DE C.V.
Vista: Supervisión y Repositorio Central de Órdenes de Fabricación (Bucket GCS)
Permite al programador auditar e integrar OFs desde el Repositorio (GCS / Red Z:\\)
generando automáticamente el archivo Excel de producción y cargándolo a la BD.
=============================================================================
"""

import os
import tempfile
from pathlib import Path
import pandas as pd
import streamlit as st

from utils.generador_of_excel import generar_excel_of_pronest
from utils.scanner_of import (
    escanear_directorio_ofs,
    analizar_carpeta_of,
    obtener_opciones_po,
    buscar_po_sugerida
)
from utils.database import (
    save_production_plan,
    get_connection,
    registrar_auditoria
)
from utils.gcs_sync import (
    is_gcs_available,
    list_ofs_in_gcs,
    download_of_pdfs_from_gcs,
    upload_of_excel_to_gcs,
    push_db_to_gcs_async
)

@st.cache_data(ttl=90, show_spinner="Consultando catálogo de OFs en Google Cloud Storage...")
def _cargar_catalogo_repositorio():
    """Consulta y cachea el listado de OFs desde GCS o almacenamiento local."""
    gcs_ok = is_gcs_available()
    ofs = []
    fuente = "Desconocido"

    if gcs_ok:
        try:
            ofs = list_ofs_in_gcs()
            if ofs:
                fuente = "Google Cloud Storage (gs://sigrama-corte-doblez-storage)"
        except Exception as e:
            print(f"[SUPERVISION] Error consultando list_ofs_in_gcs: {e}")

    # Fallback a manifiesto local o Z:\ si GCS no respondió
    if not ofs:
        local_manifest = Path(__file__).resolve().parent.parent / "pronest_files" / "manifest_ofs.json"
        if local_manifest.exists():
            try:
                import json
                with open(local_manifest, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    ofs = data.get("ordenes", [])
                    if ofs:
                        fuente = "Caché Local de Manifiesto"
            except Exception:
                pass

    if not ofs and os.path.exists(r"Z:\14 - ORDENES DE FABRICACION"):
        ofs = escanear_directorio_ofs(r"Z:\14 - ORDENES DE FABRICACION")
        if ofs:
            fuente = "Unidad de Red Z:\\14 - ORDENES DE FABRICACION"

    return ofs, fuente, gcs_ok

def view_supervision_gcs():
    # Banner de Encabezado
    st.markdown('''
    <div style="background: linear-gradient(135deg, #1e1e1e 0%, #111111 100%); 
                padding: 18px 24px; border-radius: 10px; border-left: 5px solid #EC2024; margin-bottom: 20px;">
        <div style="font-family: 'Montserrat', sans-serif; color: #FFFFFF !important; margin: 0; font-size: 24px; font-weight: 700;">
            🛰️ Supervisión y Repositorio de Órdenes de Fabricación
        </div>
        <p style="font-family: 'Questrial', sans-serif; color: #bbb; margin: 5px 0 0 0; font-size: 14px;">
            Auditoría en tiempo real del Bucket central de GCS. Monitoree las OFs con reportes ProNest listos para procesar y cárguelas a producción con un solo clic.
        </p>
    </div>
    ''', unsafe_allow_html=True)

    # 1. Consultar base de datos local
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT of_number FROM ordenes")
    ofs_en_db = {str(row[0]).strip() for row in c.fetchall()}
    conn.close()

    # 2. Cargar catálogo de OFs del repositorio
    ofs_repositorio, origen_datos, gcs_ok = _cargar_catalogo_repositorio()

    # Métricas Superiores
    completas_count = sum(1 for o in ofs_repositorio if o.get("completo"))
    pendientes_count = sum(1 for o in ofs_repositorio if o.get("of_nombre") not in ofs_en_db and o.get("completo"))

    m_col1, m_col2, m_col3, m_col4 = st.columns(4)
    with m_col1:
        st.metric("Total en Repositorio", len(ofs_repositorio))
    with m_col2:
        st.metric("Con 3 Reportes PDF", completas_count)
    with m_col3:
        st.metric("Ya en Producción", len(ofs_en_db))
    with m_col4:
        st.metric("Pendientes por Cargar", pendientes_count)

    # Indicador de estado de conexión
    if gcs_ok:
        st.caption(f"📡 Fuente de datos activa: **{origen_datos}** &bull; 🟢 **Conectado a Google Cloud Storage**")
    else:
        st.caption(f"📡 Fuente de datos activa: **{origen_datos}** &bull; ⚠️ Conexión local / sin credenciales GCS directas")

    if not ofs_repositorio:
        st.warning("⚠️ No se encontraron carpetas de OFs en el repositorio. Ejecute `SUBIR_ORDENES_A_GCS.bat` en su PC o verifique la conexión a `Z:\\`.")
        return

    st.markdown("---")

    # =========================================================================
    # 3. FILTROS Y BÚSQUEDA RÁPIDA
    # =========================================================================
    col_f1, col_f2, col_f3 = st.columns([2, 1.8, 0.8])
    with col_f1:
        busq = st.text_input("🔍 Buscar OF por nombre o número:", value="", placeholder="Ej. 00086, 00095, PROD...")
    with col_f2:
        filtro_estado = st.selectbox(
            "Filtrar por Estado:",
            [
                f"Todas las OFs ({len(ofs_repositorio)})",
                f"🟢 Solo Listas para Integrar - Pendientes ({pendientes_count})",
                f"🔵 Ya en Producción ({len(ofs_en_db)})",
                f"🟡 Incompletas - Faltan Reportes ({len(ofs_repositorio) - completas_count})"
            ]
        )
    with col_f3:
        st.write("")
        st.write("")
        if st.button("🔄 Refrescar", use_container_width=True, help="Limpia la caché y vuelve a consultar el Bucket GCS"):
            st.cache_data.clear()
            st.rerun()

    # Filtrar catálogo
    ofs_filtradas = []
    for item in ofs_repositorio:
        of_n = item.get("of_nombre", "")
        esta_en_db = of_n in ofs_en_db
        es_completa = bool(item.get("completo"))

        if busq and busq.lower() not in of_n.lower():
            continue

        if "Solo Listas para Integrar" in filtro_estado and (esta_en_db or not es_completa):
            continue
        elif "Ya en Producción" in filtro_estado and not esta_en_db:
            continue
        elif "Incompletas" in filtro_estado and es_completa:
            continue

        ofs_filtradas.append(item)

    # =========================================================================
    # 4. TABLA PRINCIPAL DE ÓRDENES ENCONTRADAS EN EL BUCKET (VISTA DESTACADA)
    # =========================================================================
    st.markdown("### 📋 Tabla de Órdenes de Fabricación en el Repositorio")
    st.markdown(f"*Mostrando **{len(ofs_filtradas)}** órdenes de trabajo encontradas según los filtros.*")

    rows_tabla = []
    for o in ofs_filtradas:
        of_n = o.get("of_nombre", "")
        esta_en_db = of_n in ofs_en_db
        es_comp = bool(o.get("completo"))

        if esta_en_db:
            estado_tag = "🔵 En Producción"
        elif es_comp:
            estado_tag = "🟢 Lista para Carga"
        else:
            estado_tag = "🟡 Incompleta"

        # Conteo de reportes PDF
        num_pdfs = sum([
            1 if o.get("resumen_pdf") else 0,
            1 if o.get("nido_pdf") else 0,
            1 if o.get("pieza_pdf") else 0
        ])

        diag_pdfs = f"{num_pdfs}/3 PDFs"

        rows_tabla.append({
            "Estado": estado_tag,
            "Orden de Fabricación": of_n,
            "Reportes": diag_pdfs,
            "Resumen PDF": "✅ Listo" if o.get("resumen_pdf") else "❌ Falta",
            "Nido PDF": "✅ Listo" if o.get("nido_pdf") else "❌ Falta",
            "Pieza PDF": "✅ Listo" if o.get("pieza_pdf") else "❌ Falta",
            "Excel ProNest": "✅ Generado" if (o.get("excel_existente") or o.get("tiene_excel")) else "⏳ Pendiente"
        })

    if rows_tabla:
        df_grid = pd.DataFrame(rows_tabla)
        st.dataframe(
            df_grid,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Estado": st.column_config.TextColumn("Estado", width="medium"),
                "Orden de Fabricación": st.column_config.TextColumn("Orden de Fabricación", width="large"),
                "Reportes": st.column_config.TextColumn("Reportes", width="small"),
                "Resumen PDF": st.column_config.TextColumn("Resumen PDF", width="small"),
                "Nido PDF": st.column_config.TextColumn("Nido PDF", width="small"),
                "Pieza PDF": st.column_config.TextColumn("Pieza PDF", width="small"),
                "Excel ProNest": st.column_config.TextColumn("Excel ProNest", width="small"),
            }
        )
    else:
        st.info("ℹ️ No hay órdenes de fabricación que coincidan con la búsqueda o filtro actual.")

    st.markdown("---")

    # =========================================================================
    # 5. PANEL DE INTEGRACIÓN AUTOMÁTICA A PRODUCCIÓN
    # =========================================================================
    st.markdown("### ⚡ Cargar / Integrar OF Seleccionada a Producción")
    st.markdown("Seleccione una orden de la lista anterior para procesarla con el motor ProNest y darla de alta en el sistema de producción.")

    # Lista ordenada: primero las pendientes completas, luego las demás
    ofs_para_integrar = sorted(
        ofs_filtradas if ofs_filtradas else ofs_repositorio,
        key=lambda x: (
            0 if (x.get("of_nombre") not in ofs_en_db and x.get("completo")) else (
                1 if x.get("completo") else 2
            )
        )
    )

    nombres_opciones = ["-- Seleccione una OF para Cargar --"] + [
        f"{'🔵 [En Prod] ' if o['of_nombre'] in ofs_en_db else ('🟢 [Listo] ' if o.get('completo') else '🟡 [Incompleto] ')}{o['of_nombre']}"
        for o in ofs_para_integrar
    ]

    col_sel1, col_sel2 = st.columns([2, 1.2])
    with col_sel1:
        selected_label = st.selectbox("Orden de Fabricación a Procesar:", nombres_opciones)
    with col_sel2:
        st.write("")
        st.write("")
        st.caption("💡 Se sugiere asociar el número de PO oficial correspondiente.")

    if selected_label and selected_label != "-- Seleccione una OF para Cargar --":
        of_sel_name = selected_label.split("] ", 1)[-1].strip()
        of_data = next((o for o in ofs_repositorio if o["of_nombre"] == of_sel_name), None)

        if of_data:
            c_info1, c_info2 = st.columns([1.5, 1])
            with c_info1:
                st.markdown(f"#### 📄 Diagnóstico de Archivos: `{of_sel_name}`")
                r_pdf = of_data.get("resumen_pdf")
                n_pdf = of_data.get("nido_pdf")
                p_pdf = of_data.get("pieza_pdf")
                excel_ex = of_data.get("excel_existente") or of_data.get("tiene_excel")
                st.markdown(f"- **1. Resumen de Trabajo:** {'✅ ' + str(r_pdf) if r_pdf else '❌ No encontrado'}")
                st.markdown(f"- **2. Detalle Nido / Cabezal:** {'✅ ' + str(n_pdf) if n_pdf else '❌ No encontrado'}")
                st.markdown(f"- **3. Detalle de Pieza:** {'✅ ' + str(p_pdf) if p_pdf else '❌ No encontrado'}")
                st.markdown(f"- **4. Archivo Excel ProNest:** {'✅ Generado previamente' if excel_ex else '⏳ Se generará automáticamente'}")

            with c_info2:
                # Búsqueda de PO sugerida desde catálogo
                labels_po, lookup_po, _ = obtener_opciones_po()
                po_sug, idx_sug = buscar_po_sugerida(of_sel_name, labels_po, lookup_po)

                st.markdown("#### 🔗 Vinculación con Orden de Compra (PO)")
                po_seleccionada = st.selectbox(
                    "PO Asociada:",
                    labels_po,
                    index=idx_sug if idx_sug < len(labels_po) else 0,
                    help="Se detecta automáticamente por coincidencia de texto con la App de POs."
                )
                po_final = lookup_po.get(po_seleccionada, {}).get("po", po_sug)

            # Botón de Integración
            ya_cargada = of_sel_name in ofs_en_db
            btn_txt = f"🔄 Re-Integrar OF {of_sel_name} a Producción (Sobrescribir)" if ya_cargada else f"⚡ Integrar OF {of_sel_name} al Sistema de Producción"

            if not of_data.get("completo"):
                st.warning(f"⚠️ No se puede integrar automáticamente la orden `{of_sel_name}` porque no contiene los 3 reportes PDF requeridos de ProNest.")
            else:
                if st.button(btn_txt, type="primary", use_container_width=True):
                    with st.spinner(f"Procesando reportes de ProNest para {of_sel_name}..."):
                        temp_dir = tempfile.mkdtemp()
                        local_res = None
                        local_nid = None
                        local_pie = None

                        # 1. Obtener los 3 PDFs (desde GCS o desde ruta local Z:\)
                        if gcs_ok:
                            try:
                                d_files = download_of_pdfs_from_gcs(of_sel_name, temp_dir)
                                local_res = d_files.get("resumen")
                                local_nid = d_files.get("nido")
                                local_pie = d_files.get("pieza")
                            except Exception as eg:
                                print(f"Error descargando desde GCS: {eg}")

                        if not (local_res and local_nid and local_pie):
                            # Intentar desde ruta local si existe
                            ruta_loc = of_data.get("ruta")
                            if ruta_loc and os.path.exists(ruta_loc):
                                diag_loc = analizar_carpeta_of(ruta_loc)
                                if diag_loc["resumen"]:
                                    local_res = os.path.join(ruta_loc, diag_loc["resumen"])
                                if diag_loc["nido"]:
                                    local_nid = os.path.join(ruta_loc, diag_loc["nido"])
                                if diag_loc["pieza"]:
                                    local_pie = os.path.join(ruta_loc, diag_loc["pieza"])

                        if not (local_res and local_nid and local_pie):
                            st.error("❌ No se pudieron recuperar los 3 reportes PDF para procesar la orden.")
                        else:
                            # 2. Generar el Excel de Producción
                            out_excel_path = os.path.join(temp_dir, f"{of_sel_name}.xlsx")
                            try:
                                generar_excel_of_pronest(
                                    resumen_pdf=local_res,
                                    nido_pdf=local_nid,
                                    pieza_pdf=local_pie,
                                    nombre_of=of_sel_name,
                                    output_path=out_excel_path,
                                    po_number=po_final
                                )

                                # 3. Cargar a la Base de Datos SQLite / Excel
                                save_production_plan(out_excel_path)
                                registrar_auditoria(
                                    usuario=st.session_state.get("usuario_actual", "Programador"),
                                    accion="INTEGRACION_OF_GCS",
                                    detalles=f"OF: {of_sel_name} integrada con éxito con PO {po_final}"
                                )

                                # 4. Subir Excel generado a GCS si está disponible
                                if gcs_ok:
                                    upload_of_excel_to_gcs(of_sel_name, out_excel_path)
                                    push_db_to_gcs_async()

                                st.success(f"🎉 ¡Orden de Fabricación **{of_sel_name}** integrada con éxito al sistema de producción!")
                                st.balloons()
                                st.cache_data.clear()
                                st.rerun()

                            except Exception as ep:
                                st.error(f"❌ Error durante la generación o carga de la OF: {ep}")
