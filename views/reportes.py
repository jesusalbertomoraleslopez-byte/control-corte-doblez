import streamlit as st
import pandas as pd
import plotly.express as px
from utils.database import get_connection, get_todas_piezas, get_nidos, get_all_ofs
from views.avances import PROCESSES

def get_area_anterior(ruta_str, current_area):
    if pd.isna(ruta_str): return None
    procesos = [p.strip() for p in str(ruta_str).split(',') if p.strip()]
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
        # IMPORTANTE: incluir of_number en GROUP BY para evitar mezcla entre OFs con mismo no_pieza
        df_avances_all = pd.read_sql_query("SELECT of_number, no_pieza, area, SUM(cantidad) as cantidad FROM avances GROUP BY of_number, no_pieza, area", conn)
        df_rechazos_all = pd.read_sql_query("SELECT of_number, no_pieza, area, SUM(cantidad) as cantidad FROM rechazos GROUP BY of_number, no_pieza, area", conn)
    else:
        df_avances_all = pd.read_sql_query("SELECT of_number, no_pieza, area, SUM(cantidad) as cantidad FROM avances WHERE of_number=? GROUP BY of_number, no_pieza, area", conn, params=(of_number,))
        df_rechazos_all = pd.read_sql_query("SELECT of_number, no_pieza, area, SUM(cantidad) as cantidad FROM rechazos WHERE of_number=? GROUP BY of_number, no_pieza, area", conn, params=(of_number,))
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
            # Buscar nidos terminados (donde hojas cortadas >= hojas requeridas)
            c.execute("""
                SELECT n.of_number, n.nido 
                FROM nidos n 
                LEFT JOIN avances a ON n.of_number = a.of_number AND n.nido = a.nido AND a.area = 'Corte'
                GROUP BY n.of_number, n.nido, n.hojas
                HAVING COUNT(DISTINCT a.hoja) >= n.hojas
            """)
            terminados_tuples = set((row[0], row[1]) for row in c.fetchall())
            conn.close()
            
            if of_number == "Todas" or of_number is None:
                df_corte_pend = df_todas[~df_todas.apply(lambda row: (row['of_number'], row['nido']) in terminados_tuples, axis=1)]
            else:
                df_corte_pend = df_todas[
                    (df_todas['of_number'] == of_number) & 
                    (~df_todas.apply(lambda row: (row['of_number'], row['nido']) in terminados_tuples, axis=1))
                ]
            
            total_wip_corte = 0
            if not df_corte_pend.empty:
                conn = get_connection()
                c_av = conn.cursor()
                for (of_n, nido_n), grp in df_corte_pend.groupby(['of_number', 'nido']):
                    c_av.execute("SELECT SUM(cantidad) FROM avances WHERE of_number=? AND nido=? AND area='Corte'", (of_n, nido_n))
                    avanzado_nido = c_av.fetchone()[0] or 0
                    total_req_nido = grp['total_requeridas'].sum()
                    total_wip_corte += max(0, total_req_nido - avanzado_nido)
                conn.close()
            
            wip_por_area[area] = int(total_wip_corte)
            continue
            
        # Post corte
        df_piezas = df_todas.copy()
        df_piezas['pasa_por_aqui'] = df_piezas['ruta'].apply(lambda x: area in [p.strip() for p in str(x).split(',') if p.strip()])
        df_piezas = df_piezas[df_piezas['pasa_por_aqui']]
        
        if df_piezas.empty:
            wip_por_area[area] = 0
            continue
            
        df_piezas['area_anterior'] = df_piezas['ruta'].apply(lambda x: get_area_anterior(x, area))
        df_agrupado = df_piezas.groupby(['of_number', 'no_pieza']).agg({
            'total_requeridas': 'sum',
            'area_anterior': 'first'
        }).reset_index()
        
        def get_wip(row):
            area_ant = row['area_anterior']
            if pd.isna(area_ant) or not area_ant: return 0
            mask = (
                (df_avances_all['of_number'] == row['of_number']) &
                (df_avances_all['no_pieza'] == row['no_pieza']) &
                (df_avances_all['area'] == area_ant)
            )
            return int(df_avances_all[mask]['cantidad'].sum())
            
        def get_terminadas_ant(row):
            mask = (
                (df_avances_all['of_number'] == row['of_number']) &
                (df_avances_all['no_pieza'] == row['no_pieza']) &
                (df_avances_all['area'] == area)
            )
            return int(df_avances_all[mask]['cantidad'].sum())
            
        def get_rechazadas_ant(row):
            mask = (
                (df_rechazos_all['of_number'] == row['of_number']) &
                (df_rechazos_all['no_pieza'] == row['no_pieza']) &
                (df_rechazos_all['area'] == area)
            )
            return int(df_rechazos_all[mask]['cantidad'].sum())
            
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
            c.execute("""
                SELECT n.nido 
                FROM nidos n 
                LEFT JOIN avances a ON n.of_number = a.of_number AND n.nido = a.nido AND a.area = 'Corte'
                WHERE n.of_number = ?
                GROUP BY n.nido, n.hojas
                HAVING COUNT(DISTINCT a.hoja) >= n.hojas
            """, (of_num,))
            terminados = [row[0] for row in c.fetchall()]
            conn.close()
            
            df_corte_pend = df_todas[~df_todas['nido'].isin(terminados)]
            if not df_corte_pend.empty:
                conn = get_connection()
                c_av = conn.cursor()
                df_g_list = []
                for (no_p, nom_p), grp in df_corte_pend.groupby(['no_pieza', 'nombre_pieza']):
                    c_av.execute(
                        "SELECT SUM(cantidad) FROM avances "
                        "WHERE of_number=? AND no_pieza=? AND area='Corte'",
                        (of_num, no_p)
                    )
                    avanzado_p = c_av.fetchone()[0] or 0
                    total_req_p = grp['total_requeridas'].sum()
                    faltante_p = max(0, total_req_p - avanzado_p)
                    if faltante_p > 0:
                        df_g_list.append({
                            'no_pieza': no_p,
                            'nombre_pieza': nom_p,
                            'cantidad_wip': int(faltante_p),
                            'of_number': of_num
                        })
                conn.close()
                if df_g_list:
                    df_g = pd.DataFrame(df_g_list)
                    details.append(df_g)
        else:
            df_piezas = df_todas.copy()
            df_piezas['pasa_por_aqui'] = df_piezas['ruta'].apply(lambda x: area in [p.strip() for p in str(x).split(',') if p.strip()])
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

