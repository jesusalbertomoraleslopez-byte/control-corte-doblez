import streamlit as st
import pandas as pd
import plotly.express as px
from utils.database import get_connection, get_todas_piezas, get_nidos, get_all_ofs
from views.avances import PROCESSES

def get_area_anterior(ruta_str, current_area):
    if pd.isna(ruta_str): return None
    procesos = str(ruta_str).split(', ')
    if current_area in procesos:
        idx = procesos.index(current_area)
        if idx > 0:
            return procesos[idx - 1]
    return None

def calculate_global_wip(of_number):
    df_todas = get_todas_piezas(of_number)
    if df_todas.empty:
        return {}

    conn = get_connection()
    if of_number == "Todas" or of_number is None:
        df_avances_all = pd.read_sql_query("SELECT no_pieza, area, SUM(cantidad) as cantidad FROM avances GROUP BY no_pieza, area", conn)
        df_rechazos_all = pd.read_sql_query("SELECT no_pieza, area, SUM(cantidad) as cantidad FROM rechazos GROUP BY no_pieza, area", conn)
    else:
        df_avances_all = pd.read_sql_query("SELECT no_pieza, area, SUM(cantidad) as cantidad FROM avances WHERE of_number=? GROUP BY no_pieza, area", conn, params=(of_number,))
        df_rechazos_all = pd.read_sql_query("SELECT no_pieza, area, SUM(cantidad) as cantidad FROM rechazos WHERE of_number=? GROUP BY no_pieza, area", conn, params=(of_number,))
    conn.close()
    
    if 'hojas' not in df_todas.columns:
        df_todas['hojas'] = 1
    
    df_todas['total_requeridas'] = df_todas['cantidad'] * df_todas['hojas']
    
    wip_por_area = {}
    
    for area in PROCESSES:
        if area == "Ingenieria":
            wip_por_area[area] = 0 # Omitido para simplicidad visual
            continue
            
        if area == "Corte":
            conn = get_connection()
            c = conn.cursor()
            if of_number == "Todas" or of_number is None:
                c.execute("SELECT DISTINCT of_number, nido FROM avances WHERE area = 'Corte'")
                terminados_tuples = set((row[0], row[1]) for row in c.fetchall())
                # Filtramos usando un MultiIndex para mayor precisión
                # Conservamos las filas donde (of_number, nido) NO está en terminados_tuples
                if not df_todas.empty:
                    df_corte_pend = df_todas[~df_todas.apply(lambda row: (row['of_number'], row['nido']) in terminados_tuples, axis=1)]
                else:
                    df_corte_pend = df_todas
            else:
                c.execute("SELECT DISTINCT nido FROM avances WHERE of_number = ? AND area = 'Corte'", (of_number,))
                terminados = [row[0] for row in c.fetchall()]
                df_corte_pend = df_todas[~df_todas['nido'].isin(terminados)]
            conn.close()
            
            wip_por_area[area] = int(df_corte_pend['total_requeridas'].sum()) if not df_corte_pend.empty else 0
            continue
            
        # Post corte
        df_piezas = df_todas.copy()
        df_piezas['pasa_por_aqui'] = df_piezas['ruta'].apply(lambda x: area in str(x).split(', '))
        df_piezas = df_piezas[df_piezas['pasa_por_aqui']]
        
        if df_piezas.empty:
            wip_por_area[area] = 0
            continue
            
        df_piezas['area_anterior'] = df_piezas['ruta'].apply(lambda x: get_area_anterior(x, area))
        df_agrupado = df_piezas.groupby('no_pieza').agg({
            'total_requeridas': 'sum',
            'area_anterior': 'first'
        }).reset_index()
        
        def get_wip(row):
            area_ant = row['area_anterior']
            if pd.isna(area_ant) or not area_ant: return 0
            wip = df_avances_all[(df_avances_all['no_pieza'] == row['no_pieza']) & (df_avances_all['area'] == area_ant)]['cantidad'].sum()
            return int(wip)
            
        def get_terminadas_ant(row):
            term = df_avances_all[(df_avances_all['no_pieza'] == row['no_pieza']) & (df_avances_all['area'] == area)]['cantidad'].sum()
            return int(term)
            
        def get_rechazadas_ant(row):
            rech = df_rechazos_all[(df_rechazos_all['no_pieza'] == row['no_pieza']) & (df_rechazos_all['area'] == area)]['cantidad'].sum()
            return int(rech)
            
        df_agrupado['wip'] = df_agrupado.apply(get_wip, axis=1)
        df_agrupado['term'] = df_agrupado.apply(get_terminadas_ant, axis=1)
        df_agrupado['rech'] = df_agrupado.apply(get_rechazadas_ant, axis=1)
        
        df_agrupado['pendiente_disp'] = df_agrupado['wip'] - df_agrupado['term'] - df_agrupado['rech']
        df_agrupado['pendiente_disp'] = df_agrupado['pendiente_disp'].apply(lambda x: max(0, x))
        
        df_agrupado['pendiente_of'] = df_agrupado['total_requeridas'] - df_agrupado['term'] - df_agrupado['rech']
        df_agrupado = df_agrupado[df_agrupado['pendiente_of'] > 0]
        
        wip_por_area[area] = int(df_agrupado['pendiente_disp'].sum())
        
    return wip_por_area

