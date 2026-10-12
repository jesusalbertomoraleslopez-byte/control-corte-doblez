"""
=============================================================================
SISTEMA DE CONTROL DE CORTE Y DOBLEZ - INDUSTRIA SIGRAMA S.A. DE C.V.
Vista: Supervisión y Repositorio Central de Órdenes de Fabricación (Bucket GCS)
Integra el motor Generador de Excel ProNest con almacenamiento automático en el
Bucket GCS y alta directa en la Base de Datos de Programación y Producción.
=============================================================================
"""

import os
import re
import datetime
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
    push_db_to_gcs
)

@st.cache_data(ttl=60, show_spinner="Consultando catálogo de OFs en Google Cloud Storage...")
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

def _detectar_calibre_desde_nombre(nombre_of: str) -> str:
    """Extrae el calibre sugerido a partir del nombre de la OF (ej. CAL. 14 -> Cal 14)."""
    m = re.search(r'cal[.\s]*(\d+)', nombre_of or "", re.IGNORECASE)
    if m:
        return f"Cal {m.group(1)}"
    return "Cal 12"

def view_supervision_gcs():
    # Banner de Encabezado
    st.markdown('''
    <div style="background: linear-gradient(135deg, #1e1e1e 0%, #111111 100%); 
                padding: 18px 24px; border-radius: 10px; border-left: 5px solid #EC2024; margin-bottom: 20px;">
        <div style="font-family: 'Montserrat', sans-serif; color: #FFFFFF !important; margin: 0; font-size: 24px; font-weight: 700;">
            🛰️ Supervisión y Repositorio de Órdenes de Fabricación
        </div>
        <p style="font-family: 'Questrial', sans-serif; color: #bbb; margin: 5px 0 0 0; font-size: 14px;">
            Auditoría en tiempo real del Bucket central de GCS. Supervise los 3 reportes PDF de ProNest, genere y guarde automáticamente el archivo Excel en el Bucket y cargue la OF a la programación de producción.
        </p>
    </div>
    ''', unsafe_allow_html=True)

    # 1. Consultar base de datos local / activa
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
        busq = st.text_input("🔍 Buscar OF por nombre o número:", value="", placeholder="Ej. 00127, 00086, RENO, 4135...")
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
    # 4. TABLA PRINCIPAL DE ÓRDENES ENCONTRADAS EN EL BUCKET
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

        num_pdfs = sum([
            1 if o.get("resumen_pdf") else 0,
            1 if o.get("nido_pdf") else 0,
            1 if o.get("pieza_pdf") else 0
        ])
        diag_pdfs = f"{num_pdfs}/3 PDFs"
        excel_ex = o.get("excel_existente")

        rows_tabla.append({
            "Estado": estado_tag,
            "Orden de Fabricación": of_n,
            "Reportes": diag_pdfs,
            "Resumen PDF": "✅ Listo" if o.get("resumen_pdf") else "❌ Falta",
            "Nido PDF": "✅ Listo" if o.get("nido_pdf") else "❌ Falta",
            "Pieza PDF": "✅ Listo" if o.get("pieza_pdf") else "❌ Falta",
            "Excel en Bucket": f"✅ {excel_ex}" if excel_ex else ("✅ Generado" if o.get("tiene_excel") else "⏳ Pendiente")
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
                "Excel en Bucket": st.column_config.TextColumn("Excel en Bucket", width="medium"),
            }
        )
    else:
        st.info("ℹ️ No hay órdenes de fabricación que coincidan con la búsqueda o filtro actual.")

    st.markdown("---")

    # =========================================================================
    # 5. PANEL DE SUPERVISIÓN, GENERACIÓN DE EXCEL PRONEST Y CARGA AL BUCKET/BD
    # =========================================================================
    st.markdown("### ⚡ Supervisar, Generar Excel ProNest y Cargar OF a Programación")
    st.markdown(
        "Seleccione una orden del repositorio para conciliar sus **3 reportes PDF de ProNest**, "
        "generar y subir automáticamente el **archivo Excel (`.xlsx`) al Bucket**, y dar de alta la OF con sus nidos y piezas en **Programación de Producción**."
    )

    # Ordenar primero las pendientes completas (de más reciente a más antigua para mostrar OF 00127 arriba)
    ofs_para_integrar = sorted(
        ofs_filtradas if ofs_filtradas else ofs_repositorio,
        key=lambda x: (
            0 if (x.get("of_nombre") not in ofs_en_db and x.get("completo")) else (
                1 if x.get("completo") else 2
            ),
            x.get("of_nombre", "")
        )
    )
    # Invertir el grupo de listas pendientes para que las OF más nuevas (ej. OF 00127) salgan al principio
    listas_pendientes = [o for o in ofs_para_integrar if o.get("of_nombre") not in ofs_en_db and o.get("completo")]
    listas_pendientes.reverse()
    otras_ofs = [o for o in ofs_para_integrar if not (o.get("of_nombre") not in ofs_en_db and o.get("completo"))]
    ofs_ordenadas_selector = listas_pendientes + otras_ofs

    nombres_opciones = ["-- Seleccione una OF para Supervisar y Cargar --"] + [
        f"{'🔵 [En Prod] ' if o['of_nombre'] in ofs_en_db else ('🟢 [Listo] ' if o.get('completo') else '🟡 [Incompleto] ')}{o['of_nombre']}"
        for o in ofs_ordenadas_selector
    ]

    selected_label = st.selectbox("Orden de Fabricación a Supervisar y Procesar:", nombres_opciones)

    if selected_label and selected_label != "-- Seleccione una OF para Supervisar y Cargar --":
        of_sel_name = selected_label.split("] ", 1)[-1].strip()
        of_data = next((o for o in ofs_repositorio if o["of_nombre"] == of_sel_name), None)

        if of_data:
            # Diagnóstico de archivos en el Bucket
            r_pdf = of_data.get("resumen_pdf")
            n_pdf = of_data.get("nido_pdf")
            p_pdf = of_data.get("pieza_pdf")
            excel_ex = of_data.get("excel_existente")

            st.markdown(f"#### 📄 Diagnóstico de Archivos en Bucket: `{of_sel_name}`")
            cd1, cd2, cd3, cd4 = st.columns(4)
            cd1.markdown(f"**1. Resumen de Trabajo:**\n\n{'✅ `' + str(r_pdf) + '`' if r_pdf else '❌ No encontrado'}")
            cd2.markdown(f"**2. Detalle Nido / Cabezal:**\n\n{'✅ `' + str(n_pdf) + '`' if n_pdf else '❌ No encontrado'}")
            cd3.markdown(f"**3. Detalle de Pieza:**\n\n{'✅ `' + str(p_pdf) + '`' if p_pdf else '❌ No encontrado'}")
            cd4.markdown(f"**4. Excel ProNest en Bucket:**\n\n{'✅ `' + str(excel_ex) + '`' if excel_ex else '⏳ Se generará y subirá al Bucket'}")

            if not of_data.get("completo"):
                st.warning(f"⚠️ No se puede supervisar/integrar automáticamente la orden `{of_sel_name}` porque no contiene los 3 reportes PDF requeridos de ProNest en el Bucket.")
                return

            # Catálogo de POs y detección inteligente
            labels_po, lookup_po, _ = obtener_opciones_po()
            po_sug, idx_sug = buscar_po_sugerida(of_sel_name, labels_po, lookup_po)
            calibre_sug = _detectar_calibre_desde_nombre(of_sel_name)

            # Parámetros de la Orden (integrado de Generador OF)
            with st.expander("📝 Parámetros de la Orden de Fabricación (Hoja 'Orden' y Vinculación PO)", expanded=True):
                cp1, cp2 = st.columns(2)
                with cp1:
                    idx_sel_po = st.selectbox(
                        "📌 Vincular con Orden de Compra (Catálogo App de PO's):",
                        options=range(len(labels_po)),
                        format_func=lambda i: labels_po[i],
                        index=idx_sug if idx_sug < len(labels_po) else 0,
                        help="Detecta automáticamente la PO desde la App de PO's en Google Cloud",
                        key=f"po_sel_{of_sel_name}"
                    )
                    po_seleccionada_label = labels_po[idx_sel_po]
                    info_po = lookup_po.get(po_seleccionada_label, {})
                    po_val = info_po.get("po", "")
                    proyecto_cliente_sug = info_po.get("proyecto", "")

                    po_manual = st.text_input(
                        "PO / Referencia asignada:",
                        value=po_val if po_val else po_sug,
                        key=f"po_man_{of_sel_name}"
                    )
                    proyecto_nombre = st.text_input(
                        "Nombre del Proyecto:",
                        value=of_sel_name,
                        key=f"proy_nom_{of_sel_name}"
                    )
                    orden_fab_input = st.text_input(
                        "Orden de Fabricación (ID en Base de Datos):",
                        value=of_sel_name,
                        key=f"of_id_{of_sel_name}"
                    )
                    usuario_actual = st.session_state.get("nombre_completo") or st.session_state.get("username") or "BRYAN MANCINAS"
                    programador_val = st.text_input(
                        "Programador responsable:",
                        value=usuario_actual,
                        key=f"prog_{of_sel_name}"
                    )

                with cp2:
                    cliente_proyecto_val = st.text_input(
                        "Nombre del Proyecto de Cliente:",
                        value=proyecto_cliente_sug if proyecto_cliente_sug else "POR DEFINIR",
                        key=f"cli_proy_{of_sel_name}"
                    )
                    desc_pronest_val = st.text_input(
                        "Descripción OF ProNest:",
                        value=of_sel_name,
                        key=f"desc_pro_{of_sel_name}"
                    )
                    c_cal, c_prio = st.columns(2)
                    with c_cal:
                        calibre_val = st.text_input(
                            "Calibre:",
                            value=calibre_sug,
                            key=f"cal_{of_sel_name}"
                        )
                    with c_prio:
                        prioridad_val = st.number_input(
                            "Prioridad de Corte:",
                            min_value=1,
                            max_value=5,
                            value=1,
                            key=f"prio_{of_sel_name}"
                        )

            params_orden = {
                "nombre_proyecto": proyecto_nombre,
                "programador": programador_val,
                "orden_fab": orden_fab_input,
                "po": po_manual,
                "desc_pronest": desc_pronest_val,
                "calibre": calibre_val,
                "prioridad": prioridad_val,
                "cliente_proyecto": cliente_proyecto_val
            }

            ya_cargada = of_sel_name in ofs_en_db
            col_b1, col_b2 = st.columns([2, 1])
            with col_b1:
                lbl_main_btn = (
                    f"🔄 Re-Supervisar, Actualizar Excel en Bucket y Recargar '{of_sel_name}' a Programación"
                    if ya_cargada
                    else f"🚀 Supervisar, Generar Excel en Bucket y Cargar '{of_sel_name}' a Programación"
                )
                btn_supervisar_cargar = st.button(lbl_main_btn, type="primary", use_container_width=True)
            with col_b2:
                btn_solo_excel = st.button("📊 Solo Generar Excel en Bucket", type="secondary", use_container_width=True)

            if btn_supervisar_cargar or btn_solo_excel:
                with st.spinner(f"Descargando los 3 reportes PDF de '{of_sel_name}' y ejecutando motor ProNest..."):
                    temp_dir = tempfile.mkdtemp()
                    local_res = None
                    local_nid = None
                    local_pie = None

                    # 1. Descargar los 3 PDFs desde el Bucket GCS (o leer desde carpeta local si aplica)
                    if gcs_ok:
                        try:
                            d_files = download_of_pdfs_from_gcs(of_sel_name, temp_dir)
                            local_res = d_files.get("resumen")
                            local_nid = d_files.get("nido")
                            local_pie = d_files.get("pieza")
                        except Exception as eg:
                            print(f"[SUPERVISION] Error descargando PDFs desde GCS: {eg}")

                    if not (local_res and local_nid and local_pie):
                        ruta_loc = of_data.get("ruta")
                        if ruta_loc and os.path.exists(ruta_loc):
                            diag_loc = analizar_carpeta_of(ruta_loc)
                            if diag_loc["resumen"]:
                                local_res = os.path.join(ruta_loc, diag_loc["resumen"])
                            if diag_loc["nido"]:
                                local_nid = os.path.join(ruta_loc, diag_loc["nido"])
                            if diag_loc["pieza"]:
                                local_pie = os.path.join(ruta_loc, diag_loc["pieza"])
                            temp_dir = ruta_loc

                    if not (local_res and local_nid and local_pie):
                        st.error("❌ No se pudieron recuperar los 3 reportes PDF desde el Bucket para procesar la orden.")
                    else:
                        try:
                            # 2. Ejecutar el motor generador de Excel ProNest (la aplicación integrada)
                            with open(local_res, "rb") as fr, open(local_nid, "rb") as fn, open(local_pie, "rb") as fp:
                                pdf_bytes_dict = {
                                    "resumen": fr.read(),
                                    "nido": fn.read(),
                                    "pieza": fp.read()
                                }

                            wb, stats = generar_excel_of_pronest(
                                pdf_bytes_dict=pdf_bytes_dict,
                                params_orden=params_orden
                            )

                            safe_name = re.sub(r'[\\/*?:"<>|]', '', params_orden["orden_fab"]).strip()
                            excel_filename = f"{safe_name}.xlsx"
                            excel_bytes = stats["excel_bytes"]

                            # Guardar archivo físico temporal (y en Z:\ si existe la carpeta local)
                            out_excel_path = os.path.join(temp_dir, excel_filename)
                            with open(out_excel_path, "wb") as f_out:
                                f_out.write(excel_bytes)

                            ruta_z = of_data.get("ruta")
                            if ruta_z and os.path.exists(ruta_z):
                                try:
                                    with open(os.path.join(ruta_z, excel_filename), "wb") as fz:
                                        fz.write(excel_bytes)
                                except Exception:
                                    pass

                            # 3. Subir automáticamente el archivo Excel (.xlsx) generado al Bucket GCS
                            subido_bucket = False
                            if gcs_ok:
                                subido_bucket = upload_of_excel_to_gcs(
                                    of_folder_name=of_sel_name,
                                    local_excel_path=out_excel_path,
                                    excel_bytes=excel_bytes,
                                    filename=excel_filename
                                )

                            if subido_bucket:
                                st.success(
                                    f"✅ Archivo Excel **`{excel_filename}`** generado y guardado automáticamente en el Bucket: "
                                    f"`gs://sigrama-corte-doblez-storage/ordenes_fabricacion/{of_sel_name}/{excel_filename}`"
                                )
                            else:
                                st.success(f"✅ Archivo Excel **`{excel_filename}`** generado correctamente.")

                            # 4. Cargar OF, Nidos y Piezas a la Base de Datos de Programación y Producción
                            if btn_supervisar_cargar:
                                with st.spinner("Cargando OF, Nidos y Piezas a la programación de producción y sincronizando con GCP..."):
                                    fecha_hoy = datetime.datetime.now().strftime("%Y-%m-%d")
                                    calibre_final = params_orden["calibre"] or stats.get("calibre", "Cal 12")

                                    save_production_plan(
                                        of_number=params_orden["orden_fab"],
                                        proyecto=params_orden["nombre_proyecto"],
                                        programador=params_orden["programador"],
                                        fecha=fecha_hoy,
                                        df_nidos=stats["df_nidos"],
                                        df_piezas=stats["df_piezas"],
                                        po=params_orden["po"],
                                        descripcion_pronest=params_orden["desc_pronest"],
                                        calibre=calibre_final,
                                        prioridad=params_orden["prioridad"],
                                        proyecto_cliente=params_orden["cliente_proyecto"]
                                    )

                                    # Respaldar base de datos actualizada en GCS inmediatamente
                                    if gcs_ok:
                                        push_db_to_gcs()

                                    registrar_auditoria(
                                        usuario=st.session_state.get("username", "Programador"),
                                        accion="SUPERVISION_INTEGRACION_OF_GCS",
                                        detalles=(
                                            f"OF: {params_orden['orden_fab']} supervisada, Excel subido al Bucket y cargada a producción "
                                            f"({stats['total_nidos']} nidos, {stats['total_piezas_fisicas']} piezas por hoja) con PO {params_orden['po']}"
                                        )
                                    )

                                    st.cache_data.clear()
                                    st.balloons()
                                    st.success(
                                        f"🎉 ¡Orden de Fabricación **{params_orden['orden_fab']}** supervisada y cargada exitosamente a la Programación de Producción! "
                                        f"({stats['total_nidos']} nidos registrados)."
                                    )

                            # 5. Mostrar Vista Previa de las 3 Hojas del Excel Generado
                            st.markdown("### 🔍 Vista Previa del Archivo Excel Generado y Cargado")
                            t1, t2, t3 = st.tabs([
                                f"📑 Hoja 1: Orden (1 registro)",
                                f"📑 Hoja 2: Nidos ({len(stats['df_nidos'])} nidos)",
                                f"📑 Hoja 3: Piezas ({len(stats['df_piezas'])} registros)"
                            ])
                            with t1:
                                st.dataframe(stats["df_orden"], use_container_width=True, hide_index=True)
                            with t2:
                                st.dataframe(stats["df_nidos"], use_container_width=True, hide_index=True)
                            with t3:
                                st.dataframe(stats["df_piezas"], use_container_width=True, hide_index=True)

                            st.download_button(
                                label=f"📥 Descargar Copia de {excel_filename}",
                                data=excel_bytes,
                                file_name=excel_filename,
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                use_container_width=True
                            )

                        except Exception as ep:
                            st.error(f"❌ Error durante la generación o carga de la OF: {ep}")
                            import traceback
                            st.code(traceback.format_exc())