def calculate_wip_on_date(of_list, target_date_str):
    limit_timestamp = f"{target_date_str} 23:59:59"
    
    conn = get_connection()
    c = conn.cursor()
    if "Todas" in of_list:
        c.execute("SELECT of_number, nido FROM avances WHERE area = 'Corte' AND timestamp <= ?", (limit_timestamp,))
        terminados_tuples = set((row[0], row[1]) for row in c.fetchall())
    else:
        placeholders = ','.join(['?'] * len(of_list))
        c.execute(f"SELECT of_number, nido FROM avances WHERE area = 'Corte' AND timestamp <= ? AND of_number IN ({placeholders})", [limit_timestamp] + list(of_list))
        terminados_tuples = set((row[0], row[1]) for row in c.fetchall())
    conn.close()
    
    wip_por_area = {}
    relevant_procs = [p for p in PROCESSES if p != "Ingenieria"]
    actual_ofs = get_all_ofs() if "Todas" in of_list else of_list
    
    for area in relevant_procs:
        total_wip_area = 0
        
        for of_num in actual_ofs:
            df_todas = get_todas_piezas(of_num)
            if df_todas.empty:
                continue
                
            if 'hojas' not in df_todas.columns:
                df_todas['hojas'] = 1
            df_todas['total_requeridas'] = pd.to_numeric(df_todas['cantidad'], errors='coerce').fillna(0) * pd.to_numeric(df_todas['hojas'], errors='coerce').fillna(1)
            
            conn = get_connection()
            df_avances_all = pd.read_sql_query(
                "SELECT no_pieza, area, SUM(cantidad) as cantidad FROM avances WHERE of_number=? AND timestamp <= ? GROUP BY no_pieza, area",
                conn, params=(of_num, limit_timestamp)
            )
            df_rechazos_all = pd.read_sql_query(
                "SELECT no_pieza, area, SUM(cantidad) as cantidad FROM rechazos WHERE of_number=? AND timestamp <= ? GROUP BY no_pieza, area",
                conn, params=(of_num, limit_timestamp)
            )
            conn.close()
            
            if area == "Corte":
                df_corte_pend = df_todas[~df_todas.apply(lambda row: (row['of_number'], row['nido']) in terminados_tuples, axis=1)]
                total_wip_area += int(df_corte_pend['total_requeridas'].sum())
            else:
                df_piezas = df_todas.copy()
                df_piezas['pasa_por_aqui'] = df_piezas['ruta'].apply(lambda x: area in [p.strip() for p in str(x).split(',') if p.strip()])
                df_piezas = df_piezas[df_piezas['pasa_por_aqui']]
                
                if df_piezas.empty:
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
                
                total_wip_area += int(df_agrupado['pendiente_disp'].sum())
                
        wip_por_area[area] = total_wip_area
        
    return wip_por_area

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
            "Empaque": "📦",
            "Almacen PT": "🏪"
        }
        
        friendly_names = {
            "Corte": "Piezas por cortar",
            "Rebabeo": "Piezas por rebabear",
            "Doblez": "Piezas por doblar",
            "Barrenado": "Piezas por barrenar",
            "Pintura": "Piezas por pintar",
            "Liberado": "Piezas por liberar",
            "Empaque": "Piezas por empacar",
            "Almacen PT": "Piezas en Almacén PT"
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
                
        # Tabs para Gráfica de Pareto y Tendencia
        tab_pareto_act, tab_tendencia_wip = st.tabs([
            "📊 Cuello de Botella Actual (Pareto)",
            "📈 Histórico y Tendencia del WIP (Lunes a Sábado)"
        ])
        
        with tab_pareto_act:
            df_chart = pd.DataFrame({
                "Proceso": [friendly_names.get(p, p) for p in relevant_procs],
                "WIP Disponible": [wip_data.get(p, 0) for p in relevant_procs]
            })
            fig = px.bar(df_chart, x="Proceso", y="WIP Disponible", title="Distribución del Cuello de Botella (WIP en Piso)", 
                         color="WIP Disponible", color_continuous_scale="Reds", text_auto=True)
            fig.update_layout(xaxis_title="Área / Proceso", yaxis_title="Cantidad de Piezas en WIP")
            st.plotly_chart(fig, use_container_width=True)
            
        with tab_tendencia_wip:
            # Obtener todas las fechas con avances
            conn = get_connection()
            c = conn.cursor()
            c.execute("SELECT DISTINCT date(timestamp) FROM avances WHERE timestamp IS NOT NULL ORDER BY date(timestamp) ASC")
            all_dates = [row[0] for row in c.fetchall() if row[0]]
            conn.close()
            
            if all_dates:
                min_d = pd.to_datetime(all_dates[0]).date()
                max_d = pd.to_datetime(all_dates[-1]).date()
                default_start = pd.to_datetime(all_dates[-min(7, len(all_dates))]).date()
                
                col_date_start, col_date_end = st.columns(2)
                with col_date_start:
                    start_date = st.date_input("Fecha Inicio Tendencia:", default_start, min_value=min_d, max_value=max_d, key="wip_trend_start")
                with col_date_end:
                    end_date = st.date_input("Fecha Fin Tendencia:", max_d, min_value=min_d, max_value=max_d, key="wip_trend_end")
            else:
                start_date = pd.to_datetime("today").date() - pd.Timedelta(days=7)
                end_date = pd.to_datetime("today").date()
                
            date_range = pd.date_range(start=start_date, end=end_date).strftime('%Y-%m-%d').tolist()
            
            wip_history = []
            for date_str in date_range:
                dt_obj = pd.to_datetime(date_str)
                dias_es = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
                day_name = dias_es[dt_obj.weekday()]
                display_label = f"{day_name} ({dt_obj.strftime('%d/%m')})"
                
                wip_on_date = calculate_wip_on_date(of_list, date_str)
                for area, val in wip_on_date.items():
                    wip_history.append({
                        "Fecha": display_label,
                        "Área / Proceso": friendly_names.get(area, area),
                        "Piezas en WIP": val
                    })
                    
            df_history = pd.DataFrame(wip_history)
            if not df_history.empty:
                fig_trend = px.line(
                    df_history, 
                    x="Fecha", 
                    y="Piezas en WIP", 
                    color="Área / Proceso",
                    title="Evolución Diaria del WIP por Área",
                    markers=True,
                    line_shape="spline",
                    color_discrete_map={
                        "Piezas por cortar": "#FFD700",
                        "Piezas por rebabear": "#FF6347",
                        "Piezas por doblar": "#DC143C",
                        "Piezas por barrenar": "#8B0000",
                        "Piezas por pintar": "#9370DB",
                        "Piezas por liberar": "#00BFFF",
                        "Piezas por empacar": "#32CD32"
                    }
                )
                fig_trend.update_layout(
                    xaxis_title="Día de la Semana",
                    yaxis_title="Piezas en Espera (WIP)",
                    legend_title="Estación de Trabajo",
                    hovermode="x unified"
                )
                st.plotly_chart(fig_trend, use_container_width=True)
            else:
                st.info("No hay datos históricos suficientes para calcular la tendencia del WIP.")
        
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
            
            excel_sheet_names = {
                "Corte": "x-Cortar",
                "Rebabeo": "x-Rebabear",
                "Doblez": "x-Doblar",
                "Barrenado": "x-Barrenar",
                "Pintura": "x-Pintar",
                "Liberado": "x-Liberar",
                "Empaque": "x-Empacar",
                "Almacen PT": "x-Almacen PT"
            }
            
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
                    df_c.insert(0, 'Área / Proceso', excel_sheet_names.get(area, area))
                    consolidado_rows.append(df_c)
                    
                    # Sumar para el Resumen
                    wip_sum = df_area['Cantidad WIP'].sum()
                    summary_rows.append({
                        "Área / Proceso": excel_sheet_names.get(area, area),
                        "Total Piezas en WIP": int(wip_sum)
                    })
                else:
                    summary_rows.append({
                        "Área / Proceso": excel_sheet_names.get(area, area),
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
                
                # 3. Escribir las pestañas individuales de cada área con nombres cortos
                for area in relevant_procs:
                    df_area = detailed_dfs.get(area, pd.DataFrame(columns=['OF', 'Proyecto', 'Proyecto Cliente', 'PO', 'Prioridad', 'Calibre OF', 'No. Parte', 'Descripción', 'Cantidad WIP']))
                    sheet_title = excel_sheet_names.get(area, area)[:31]
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
            
        # --- NUEVAS GRÁFICAS DE RENDIMIENTO SEMANAL (L-M-M-J-V-S-D) ---
        st.markdown("---")
        st.markdown("### 📅 Gráficas de Rendimiento Semanal (L-M-M-J-V-S-D)")
        st.markdown("Visualiza la producción, mermas y evolución del WIP agrupados por proceso y por día de la semana:")
        
        # Obtener fecha máxima de la BD como default
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT MAX(date(timestamp)) FROM avances")
        row = c.fetchone()
        max_date_db = pd.to_datetime(row[0]).date() if (row and row[0]) else pd.to_datetime("today").date()
        conn.close()
        
        ref_date = st.date_input(
            "Selecciona un día para ver su semana correspondiente (Lunes a Domingo):",
            value=max_date_db,
            key="weekly_report_ref_date"
        )
        
        # Calcular los 7 días de la semana
        lunes = ref_date - pd.Timedelta(days=ref_date.weekday())
        dias_semana = [lunes + pd.Timedelta(days=i) for i in range(7)]
        dias_labels = ["L", "M", "M", "J", "V", "S", "D"]
        dias_nombres_completos = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
        
        # Consultar avances y rechazos para cada día de la semana
        conn = get_connection()
        
        prod_areas = []
        prod_dias = []
        prod_valores = []
        
        scrap_areas = []
        scrap_dias = []
        scrap_valores = []
        
        wip_areas = []
        wip_dias = []
        wip_valores = []
        
        for idx_day, d in enumerate(dias_semana):
            date_str = d.strftime('%Y-%m-%d')
            day_label = dias_labels[idx_day]
            
            # Avances de este día
            df_av_d = pd.read_sql_query(
                "SELECT area, SUM(cantidad) as total FROM avances WHERE date(timestamp) = ? GROUP BY area",
                conn, params=(date_str,)
            )
            # Rechazos de este día
            df_rec_d = pd.read_sql_query(
                "SELECT area, SUM(cantidad) as total FROM rechazos WHERE date(timestamp) = ? GROUP BY area",
                conn, params=(date_str,)
            )
            
            # Calcular WIP de este día
            wip_on_date = calculate_wip_on_date(of_list, date_str)
            
            for proc in relevant_procs:
                proc_friendly = friendly_names.get(proc, proc)
                
                # Producción
                p_val = df_av_d[df_av_d['area'] == proc]['total'].sum() if not df_av_d.empty else 0
                prod_areas.append(proc_friendly)
                prod_dias.append(day_label)
                prod_valores.append(int(p_val))
                
                # Scrap
                s_val = df_rec_d[df_rec_d['area'] == proc]['total'].sum() if not df_rec_d.empty else 0
                scrap_areas.append(proc_friendly)
                scrap_dias.append(day_label)
                scrap_valores.append(int(s_val))
                
                # WIP
                w_val = wip_on_date.get(proc, 0)
                wip_areas.append(proc_friendly)
                wip_dias.append(day_label)
                wip_valores.append(int(w_val))
                
        conn.close()
        
        # Crear pestañas para las 3 gráficas
        tab_prod_w, tab_scrap_w, tab_wip_w = st.tabs([
            "📈 Producción Semanal (L-M-M-J-V-S-D)",
            "🚨 Scrap Semanal (L-M-M-J-V-S-D)",
            "⏳ WIP Semanal (L-M-M-J-V-S-D)"
        ])
        
        import plotly.graph_objects as go
        
        # Paleta de colores para los días L M M J V S D
        colors_days = ['#FFD700', '#FF8C00', '#FF4500', '#EC2024', '#9370DB', '#00BFFF', '#32CD32']
        
        # Construir listas de colores repetidas
        prod_colors_list = [colors_days[dias_labels.index(d)] for d in prod_dias]
        scrap_colors_list = [colors_days[dias_labels.index(d)] for d in scrap_dias]
        wip_colors_list = [colors_days[dias_labels.index(d)] for d in wip_dias]
        
        with tab_prod_w:
            fig_p = go.Figure()
            fig_p.add_trace(go.Bar(
                x=[prod_areas, prod_dias],
                y=prod_valores,
                marker_color=prod_colors_list,
                text=prod_valores,
                textposition='outside'
            ))
            fig_p.update_layout(
                title=f"<b>Producción Diaria por Estación (Semana del {lunes.strftime('%d/%m/%Y')} al {dias_semana[-1].strftime('%d/%m/%Y')})</b>",
                title_x=0.5,
                xaxis_title="Proceso / Día de la Semana",
                yaxis_title="Piezas Producidas",
                height=450,
                margin=dict(t=50, b=50, l=40, r=40)
            )
            st.plotly_chart(fig_p, use_container_width=True)
            
        with tab_scrap_w:
            fig_s = go.Figure()
            fig_s.add_trace(go.Bar(
                x=[scrap_areas, scrap_dias],
                y=scrap_valores,
                marker_color=scrap_colors_list,
                text=scrap_valores,
                textposition='outside'
            ))
            fig_s.update_layout(
                title=f"<b>Scrap Registrado por Estación (Semana del {lunes.strftime('%d/%m/%Y')} al {dias_semana[-1].strftime('%d/%m/%Y')})</b>",
                title_x=0.5,
                xaxis_title="Proceso / Día de la Semana",
                yaxis_title="Piezas Rechazadas",
                height=450,
                margin=dict(t=50, b=50, l=40, r=40)
            )
            st.plotly_chart(fig_s, use_container_width=True)
            
        with tab_wip_w:
            fig_w = go.Figure()
            fig_w.add_trace(go.Bar(
                x=[wip_areas, wip_dias],
                y=wip_valores,
                marker_color=wip_colors_list,
                text=wip_valores,
                textposition='outside'
            ))
            fig_w.update_layout(
                title=f"<b>Evolución del WIP por Estación (Semana del {lunes.strftime('%d/%m/%Y')} al {dias_semana[-1].strftime('%d/%m/%Y')})</b>",
                title_x=0.5,
                xaxis_title="Proceso / Día de la Semana",
                yaxis_title="Piezas en WIP",
                height=450,
                margin=dict(t=50, b=50, l=40, r=40)
            )
            st.plotly_chart(fig_w, use_container_width=True)
        
    else:
        st.info("No hay datos para esta OF.")