def get_global_wip_for_ofs(of_list):
    total_wip = {p: 0 for p in PROCESSES if p != "Ingenieria"}
    
    # If list is empty, return 0s
    if not of_list:
        return total_wip
        
    # calculate_global_wip already supports "Todas"
    if "Todas" in of_list:
        return calculate_global_wip("Todas")
        
    for of_num in of_list:
        wip = calculate_global_wip(of_num)
        for k, v in wip.items():
            total_wip[k] = total_wip.get(k, 0) + v
    return total_wip

def get_wip_pieces_detail(of_list, area):
    details = []
    
    # Si viene "Todas", expandir a todas las OFs en la base de datos
    if "Todas" in of_list:
        of_list = get_all_ofs()
        
    for of_num in of_list:
        df_todas = get_todas_piezas(of_num)
        if df_todas.empty:
            continue
            
        conn = get_connection()
        df_avances_all = pd.read_sql_query("SELECT no_pieza, area, SUM(cantidad) as cantidad FROM avances WHERE of_number=? GROUP BY no_pieza, area", conn, params=(of_num,))
        df_rechazos_all = pd.read_sql_query("SELECT no_pieza, area, SUM(cantidad) as cantidad FROM rechazos WHERE of_number=? GROUP BY no_pieza, area", conn, params=(of_num,))
        conn.close()
        
        if 'hojas' not in df_todas.columns:
            df_todas['hojas'] = 1
        
        df_todas['total_requeridas'] = pd.to_numeric(df_todas['cantidad'], errors='coerce').fillna(0) * pd.to_numeric(df_todas['hojas'], errors='coerce').fillna(1)
        
        if area == "Corte":
            conn = get_connection()
            c = conn.cursor()
            c.execute("SELECT DISTINCT nido FROM avances WHERE of_number = ? AND area = 'Corte'", (of_num,))
            terminados = [row[0] for row in c.fetchall()]
            conn.close()
            
            df_corte_pend = df_todas[~df_todas['nido'].isin(terminados)]
            if not df_corte_pend.empty:
                df_g = df_corte_pend.groupby(['no_pieza', 'nombre_pieza'])['total_requeridas'].sum().reset_index()
                df_g['of_number'] = of_num
                df_g.rename(columns={'total_requeridas': 'cantidad_wip'}, inplace=True)
                details.append(df_g)
        else:
            df_piezas = df_todas.copy()
            df_piezas['pasa_por_aqui'] = df_piezas['ruta'].apply(lambda x: area in str(x).split(', '))
            df_piezas = df_piezas[df_piezas['pasa_por_aqui']]
            
            if df_piezas.empty:
                continue
                
            df_piezas['area_anterior'] = df_piezas['ruta'].apply(lambda x: get_area_anterior(x, area))
            df_agrupado = df_piezas.groupby(['no_pieza', 'nombre_pieza']).agg({
                'total_requeridas': 'sum',
                'area_anterior': 'first'
            }).reset_index()
            
            def get_wip(row):
                area_ant = row['area_anterior']
                if pd.isna(area_ant) or not area_ant: return 0
                wip = df_avances_all[(df_avances_all['no_pieza'] == row['no_pieza']) & (df_avances_all['area'] == area_ant)]['cantidad'].sum()
                return int(wip)
                
            def get_terminadas_ant(row):
                term = df_avances_all[(df_avances_all['no_pieza'] == row['no_pieza']) & (df_avances_all['area'] == area)]['cantidad'].sum()
                return int(term)
                
            def get_rechazadas_ant(row):
                rech = df_rechazos_all[(df_rechazos_all['no_pieza'] == row['no_pieza']) & (df_rechazos_all['area'] == area)]['cantidad'].sum()
                return int(rech)
                
            df_agrupado['wip'] = df_agrupado.apply(get_wip, axis=1)
            df_agrupado['term'] = df_agrupado.apply(get_terminadas_ant, axis=1)
            df_agrupado['rech'] = df_agrupado.apply(get_rechazadas_ant, axis=1)
            
            df_agrupado['pendiente_disp'] = df_agrupado['wip'] - df_agrupado['term'] - df_agrupado['rech']
            df_agrupado['pendiente_disp'] = df_agrupado['pendiente_disp'].apply(lambda x: max(0, x))
            
            df_g = df_agrupado[df_agrupado['pendiente_disp'] > 0][['no_pieza', 'nombre_pieza', 'pendiente_disp']].copy()
            if not df_g.empty:
                df_g['of_number'] = of_num
                df_g.rename(columns={'pendiente_disp': 'cantidad_wip'}, inplace=True)
                details.append(df_g)
                
    if not details:
        return pd.DataFrame(columns=['OF', 'No. Pieza', 'Descripción', 'Cantidad WIP'])
        
    df_res = pd.concat(details, ignore_index=True)
    df_res.rename(columns={
        'of_number': 'OF',
        'no_pieza': 'No. Pieza',
        'nombre_pieza': 'Descripción',
        'cantidad_wip': 'Cantidad WIP'
    }, inplace=True)
    
    df_res = df_res[['OF', 'No. Pieza', 'Descripción', 'Cantidad WIP']]
    df_res['Cantidad WIP'] = df_res['Cantidad WIP'].astype(int)
    return df_res

