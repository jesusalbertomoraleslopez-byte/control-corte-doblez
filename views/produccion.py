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
    tab_carga, tab_rutas = st.tabs([
        "📤 3.1 CARGA", 
        "🛣️ 3.2 SELECCIÓN DE PROCESOS"
    ])

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
        if active_of is not None:
            of_number = active_of['of_number']
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

    # ══════════════════════════════════════════════════════════
    # ZONA DE LIMPIEZA — SIEMPRE VISIBLE
    # ══════════════════════════════════════════════════════════
    st.markdown("""
    <div style="background:#FFF3CD; border:2px solid #EC2024; border-radius:8px;
                padding:12px 18px; margin-bottom:12px;">
      <b style="color:#111111; font-size:16px;">🗑️ Limpieza de Registros / Nueva Orden de Fabricación</b>
    </div>
    """, unsafe_allow_html=True)

    col_estado, col_btn = st.columns([3, 1])
    with col_estado:
        if active_of:
            proj_client_info = f" | Cliente: {active_of.get('proyecto_cliente')}" if active_of.get('proyecto_cliente') else ""
            st.warning(
                f"⚠️ OF Activa: **{active_of['of_number']}** — "
                f"Proyecto: **{active_of['proyecto']}**{proj_client_info}"
            )
        else:
            st.info("ℹ️ No hay registros activos.")
    with col_btn:
        if st.button("🗑️ Limpiar todos los registros", type="primary", use_container_width=True):
            if 'temp_production_data' in st.session_state: del st.session_state['temp_production_data']
            reset_of()

    st.markdown("---")

    tab_avances, tab_correccion, tab_reportes = st.tabs([
        "📝 4.1 AVANCES POR ÁREA", 
        "✏️ 4.2 CORRECCIONES", 
        "📊 4.3 REPORTES"
    ])

    with tab_avances:
        if active_of is not None:
            view_avances()
        else:
            st.info("⚠️ Primero debes Cargar y Confirmar un Plan de Producción en el menú de 'Planeación'.")
            
    with tab_correccion:
        if active_of is not None:
            view_correcciones()
        else:
            st.info("⚠️ Primero debes Cargar y Confirmar un Plan de Producción en el menú de 'Planeación'.")
            
    with tab_reportes:
        if active_of is not None:
            view_reportes()
        else:
            st.info("⚠️ Primero debes Cargar y Confirmar un Plan de Producción en el menú de 'Planeación'.")
