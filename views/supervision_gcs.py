"""
=============================================================================
SISTEMA DE CONTROL DE CORTE Y DOBLEZ - INDUSTRIA SIGRAMA S.A. DE C.V.
Vista: Supervisión y Repositorio Central de Órdenes de Fabricación
Permite al programador integrar OFs desde el Repositorio (GCS / Red Z:\\)
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

def view_supervision_gcs():
    st.markdown('''
    <div style="background: linear-gradient(135deg, #1e1e1e 0%, #111111 100%); 
                padding: 18px 24px; border-radius: 10px; border-left: 5px solid #EC2024; margin-bottom: 20px;">
        <div style="font-family: 'Montserrat', sans-serif; color: #FFFFFF !important; margin: 0; font-size: 24px; font-weight: 700;">
            🛰️ Supervisión y Repositorio de Órdenes de Fabricación
        </div>
        <p style="font-family: 'Questrial', sans-serif; color: #bbb; margin: 5px 0 0 0; font-size: 14px;">
            Seleccione una Orden de Fabricación del repositorio para ejecutar el motor ProNest, generar el Excel de producción y cargarla automáticamente con sus nidos y piezas a la base de datos.
        </p>
    </div>
    ''', unsafe_allow_html=True)

    # 1. Verificar qué OFs ya están registradas en la Base de Datos
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT of_number FROM ordenes")
    ofs_en_db = {str(row[0]).strip() for row in c.fetchall()}
    conn.close()

    # 2. Consultar catálogo de OFs del Repositorio
    # Intentar primero GCS, si no está disponible o está vacío, consultar local/Z:\
    gcs_ok = is_gcs_available()
    ofs_repositorio = []
    origen_datos = "Desconocido"

    if gcs_ok:
        ofs_repositorio = list_ofs_in_gcs()
        if ofs_repositorio:
            origen_datos = "Google Cloud Storage (gs://sigrama-corte-doblez-storage)"

    # Fallback a local o Z:\ si GCS no tiene OFs o no está conectado
    if not ofs_repositorio:
        local_manifest = Path(__file__).resolve().parent.parent / "pronest_files" / "manifest_ofs.json"
        if local_manifest.exists():
            try:
                import json
                with open(local_manifest, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    ofs_repositorio = data.get("ordenes", [])
                    if ofs_repositorio:
                        origen_datos = "Caché Local de Manifiesto"
            except Exception:
                pass

    if not ofs_repositorio and os.path.exists(r"Z:\14 - ORDENES DE FABRICACION"):
        ofs_repositorio = escanear_directorio_ofs(r"Z:\14 - ORDENES DE FABRICACION")
        if ofs_repositorio:
            origen_datos = "Unidad de Red Z:\\14 - ORDENES DE FABRICACION"

    # Tarjetas de estado superior
    m_col1, m_col2, m_col3, m_col4 = st.columns(4)
    with m_col1:
        st.metric("Total en Repositorio", len(ofs_repositorio))
    with m_col2:
        completas_count = sum(1 for o in ofs_repositorio if o.get("completo"))
        st.metric("Con 3 Reportes PDF", completas_count)
    with m_col3:
        st.metric("Ya en Producción", len(ofs_en_db))
    with m_col4:
        pendientes_count = sum(1 for o in ofs_repositorio if o.get("of_nombre") not in ofs_en_db and o.get("completo"))
        st.metric("Pendientes por Cargar", pendientes_count)

    st.caption(f"📡 Fuente de datos activa: **{origen_datos}**")

    if not ofs_repositorio:
        st.warning("⚠️ No se encontraron carpetas de OFs en el repositorio. Ejecute `SUBIR_ORDENES_A_GCS.bat` en su PC o verifique la conexión a `Z:\\`.")
        return

    st.markdown("---")

    # 3. Filtros y búsqueda
    col_f1, col_f2, col_f3 = st.columns([2, 1.5, 1])
    with col_f1:
        busq = st.text_input("🔍 Buscar OF por nombre o número:", value="", placeholder="Ej. 00086, 00095, PROD...")
    with col_f2:
        filtro_estado = st.selectbox(
            "Estado de Integración:",
            ["Todas", "🟢 Solo Listas para Integrar (Pendientes)", "🔵 Ya en Producción", "🟡 Incompletas"]
        )
    with col_f3:
        st.write("")
        st.write("")
        if st.button("🔄 Actualizar Repositorio", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    # Filtrar lista
    ofs_mostradas = []
    for item in ofs_repositorio:
        of_n = item.get("of_nombre", "")
        esta_en_db = of_n in ofs_en_db
        es_completa = bool(item.get("completo"))

        if busq and busq.lower() not in of_n.lower():
            continue

        if filtro_estado == "🟢 Solo Listas para Integrar (Pendientes)" and (esta_en_db or not es_completa):
            continue
        elif filtro_estado == "🔵 Ya en Producción" and not esta_en_db:
            continue
        elif filtro_estado == "🟡 Incompletas" and es_completa:
            continue

        ofs_mostradas.append(item)

    # 4. Selector de OF para integración
    st.markdown("### ⚡ Panel de Integración Automática a Producción")

    nombres_opciones = ["-- Seleccione una OF del Repositorio --"] + [
        f"{'🔵 [En Prod] ' if o['of_nombre'] in ofs_en_db else ('🟢 [Listo] ' if o.get('completo') else '🟡 [Incompleto] ')}{o['of_nombre']}"
        for o in ofs_mostradas
    ]

    selected_label = st.selectbox("Seleccionar Orden de Fabricación para Procesar:", nombres_opciones)

    if selected_label and selected_label != "-- Seleccione una OF del Repositorio --":
        # Extraer nombre limpio
        of_sel_name = selected_label.split("] ", 1)[-1].strip()
        of_data = next((o for o in ofs_repositorio if o["of_nombre"] == of_sel_name), None)

        if of_data:
            c_info1, c_info2 = st.columns([1.5, 1])
            with c_info1:
                st.markdown(f"#### 📄 Diagnóstico de Archivos: `{of_sel_name}`")
                r_pdf = of_data.get("resumen_pdf")
                n_pdf = of_data.get("nido_pdf")
                p_pdf = of_data.get("pieza_pdf")
                st.markdown(f"- **1. Resumen de Trabajo:** {'✅ ' + r_pdf if r_pdf else '❌ No encontrado'}")
                st.markdown(f"- **2. Detalle Nido / Cabezal:** {'✅ ' + n_pdf if n_pdf else '❌ No encontrado'}")
                st.markdown(f"- **3. Detalle de Pieza:** {'✅ ' + p_pdf if p_pdf else '❌ No encontrado'}")
                st.markdown(f"- **4. Archivo Excel ProNest:** {'✅ ' + of_data.get('excel_existente') if of_data.get('excel_existente') else '⏳ Se generará automáticamente'}")

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
            btn_txt = "🔄 Re-Integrar OF a Producción (Sobrescribir)" if ya_cargada else "⚡ Integrar OF al Sistema de Producción"

            if not of_data.get("completo"):
                st.warning("⚠️ No se puede integrar automáticamente esta OF porque no contiene los 3 reportes PDF requeridos de ProNest.")
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
                                st.rerun()

                            except Exception as ep:
                                st.error(f"❌ Error durante la generación o carga de la OF: {ep}")

    # 5. Tabla general del Repositorio
    st.markdown("---")
    st.subheader("📋 Catálogo General del Repositorio")
    
    rows_tabla = []
    for o in ofs_mostradas:
        of_n = o.get("of_nombre", "")
        en_prod = "🔵 En Producción" if of_n in ofs_en_db else ("🟢 Lista para Carga" if o.get("completo") else "🟡 Incompleta")
        rows_tabla.append({
            "Estado": en_prod,
            "Orden de Fabricación": of_n,
            "Resumen": "✅" if o.get("resumen_pdf") else "❌",
            "Nido": "✅" if o.get("nido_pdf") else "❌",
            "Pieza": "✅" if o.get("pieza_pdf") else "❌",
            "Excel": "✅" if o.get("excel_existente") or o.get("tiene_excel") else "⏳ Pendiente"
        })

    if rows_tabla:
        st.dataframe(pd.DataFrame(rows_tabla), use_container_width=True, hide_index=True)
    else:
        st.info("No hay órdenes que coincidan con los filtros seleccionados.")
