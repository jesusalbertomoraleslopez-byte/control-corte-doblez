import streamlit as st
import pandas as pd
import re
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.plantilla_excel import generar_plantilla
from utils.database import clear_db, clear_avances_rechazos, save_production_plan, get_active_of, get_todas_piezas, update_ruta_piezas
from views.avances import view_avances, PROCESSES
from views.reportes import view_reportes
from views.correcciones import view_correcciones


def reset_of():
    """Limpia solo los registros de producción (avances y rechazos)."""
    clear_avances_rechazos()
    st.rerun()


def normalizar_nido(valor):
    """Convierte cualquier formato de NIDO a N01, N02, etc. y descarta texto inválido."""
    if pd.isna(valor):
        return None
    s = str(valor).strip()
    
    # Palabras clave a ignorar (como totales, subtotales, encabezados)
    if s.upper() in ["TOTAL", "NIDOS", "NIDO", "TOTALES"]:
        return None
        
    m = re.search(r'\d+', s)
    if m:
        return f"N{int(m.group()):02d}"
        
    # Si no tiene números y no es una de las palabras ignoradas, tal vez sea un código especial
    # Pero por seguridad, si no tiene números, lo mejor suele ser ignorarlo
    return None


def calcular_totales(df_nidos, df_piezas):
    """Cruza nidos y piezas para calcular CANTIDAD * REPETICION."""
    df_n = df_nidos.dropna(how='all').copy()
    df_p = df_piezas.dropna(how='all').copy()

    col_nido_n = next((c for c in df_n.columns if 'NIDO' in str(c).upper()), None)
    col_hojas  = next((c for c in df_n.columns if 'HOJA' in str(c).upper()), None)
    col_cal_n  = next((c for c in df_n.columns if 'CALIBRE' in str(c).upper()), None)
    col_nido_p = next((c for c in df_p.columns if 'NIDO' in str(c).upper()), None)
    col_pieza  = next((c for c in df_p.columns if 'PIEZA' in str(c).upper() and 'NOMBRE' not in str(c).upper()), None)
    col_nombre = next((c for c in df_p.columns if 'NOMBRE' in str(c).upper()), None)
    col_cant   = next((c for c in df_p.columns if 'CANTIDAD' in str(c).upper()), None)

    if not all([col_nido_n, col_hojas, col_nido_p, col_cant]):
        return pd.DataFrame()

    df_n['__KEY__'] = df_n[col_nido_n].apply(normalizar_nido)
    df_p['__KEY__'] = df_p[col_nido_p].apply(normalizar_nido)

    slim_cols = ['__KEY__', col_hojas] + ([col_cal_n] if col_cal_n else [])
    df_slim = df_n[slim_cols].copy()
    df_slim.columns = ['__KEY__', 'HOJAS'] + (['CALIBRE'] if col_cal_n else [])

    merged = df_p.merge(df_slim, on='__KEY__', how='left')
    merged['HOJAS'] = pd.to_numeric(merged['HOJAS'], errors='coerce').fillna(1).astype(int)
    merged[col_cant] = pd.to_numeric(merged[col_cant], errors='coerce').fillna(0).astype(int)
    merged['CANTIDAD * REPETICION'] = merged[col_cant] * merged['HOJAS']

    cols_out = []
    if 'CALIBRE' in merged.columns: cols_out.append('CALIBRE')
    cols_out.append('__KEY__')
    if col_pieza:  cols_out.append(col_pieza)
    if col_nombre: cols_out.append(col_nombre)
    cols_out += [col_cant, 'HOJAS', 'CANTIDAD * REPETICION']

    df_out = merged[[c for c in cols_out if c in merged.columns]].copy()
    df_out.rename(columns={'__KEY__': 'NIDO', col_cant: 'CANTIDAD'}, inplace=True)
    # Asegurar todo sea string para evitar errores Arrow
    return df_out.astype(str)


