import os
import io
import datetime
import pandas as pd
import streamlit as st

from utils.generador_of_excel import generar_excel_of_pronest
from utils.scanner_of import (
    escanear_directorio_ofs,
    analizar_carpeta_of,
    cargar_catalogo_pos_app,
    obtener_opciones_po,
    buscar_po_sugerida
)
from utils.database import save_production_plan, get_connection, registrar_auditoria

def view_generador_of():
    st.markdown('''
    <div style="background: linear-gradient(135deg, #1e1e1e 0%, #111111 100%); 
                padding: 18px 24px; border-radius: 10px; border-left: 5px solid #EC2024; margin-bottom: 20px;">
        <div style="font-family: 'Montserrat', sans-serif; color: #FFFFFF !important; margin: 0; font-size: 24px; font-weight: 700;">
            📑 Generador de Órdenes de Fabricación ProNest
        </div>
        <p style="font-family: 'Questrial', sans-serif; color: #bbb; margin: 5px 0 0 0; font-size: 14px;">
            Escaneo de carpetas en <code>Z:\\14 - ORDENES DE FABRICACION</code>, diagnóstico de reportes PDF, enlace con App de PO's y carga directa al sistema de producción.
        </p>
    </div>
    ''', unsafe_allow_html=True)

    base_dir = r"Z:\14 - ORDENES DE FABRICACION"
    
    # Barra de herramientas superior
    c_top1, c_top2, c_top3 = st.columns([2, 1, 1])
    with c_top1:
        ruta_directorio = st.text_input("📁 Directorio de Órdenes de Fabricación:", value=base_dir)
    with c_top2:
        st.write("")
        st.write("")
        if st.button("🔄 Re-escanear Carpetas", use_container_width=True):
            st.cache_data.clear()
            st.toast("Caché limpiada. Re-escaneando carpetas...", icon="🔄")
            st.rerun()
    with c_top3:
        st.write("")
        st.write("")
        if not os.path.exists(ruta_directorio):
            st.warning("⚠️ Ruta Z:\\ no accesible")
        else:
            st.success("✅ Conectado a Z:\\")

    if not os.path.exists(ruta_directorio):
        st.warning(f"⚠️ La unidad de red `{ruta_directorio}` no está disponible en este servidor (normal en la versión en la nube `control-corte-doblez.streamlit.app`).")
        st.info("""
        💡 **Para escanear `Z:\\14 - ORDENES DE FABRICACION` de forma directa en red local:**
        - Abra la aplicación en su computadora local en: **[http://localhost:8501](http://localhost:8501)**
        """)

        st.markdown("---")
        st.subheader("📤 Alternativa Web: Cargar los 3 Reportes PDF de ProNest")
        st.caption("Si está fuera de la red local o en la nube, puede subir los 3 PDFs para generar el Excel y cargarlo a producción:")

        col_u1, col_u2, col_u3 = st.columns(3)
        with col_u1:
            up_res = st.file_uploader("📄 1. RESUMEN DE TRABAJO (PDF)", type=["pdf"], key="c_up_res")
        with col_u2:
            up_nid = st.file_uploader("📄 2. DETALLE DEL NIDO DE CABEZAL (PDF)", type=["pdf"], key="c_up_nid")
        with col_u3:
            up_pie = st.file_uploader("📄 3. DETALLE DE LA PIEZA (PDF)", type=["pdf"], key="c_up_pie")

        if up_res and up_nid and up_pie:
            of_cloud_nom = st.text_input("Número / Nombre de la OF:", value=up_res.name.replace(".pdf", ""))
            po_cloud = st.text_input("Orden de Compra (PO):", value="")
            proj_cloud = st.text_input("Nombre del Proyecto de Cliente:", value="")

            if st.button("🚀 Procesar Reportes y Generar OF", type="primary", use_container_width=True):
                try:
                    bytes_dict = {
                        "resumen": up_res.getvalue(),
                        "nido": up_nid.getvalue(),
                        "pieza": up_pie.getvalue()
                    }
                    wb_c, stats_c = generar_excel_of_pronest(
                        pdf_bytes_dict=bytes_dict,
                        params_orden={
                            "orden_fab": of_cloud_nom,
                            "nombre_proyecto": of_cloud_nom,
                            "po": po_cloud,
                            "cliente_proyecto": proj_cloud
                        }
                    )
                    st.success("✅ ¡Orden procesada con éxito!")
                    st.download_button(
                        label=f"📥 Descargar {of_cloud_nom}.xlsx",
                        data=stats_c["excel_bytes"],
                        file_name=f"{of_cloud_nom}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )
                except Exception as ex_c:
                    st.error(f"❌ Error al procesar: {ex_c}")
        return

    # Escaneo de carpetas
    with st.spinner("Escaneando carpetas y diagnosticando archivos en Z:\\..."):
        carpetas = escanear_directorio_ofs(ruta_directorio)

    if not carpetas:
        st.warning("No se encontraron carpetas de órdenes de fabricación en el directorio especificado.")
        return

    # Catálogo de PO's
    labels_po, lookup_po, df_pos = obtener_opciones_po()

    # Métricas generales
    total = len(carpetas)
    listas = sum(1 for c in carpetas if c["completo"])
    incompletas = total - listas
    con_excel = sum(1 for c in carpetas if c["tiene_excel"])

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("📁 Total Carpetas/Rev", total)
    m2.metric("✅ Con 3 PDFs Listas", listas)
    m3.metric("⚠️ Faltan PDFs", incompletas)
    m4.metric("📊 Con Excel Generado", con_excel)

    st.markdown("---")

    # Filtros y Búsqueda
    col_filtro1, col_filtro2, col_filtro3 = st.columns([2, 1, 1])
    with col_filtro1:
        search_query = st.text_input("🔍 Buscar por Nombre de OF o Revisión:", placeholder="Ej. 1494, REV 1, etc.").strip().lower()
    with col_filtro2:
        filtro_estado = st.selectbox("Estado de PDFs:", ["Todos", "Listas (3 PDFs)", "Incompletas (Faltan PDFs)"])
    with col_filtro3:
        filtro_excel = st.selectbox("Archivo Excel:", ["Todos", "Sin Excel", "Con Excel Ya Generado"])

    # Filtrado
    carpetas_filtradas = []
    for c in carpetas:
        if search_query and (search_query not in c["etiqueta"].lower()):
            continue
        if filtro_estado == "Listas (3 PDFs)" and not c["completo"]:
            continue
        if filtro_estado == "Incompletas (Faltan PDFs)" and c["completo"]:
            continue
        if filtro_excel == "Sin Excel" and c["tiene_excel"]:
            continue
        if filtro_excel == "Con Excel Ya Generado" and not c["tiene_excel"]:
            continue
        carpetas_filtradas.append(c)

    # Preparar DataFrame para visualización y selección interactiva
    filas_tabla = []
    for c in carpetas_filtradas:
        estado_desc = "✅ Listo (3 PDFs)" if c["completo"] else "⚠️ Incompleto"
        excel_desc = f"📊 {c['excel_existente']}" if c["tiene_excel"] else "❌ Sin Excel"
        filas_tabla.append({
            "Seleccionar": False,
            "Orden de Fabricación": c["etiqueta"],
            "Diagnóstico PDFs": estado_desc,
            "Excel en Carpeta": excel_desc,
            "Resumen": "✅" if c["resumen_pdf"] else "❌",
            "Nidos": "✅" if c["nido_pdf"] else "❌",
            "Piezas": "✅" if c["pieza_pdf"] else "❌",
            "Ruta": c["ruta"],
            "Completo": c["completo"],
            "NombreOF": c["of_nombre"],
            "Subcarpeta": c.get("subcarpeta", "")
        })

    df_display = pd.DataFrame(filas_tabla)

    st.subheader(f"📋 Carpetas Disponibles ({len(df_display)} encontradas)")
    st.caption("Marque la casilla **'Seleccionar'** en una o más órdenes para configurar parámetros, generar el Excel oficial o cargarlas directo al sistema de producción.")

    # Data Editor con checkboxes interactivos
    edited_df = st.data_editor(
        df_display,
        column_config={
            "Seleccionar": st.column_config.CheckboxColumn(
                "Seleccionar",
                help="Marque para procesar esta orden",
                default=False,
            ),
            "Orden de Fabricación": st.column_config.TextColumn("Orden de Fabricación", width="large", disabled=True),
            "Diagnóstico PDFs": st.column_config.TextColumn("Diagnóstico PDFs", width="medium", disabled=True),
            "Excel en Carpeta": st.column_config.TextColumn("Excel en Carpeta", width="medium", disabled=True),
            "Resumen": st.column_config.TextColumn("Resumen", width="small", disabled=True),
            "Nidos": st.column_config.TextColumn("Nidos", width="small", disabled=True),
            "Piezas": st.column_config.TextColumn("Piezas", width="small", disabled=True),
            "Ruta": None,
            "Completo": None,
            "NombreOF": None,
            "Subcarpeta": None
        },
        disabled=["Orden de Fabricación", "Diagnóstico PDFs", "Excel en Carpeta", "Resumen", "Nidos", "Piezas"],
        hide_index=True,
        use_container_width=True,
        height=320,
        key="tabla_seleccion_ofs"
    )

    # Identificar carpetas seleccionadas
    seleccionados = edited_df[edited_df["Seleccionar"] == True]
    num_sel = len(seleccionados)

    if num_sel == 0:
        st.info("💡 Por favor, marque la casilla de verificación de una o varias órdenes de fabricación en la tabla anterior para continuar.")
        return

    st.markdown("---")
    st.subheader(f"⚙️ Configuración y Carga de Órdenes Seleccionadas ({num_sel})")

    # MODO 1: Una sola orden seleccionada (Vista detallada e interactiva)
    if num_sel == 1:
        sel_row = seleccionados.iloc[0]
        of_nombre_sel = sel_row["NombreOF"]
        of_etiqueta_sel = sel_row["Orden de Fabricación"]
        subcarpeta_sel = sel_row.get("Subcarpeta", "")
        target_folder = sel_row["Ruta"]
        es_completo = sel_row["Completo"]

        nombre_of_sugerido = f"{of_nombre_sel} - {subcarpeta_sel}" if subcarpeta_sel else of_nombre_sel

        st.markdown(f"### 📂 Carpeta Activa: **`{of_etiqueta_sel}`**")
        st.caption(f"Ruta física: `{target_folder}`")

        # Diagnóstico de PDFs detallado
        diag = analizar_carpeta_of(target_folder)
        c_diag1, c_diag2, c_diag3 = st.columns(3)
        c_diag1.markdown(f"**RESUMEN DE TRABAJO:** {'✅ ' + diag['resumen'] if diag['resumen'] else '❌ Faltante'}")
        c_diag2.markdown(f"**NIDO DE CABEZAL:** {'✅ ' + diag['nido'] if diag['nido'] else '❌ Faltante'}")
        c_diag3.markdown(f"**DETALLE DE LA PIEZA:** {'✅ ' + diag['pieza'] if diag['pieza'] else '❌ Faltante'}")

        if not es_completo:
            st.error("⚠️ Esta carpeta no cuenta con los 3 reportes PDF requeridos de ProNest. Asegúrese de exportar los 3 PDFs desde ProNest a esta carpeta antes de generar el Excel.")
            return

        # Búsqueda inteligente de PO sugerida
        po_sug, idx_sug = buscar_po_sugerida(nombre_of_sugerido, labels_po, lookup_po)

        # Formulario de parámetros
        with st.expander("📝 Parámetros de la Orden de Fabricación (Hoja 'Orden')", expanded=True):
            cp1, cp2 = st.columns(2)
            with cp1:
                idx_sel_po = st.selectbox(
                    "📌 Vincular con Orden de Compra (PO de App de PO's):",
                    options=range(len(labels_po)),
                    format_func=lambda i: labels_po[i],
                    index=idx_sug,
                    help="Conectado en tiempo real a la base de datos de la App de PO's"
                )

                po_seleccionada_label = labels_po[idx_sel_po]
                info_po = lookup_po.get(po_seleccionada_label, {})
                po_val = info_po.get("po", "")
                proyecto_cliente_sug = info_po.get("proyecto", "")

                po_manual = st.text_input("PO / Referencia asignada:", value=po_val if po_val else po_sug)
                proyecto_nombre = st.text_input("Nombre del Proyecto:", value=nombre_of_sugerido)
                orden_fab_input = st.text_input("Orden de Fabricación (ID en Base de Datos):", value=nombre_of_sugerido)
                usuario_actual = st.session_state.get("nombre_completo", "BRYAN MANCINAS")
                programador_val = st.text_input("Programador responsable:", value=usuario_actual if usuario_actual else "BRYAN MANCINAS")

            with cp2:
                cliente_proyecto_val = st.text_input(
                    "Nombre del Proyecto de Cliente:",
                    value=proyecto_cliente_sug if proyecto_cliente_sug else "POR DEFINIR"
                )
                desc_pronest_val = st.text_input("Descripción OF ProNest:", value=nombre_of_sugerido)
                
                c_cal, c_prio = st.columns(2)
                with c_cal:
                    calibre_val = st.text_input("Calibre:", value="Cal 12")
                with c_prio:
                    prioridad_val = st.number_input("Prioridad de Corte:", min_value=1, max_value=5, value=1)

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

        # Botones de Acción
        col_btn1, col_btn2 = st.columns(2)

        with col_btn1:
            btn_generar_excel = st.button("📊 Generar y Guardar Archivo Excel (.xlsx)", type="secondary", use_container_width=True)

        with col_btn2:
            btn_cargar_db = st.button("🚀 Dar de Alta Directo en Producción (1 Clic)", type="primary", use_container_width=True)

        # Procesamiento
        if btn_generar_excel or btn_cargar_db:
            with st.spinner("Conciliando reportes PDF de ProNest y generando estructura de datos..."):
                try:
                    wb, stats = generar_excel_of_pronest(target_folder, params_orden=params_orden)
                    import re
                    safe_name = re.sub(r'[\\/*?:"<>|]', '', orden_fab_input).strip()
                    excel_filename = f"{safe_name}.xlsx"
                    excel_save_path = os.path.join(target_folder, excel_filename)

                    # Guardar archivo físico en la carpeta Z:\
                    with open(excel_save_path, "wb") as f_out:
                        f_out.write(stats["excel_bytes"])

                    st.success(f"✅ Archivo Excel generado y guardado exitosamente en: `{excel_save_path}`")

                    # Si se pulsó "Dar de Alta Directo en Producción"
                    if btn_cargar_db:
                        with st.spinner("Registrando orden, nidos y piezas en la Base de Datos de Producción..."):
                            df_n = stats["df_nidos"]
                            df_p = stats["df_piezas"]
                            fecha_hoy = datetime.datetime.now().strftime("%Y-%m-%d")

                            save_production_plan(
                                of_number=params_orden["orden_fab"],
                                proyecto=params_orden["nombre_proyecto"],
                                programador=params_orden["programador"],
                                fecha=fecha_hoy,
                                df_nidos=df_n,
                                df_piezas=df_p,
                                po=params_orden["po"],
                                descripcion_pronest=params_orden["desc_pronest"],
                                calibre=params_orden["calibre"],
                                prioridad=params_orden["prioridad"],
                                proyecto_cliente=params_orden["cliente_proyecto"]
                            )

                            # Registrar auditoría
                            user_log = st.session_state.get("username", "sistema")
                            registrar_auditoria(
                                user_log, 
                                "Carga OF Directa ProNest", 
                                f"OF {params_orden['orden_fab']} ({stats['total_piezas_fisicas']} piezas) dada de alta directo a producción desde ProNest Generator."
                            )

                            st.balloons()
                            st.success(f"🎉 ¡La Orden **{params_orden['orden_fab']}** fue dada de alta exitosamente en la Base de Datos de Producción!")
                            st.info("💡 Ya puede ser visualizada y monitoreada en los módulos de **Control de Producción**, **Planeación de Corte** y **Panel de Control**.")

                    # Visualización de DataFrames generados
                    st.markdown("### 🔍 Vista Previa de Datos Generados")
                    t1, t2, t3 = st.tabs([
                        f"📑 Hoja 1: Orden ({len(stats['df_orden'])} fila)",
                        f"📑 Hoja 2: Nidos ({len(stats['df_nidos'])} nidos)",
                        f"📑 Hoja 3: Piezas ({len(stats['df_piezas'])} registros, {stats['total_piezas_fisicas']} piezas físicas)"
                    ])

                    with t1:
                        st.dataframe(stats["df_orden"], use_container_width=True)
                    with t2:
                        st.dataframe(stats["df_nidos"], use_container_width=True)
                    with t3:
                        st.dataframe(stats["df_piezas"], use_container_width=True)

                    # Botón para descargar copia local
                    st.download_button(
                        label=f"📥 Descargar Copia Local de {excel_filename}",
                        data=stats["excel_bytes"],
                        file_name=excel_filename,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )

                except Exception as e:
                    st.error(f"❌ Error al procesar la orden: {str(e)}")
                    import traceback
                    st.code(traceback.format_exc())

    # MODO 2: Selección Múltiple (Procesamiento en Lote)
    else:
        st.markdown(f"### 📦 Procesamiento Masivo en Lote ({num_sel} Órdenes Seleccionadas)")
        
        incompletas_en_sel = seleccionados[seleccionados["Completo"] == False]
        if not incompletas_en_sel.empty:
            st.warning(f"⚠️ {len(incompletas_en_sel)} de las órdenes seleccionadas están incompletas (les faltan PDFs) y serán omitidas.")
            seleccionados = seleccionados[seleccionados["Completo"] == True]

        if seleccionados.empty:
            st.error("Ninguna de las órdenes seleccionadas cuenta con los 3 PDFs requeridos.")
            return

        st.write("Órdenes válidas para procesar:")
        st.write(", ".join(f"**{x}**" for x in seleccionados["Orden de Fabricación"]))

        c_batch1, c_batch2 = st.columns(2)
        with c_batch1:
            cargar_en_db_batch = st.checkbox("🚀 Cargar automáticamente a la Base de Datos de Producción", value=True)
        with c_batch2:
            sobreescribir_existentes = st.checkbox("Re-generar aunque ya exista el archivo Excel", value=False)

        if st.button(f"⚡ Procesar {len(seleccionados)} Órdenes Seleccionadas", type="primary", use_container_width=True):
            barra_progreso = st.progress(0)
            status_text = st.empty()
            exitos = 0
            errores = 0

            for i, (_, row) in enumerate(seleccionados.iterrows()):
                of_nom = row["NombreOF"]
                sub_c = row.get("Subcarpeta", "")
                of_efectivo = f"{of_nom} - {sub_c}" if sub_c else of_nom
                target_f = row["Ruta"]
                status_text.text(f"Procesando {i+1}/{len(seleccionados)}: {of_efectivo}...")

                try:
                    import re
                    safe_name = re.sub(r'[\\/*?:"<>|]', '', of_efectivo).strip()
                    # Búsqueda automática de PO
                    po_sug, _ = buscar_po_sugerida(of_efectivo, labels_po, lookup_po)
                    wb, stats = generar_excel_of_pronest(target_f, params_orden={"orden_fab": of_efectivo, "nombre_proyecto": of_efectivo, "po": po_sug})
                    excel_path = os.path.join(target_f, f"{safe_name}.xlsx")
                    
                    with open(excel_path, "wb") as f_out:
                        f_out.write(stats["excel_bytes"])

                    if cargar_en_db_batch:
                        fecha_hoy = datetime.datetime.now().strftime("%Y-%m-%d")
                        save_production_plan(
                            of_number=of_efectivo,
                            proyecto=of_efectivo,
                            programador="SISTEMA PRO-NEST",
                            fecha=fecha_hoy,
                            df_nidos=stats["df_nidos"],
                            df_piezas=stats["df_piezas"],
                            po=po_sug,
                            descripcion_pronest=of_efectivo,
                            calibre=stats.get("calibre", "Cal 12"),
                            prioridad=1,
                            proyecto_cliente="POR DEFINIR"
                        )
                    exitos += 1
                except Exception as e:
                    errores += 1

                barra_progreso.progress((i + 1) / len(seleccionados))

            status_text.text("¡Procesamiento finalizado!")
            st.success(f"✅ Procesadas con éxito: {exitos} orden(es).")
            if errores > 0:
                st.warning(f"⚠️ Errores en: {errores} orden(es).")
            st.balloons()