def style_excel_sheet(writer, df, sheet_name):
    workbook = writer.book
    worksheet = writer.sheets[sheet_name]
    
    header_format = workbook.add_format({
        'bold': True,
        'text_wrap': True,
        'valign': 'vcenter',
        'align': 'center',
        'fg_color': '#EC2024', # Rojo SIGRAMA
        'font_color': '#FFFFFF', # Blanco
        'font_name': 'Arial',
        'font_size': 10,
        'border': 1,
        'border_color': '#B0B0B0'
    })
    
    cell_format = workbook.add_format({
        'font_name': 'Arial',
        'font_size': 9,
        'border': 1,
        'border_color': '#D3D3D3',
        'valign': 'vcenter'
    })
    
    number_format = workbook.add_format({
        'font_name': 'Arial',
        'font_size': 9,
        'border': 1,
        'border_color': '#D3D3D3',
        'valign': 'vcenter',
        'align': 'right'
    })
    
    worksheet.hide_gridlines(2) # 2 = show on screen and when printing
    
    for col_num, col_name in enumerate(df.columns):
        worksheet.write(0, col_num, str(col_name), header_format)
        
        # Calcular ancho
        col_data = df[col_name].dropna()
        max_len = max(
            col_data.astype(str).map(len).max() if not col_data.empty else 0,
            len(str(col_name))
        ) + 4
        max_len = min(50, max(12, max_len))
        
        is_num = pd.api.types.is_numeric_dtype(df[col_name])
        fmt = number_format if is_num else cell_format
        worksheet.set_column(col_num, col_num, max_len, fmt)

