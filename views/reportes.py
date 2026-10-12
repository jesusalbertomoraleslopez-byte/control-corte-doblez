import streamlit as st
import pandas as pd
import plotly.express as px
from utils.database import get_connection, get_todas_piezas, get_nidos, get_all_ofs, get_local_today
from views.avances import PROCESSES

def get_area_anterior(ruta_str, current_area):
    if pd.isna(ruta_str): return None
    procesos = [p.strip() for p in str(ruta_str).split(',') if p.strip()]
    if current_area in procesos:
        idx = procesos.index(current_area)
        if idx > 0:
            return procesos[idx - 1]
    return None


@st.cache_data(ttl=30, show_spinner=False)
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

@st.cache_data(ttl=45, show_spinner=False)
def get_wip_pieces_detail(of_list, area):
    if not of_list:
        return pd.DataFrame(columns=['OF', 'No. Pieza', 'Descripción', 'Cantidad WIP'])

    is_todas = "Todas" in of_list
    df_todas = get_todas_piezas("Todas" if is_todas else None)
    if not is_todas and not df_todas.empty:
        df_todas = df_todas[df_todas['of_number'].isin(of_list)].copy()

    if df_todas.empty:
        return pd.DataFrame(columns=['OF', 'No. Pieza', 'Descripción', 'Cantidad WIP'])

    if 'hojas' not in df_todas.columns:
        df_todas['hojas'] = 1
    df_todas['total_requeridas'] = (
        pd.to_numeric(df_todas['cantidad'], errors='coerce').fillna(0)
        * pd.to_numeric(df_todas['hojas'], errors='coerce').fillna(1)
    )

    conn = get_connection()
    if is_todas:
        df_avances_all = pd.read_sql_query(
            "SELECT of_number, no_pieza, area, SUM(cantidad) as cantidad FROM avances GROUP BY of_number, no_pieza, area",
            conn
        )
        df_rechazos_all = pd.read_sql_query(
            "SELECT of_number, no_pieza, area, SUM(cantidad) as cantidad FROM rechazos GROUP BY of_number, no_pieza, area",
            conn
        )
    else:
        placeholders = ','.join(['?'] * len(of_list))
        df_avances_all = pd.read_sql_query(
            f"SELECT of_number, no_pieza, area, SUM(cantidad) as cantidad FROM avances WHERE of_number IN ({placeholders}) GROUP BY of_number, no_pieza, area",
            conn, params=list(of_list)
        )
        df_rechazos_all = pd.read_sql_query(
            f"SELECT of_number, no_pieza, area, SUM(cantidad) as cantidad FROM rechazos WHERE of_number IN ({placeholders}) GROUP BY of_number, no_pieza, area",
            conn, params=list(of_list)
        )

    if area == "Corte":
        c = conn.cursor()
        c.execute("""
            SELECT n.of_number, n.nido 
            FROM nidos n 
            LEFT JOIN avances a ON n.of_number = a.of_number AND n.nido = a.nido AND a.area = 'Corte'
            GROUP BY n.of_number, n.nido, n.hojas
            HAVING COUNT(DISTINCT a.hoja) >= n.hojas
        """)
        terminados_set = set((row[0], row[1]) for row in c.fetchall())
        conn.close()

        mask_pend = ~df_todas.set_index(['of_number', 'nido']).index.isin(terminados_set)
        df_corte_pend = df_todas[mask_pend]
        if df_corte_pend.empty:
            return pd.DataFrame(columns=['OF', 'No. Pieza', 'Descripción', 'Cantidad WIP'])

        df_req_grp = (
            df_corte_pend.groupby(['of_number', 'no_pieza', 'nombre_pieza'], as_index=False)['total_requeridas']
            .sum()
        )
        df_av_corte = df_avances_all[df_avances_all['area'] == 'Corte'][['of_number', 'no_pieza', 'cantidad']]
        df_merged = df_req_grp.merge(df_av_corte, on=['of_number', 'no_pieza'], how='left')
        df_merged['cantidad'] = df_merged['cantidad'].fillna(0)
        df_merged['Cantidad WIP'] = (df_merged['total_requeridas'] - df_merged['cantidad']).clip(lower=0).astype(int)
        df_merged = df_merged[df_merged['Cantidad WIP'] > 0]
        df_merged.rename(columns={
            'of_number': 'OF',
            'no_pieza': 'No. Pieza',
            'nombre_pieza': 'Descripción'
        }, inplace=True)
        return df_merged[['OF', 'No. Pieza', 'Descripción', 'Cantidad WIP']].reset_index(drop=True)

    conn.close()
    df_piezas = df_todas.copy()
    df_piezas['pasa_por_aqui'] = df_piezas['ruta'].apply(
        lambda x: area in [p.strip() for p in str(x).split(',') if p.strip()]
    )
    df_piezas = df_piezas[df_piezas['pasa_por_aqui']]
    if df_piezas.empty:
        return pd.DataFrame(columns=['OF', 'No. Pieza', 'Descripción', 'Cantidad WIP'])

    df_piezas['area_anterior'] = df_piezas['ruta'].apply(lambda x: get_area_anterior(x, area))
    df_agrupado = df_piezas.groupby(['of_number', 'no_pieza', 'nombre_pieza'], as_index=False).agg({
        'total_requeridas': 'sum',
        'area_anterior': 'first'
    })

    av_map = df_avances_all.set_index(['of_number', 'no_pieza', 'area'])['cantidad'].to_dict() if not df_avances_all.empty else {}
    rec_map = df_rechazos_all.set_index(['of_number', 'no_pieza', 'area'])['cantidad'].to_dict() if not df_rechazos_all.empty else {}

    df_agrupado['wip'] = [
        int(av_map.get((r['of_number'], r['no_pieza'], r['area_anterior']), 0)) if pd.notna(r['area_anterior']) and r['area_anterior'] else 0
        for _, r in df_agrupado.iterrows()
    ]
    df_agrupado['term'] = [
        int(av_map.get((r['of_number'], r['no_pieza'], area), 0))
        for _, r in df_agrupado.iterrows()
    ]
    df_agrupado['rech'] = [
        int(rec_map.get((r['of_number'], r['no_pieza'], area), 0))
        for _, r in df_agrupado.iterrows()
    ]
    df_agrupado['Cantidad WIP'] = (df_agrupado['wip'] - df_agrupado['term'] - df_agrupado['rech']).clip(lower=0).astype(int)
    df_res = df_agrupado[df_agrupado['Cantidad WIP'] > 0].rename(columns={
        'of_number': 'OF',
        'no_pieza': 'No. Pieza',
        'nombre_pieza': 'Descripción'
    })
    return df_res[['OF', 'No. Pieza', 'Descripción', 'Cantidad WIP']].reset_index(drop=True)