# ──────────────────────────────────────────────────────────
def view_planeacion():
    st.title("3. PLANEACIÓN DE PRODUCCIÓN")

    # Inicializar session_state
    if 'production_data' not in st.session_state:
        st.session_state.production_data = None
    if 'of_number' not in st.session_state:
        st.session_state.of_number = None
    if 'temp_production_data' not in st.session_state:
        st.session_state.temp_production_data = None

    active_of = get_active_of()

    if active_of:
        proj_client_info = f" | Cliente: {active_of.get('proyecto_cliente')}" if active_of.get('proyecto_cliente') else ""
        st.info(
            f"ℹ️ OF Activa actualmente: **{active_of['of_number']}** — "
            f"Proyecto: **{active_of['proyecto']}**{proj_client_info}"
        )
    else:
        st.info("ℹ️ No hay planes de producción activos.")

    st.markdown("---")

    # ══════════════════════════════════════════════════════════
    # SUB SECCIONES (TABS)
    # ══════════════════════════════════════════════════════════
    tab_carga, tab_rutas, tab_gantt = st.tabs([
        "📤 3.1 CARGA", 
        "🛣️ 3.2 SELECCIÓN DE PROCESOS",
        "📅 3.3 PROGRAMACIÓN Y GANTT"
    ])

    with tab_gantt:
        st.markdown("### 📅 3.3 Programación y Diagrama de Gantt (Corte Láser)")
        st.markdown("👇 **Asigna las fechas de inicio, duraciones y estados para cada Orden de Fabricación (OF).**")
        
        import datetime
        from utils.database import get_connection, save_db_to_excel, sync_and_push_db
        
        conn = get_connection()
        # 1. Obtener la cantidad de piezas total por cada OF
        df_pzs = pd.read_sql_query("""
            SELECT p.of_number, SUM(p.cantidad * n.hojas) as total_piezas
            FROM piezas p
            JOIN nidos n ON p.of_number = n.of_number AND p.nido = n.nido
            GROUP BY p.of_number
        """, conn)
        
        # 2. Obtener los datos de planificación de la tabla ordenes
        df_ordenes_gantt = pd.read_sql_query("""
            SELECT of_number, gantt_inicio, gantt_dias, gantt_avance
            FROM ordenes
        """, conn)
        
        # 3. Calcular avance real en Corte (hojas cortadas / total hojas de cada OF)
        df_total_hojas = pd.read_sql_query("SELECT of_number, SUM(hojas) as total_hojas FROM nidos GROUP BY of_number", conn)
        df_cortadas = pd.read_sql_query("""
            SELECT of_number, COUNT(DISTINCT nido || '||' || hoja) as hojas_cortadas 
            FROM avances 
            WHERE area = 'Corte' AND hoja IS NOT NULL
            GROUP BY of_number
        """, conn)
        conn.close()
        
        total_hojas_map = df_total_hojas.set_index("of_number")["total_hojas"].to_dict()
        cortadas_map = df_cortadas.set_index("of_number")["hojas_cortadas"].to_dict()
        
        pct_map = {}
        for of_id in df_ordenes_gantt["of_number"]:
            tot_h = total_hojas_map.get(of_id, 0)
            cort_h = cortadas_map.get(of_id, 0)
            pct_map[of_id] = (cort_h / tot_h * 100) if tot_h > 0 else 0.0
        
        if df_ordenes_gantt.empty:
            st.info("⚠️ No se encontraron Órdenes de Fabricación cargadas en el sistema.")
        else:
            df_prog = df_ordenes_gantt.merge(df_pzs, on="of_number", how="left")
            df_prog["total_piezas"] = df_prog["total_piezas"].fillna(0).astype(int)
            
            # Formatear columnas
            df_prog["INICIO"] = pd.to_datetime(df_prog["gantt_inicio"], errors='coerce').dt.date
            # Si es nulo, usar la fecha de hoy por defecto
            df_prog["INICIO"] = df_prog["INICIO"].fillna(datetime.date.today())
            df_prog["DIAS"] = df_prog["gantt_dias"].fillna(1).astype(int)
            df_prog["AVANCE"] = df_prog["gantt_avance"].fillna("PENDIENTE").astype(str)
            
            # Calcular columna FINAL APROXIMADO
            def calc_final(row):
                if pd.isna(row["INICIO"]):
                    return None
                return (pd.to_datetime(row["INICIO"]) + pd.to_timedelta(row["DIAS"], unit='D')).date()
                
            df_prog["FINAL APROXIMADO"] = df_prog.apply(calc_final, axis=1)
            
            df_display = df_prog[["of_number", "total_piezas", "INICIO", "DIAS", "FINAL APROXIMADO", "AVANCE"]].copy()
            df_display.rename(columns={
                "of_number": "ORDENES DE FABRICACION",
                "total_piezas": "CANTIDAD PZS."
            }, inplace=True)
            
            # Agregar avance real calculado en base a hojas físicas con formato condicional visual (emoji)
            def get_avance_real_emoji(of_id):
                pct = pct_map.get(of_id, 0.0)
                if pct >= 100.0:
                    return f"🟢 {pct:.1f}%"
                elif pct > 0.0:
                    return f"🟡 {pct:.1f}%"
                else:
                    return f"⚪ {pct:.1f}%"
            
            df_display["AVANCE REAL (CORTE)"] = df_display["ORDENES DE FABRICACION"].map(get_avance_real_emoji)
            
            # Reordenar columnas para posicionar el Avance Real visiblemente
            df_display = df_display[[
                "ORDENES DE FABRICACION", "CANTIDAD PZS.", "INICIO", "DIAS", 
                "FINAL APROXIMADO", "AVANCE REAL (CORTE)", "AVANCE"
            ]]
            
            # Configurar columnas del data_editor
            column_config = {
                "ORDENES DE FABRICACION": st.column_config.TextColumn(
                    "ORDENES DE FABRICACION", 
                    disabled=True, 
                    help="Código único de la Orden de Fabricación."
                ),
                "CANTIDAD PZS.": st.column_config.NumberColumn(
                    "CANTIDAD PZS.", 
                    disabled=True, 
                    help="Suma total de piezas programadas en esta OF."
                ),
                "INICIO": st.column_config.DateColumn(
                    "📅 Fecha de Inicio", 
                    required=True, 
                    format="DD/MM/YYYY",
                    help="Haz doble clic para abrir el calendario interactivo y seleccionar la fecha de inicio."
                ),
                "DIAS": st.column_config.NumberColumn(
                    "⏳ Días de Duración", 
                    min_value=1, 
                    step=1, 
                    required=True,
                    help="Número de días estimados para realizar el corte."
                ),
                "FINAL APROXIMADO": st.column_config.DateColumn(
                    "🏁 Fin Aproximado", 
                    disabled=True, 
                    format="DD/MM/YYYY",
                    help="Fecha estimada de finalización calculada automáticamente."
                ),
                "AVANCE REAL (CORTE)": st.column_config.TextColumn(
                    "📊 Avance Físico Corte", 
                    disabled=True,
                    help="Porcentaje real del proceso de corte basado en hojas físicas cortadas."
                ),
                "AVANCE": st.column_config.SelectboxColumn(
                    "🔔 Estado Manual",
                    options=["PENDIENTE", "100%", "SE REPROGRAMA FECHA", "PROCESO 1RA. PARTE"],
                    required=True,
                    help="Estado general asignado de forma manual."
                )
            }
            
            # Mostrar editor de datos
            df_edited = st.data_editor(
                df_display,
                column_config=column_config,
                hide_index=True,
                use_container_width=True,
                key="gantt_scheduler_editor"
            )
            
            # Botón de guardar cambios
            if st.button("💾 Guardar Plan de Corte", type="primary", key="save_gantt_plan_btn", use_container_width=True):
                conn = get_connection()
                c = conn.cursor()
                for idx, row in df_edited.iterrows():
                    of_id = row["ORDENES DE FABRICACION"]
                    inicio_str = row["INICIO"].strftime("%Y-%m-%d") if row["INICIO"] else None
                    dias_val = int(row["DIAS"])
                    avance_val = str(row["AVANCE"])
                    
                    c.execute("""
                        UPDATE ordenes 
                        SET gantt_inicio = ?, gantt_dias = ?, gantt_avance = ?
                        WHERE of_number = ?
                    """, (inicio_str, dias_val, avance_val, of_id))
                conn.commit()
                conn.close()
                
                # Sincronizar Excel y GitHub
                save_db_to_excel()
                sync_and_push_db()
                st.success("✅ ¡Plan de corte guardado y sincronizado con éxito!")
                st.rerun()
                
            # 3. Dibujar el Diagrama de Gantt
            st.markdown("---")
            
            gantt_data = []
            for idx, row in df_edited.iterrows():
                if row["INICIO"] and row["DIAS"]:
                    start_date = pd.to_datetime(row["INICIO"])
                    finish_date = start_date + pd.to_timedelta(int(row["DIAS"]), unit='D')
                    of_id = row["ORDENES DE FABRICACION"]
                    real_pct = pct_map.get(of_id, 0.0)
                    
                    # Formato condicional automático para el Gantt según avance real
                    if real_pct >= 100.0:
                        color_category = "Completado (100%)"
                        dias_label = f"{int(row['DIAS'])} días (Completado)"
                    elif real_pct > 0.0:
                        color_category = "En Proceso (1%-99%)"
                        dias_label = f"{int(row['DIAS'])} días ({real_pct:.0f}% avance)"
                    else:
                        color_category = "Pendiente (0%)"
                        dias_label = f"{int(row['DIAS'])} días (Pendiente)"
                    
                    gantt_data.append({
                        "OF": of_id,
                        "Start": start_date,
                        "Finish": finish_date,
                        "Estado Real": color_category,
                        "Dias": dias_label
                    })
                    
            if gantt_data:
                df_gantt = pd.DataFrame(gantt_data)
                
                color_map = {
                    "Completado (100%)": "#28a745",    # Verde
                    "En Proceso (1%-99%)": "#ffc107",  # Amarillo
                    "Pendiente (0%)": "#6c757d"        # Gris
                }
                
                import plotly.express as px
                fig = px.timeline(
                    df_gantt,
                    x_start="Start",
                    x_end="Finish",
                    y="OF",
                    color="Estado Real",
                    text="Dias",
                    color_discrete_map=color_map,
                    title="DIAGRAMA DE GANTT CORTE LASER"
                )
                
                fig.update_yaxes(autorange="reversed")  # Invertir eje Y para mantener el orden de la tabla
                fig.update_layout(
                    plot_bgcolor="#ffffff",
                    paper_bgcolor="#ffffff",
                    font_color="#222222",
                    title_font_size=20,
                    title_x=0.5,
                    margin=dict(l=10, r=10, t=60, b=60),
                    showlegend=True,
                    legend_title_text="Estado Real de Avance"
                )
                fig.update_xaxes(
                    tickformat="%d/%m/%Y",
                    gridcolor="#e9ecef",
                    linecolor="#cccccc",
                    tickfont=dict(color="#333333")
                )
                fig.update_traces(
                    textposition="auto",
                    textfont=dict(size=12, family="sans-serif")
                )
                
                st.plotly_chart(fig, use_container_width=True)

    with tab_carga:
        st.markdown("### 📋 Paso 1: Cargar Plan de Producción")

        col_dl, col_info = st.columns([1, 2])
        with col_dl:
            try:
                plantilla_data = generar_plantilla()
                st.download_button(
                    label="📥 Descargar Plantilla Excel",
                    data=plantilla_data,
                    file_name="Plantilla_Plan_Produccion_SIGRAMA.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            except Exception as ex:
                st.error(f"Error generando plantilla: {ex}")
        with col_info:
            with st.expander("ℹ️ Formato requerido del Excel"):
                st.markdown("""
                El archivo debe contener **exactamente 3 hojas**:
                1. **Orden**: Fila 1 Títulos, Fila 2 Datos (Nombre del Proyecto, Fecha, Programador, Orden de Fabricación, PO, PRIORIDAD, CALIBRE).
                2. **Nidos**: Columnas NIDO, HOJAS.
                3. **Piezas**: Columnas NIDO, No. PIEZA, NOMBRE DE PIEZA, CANTIDAD, RUTA (Opcional).
                
                *Nota: La columna RUTA permite definir procesos específicos separados por comas (Ej: Corte, Barrenado, Pintura). Si se omite, se usará la ruta completa por defecto.*
                """)

        uploaded_file = st.file_uploader(
            "Sube el Plan de Producción (Excel) *",
            type=["xlsx", "xls"],
            key="uploaded_excel"
        )

        if uploaded_file is not None:
            if st.button("🔍 Analizar Archivo", type="primary"):
                try:
                    # Leer las 3 pestañas
                    df_orden  = pd.read_excel(uploaded_file, sheet_name=0, header=0)
                    df_nidos  = pd.read_excel(uploaded_file, sheet_name=1, header=0)
                    df_piezas = pd.read_excel(uploaded_file, sheet_name=2, header=0)

                    # Extraer info de Orden
                    if df_orden.empty:
                        st.error("❌ La hoja 'Orden' está vacía o no tiene la fila de datos.")
                        st.stop()
                    
                    # Obtener columnas seguras (ignorando mayúsculas/minúsculas)
                    def get_val(df, col_keywords, is_date=False):
                        for c in df.columns:
                            if any(k in str(c).upper() for k in col_keywords):
                                val = df[c].iloc[0]
                                if is_date:
                                    try:
                                        if str(val).replace('.', '').isdigit():
                                            dt = pd.to_datetime(float(val), unit='D', origin='1899-12-30')
                                            return dt.strftime('%Y-%m-%d')
                                        else:
                                            return pd.to_datetime(val).strftime('%Y-%m-%d')
                                    except:
                                        pass
                                return str(val).strip()
                        return "No encontrado"

                    def clean_val(v):
                        return "" if v == "No encontrado" else v

                    proy = get_val(df_orden, ['PROYECTO'])
                    prog = get_val(df_orden, ['PROGRAMADOR'])
                    fecha = get_val(df_orden, ['FECHA'], is_date=True)
                    of_num = get_val(df_orden, ['ORDEN DE FABRICAC', 'OF'])
                    
                    po = clean_val(get_val(df_orden, ['PO']))
                    desc_pronest = clean_val(get_val(df_orden, ['DESCRIPCION DE OF PRONEST', 'DESCRIPCIÓN DE OF PRONEST', 'PRONEST']))
                    calibre_of = clean_val(get_val(df_orden, ['CALIBRE']))
                    prioridad = clean_val(get_val(df_orden, ['PRIORIDAD']))
                    proy_cliente = clean_val(get_val(df_orden, ['NOMBRE DEL PROYECTO DE CLIENTE', 'PROYECTO DE CLIENTE', 'PROYECTO CLIENTE']))

                    # Normalizar NIDO y limpiar filas vacías
                    df_nidos = df_nidos.dropna(how='all')
                    df_piezas = df_piezas.dropna(how='all')
                    for df in [df_nidos, df_piezas]:
                        col_n = next((c for c in df.columns if 'NIDO' in str(c).upper()), None)
                        if col_n:
                            df[col_n] = df[col_n].apply(normalizar_nido)
                            df.dropna(subset=[col_n], inplace=True)

                    st.session_state.temp_production_data = {
                        "proyecto":            proy,
                        "programador":         prog,
                        "fecha":               fecha,
                        "of_number":           of_num,
                        "po":                  po,
                        "descripcion_pronest": desc_pronest,
                        "calibre":             calibre_of,
                        "prioridad":           prioridad,
                        "proyecto_cliente":    proy_cliente,
                        "nidos":               df_nidos.astype(str),
                        "piezas":              df_piezas.astype(str)
                    }
                except Exception as e:
                    st.error(f"Error procesando el Excel: {str(e)}")

        # ── AUDITORÍA DE DATOS TEMP ──────────────────────────────────────
        if st.session_state.temp_production_data is not None:
            st.markdown("---")
            st.subheader("🕵️ Auditoría de Datos (Pre-Carga)")
            data = st.session_state.temp_production_data

            errores = []
            if data['of_number'] == "No encontrado" or not data['of_number']:
                errores.append("No se encontró 'Orden de Fabricación' válida en la hoja 1.")
            if data['of_number'] == st.session_state.of_number:
                errores.append(f"La OF {data['of_number']} ya está cargada actualmente en el sistema.")

            df_n = data['nidos']
            df_p = data['piezas']
            col_n_nido = next((c for c in df_n.columns if 'NIDO' in str(c).upper()), None)
            col_p_nido = next((c for c in df_p.columns if 'NIDO' in str(c).upper()), None)

            if not col_n_nido: errores.append("Falta columna 'NIDO' en la hoja Nidos.")
            if not col_p_nido: errores.append("Falta columna 'NIDO' en la hoja Piezas.")

            df_totales = pd.DataFrame()
            if not errores:
                nidos_n = set(df_n[col_n_nido].dropna().unique())
                nidos_p = set(df_p[col_p_nido].dropna().unique())

                if nidos_n != nidos_p:
                    faltantes_p = nidos_n - nidos_p
                    faltantes_n = nidos_p - nidos_n
                    if faltantes_p: errores.append(f"Los nidos {faltantes_p} están en la hoja 'Nidos' pero NO en 'Piezas'.")
                    if faltantes_n: errores.append(f"Los nidos {faltantes_n} están en la hoja 'Piezas' pero NO en 'Nidos'.")

                df_totales = calcular_totales(df_n, df_p)
                if df_totales.empty:
                    errores.append("No se pudieron cruzar Nidos y Piezas correctamente para calcular totales.")

            if not errores:
                st.success("✅ **¡Todo correcto!** Los datos cuadran perfectamente.")
                
                # --- PREVISUALIZACIÓN DE PRE-CARGA ---
                with st.expander("🔍 Previsualizar Registros a Cargar (Nidos y Piezas)", expanded=True):
                    st.info("Los siguientes datos se guardarán en la base de datos para la nueva OF:")
                    
                    t1, t2, t3 = st.tabs(["🗂️ Nidos (Pre-Carga)", "🔩 Piezas (Pre-Carga)", "📊 Totales Calculados"])
                    with t1:
                        st.dataframe(df_n, use_container_width=True, height=250)
                    with t2:
                        st.dataframe(df_p, use_container_width=True, height=250)
                    with t3:
                        if not df_totales.empty:
                            st.caption("Fórmula: Cantidad × Hojas (repeticiones) = Total real a fabricar")
                            st.dataframe(df_totales, use_container_width=True, height=250)
                            try:
                                total_precarga = int(pd.to_numeric(df_totales['CANTIDAD * REPETICION'], errors='coerce').sum())
                                st.markdown(f"🔢 Total de piezas estimadas a cargar: **`{total_precarga}`**")
                            except Exception:
                                pass
                
                if st.button("🚀 Confirmar y Cargar a Base de Datos", type="primary", use_container_width=True):
                    # Guardar en SQLite
                    save_production_plan(
                        of_number=data['of_number'],
                        proyecto=data['proyecto'],
                        programador=data['programador'],
                        fecha=data['fecha'],
                        df_nidos=df_n,
                        df_piezas=df_p,
                        po=data.get('po', ''),
                        descripcion_pronest=data.get('descripcion_pronest', ''),
                        calibre=data.get('calibre', ''),
                        prioridad=data.get('prioridad', ''),
                        proyecto_cliente=data.get('proyecto_cliente', '')
                    )
                    
                    st.session_state.production_data = {
                        "proyecto":            data['proyecto'],
                        "programador":         data['programador'],
                        "fecha":               data['fecha'],
                        "po":                  data.get('po', ''),
                        "descripcion_pronest": data.get('descripcion_pronest', ''),
                        "calibre":             data.get('calibre', ''),
                        "prioridad":           data.get('prioridad', ''),
                        "proyecto_cliente":    data.get('proyecto_cliente', ''),
                        "nidos":               df_n,
                        "piezas":              df_p,
                        "totales":             df_totales,
                    }
                    st.session_state.of_number = data['of_number']
                    
                    # Limpiar temp state
                    del st.session_state['temp_production_data']
                    
                    st.success(f"✅ ¡Orden {data['of_number']} cargada correctamente!")
                    st.balloons()
                    st.rerun()
            else:
                for err in errores:
                    st.error(f"❌ {err}")

        # ── RESUMEN DE LA OF CARGADA ─────────────────────────────────────
        if st.session_state.production_data is not None:
            st.markdown("---")
            data = st.session_state.production_data
            st.subheader(f"📌 Resumen de la OF Activa: {st.session_state.of_number}")

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Proyecto",    data.get('proyecto', '—'))
            c2.metric("Programador", data.get('programador', '—'))
            c3.metric("Fecha",       data.get('fecha', '—'))
            c4.metric("PO",          data.get('po', '—'))
            
            c1_b, c2_b, c3_b, c4_b = st.columns(4)
            c1_b.metric("Prioridad",   data.get('prioridad', '—'))
            c2_b.metric("Calibre OF",   data.get('calibre', '—'))
            c3_b.metric("Proyecto Cliente", data.get('proyecto_cliente', '—'))
            c4_b.metric("Descripción Pronest", data.get('descripcion_pronest', '—'))

            df_t = data.get('totales', pd.DataFrame())
            if not df_t.empty and 'CANTIDAD * REPETICION' in df_t.columns:
                try:
                    total_rep = int(pd.to_numeric(df_t['CANTIDAD * REPETICION'], errors='coerce').sum())
                    total_nidos = df_t['NIDO'].nunique() if 'NIDO' in df_t.columns else "—"
                    c1.metric("Total Nidos",   total_nidos)
                    c3.metric("Total Piezas (con repetición)", total_rep)
                except Exception:
                    pass

            tab1, tab2, tab3 = st.tabs(["🗂️ Nidos", "🔩 Piezas", "📊 Totales (Auto)"])
            with tab1:
                st.dataframe(data['nidos'], use_container_width=True, height=350)
            with tab2:
                st.dataframe(data['piezas'], use_container_width=True, height=350)
            with tab3:
                if not df_t.empty:
                    st.caption("Cantidad × Hojas (repeticiones) = Total real a fabricar")
                    st.dataframe(df_t, use_container_width=True, height=400)
                    if 'CANTIDAD * REPETICION' in df_t.columns:
                        total = int(pd.to_numeric(df_t['CANTIDAD * REPETICION'], errors='coerce').sum())
                        st.markdown(f"### 🔢 Total de piezas a fabricar: `{total}`")
                else:
                    st.warning("No se pudo calcular Totales.")

    with tab_rutas:
        st.markdown("### 🛣️ Paso 2: Selección Dinámica de Procesos (Rutas)")
        from utils.database import get_all_ofs
        all_ofs_list = get_all_ofs()
        if all_ofs_list:
            default_idx = 0
            if active_of is not None and active_of['of_number'] in all_ofs_list:
                default_idx = all_ofs_list.index(active_of['of_number'])
            
            of_number = st.selectbox(
                "🔍 Selecciona la Orden de Fabricación (OF) a configurar:",
                all_ofs_list,
                index=default_idx,
                key="route_config_of_selector"
            )
            df_todas = get_todas_piezas(of_number)
            
            if not df_todas.empty:
                st.markdown("👇 **Selecciona qué procesos requiere cada pieza.** Al guardar, el sistema enrutará las piezas dinámicamente.")
                
                if st.session_state.get('rutas_guardadas'):
                    st.success(f"✅ ¡Se guardaron las rutas de {st.session_state['rutas_guardadas']} piezas exitosamente en la Base de Datos!")
                    del st.session_state['rutas_guardadas']
                
                # Crear dataframe booleano para la tabla editable
                # Como la ruta es por NO. PIEZA (no por nido), agrupamos
                df_rutas = df_todas[['no_pieza', 'nombre_pieza', 'ruta']].drop_duplicates(subset=['no_pieza']).copy()
                
                # Crear columnas booleanas por cada proceso
                def is_proc_checked(proc, ruta_str):
                    if pd.isna(ruta_str) or not str(ruta_str).strip() or str(ruta_str).lower() in ['nan', 'none']:
                        return proc != "Barrenado"
                    return proc in str(ruta_str).split(', ')

                for proc in PROCESSES:
                    df_rutas[proc] = df_rutas['ruta'].apply(lambda x: is_proc_checked(proc, x))
                
                # Botones de selección masiva global
                col_glob1, col_glob2 = st.columns(2)
                if col_glob1.button("✅ Habilitar TODOS los procesos a TODAS las piezas", use_container_width=True):
                    st.session_state['check_global'] = True
                if col_glob2.button("❌ Quitar TODOS los procesos a TODAS las piezas", use_container_width=True):
                    st.session_state['uncheck_global'] = True
                    
                st.markdown("---")

                # Botones de selección masiva por proceso
                col_sel1, col_sel2, col_sel3 = st.columns([1, 1, 2])
                proc_masivo = col_sel1.selectbox("Proceso a modificar masivamente:", PROCESSES)
                if col_sel2.button(f"✅ Habilitar {proc_masivo} a TODAS"):
                    st.session_state[f'check_all_{proc_masivo}'] = True
                if col_sel3.button(f"❌ Quitar {proc_masivo} a TODAS"):
                    st.session_state[f'uncheck_all_{proc_masivo}'] = True
                    
                # Aplicar modificaciones masivas al dataframe antes de mostrarlo
                if st.session_state.get('check_global', False):
                    for proc in PROCESSES: df_rutas[proc] = True
                    st.session_state['check_global'] = False
                
                if st.session_state.get('uncheck_global', False):
                    for proc in PROCESSES: df_rutas[proc] = False
                    st.session_state['uncheck_global'] = False

                for proc in PROCESSES:
                    if st.session_state.get(f'check_all_{proc}', False):
                        df_rutas[proc] = True
                        st.session_state[f'check_all_{proc}'] = False # reset
                    if st.session_state.get(f'uncheck_all_{proc}', False):
                        df_rutas[proc] = False
                        st.session_state[f'uncheck_all_{proc}'] = False # reset
                
                # Preparar configuración de columnas
                column_config = {
                    "no_pieza": st.column_config.TextColumn("No. Pieza", disabled=True),
                    "nombre_pieza": st.column_config.TextColumn("Descripción", disabled=True),
                    "ruta": None # Ocultar columna texto cruda
                }
                
                # Mostrar editor
                df_editado = st.data_editor(
                    df_rutas,
                    column_config=column_config,
                    hide_index=True,
                    use_container_width=True,
                    height=500
                )
                
                if st.button("💾 Guardar Rutas Seleccionadas", type="primary"):
                    actualizaciones = []
                    for idx, row in df_editado.iterrows():
                        ruta_lista = [proc for proc in PROCESSES if row[proc]]
                        ruta_str = ", ".join(ruta_lista)
                        
                        # Solo actualizar si cambió
                        if ruta_str != str(row['ruta']):
                            actualizaciones.append({
                                'no_pieza': row['no_pieza'],
                                'ruta': ruta_str
                            })
                    
                    if actualizaciones:
                        update_ruta_piezas(of_number, actualizaciones)
                        st.session_state['rutas_guardadas'] = len(actualizaciones)
                        st.rerun()
                    else:
                        st.info("No hubo cambios en las rutas para guardar. Todo está al día.")
            else:
                st.warning("No se encontraron piezas para esta OF.")
        else:
            st.info("⚠️ Primero debes Cargar y Confirmar un Plan de Producción en la pestaña '3.1 CARGA'.")



    # Fin de view_planeacion
    pass

def view_produccion():
    st.title("4. CONTROL DE PRODUCCIÓN")

    active_of = get_active_of()

    if active_of is not None:
        view_avances()
    else:
        st.info("⚠️ Primero debes Cargar y Confirmar un Plan de Producción en el menú de 'Planeación'.")