def view_reportes():
    st.markdown("## 📊 Dashboard de Reportes y WIP Global")
    
    # ── Top Filters ──────────────────────────────────────────────
    conn = get_connection()
    df_ofs = pd.read_sql_query("SELECT of_number, proyecto FROM ordenes", conn)
    conn.close()
    
    if df_ofs.empty:
        st.warning("⚠️ No hay planes de producción activos.")
        return
        
    proyectos = ["Todos"] + [p for p in df_ofs['proyecto'].dropna().unique() if p.strip()]
    
    col_p, col_o = st.columns(2)
    with col_p:
        sel_proyecto = st.selectbox("📂 Proyecto (PO):", proyectos, key="rep_proj")
        
    # Filter OFs based on Project
    if sel_proyecto == "Todos":
        ofs_disponibles = df_ofs['of_number'].tolist()
    else:
        ofs_disponibles = df_ofs[df_ofs['proyecto'] == sel_proyecto]['of_number'].tolist()
        
    with col_o:
        sel_ofs = st.multiselect("📍 Selecciona las OFs para ver su estatus de WIP:", ["Todas"] + ofs_disponibles, default=["Todas"], key="rep_ofs")
        
    if not sel_ofs:
        of_list = []
        display_name = "Ninguna"
    elif "Todas" in sel_ofs:
        of_list = ["Todas"]
        display_name = "Múltiples OFs" if sel_proyecto == "Todos" else f"Múltiples OFs ({sel_proyecto})"
    else:
        of_list = sel_ofs
        display_name = sel_ofs[0] if len(sel_ofs) == 1 else "Varias OFs seleccionadas"
    
    with st.spinner("Calculando WIP en tiempo real..."):
        wip_data = get_global_wip_for_ofs(of_list)
    
    if wip_data and any(v > 0 for v in wip_data.values()) or True:
        st.markdown(f"### 🏭 Piezas Disponibles (WIP) por Área para {display_name}")
        st.markdown("Estos números reflejan las piezas exactas que están físicamente listas para trabajarse en cada estación.")
        
        # Calcular Total en Piso excluyendo Corte
        total_piso = sum(v for k, v in wip_data.items() if k not in ["Corte", "Ingenieria"])
        
        relevant_procs = [p for p in PROCESSES if p != "Ingenieria"]
        total_general = sum(wip_data.get(p, 0) for p in relevant_procs)
        pct_piso = (total_piso / total_general * 100) if total_general > 0 else 0
        
        st.markdown(
            f'''
            <div style="background-color: #e6f3ff; border-top: 5px solid #0056b3; padding: 20px; border-radius: 8px; margin-bottom: 25px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); display: flex; justify-content: space-around; align-items: center; position: relative;">
                <div style="text-align: center; width: 45%;">
                    <div style="position: absolute; top: 10px; left: 10px; background-color: #cce5ff; color: #004085; padding: 2px 8px; border-radius: 12px; font-size: 0.85rem; font-weight: bold; box-shadow: inset 0 1px 2px rgba(0,0,0,0.1);">{pct_piso:.1f}%</div>
                    <p style="margin: 0; font-size: 1.1rem; color: #555; font-weight: bold; text-transform: uppercase;">🏭 TOTAL EN PISO (EXCLUYENDO CORTE)</p>
                    <div style="margin: 5px 0 0 0; font-size: 4rem; font-weight: 900; color: #0056b3;">{total_piso}</div>
                </div>
                <div style="width: 2px; height: 80px; background-color: #b3d7ff;"></div>
                <div style="text-align: center; width: 45%;">
                    <p style="margin: 0; font-size: 1.1rem; color: #333; font-weight: bold; text-transform: uppercase;">📦 TOTAL DE LAS OF SELECCIONADAS</p>
                    <div style="margin: 5px 0 0 0; font-size: 4rem; font-weight: 900; color: #111;">{total_general}</div>
                </div>
            </div>
            ''', unsafe_allow_html=True
        )
        
        cols = st.columns(4)
        
        process_icons = {
            "Corte": "✂️",
            "Rebabeo": "⚙️",
            "Doblez": "📐",
            "Barrenado": "🔩",
            "Pintura": "🎨",
            "Liberado": "✅",
            "Empaque": "📦"
        }
        
        friendly_names = {
            "Corte": "Piezas por cortar",
            "Rebabeo": "Piezas por rebabear",
            "Doblez": "Piezas por doblar",
            "Barrenado": "Piezas por barrenar",
            "Pintura": "Piezas por pintar",
            "Liberado": "Piezas por liberar",
            "Empaque": "Piezas por empacar"
        }
        
        for i, proc in enumerate(relevant_procs):
            with cols[i % 4]:
                wip_val = wip_data.get(proc, 0)
                color = "#EC2024" if wip_val > 0 else "#28a745"
                icon = process_icons.get(proc, "🏭")
                pct = (wip_val / total_general * 100) if total_general > 0 else 0
                label = friendly_names.get(proc, proc)
                st.markdown(
                    f'''
                    <div style="background-color: #f8f9fa; border-top: 5px solid {color}; padding: 20px; border-radius: 8px; margin-bottom: 20px; text-align: center; box-shadow: 0 4px 6px rgba(0,0,0,0.1); position: relative;">
                        <div style="position: absolute; top: 10px; right: 10px; background-color: #e9ecef; color: #495057; padding: 2px 8px; border-radius: 12px; font-size: 0.85rem; font-weight: bold; box-shadow: inset 0 1px 2px rgba(0,0,0,0.1);">{pct:.1f}%</div>
                        <div style="font-size: 2.2rem; margin-bottom: 5px;">{icon}</div>
                        <p style="margin: 0; font-size: 0.95rem; color: #555; font-weight: bold; text-transform: uppercase;">{label}</p>
                        <h2 style="margin: 5px 0 0 0; font-size: 3rem; font-weight: 900; color: {color};">{wip_val}</h2>
                    </div>
                    ''', unsafe_allow_html=True
                )
                
        # Gráfica de Barras
        df_chart = pd.DataFrame({
            "Proceso": [friendly_names.get(p, p) for p in relevant_procs],
            "WIP Disponible": [wip_data.get(p, 0) for p in relevant_procs]
        })
        
        fig = px.bar(df_chart, x="Proceso", y="WIP Disponible", title="Distribución del Cuello de Botella (WIP en Piso)", 
                     color="WIP Disponible", color_continuous_scale="Reds", text_auto=True)
        fig.update_layout(xaxis_title="Área / Proceso", yaxis_title="Cantidad de Piezas en WIP")
        st.plotly_chart(fig, use_container_width=True)
        
        # --- DETALLE DE WIP POR PROCESO ---
        st.markdown("### 🔍 Detalle y Descarga de Piezas en WIP")
        st.markdown("Selecciona un proceso para ver la lista exacta de piezas y cantidades que se encuentran esperando en esa estación:")
        
        inv_friendly_names = {v: k for k, v in friendly_names.items()}
        proc_wip_options = ["Selecciona un área..."] + [friendly_names[p] for p in relevant_procs]
        proc_wip_selected_friendly = st.selectbox(
            "Selecciona un Proceso/Área:", 
            proc_wip_options,
            key="wip_detail_selector"
        )
        
        if proc_wip_selected_friendly != "Selecciona un área...":
            proc_wip_selected = inv_friendly_names[proc_wip_selected_friendly]
            df_wip_det = get_wip_pieces_detail(of_list, proc_wip_selected)
            if df_wip_det.empty:
                st.info(f"✅ No hay piezas pendientes (WIP) esperando en el área de **{proc_wip_selected_friendly}**.")
            else:
                st.dataframe(df_wip_det, use_container_width=True, height=250, hide_index=True)
                csv_data = df_wip_det.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label=f"📥 Descargar Reporte de Piezas en WIP - {proc_wip_selected_friendly} (CSV)",
                    data=csv_data,
                    file_name=f"WIP_{proc_wip_selected}_{display_name.replace(' ', '_')}.csv",
                    mime="text/csv",
                    type="primary",
                    use_container_width=True
                )
        
        st.markdown("---")
        st.markdown("### 📥 Exportar Datos")
        
        # Generar Reporte Excel
        def get_excel_report(ofs):
            import io
            conn = get_connection()
            if not ofs:
                df_av = pd.DataFrame()
                df_rech = pd.DataFrame()
            elif "Todas" in ofs:
                df_av = pd.read_sql_query("SELECT id, of_number, nido, no_pieza, area, cantidad, operador, maquina, timestamp FROM avances ORDER BY timestamp DESC", conn)
                df_rech = pd.read_sql_query("SELECT id, of_number, nido, no_pieza, area, cantidad, motivo, operador, maquina, timestamp FROM rechazos ORDER BY timestamp DESC", conn)
            else:
                placeholders = ','.join(['?'] * len(ofs))
                df_av = pd.read_sql_query(f"SELECT id, of_number, nido, no_pieza, area, cantidad, operador, maquina, timestamp FROM avances WHERE of_number IN ({placeholders}) ORDER BY timestamp DESC", conn, params=list(ofs))
                df_rech = pd.read_sql_query(f"SELECT id, of_number, nido, no_pieza, area, cantidad, motivo, operador, maquina, timestamp FROM rechazos WHERE of_number IN ({placeholders}) ORDER BY timestamp DESC", conn, params=list(ofs))
            conn.close()
            
            # Renombrar columnas
            rename_av = {
                "id": "ID Transacción",
                "of_number": "OF",
                "nido": "Nido / Nesteo",
                "no_pieza": "No. Parte",
                "area": "Área / Proceso",
                "cantidad": "Cantidad",
                "operador": "Operador",
                "maquina": "Máquina",
                "timestamp": "Fecha / Hora"
            }
            rename_rech = {
                "id": "ID Transacción",
                "of_number": "OF",
                "nido": "Nido / Nesteo",
                "no_pieza": "No. Parte",
                "area": "Área / Proceso",
                "cantidad": "Cantidad Rechazada",
                "motivo": "Motivo de Scrap",
                "operador": "Operador",
                "maquina": "Máquina",
                "timestamp": "Fecha / Hora"
            }
            
            if not df_av.empty:
                df_av = df_av.rename(columns=rename_av)
            if not df_rech.empty:
                df_rech = df_rech.rename(columns=rename_rech)
                
            df_resumen = pd.DataFrame({
                "Área / Proceso": [friendly_names.get(p, p) for p in relevant_procs],
                "Piezas en WIP": [wip_data.get(p, 0) for p in relevant_procs]
            })
            
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                if not df_av.empty:
                    df_av.to_excel(writer, sheet_name='Avances Detallados', index=False)
                    style_excel_sheet(writer, df_av, 'Avances Detallados')
                if not df_rech.empty:
                    df_rech.to_excel(writer, sheet_name='Rechazos', index=False)
                    style_excel_sheet(writer, df_rech, 'Rechazos')
                
                df_resumen.to_excel(writer, sheet_name='Resumen WIP', index=False)
                style_excel_sheet(writer, df_resumen, 'Resumen WIP')
                
            return output.getvalue()
            
        # Generar Reporte de Piezas en WIP consolidado con una pestaña por área
        def get_wip_consolidado_excel(ofs):
            import io
            conn = get_connection()
            df_meta = pd.read_sql_query("SELECT * FROM ordenes", conn)
            conn.close()
            
            # Recopilar datos detallados de todas las áreas y construir el Consolidado
            consolidado_rows = []
            detailed_dfs = {}
            summary_rows = []
            
            for area in relevant_procs:
                df_area = get_wip_pieces_detail(ofs, area)
                
                if not df_area.empty:
                    df_area = df_area.merge(df_meta, left_on='OF', right_on='of_number', how='left')
                    if 'of_number' in df_area.columns:
                        df_area.drop(columns=['of_number'], inplace=True)
                    rename_map = {
                        'proyecto': 'Proyecto',
                        'programador': 'Programador',
                        'fecha': 'Fecha Producción',
                        'po': 'PO',
                        'prioridad': 'Prioridad',
                        'calibre': 'Calibre OF',
                        'proyecto_cliente': 'Proyecto Cliente',
                        'descripcion_pronest': 'Descripción Pronest',
                        'fecha_carga': 'Fecha Carga'
                    }
                    df_area.rename(columns=rename_map, inplace=True)
                    
                    df_area.rename(columns={
                        'no_pieza': 'No. Parte',
                        'nombre_pieza': 'Descripción',
                        'cantidad_wip': 'Cantidad WIP',
                        'pendiente_disp': 'Cantidad WIP'
                    }, inplace=True)
                    
                    cols_first = ['OF', 'Proyecto', 'Proyecto Cliente', 'PO', 'Prioridad', 'Calibre OF', 'Fecha Producción']
                    cols_other = [c for c in df_area.columns if c not in cols_first]
                    cols_first = [c for c in cols_first if c in df_area.columns]
                    df_area = df_area[cols_first + cols_other]
                    
                    # Guardar para la pestaña del área
                    detailed_dfs[area] = df_area
                    
                    # Añadir al Consolidado
                    df_c = df_area.copy()
                    df_c.insert(0, 'Área / Proceso', friendly_names.get(area, area))
                    consolidado_rows.append(df_c)
                    
                    # Sumar para el Resumen
                    wip_sum = df_area['Cantidad WIP'].sum()
                    summary_rows.append({
                        "Área / Proceso": friendly_names.get(area, area),
                        "Total Piezas en WIP": int(wip_sum)
                    })
                else:
                    summary_rows.append({
                        "Área / Proceso": friendly_names.get(area, area),
                        "Total Piezas en WIP": 0
                    })
            
            # Construir DataFrame de Resumen por Área
            df_resumen_wip = pd.DataFrame(summary_rows)
            
            # Construir DataFrame de Consolidado
            if consolidado_rows:
                df_consolidado = pd.concat(consolidado_rows, ignore_index=True)
            else:
                df_consolidado = pd.DataFrame(columns=['Área / Proceso', 'OF', 'Proyecto', 'Proyecto Cliente', 'PO', 'Prioridad', 'Calibre OF', 'No. Parte', 'Descripción', 'Cantidad WIP'])
            
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                # 1. Escribir el Resumen por Área
                df_resumen_wip.to_excel(writer, sheet_name='Resumen por Área', index=False)
                style_excel_sheet(writer, df_resumen_wip, 'Resumen por Área')
                
                # 2. Escribir el Consolidado
                df_consolidado.to_excel(writer, sheet_name='Consolidado', index=False)
                style_excel_sheet(writer, df_consolidado, 'Consolidado')
                
                # 3. Escribir las pestañas individuales de cada área con nombres legibles
                for area in relevant_procs:
                    df_area = detailed_dfs.get(area, pd.DataFrame(columns=['OF', 'Proyecto', 'Proyecto Cliente', 'PO', 'Prioridad', 'Calibre OF', 'No. Parte', 'Descripción', 'Cantidad WIP']))
                    sheet_title = friendly_names.get(area, area)[:31]
                    df_area.to_excel(writer, sheet_name=sheet_title, index=False)
                    style_excel_sheet(writer, df_area, sheet_title)
                    
            return output.getvalue()

        excel_data = get_excel_report(of_list)
        wip_excel_data = get_wip_consolidado_excel(of_list)
        
        file_sufix = "Multiples" if len(of_list) != 1 or "Todas" in of_list else of_list[0]
        
        col_dl1, col_dl2 = st.columns(2)
        with col_dl1:
            st.download_button(
                label="📊 Descargar Reporte de Transacciones (Excel)",
                data=excel_data,
                file_name=f"Reporte_Transacciones_OF_{file_sufix}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
        with col_dl2:
            st.download_button(
                label="📥 Descargar Reporte Detallado de WIP por Área (Excel)",
                data=wip_excel_data,
                file_name=f"Reporte_Detallado_WIP_Areas_{file_sufix}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary",
                use_container_width=True
            )
        
    else:
        st.info("No hay datos para esta OF.")