@st.cache_data(ttl=60, show_spinner=False)
def calculate_wip_on_date(of_list, target_date_str):
    limit_timestamp = f"{target_date_str} 23:59:59"
    relevant_procs = [p for p in PROCESSES if p != "Ingenieria"]
    wip_por_area = {area: 0 for area in relevant_procs}
    if not of_list:
        return wip_por_area

    is_todas = "Todas" in of_list
    df_todas = get_todas_piezas("Todas" if is_todas else None)
    if not is_todas and not df_todas.empty:
        df_todas = df_todas[df_todas['of_number'].isin(of_list)].copy()
    if df_todas.empty:
        return wip_por_area

    if 'hojas' not in df_todas.columns:
        df_todas['hojas'] = 1
    df_todas['total_requeridas'] = (
        pd.to_numeric(df_todas['cantidad'], errors='coerce').fillna(0)
        * pd.to_numeric(df_todas['hojas'], errors='coerce').fillna(1)
    )

    conn = get_connection()
    c = conn.cursor()
    if is_todas:
        c.execute("SELECT of_number, nido FROM avances WHERE area = 'Corte' AND timestamp <= ?", (limit_timestamp,))
        terminados_tuples = set((row[0], row[1]) for row in c.fetchall())
        df_avances_all = pd.read_sql_query(
            "SELECT of_number, no_pieza, area, SUM(cantidad) as cantidad FROM avances WHERE timestamp <= ? GROUP BY of_number, no_pieza, area",
            conn, params=(limit_timestamp,)
        )
        df_rechazos_all = pd.read_sql_query(
            "SELECT of_number, no_pieza, area, SUM(cantidad) as cantidad FROM rechazos WHERE timestamp <= ? GROUP BY of_number, no_pieza, area",
            conn, params=(limit_timestamp,)
        )
    else:
        placeholders = ','.join(['?'] * len(of_list))
        c.execute(f"SELECT of_number, nido FROM avances WHERE area = 'Corte' AND timestamp <= ? AND of_number IN ({placeholders})", [limit_timestamp] + list(of_list))
        terminados_tuples = set((row[0], row[1]) for row in c.fetchall())
        df_avances_all = pd.read_sql_query(
            f"SELECT of_number, no_pieza, area, SUM(cantidad) as cantidad FROM avances WHERE timestamp <= ? AND of_number IN ({placeholders}) GROUP BY of_number, no_pieza, area",
            conn, params=[limit_timestamp] + list(of_list)
        )
        df_rechazos_all = pd.read_sql_query(
            f"SELECT of_number, no_pieza, area, SUM(cantidad) as cantidad FROM rechazos WHERE timestamp <= ? AND of_number IN ({placeholders}) GROUP BY of_number, no_pieza, area",
            conn, params=[limit_timestamp] + list(of_list)
        )
    conn.close()

    av_map = df_avances_all.set_index(['of_number', 'no_pieza', 'area'])['cantidad'].to_dict() if not df_avances_all.empty else {}
    rec_map = df_rechazos_all.set_index(['of_number', 'no_pieza', 'area'])['cantidad'].to_dict() if not df_rechazos_all.empty else {}

    for area in relevant_procs:
        if area == "Corte":
            mask_pend = ~df_todas.set_index(['of_number', 'nido']).index.isin(terminados_tuples)
            wip_por_area[area] = int(df_todas[mask_pend]['total_requeridas'].sum())
        else:
            df_piezas = df_todas[df_todas['ruta'].apply(lambda x: area in [p.strip() for p in str(x).split(',') if p.strip()])].copy()
            if df_piezas.empty:
                wip_por_area[area] = 0
                continue
            df_piezas['area_anterior'] = df_piezas['ruta'].apply(lambda x: get_area_anterior(x, area))
            df_agrupado = df_piezas.groupby(['of_number', 'no_pieza'], as_index=False).agg({
                'total_requeridas': 'sum',
                'area_anterior': 'first'
            })
            total_area = 0
            for _, r in df_agrupado.iterrows():
                a_ant = r['area_anterior']
                w_val = int(av_map.get((r['of_number'], r['no_pieza'], a_ant), 0)) if pd.notna(a_ant) and a_ant else 0
                t_val = int(av_map.get((r['of_number'], r['no_pieza'], area), 0))
                r_val = int(rec_map.get((r['of_number'], r['no_pieza'], area), 0))
                total_area += max(0, w_val - t_val - r_val)
            wip_por_area[area] = total_area

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
    # Obtener y formatear fecha en español
    import datetime
    dias_semana = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
    meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
    today = get_local_today()
    dia_nombre = dias_semana[today.weekday()]
    mes_nombre = meses[today.month - 1]
    fecha_grande = f"{dia_nombre}, {today.day} de {mes_nombre} de {today.year}"

    col_title, col_date = st.columns([1.8, 1.2])
    with col_title:
        st.markdown('<h2 style="margin: 0; font-family: \'Montserrat\'; font-weight: 900; font-size: 1.8rem;">📊 Dashboard de Reportes y WIP Global</h2>', unsafe_allow_html=True)
    with col_date:
        st.markdown(f'<div style="text-align: right; padding-top: 5px;"><span style="font-size: 1.4rem; font-weight: 800; color: #EC2024; font-family: \'Montserrat\';">📅 {fecha_grande}</span></div>', unsafe_allow_html=True)
    
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
    
    relevant_procs = [p for p in PROCESSES if p != "Ingenieria"]
    process_icons = {
        "Corte": "✂️",
        "Rebabeo": "⚙️",
        "Doblez": "📐",
        "Barrenado": "🔩",
        "Pintura": "🎨",
        "Liberado": "✅",
        "Empaque": "📦",
        "TOTAL_PISO": "🏭",
        "TOTAL_GENERAL": "📦"
    }
    friendly_names = {
        "Corte": "Piezas por cortar",
        "Rebabeo": "Piezas por rebabear",
        "Doblez": "Piezas por doblar",
        "Barrenado": "Piezas por barrenar",
        "Pintura": "Piezas por pintar",
        "Liberado": "Piezas por liberar",
        "Empaque": "Piezas por empacar",
        "TOTAL_PISO": "Total en Piso (Excluyendo Corte)",
        "TOTAL_GENERAL": "Total de las OF Seleccionadas"
    }
    inv_friendly_names = {v: k for k, v in friendly_names.items()}

    # ── Función auxiliar: Detalle enriquecido de piezas en WIP con metadatos de OF y Nidos ──
    def get_wip_pieces_rich_detail(ofs_target, area_target):
        if area_target == "TOTAL_PISO":
            areas_to_query = [p for p in relevant_procs if p != "Corte"]
        elif area_target == "TOTAL_GENERAL":
            areas_to_query = list(relevant_procs)
        else:
            areas_to_query = [area_target]

        conn = get_connection()
        df_meta = pd.read_sql_query("SELECT * FROM ordenes", conn)
        df_pzs_nidos = pd.read_sql_query(
            "SELECT of_number, no_pieza, GROUP_CONCAT(DISTINCT nido) as nidos_str, MAX(ruta) as ruta_str "
            "FROM piezas GROUP BY of_number, no_pieza",
            conn
        )
        conn.close()

        frames = []
        for ar in areas_to_query:
            df_ar = get_wip_pieces_detail(ofs_target, ar)
            if not df_ar.empty:
                df_ar = df_ar.copy()
                df_ar["Área"] = ar
                df_ar["Estación"] = friendly_names.get(ar, ar)
                frames.append(df_ar)

        if not frames:
            return pd.DataFrame(columns=[
                "Área", "Estación", "OF", "Proyecto", "Proyecto Cliente", "PO",
                "Prioridad", "Calibre", "Nidos", "No. Pieza", "Descripción",
                "Cantidad WIP", "Ruta"
            ])

        df_all = pd.concat(frames, ignore_index=True)
        if not df_meta.empty:
            cols_meta = [c for c in ["of_number", "proyecto", "proyecto_cliente", "po", "prioridad", "calibre", "fecha"] if c in df_meta.columns]
            df_all = df_all.merge(df_meta[cols_meta], left_on="OF", right_on="of_number", how="left")
            if "of_number" in df_all.columns:
                df_all.drop(columns=["of_number"], inplace=True)

        if not df_pzs_nidos.empty:
            df_all = df_all.merge(
                df_pzs_nidos,
                left_on=["OF", "No. Pieza"],
                right_on=["of_number", "no_pieza"],
                how="left"
            )
            for col_drop in ["of_number", "no_pieza"]:
                if col_drop in df_all.columns:
                    df_all.drop(columns=[col_drop], inplace=True)

        df_all.rename(columns={
            "proyecto": "Proyecto",
            "proyecto_cliente": "Proyecto Cliente",
            "po": "PO",
            "prioridad": "Prioridad",
            "calibre": "Calibre",
            "fecha": "Fecha OF",
            "nidos_str": "Nidos",
            "ruta_str": "Ruta"
        }, inplace=True)

        for col_fill in ["Proyecto", "Proyecto Cliente", "PO", "Prioridad", "Calibre", "Nidos", "Ruta"]:
            if col_fill not in df_all.columns:
                df_all[col_fill] = "—"
            else:
                df_all[col_fill] = df_all[col_fill].fillna("—").replace("", "—")

        df_all["Cantidad WIP"] = pd.to_numeric(df_all["Cantidad WIP"], errors="coerce").fillna(0).astype(int)
        return df_all

    # ── Función auxiliar: Generador de Excel Multi-Hoja con Pareto 80/20 ──
    def build_drilldown_pareto_excel(df_vista_actual, df_pareto_sku, df_detalle_of, df_resumen_of, titulo_estacion):
        import io
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            if not df_vista_actual.empty:
                df_vista_actual.to_excel(writer, sheet_name="Vista Actual", index=False)
                style_excel_sheet(writer, df_vista_actual, "Vista Actual")
            if not df_pareto_sku.empty:
                df_pareto_sku.to_excel(writer, sheet_name="Pareto Piezas (80-20)", index=False)
                style_excel_sheet(writer, df_pareto_sku, "Pareto Piezas (80-20)")
            if not df_detalle_of.empty:
                df_detalle_of.to_excel(writer, sheet_name="Detalle por OF y Pieza", index=False)
                style_excel_sheet(writer, df_detalle_of, "Detalle por OF y Pieza")
            if not df_resumen_of.empty:
                df_resumen_of.to_excel(writer, sheet_name="Resumen por OF", index=False)
                style_excel_sheet(writer, df_resumen_of, "Resumen por OF")
        return output.getvalue()

    # ══════════════════════════════════════════════════════════════════════════
    # PANTALLA NUEVA ESTILO ODOO: DETALLE + TABLA + PARETO (80/20) + EXCEL
    # ══════════════════════════════════════════════════════════════════════════
    active_drill_area = st.session_state.get("wip_drilldown_area", None)

    if active_drill_area:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots

        icon_act = process_icons.get(active_drill_area, "🏭")
        label_act = friendly_names.get(active_drill_area, active_drill_area)

        # Barra superior estilo Odoo (Breadcrumb + Botón Regresar + Selector Rápido)
        col_back, col_bread, col_switch = st.columns([1.1, 2.3, 1.6])
        with col_back:
            if st.button("⬅️ Volver al Dashboard WIP", type="primary", use_container_width=True, key="btn_back_wip_main"):
                st.session_state["wip_drilldown_area"] = None
                st.session_state.pop("wip_pareto_click_filter", None)
                st.rerun()

        with col_bread:
            st.markdown(
                f"""
                <div style="background:#f8f9fa; border:1px solid #dee2e6; border-left:5px solid #EC2024;
                            border-radius:8px; padding:10px 16px; display:flex; align-items:center; gap:8px;">
                    <span style="color:#6c757d; font-weight:600; font-size:0.95rem;">📊 Dashboard WIP Global</span>
                    <span style="color:#adb5bd; font-weight:bold;">/</span>
                    <span style="color:#111; font-weight:900; font-size:1.1rem; font-family:'Montserrat',sans-serif;">
                        {icon_act} {label_act.upper()}
                    </span>
                </div>
                """,
                unsafe_allow_html=True
            )

        with col_switch:
            switch_keys = relevant_procs + ["TOTAL_PISO", "TOTAL_GENERAL"]
            def _fmt_switch(k):
                cnt = (
                    sum(v for ak, v in wip_data.items() if ak not in ["Corte", "Ingenieria"])
                    if k == "TOTAL_PISO"
                    else (
                        sum(wip_data.get(p, 0) for p in relevant_procs)
                        if k == "TOTAL_GENERAL"
                        else wip_data.get(k, 0)
                    )
                )
                return f"{process_icons.get(k, '🏭')} {friendly_names.get(k, k)} ({cnt:,} pzs)"

            idx_curr = switch_keys.index(active_drill_area) if active_drill_area in switch_keys else 0
            new_area_sel = st.selectbox(
                "Cambiar estación rápidamente:",
                options=switch_keys,
                index=idx_curr,
                format_func=_fmt_switch,
                label_visibility="collapsed",
                key="odoo_quick_area_switcher"
            )
            if new_area_sel != active_drill_area:
                st.session_state["wip_drilldown_area"] = new_area_sel
                st.session_state.pop("wip_pareto_click_filter", None)
                st.rerun()

        # Obtener datos detallados para el área seleccionada
        df_rich = get_wip_pieces_rich_detail(of_list, active_drill_area)

        if df_rich.empty:
            st.info(f"✅ Actualmente no hay piezas pendientes en **{label_act}** para las OFs seleccionadas.")
            return

        # Calcular tablas base:
        # 1) Pareto agrupado por Pieza (SKU)
        df_pareto_sku = (
            df_rich.groupby(["No. Pieza", "Descripción"], as_index=False)
            .agg(
                Cantidad_WIP=("Cantidad WIP", "sum"),
                Cant_OFs=("OF", "nunique"),
                OFs_Involucradas=("OF", lambda s: ", ".join(sorted(set(str(x) for x in s)))),
                Proyectos=("Proyecto", lambda s: ", ".join(sorted(set(str(x) for x in s if str(x) != "—")))),
                Calibres=("Calibre", lambda s: ", ".join(sorted(set(str(x) for x in s if str(x) != "—"))))
            )
            .sort_values("Cantidad_WIP", ascending=False)
            .reset_index(drop=True)
        )
        total_wip_area = int(df_pareto_sku["Cantidad_WIP"].sum())
        df_pareto_sku["Ranking #"] = df_pareto_sku.index + 1
        df_pareto_sku["% Participación"] = (df_pareto_sku["Cantidad_WIP"] / max(1, total_wip_area) * 100).round(2)
        df_pareto_sku["% Acumulado"] = df_pareto_sku["% Participación"].cumsum().round(2).clip(upper=100.0)

        def _clasificar_abc(pct_acum, idx_row):
            if idx_row == 0 or pct_acum <= 80.0:
                return "🔴 A - Vital (80%)"
            elif pct_acum <= 95.0:
                return "🟠 B - Importante (15%)"
            return "🔵 C - Trivial (5%)"

        df_pareto_sku["Clase Pareto"] = [
            _clasificar_abc(row["% Acumulado"], idx) for idx, row in df_pareto_sku.iterrows()
        ]
        df_pareto_sku.rename(columns={
            "Cantidad_WIP": "Cantidad WIP",
            "Cant_OFs": "N° OFs",
            "OFs_Involucradas": "OFs Involucradas"
        }, inplace=True)

        # Mapear la Clase Pareto al detalle por OF y Pieza
        sku_to_clase = df_pareto_sku.set_index("No. Pieza")["Clase Pareto"].to_dict()
        df_rich = df_rich.sort_values("Cantidad WIP", ascending=False).reset_index(drop=True)
        df_rich["Ranking #"] = df_rich.index + 1
        df_rich["% del WIP"] = (df_rich["Cantidad WIP"] / max(1, total_wip_area) * 100).round(2)
        df_rich["% Acumulado"] = df_rich["% del WIP"].cumsum().round(2).clip(upper=100.0)
        df_rich["Clase Pareto"] = df_rich["No. Pieza"].map(sku_to_clase).fillna("🔵 C - Trivial (5%)")

        # 2) Consolidado por OF
        df_resumen_of = (
            df_rich.groupby(["OF", "Proyecto", "Proyecto Cliente", "PO", "Prioridad", "Calibre"], as_index=False)
            .agg(
                SKUs_Distintos=("No. Pieza", "nunique"),
                Cantidad_WIP=("Cantidad WIP", "sum")
            )
            .sort_values("Cantidad_WIP", ascending=False)
            .reset_index(drop=True)
        )
        df_resumen_of["Ranking #"] = df_resumen_of.index + 1
        df_resumen_of["% Participación"] = (df_resumen_of["Cantidad_WIP"] / max(1, total_wip_area) * 100).round(2)
        df_resumen_of["% Acumulado"] = df_resumen_of["% Participación"].cumsum().round(2).clip(upper=100.0)
        df_resumen_of.rename(columns={"SKUs_Distintos": "Piezas Distintas (SKUs)", "Cantidad_WIP": "Cantidad WIP"}, inplace=True)

        # ── KPIs Superiores de la Estación ──
        total_skus = len(df_pareto_sku)
        total_ofs_area = df_rich["OF"].nunique()
        top1_row = df_pareto_sku.iloc[0]
        skus_clase_a = len(df_pareto_sku[df_pareto_sku["Clase Pareto"].str.startswith("🔴")])
        pct_skus_a = (skus_clase_a / max(1, total_skus) * 100)

        k1, k2, k3, k4, k5 = st.columns(5)
        kpi_cards_data = [
            (k1, "PIEZAS EN WIP", f"{total_wip_area:,}", f"Estación: {label_act}", "#EC2024"),
            (k2, "PIEZAS DISTINTAS (SKUs)", f"{total_skus:,}", "Números de parte únicos", "#0056b3"),
            (k3, "ÓRDENES (OFs)", f"{total_ofs_area:,}", "Con material pendiente", "#6f42c1"),
            (k4, "PIEZA #1 MAYOR VOLUMEN", f"{int(top1_row['Cantidad WIP']):,} pzs", f"{top1_row['No. Pieza']} ({top1_row['% Participación']:.1f}%)", "#fd7e14"),
            (k5, "LEY DE PARETO (80/20)", f"{skus_clase_a} de {total_skus} SKUs", f"{pct_skus_a:.0f}% de piezas = 80% del WIP", "#28a745"),
        ]
        for col_k, k_title, k_val, k_sub, k_color in kpi_cards_data:
            with col_k:
                st.markdown(
                    f"""
                    <div style="background:#ffffff; border:1px solid #e2e8f0; border-top:4px solid {k_color};
                                border-radius:8px; padding:12px 10px; text-align:center; box-shadow:0 2px 5px rgba(0,0,0,0.05); margin-top:8px; margin-bottom:10px;">
                        <div style="font-size:0.74rem; color:#64748b; font-weight:800; text-transform:uppercase;">{k_title}</div>
                        <div style="font-size:1.75rem; font-weight:900; color:{k_color}; font-family:'Montserrat',sans-serif; margin:3px 0;">{k_val}</div>
                        <div style="font-size:0.75rem; color:#334155; font-weight:600; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">{k_sub}</div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

        # ── SECCIÓN 1: GRÁFICO DE PARETO INTERACTIVO (CANTIDAD Y PIEZAS MÁS IMPORTANTES) ──
        st.markdown("### 📊 Análisis de Pareto (80/20) — Piezas y Órdenes Más Importantes por Cantidad")
        col_p_dim, col_p_top = st.columns([2.2, 1.3])
        with col_p_dim:
            pareto_dim = st.radio(
                "Agrupar Gráfico de Pareto por:",
                [
                    "🔩 Por Pieza / No. Parte (SKUs más importantes)",
                    "📁 Por Orden de Fabricación (OF)",
                    "📂 Por Proyecto / PO",
                    "📏 Por Calibre"
                ],
                horizontal=True,
                key="odoo_pareto_dim_radio"
            )
        with col_p_top:
            top_n_choice = st.select_slider(
                "Cantidad de barras a mostrar en el Pareto:",
                options=["Top 10", "Top 15", "Top 25", "Top 40", "Todas"],
                value="Top 15",
                key="odoo_pareto_top_slider"
            )

        if pareto_dim.startswith("🔩"):
            df_p_plot = df_pareto_sku.copy()
            df_p_plot["Etiqueta"] = df_p_plot["No. Pieza"].astype(str)
            df_p_plot["Hover_Extra"] = df_p_plot["Descripción"].astype(str) + " | OFs: " + df_p_plot["OFs Involucradas"].astype(str)
            x_axis_title = "Número de Parte (Pieza)"
        elif pareto_dim.startswith("📁"):
            df_p_plot = df_resumen_of.copy()
            df_p_plot["Etiqueta"] = df_p_plot["OF"].astype(str)
            df_p_plot["Hover_Extra"] = "Proyecto: " + df_p_plot["Proyecto"].astype(str) + " | PO: " + df_p_plot["PO"].astype(str)
            df_p_plot["Clase Pareto"] = [
                _clasificar_abc(row["% Acumulado"], idx) for idx, row in df_p_plot.iterrows()
            ]
            x_axis_title = "Orden de Fabricación (OF)"
        elif pareto_dim.startswith("📂"):
            df_p_plot = (
                df_rich.groupby(["Proyecto", "PO"], as_index=False)["Cantidad WIP"]
                .sum()
                .sort_values("Cantidad WIP", ascending=False)
                .reset_index(drop=True)
            )
            df_p_plot["% Participación"] = (df_p_plot["Cantidad WIP"] / max(1, total_wip_area) * 100).round(2)
            df_p_plot["% Acumulado"] = df_p_plot["% Participación"].cumsum().round(2).clip(upper=100.0)
            df_p_plot["Clase Pareto"] = [_clasificar_abc(r["% Acumulado"], i) for i, r in df_p_plot.iterrows()]
            df_p_plot["Etiqueta"] = df_p_plot["Proyecto"].astype(str) + " (" + df_p_plot["PO"].astype(str) + ")"
            df_p_plot["Hover_Extra"] = df_p_plot["Etiqueta"]
            x_axis_title = "Proyecto / PO"
        else:
            df_p_plot = (
                df_rich.groupby("Calibre", as_index=False)["Cantidad WIP"]
                .sum()
                .sort_values("Cantidad WIP", ascending=False)
                .reset_index(drop=True)
            )
            df_p_plot["% Participación"] = (df_p_plot["Cantidad WIP"] / max(1, total_wip_area) * 100).round(2)
            df_p_plot["% Acumulado"] = df_p_plot["% Participación"].cumsum().round(2).clip(upper=100.0)
            df_p_plot["Clase Pareto"] = [_clasificar_abc(r["% Acumulado"], i) for i, r in df_p_plot.iterrows()]
            df_p_plot["Etiqueta"] = df_p_plot["Calibre"].astype(str)
            df_p_plot["Hover_Extra"] = "Calibre: " + df_p_plot["Calibre"].astype(str)
            x_axis_title = "Calibre"

        if top_n_choice != "Todas":
            n_limit = int(top_n_choice.replace("Top ", ""))
            df_p_view = df_p_plot.head(n_limit).copy()
        else:
            df_p_view = df_p_plot.copy()

        bar_colors = [
            "#EC2024" if str(c).startswith("🔴") else ("#FF8C00" if str(c).startswith("🟠") else "#6C757D")
            for c in df_p_view["Clase Pareto"]
        ]

        fig_pareto = make_subplots(specs=[[{"secondary_y": True}]])
        fig_pareto.add_trace(
            go.Bar(
                x=df_p_view["Etiqueta"],
                y=df_p_view["Cantidad WIP"],
                name="Cantidad Piezas (WIP)",
                marker_color=bar_colors,
                text=df_p_view["Cantidad WIP"].apply(lambda v: f"{int(v):,}"),
                textposition="outside",
                customdata=df_p_view[["Hover_Extra", "% Participación", "% Acumulado", "Clase Pareto"]].values,
                hovertemplate=(
                    "<b>%{x}</b><br>"
                    "%{customdata[0]}<br>"
                    "<b>Cantidad WIP:</b> %{y:,} pzs<br>"
                    "<b>% del Total:</b> %{customdata[1]:.1f}%<br>"
                    "<b>% Acumulado:</b> %{customdata[2]:.1f}%<br>"
                    "<b>Clasificación:</b> %{customdata[3]}<extra></extra>"
                )
            ),
            secondary_y=False
        )
        fig_pareto.add_trace(
            go.Scatter(
                x=df_p_view["Etiqueta"],
                y=df_p_view["% Acumulado"],
                name="% Acumulado (Curva Pareto)",
                mode="lines+markers+text",
                text=df_p_view["% Acumulado"].apply(lambda v: f"{v:.0f}%"),
                textposition="top center",
                line=dict(color="#111111", width=3),
                marker=dict(size=8, color="#FFD700", line=dict(color="#111111", width=2)),
                hovertemplate="<b>%{x}</b><br>% Acumulado: <b>%{y:.1f}%</b><extra></extra>"
            ),
            secondary_y=True
        )
        # Línea de referencia 80%
        fig_pareto.add_hline(
            y=80,
            line_dash="dash",
            line_color="#28a745",
            line_width=2,
            annotation_text="Umbral 80% Pareto (Clase A)",
            annotation_position="bottom right",
            secondary_y=True
        )
        max_y_bar = int(df_p_view["Cantidad WIP"].max()) if not df_p_view.empty else 10
        fig_pareto.update_layout(
            title=f"<b>Gráfico de Pareto 80/20 — {label_act} ({len(df_p_view)} mostrados de {len(df_p_plot)})</b>  <span style='font-size:12px;color:#555;'>[🔴 Clase A (0-80%) | 🟠 Clase B (80-95%) | 🔵 Clase C (95-100%)]</span>",
            xaxis_title=x_axis_title,
            height=430,
            margin=dict(t=55, b=70, l=50, r=50),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            hovermode="x unified",
            xaxis_tickangle=-30
        )
        fig_pareto.update_yaxes(title_text="<b>Cantidad de Piezas (WIP)</b>", range=[0, max_y_bar * 1.18], secondary_y=False)
        fig_pareto.update_yaxes(title_text="<b>% Acumulado</b>", range=[0, 108], ticksuffix="%", secondary_y=True)

        st.plotly_chart(fig_pareto, use_container_width=True, key="odoo_drilldown_pareto_chart")

        # ── SECCIÓN 2: TABLA INTERACTIVA CON MÚLTIPLES PRESENTACIONES, ORDENAMIENTOS Y DESCARGA EXCEL ──
        st.markdown("---")
        st.markdown("### 📋 Tabla de Detalle, Presentaciones y Descarga en Excel")

        col_pres, col_sort, col_abc, col_search = st.columns([1.6, 1.4, 1.1, 1.4])
        with col_pres:
            presentacion_sel = st.selectbox(
                "📑 Presentación de la Tabla:",
                [
                    "🔩 Pareto por Pieza / SKU (Piezas más importantes por cantidad)",
                    "📋 Detalle Completo (Por OF, Nido y Pieza)",
                    "📁 Consolidado por Orden de Fabricación (OF)",
                    "🏷️ Consolidado por Proyecto / PO y Calibre"
                ],
                index=0,
                key="odoo_table_presentation"
            )
        with col_sort:
            orden_sel = st.selectbox(
                "🔃 Ordenar por:",
                [
                    "🔥 Mayor a Menor Cantidad WIP (Pareto)",
                    "❄️ Menor a Mayor Cantidad WIP",
                    "🔤 Número de Pieza / Clave (A-Z)",
                    "📝 Descripción / Proyecto (A-Z)",
                    "🔢 Orden de Fabricación (OF)"
                ],
                index=0,
                key="odoo_table_sort"
            )
        with col_abc:
            filtro_abc = st.selectbox(
                "🎯 Filtrar Clase Pareto:",
                [
                    "Todas las Clases",
                    "🔴 Solo Clase A (Vitales 80%)",
                    "🟠 Solo Clase B (Importantes 15%)",
                    "🔵 Solo Clase C (Triviales 5%)"
                ],
                index=0,
                key="odoo_table_abc_filter"
            )
        with col_search:
            texto_buscar = st.text_input(
                "🔍 Buscar Pieza / Descripción / OF / PO:",
                value="",
                placeholder="Ej. 12-D-6030, OF 00127...",
                key="odoo_table_search"
            )

        # Seleccionar DataFrame según la presentación elegida
        if presentacion_sel.startswith("🔩"):
            df_table_view = df_pareto_sku[[
                "Ranking #", "Clase Pareto", "No. Pieza", "Descripción",
                "Cantidad WIP", "% Participación", "% Acumulado",
                "N° OFs", "OFs Involucradas", "Proyectos", "Calibres"
            ]].copy()
        elif presentacion_sel.startswith("📋"):
            cols_det = [
                "Ranking #", "Clase Pareto", "OF", "Proyecto", "Proyecto Cliente",
                "PO", "Prioridad", "Calibre", "Nidos", "No. Pieza", "Descripción",
                "Cantidad WIP", "% del WIP", "% Acumulado", "Ruta"
            ]
            if active_drill_area in ["TOTAL_PISO", "TOTAL_GENERAL"]:
                cols_det.insert(2, "Estación")
            df_table_view = df_rich[[c for c in cols_det if c in df_rich.columns]].copy()
        elif presentacion_sel.startswith("📁"):
            df_res_of_copy = df_resumen_of.copy()
            df_res_of_copy["Clase Pareto"] = [
                _clasificar_abc(r["% Acumulado"], i) for i, r in df_res_of_copy.iterrows()
            ]
            df_table_view = df_res_of_copy[[
                "Ranking #", "Clase Pareto", "OF", "Proyecto", "Proyecto Cliente",
                "PO", "Prioridad", "Calibre", "Piezas Distintas (SKUs)",
                "Cantidad WIP", "% Participación", "% Acumulado"
            ]].copy()
        else:
            df_proy_cal = (
                df_rich.groupby(["Proyecto", "Proyecto Cliente", "PO", "Calibre"], as_index=False)
                .agg(
                    OFs=("OF", "nunique"),
                    SKUs=("No. Pieza", "nunique"),
                    Cantidad_WIP=("Cantidad WIP", "sum")
                )
                .sort_values("Cantidad_WIP", ascending=False)
                .reset_index(drop=True)
            )
            df_proy_cal["Ranking #"] = df_proy_cal.index + 1
            df_proy_cal["% Participación"] = (df_proy_cal["Cantidad_WIP"] / max(1, total_wip_area) * 100).round(2)
            df_proy_cal["% Acumulado"] = df_proy_cal["% Participación"].cumsum().round(2).clip(upper=100.0)
            df_proy_cal["Clase Pareto"] = [_clasificar_abc(r["% Acumulado"], i) for i, r in df_proy_cal.iterrows()]
            df_proy_cal.rename(columns={"Cantidad_WIP": "Cantidad WIP"}, inplace=True)
            df_table_view = df_proy_cal[[
                "Ranking #", "Clase Pareto", "Proyecto", "Proyecto Cliente", "PO",
                "Calibre", "OFs", "SKUs", "Cantidad WIP", "% Participación", "% Acumulado"
            ]].copy()

        # Aplicar filtro Clase ABC
        if filtro_abc != "Todas las Clases" and "Clase Pareto" in df_table_view.columns:
            prefix_abc = filtro_abc.split()[0]  # 🔴, 🟠, 🔵
            df_table_view = df_table_view[df_table_view["Clase Pareto"].str.startswith(prefix_abc)]

        # Aplicar buscador de texto
        if texto_buscar.strip():
            q_str = texto_buscar.strip().lower()
            mask_txt = df_table_view.astype(str).apply(lambda col: col.str.lower().str.contains(q_str, na=False)).any(axis=1)
            df_table_view = df_table_view[mask_txt]

        # Aplicar ordenamiento dinámico
        if orden_sel.startswith("🔥") and "Cantidad WIP" in df_table_view.columns:
            df_table_view = df_table_view.sort_values("Cantidad WIP", ascending=False)
        elif orden_sel.startswith("❄️") and "Cantidad WIP" in df_table_view.columns:
            df_table_view = df_table_view.sort_values("Cantidad WIP", ascending=True)
        elif orden_sel.startswith("🔤"):
            col_key = "No. Pieza" if "No. Pieza" in df_table_view.columns else ("OF" if "OF" in df_table_view.columns else "Proyecto")
            df_table_view = df_table_view.sort_values(col_key, ascending=True)
        elif orden_sel.startswith("📝"):
            col_desc = "Descripción" if "Descripción" in df_table_view.columns else "Proyecto"
            df_table_view = df_table_view.sort_values(col_desc, ascending=True)
        elif orden_sel.startswith("🔢"):
            col_of = "OF" if "OF" in df_table_view.columns else ("OFs Involucradas" if "OFs Involucradas" in df_table_view.columns else "Ranking #")
            df_table_view = df_table_view.sort_values(col_of, ascending=True)

        # Botones de descarga Excel (.xlsx) y CSV arriba y abajo de la tabla
        excel_bytes_drill = build_drilldown_pareto_excel(
            df_vista_actual=df_table_view,
            df_pareto_sku=df_pareto_sku,
            df_detalle_of=df_rich,
            df_resumen_of=df_resumen_of,
            titulo_estacion=label_act
        )
        csv_bytes_drill = df_table_view.to_csv(index=False).encode("utf-8-sig")
        clean_area_fn = active_drill_area.replace(" ", "_")

        col_btn_xl, col_btn_csv, col_info_cnt = st.columns([1.8, 1.4, 1.8])
        with col_btn_xl:
            st.download_button(
                label=f"📥 Descargar Excel con Pareto y Detalle ({label_act}) [.xlsx]",
                data=excel_bytes_drill,
                file_name=f"Pareto_y_Detalle_WIP_{clean_area_fn}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary",
                use_container_width=True,
                key="btn_dl_excel_drill_top"
            )
        with col_btn_csv:
            st.download_button(
                label="📄 Descargar Tabla Actual (.csv)",
                data=csv_bytes_drill,
                file_name=f"Tabla_WIP_{clean_area_fn}.csv",
                mime="text/csv",
                use_container_width=True,
                key="btn_dl_csv_drill_top"
            )
        with col_info_cnt:
            suma_filtrada = int(df_table_view["Cantidad WIP"].sum()) if "Cantidad WIP" in df_table_view.columns else 0
            st.markdown(
                f"<div style='padding:8px 12px; background:#f1f5f9; border-radius:6px; text-align:right; font-weight:700; color:#1e293b;'>"
                f"Mostrando <b>{len(df_table_view):,}</b> registros | Total filtrado: <span style='color:#EC2024;font-size:1.05rem;'>{suma_filtrada:,} pzs</span>"
                f"</div>",
                unsafe_allow_html=True
            )

        # Configurar columnas visuales para st.dataframe
        col_cfg = {}
        if "% Participación" in df_table_view.columns:
            col_cfg["% Participación"] = st.column_config.ProgressColumn(
                "% del WIP", min_value=0, max_value=100, format="%.1f%%"
            )
        if "% del WIP" in df_table_view.columns:
            col_cfg["% del WIP"] = st.column_config.ProgressColumn(
                "% del WIP", min_value=0, max_value=100, format="%.1f%%"
            )
        if "% Acumulado" in df_table_view.columns:
            col_cfg["% Acumulado"] = st.column_config.NumberColumn(
                "% Acumulado (Pareto)", format="%.1f%%"
            )
        if "Cantidad WIP" in df_table_view.columns:
            col_cfg["Cantidad WIP"] = st.column_config.NumberColumn(
                "Cantidad WIP (Pzs)", format="%d"
            )

        st.dataframe(
            df_table_view,
            use_container_width=True,
            height=460,
            hide_index=True,
            column_config=col_cfg
        )
        return

    # ══════════════════════════════════════════════════════════════════════════
    # PANTALLA PRINCIPAL: DASHBOARD DE REPORTES Y WIP GLOBAL (TARJETAS CLICABLES)
    # ══════════════════════════════════════════════════════════════════════════
    if wip_data and any(v > 0 for v in wip_data.values()) or True:
        st.markdown(f"### 🏭 Piezas Disponibles (WIP) por Área para {display_name}")
        st.markdown("💡 **Tip estilo Odoo:** Da clic directamente sobre cualquier **tarjeta de piezas (ej. 709 Piezas por cortar)** o sobre las **barras de la gráfica** para abrir la pantalla con el **Detalle en Tabla, Gráfico de Pareto (80/20) y Descarga en Excel**.")
        
        # Calcular Total en Piso excluyendo Corte
        total_piso = sum(v for k, v in wip_data.items() if k not in ["Corte", "Ingenieria"])
        total_general = sum(wip_data.get(p, 0) for p in relevant_procs)
        pct_piso = (total_piso / total_general * 100) if total_general > 0 else 0
        
        st.markdown(
            f'''
            <div style="background-color: #e6f3ff; border-top: 5px solid #0056b3; padding: 20px; border-radius: 8px; margin-bottom: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); display: flex; justify-content: space-around; align-items: center; position: relative;">
                <div data-drill-label="Ver Detalle en Piso" style="text-align: center; width: 45%; cursor: pointer; transition: transform 0.15s;" title="Clic para abrir Detalle y Pareto de Total en Piso">
                    <div style="position: absolute; top: 10px; left: 10px; background-color: #cce5ff; color: #004085; padding: 2px 8px; border-radius: 12px; font-size: 0.85rem; font-weight: bold; box-shadow: inset 0 1px 2px rgba(0,0,0,0.1);">{pct_piso:.1f}%</div>
                    <p style="margin: 0; font-size: 1.1rem; color: #555; font-weight: bold; text-transform: uppercase;">🏭 TOTAL EN PISO (EXCLUYENDO CORTE)</p>
                    <div style="margin: 5px 0 0 0; font-size: 4rem; font-weight: 900; color: #0056b3;">{total_piso}</div>
                </div>
                <div style="width: 2px; height: 80px; background-color: #b3d7ff;"></div>
                <div data-drill-label="Ver Detalle Total OFs" style="text-align: center; width: 45%; cursor: pointer; transition: transform 0.15s;" title="Clic para abrir Detalle y Pareto Total">
                    <p style="margin: 0; font-size: 1.1rem; color: #333; font-weight: bold; text-transform: uppercase;">📦 TOTAL DE LAS OF SELECCIONADAS</p>
                    <div style="margin: 5px 0 0 0; font-size: 4rem; font-weight: 900; color: #111;">{total_general}</div>
                </div>
            </div>
            ''', unsafe_allow_html=True
        )
        col_top_b1, col_top_b2 = st.columns(2)
        with col_top_b1:
            if st.button(f"🔍 Ver Detalle en Piso ({total_piso:,} pzs) — Tabla y Pareto", key="btn_drill_total_piso", use_container_width=True):
                st.session_state["wip_drilldown_area"] = "TOTAL_PISO"
                st.rerun()
        with col_top_b2:
            if st.button(f"🔍 Ver Detalle Total OFs ({total_general:,} pzs) — Tabla y Pareto", key="btn_drill_total_gen", use_container_width=True):
                st.session_state["wip_drilldown_area"] = "TOTAL_GENERAL"
                st.rerun()

        st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
        cols = st.columns(4)
        
        for i, proc in enumerate(relevant_procs):
            with cols[i % 4]:
                wip_val = wip_data.get(proc, 0)
                color = "#EC2024" if wip_val > 0 else "#28a745"
                icon = process_icons.get(proc, "🏭")
                pct = (wip_val / total_general * 100) if total_general > 0 else 0
                label = friendly_names.get(proc, proc)
                btn_label_short = f"🔍 {label} ({wip_val:,})"
                st.markdown(
                    f'''
                    <div class="odoo-wip-card" data-drill-label="{btn_label_short}"
                         style="background-color: #f8f9fa; border-top: 5px solid {color}; padding: 18px 15px 12px 15px; border-radius: 8px 8px 0 0; margin-bottom: 0px; text-align: center; box-shadow: 0 4px 6px rgba(0,0,0,0.08); position: relative; cursor: pointer; transition: all 0.15s ease;"
                         title="Clic para abrir Detalle en Tabla y Pareto de {label}">
                        <div style="position: absolute; top: 10px; right: 10px; background-color: #e9ecef; color: #495057; padding: 2px 8px; border-radius: 12px; font-size: 0.85rem; font-weight: bold; box-shadow: inset 0 1px 2px rgba(0,0,0,0.1);">{pct:.1f}%</div>
                        <div style="font-size: 2.2rem; margin-bottom: 4px;">{icon}</div>
                        <p style="margin: 0; font-size: 0.95rem; color: #555; font-weight: bold; text-transform: uppercase;">{label}</p>
                        <h2 style="margin: 4px 0 2px 0; font-size: 3rem; font-weight: 900; color: {color};">{wip_val}</h2>
                        <div style="font-size: 0.72rem; color: #6c757d; font-weight: 600; margin-top: 2px;">📊 Clic para ver Tabla y Pareto ➔</div>
                    </div>
                    ''', unsafe_allow_html=True
                )
                if st.button(btn_label_short, key=f"btn_wip_card_{proc}", use_container_width=True):
                    st.session_state["wip_drilldown_area"] = proc
                    st.rerun()
                st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)

        # Script JS ligero para que dar clic en cualquier parte de la tarjeta HTML dispare el botón inmediatamente
        import streamlit.components.v1 as components
        components.html(
            """
            <script>
            (function() {
                const doc = window.parent.document;
                function bindOdooCards() {
                    const cards = doc.querySelectorAll('[data-drill-label]');
                    cards.forEach(card => {
                        if (card.dataset.boundClick) return;
                        card.dataset.boundClick = "1";
                        card.addEventListener('mouseenter', () => {
                            card.style.transform = 'translateY(-3px)';
                            card.style.boxShadow = '0 8px 16px rgba(236,32,36,0.18)';
                        });
                        card.addEventListener('mouseleave', () => {
                            card.style.transform = 'none';
                            card.style.boxShadow = '0 4px 6px rgba(0,0,0,0.08)';
                        });
                        card.addEventListener('click', () => {
                            const targetText = card.getAttribute('data-drill-label');
                            const buttons = doc.querySelectorAll('button');
                            for (const btn of buttons) {
                                if (btn.innerText && btn.innerText.includes(targetText)) {
                                    btn.click();
                                    break;
                                }
                            }
                        });
                    });
                }
                bindOdooCards();
                setTimeout(bindOdooCards, 400);
                setTimeout(bindOdooCards, 1200);
            })();
            </script>
            """,
            height=0
        )

        # Tabs para Gráfica de Pareto y Tendencia
        tab_pareto_act, tab_tendencia_wip = st.tabs([
            "📊 Cuello de Botella Actual (Pareto — Clic en Barra para Detalle)",
            "📈 Histórico y Tendencia del WIP (Lunes a Sábado)"
        ])
        
        with tab_pareto_act:
            df_chart = pd.DataFrame({
                "Proceso": [friendly_names.get(p, p) for p in relevant_procs],
                "WIP Disponible": [wip_data.get(p, 0) for p in relevant_procs]
            })
            fig = px.bar(
                df_chart,
                x="Proceso",
                y="WIP Disponible",
                title="Distribución del Cuello de Botella (WIP en Piso) — 💡 Haz clic en cualquier barra para abrir su Detalle y Pareto",
                color="WIP Disponible",
                color_continuous_scale="Reds",
                text_auto=True
            )
            fig.update_layout(xaxis_title="Área / Proceso", yaxis_title="Cantidad de Piezas en WIP")
            chart_event = st.plotly_chart(
                fig,
                use_container_width=True,
                on_select="rerun",
                selection_mode="points",
                key="wip_bottleneck_clickable_chart"
            )
            if chart_event and hasattr(chart_event, "selection") and chart_event.selection:
                pts = chart_event.selection.get("points", [])
                if pts:
                    clicked_proc_friendly = pts[0].get("x")
                    if clicked_proc_friendly in inv_friendly_names:
                        st.session_state["wip_drilldown_area"] = inv_friendly_names[clicked_proc_friendly]
                        st.rerun()
            
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
        
        # --- DETALLE RÁPIDO POR SELECTOR (TAMBIÉN ABRE VISTA COMPLETA) ---
        st.markdown("### 🔍 Acceso Rápido a Detalle y Pareto por Proceso")
        col_sel_q, col_btn_q = st.columns([2.5, 1.5])
        with col_sel_q:
            proc_wip_options = ["Selecciona un área..."] + [friendly_names[p] for p in relevant_procs]
            proc_wip_selected_friendly = st.selectbox(
                "Selecciona un Proceso/Área:", 
                proc_wip_options,
                key="wip_detail_selector"
            )
        with col_btn_q:
            st.markdown("<div style='height:28px;'></div>", unsafe_allow_html=True)
            if proc_wip_selected_friendly != "Selecciona un área...":
                proc_wip_selected = inv_friendly_names[proc_wip_selected_friendly]
                if st.button(f"🚀 Abrir Pantalla Pareto y Detalle de {proc_wip_selected_friendly}", type="primary", use_container_width=True):
                    st.session_state["wip_drilldown_area"] = proc_wip_selected
                    st.rerun()
        
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
                "Empaque": "x-Empacar"
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

        file_sufix = "Multiples" if len(of_list) != 1 or "Todas" in of_list else of_list[0]
        
        col_dl1, col_dl2 = st.columns(2)
        with col_dl1:
            st.download_button(
                label="📊 Descargar Reporte de Transacciones (Excel)",
                data=lambda: get_excel_report(of_list),
                file_name=f"Reporte_Transacciones_OF_{file_sufix}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
        with col_dl2:
            st.download_button(
                label="📥 Descargar Reporte Detallado de WIP por Área (Excel)",
                data=lambda: get_wip_consolidado_excel(of_list),
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
        dias_letras = ["L", "M", "M", "J", "V", "S", "D"]
        # Labels con fecha real para identificar cada día claramente en el chart
        dias_labels = [f"{dias_letras[i]}-{(lunes + pd.Timedelta(days=i)).strftime('%d')}" for i in range(7)]
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
        
        # Para calcular delta (reducción diaria del WIP)
        wip_prev_by_area = {}  # WIP del día anterior por área
        wip_delta_areas = []
        wip_delta_dias = []
        wip_delta_valores = []
        
        total_produccion_semana = 0
        
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
            
            # Calcular WIP de este día (acumulado hasta este día)
            wip_on_date = calculate_wip_on_date(of_list, date_str)
            
            # Sumar producción total del día para detectar semanas vacías
            total_produccion_semana += (df_av_d['total'].sum() if not df_av_d.empty else 0)
            
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
                
                # WIP absoluto
                w_val = wip_on_date.get(proc, 0)
                wip_areas.append(proc_friendly)
                wip_dias.append(day_label)
                wip_valores.append(int(w_val))
                
                # Delta: reducción del WIP respecto al día anterior
                prev_wip = wip_prev_by_area.get(proc, None)
                if prev_wip is not None:
                    delta = prev_wip - w_val  # positivo = bajó el WIP (se avanzó)
                else:
                    delta = 0  # primer día, sin comparación
                wip_delta_areas.append(proc_friendly)
                wip_delta_dias.append(day_label)
                wip_delta_valores.append(int(delta))
                wip_prev_by_area[proc] = w_val
                
        conn.close()
        
        # Aviso si la semana seleccionada no tiene producción registrada
        if total_produccion_semana == 0:
            st.warning(
                f"⚠️ La semana del {lunes.strftime('%d/%m/%Y')} al {dias_semana[-1].strftime('%d/%m/%Y')} "
                f"**no tiene avances de producción registrados**. "
                f"Los valores del WIP se muestran tal como quedaron al final de la semana anterior sin variación diaria. "
                f"Selecciona otra semana con producción registrada para ver la evolución diaria."
            )
        
        # Crear pestañas para las 3 gráficas
        tab_prod_w, tab_scrap_w, tab_wip_w = st.tabs([
            "📈 Producción Semanal (L-M-M-J-V-S-D)",
            "🚨 Scrap Semanal (L-M-M-J-V-S-D)",
            "⏳ WIP Semanal (L-M-M-J-V-S-D)"
        ])
        
        import plotly.graph_objects as go
        
        # Paleta de colores para los días L M M J V S D
        colors_days = ['#FFD700', '#FF8C00', '#FF4500', '#EC2024', '#9370DB', '#00BFFF', '#32CD32']
        
        # Construir listas de colores repetidas (usando índice del label)
        prod_colors_list = [colors_days[dias_labels.index(d)] for d in prod_dias]
        scrap_colors_list = [colors_days[dias_labels.index(d)] for d in scrap_dias]
        wip_colors_list = [colors_days[dias_labels.index(d)] for d in wip_dias]
        wip_delta_colors_list = [colors_days[dias_labels.index(d)] for d in wip_delta_dias]
        
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
            st.markdown("**WIP Acumulado al Final de Cada Día** — piezas en espera de ser procesadas")
            fig_w = go.Figure()
            fig_w.add_trace(go.Bar(
                x=[wip_areas, wip_dias],
                y=wip_valores,
                marker_color=wip_colors_list,
                text=wip_valores,
                textposition='outside'
            ))
            fig_w.update_layout(
                title=f"<b>WIP por Estación al Cierre de Cada Día (Semana {lunes.strftime('%d/%m/%Y')} – {dias_semana[-1].strftime('%d/%m/%Y')})</b>",
                title_x=0.5,
                xaxis_title="Proceso / Día de la Semana",
                yaxis_title="Piezas en WIP",
                height=450,
                margin=dict(t=50, b=50, l=40, r=40)
            )
            st.plotly_chart(fig_w, use_container_width=True)
            
            st.markdown("---")
            st.markdown("**Reducción Diaria del WIP** — cuántas piezas se avanzaron por área cada día (WIP día anterior − WIP día actual)")
            fig_delta = go.Figure()
            fig_delta.add_trace(go.Bar(
                x=[wip_delta_areas, wip_delta_dias],
                y=wip_delta_valores,
                marker_color=wip_delta_colors_list,
                text=wip_delta_valores,
                textposition='outside'
            ))
            fig_delta.update_layout(
                title=f"<b>Reducción Diaria del WIP por Estación (Semana {lunes.strftime('%d/%m/%Y')} – {dias_semana[-1].strftime('%d/%m/%Y')})</b>",
                title_x=0.5,
                xaxis_title="Proceso / Día de la Semana",
                yaxis_title="Piezas avanzadas (WIP reducido)",
                height=450,
                margin=dict(t=50, b=50, l=40, r=40)
            )
            st.plotly_chart(fig_delta, use_container_width=True)
        
    else:
        st.info("No hay datos para esta OF.")
