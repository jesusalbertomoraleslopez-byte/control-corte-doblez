import streamlit as st
import pandas as pd
import sqlite3
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET
import io
from views.reportes import view_reportes

from utils.database import get_connection as _get_db_connection

def get_connection():
    return _get_db_connection()

def fetch_data(query, params=()):
    conn = get_connection()
    df = pd.read_sql(query, conn, params=params)
    conn.close()
    return df

def convert_df(df):
    return df.to_csv(index=False).encode('utf-8')

def get_sample_req_excel():
    import io
    output = io.BytesIO()
    df_sample = pd.DataFrame([
        {"SKU": "12-D-6090-05", "Total": 10},
        {"SKU": "11-A-6034-01", "Total": 25},
        {"SKU": "NUEVA_PIEZA_EJEMPLO", "Total": 5}
    ])
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_sample.to_excel(writer, index=False, sheet_name="Requerimiento")
    return output.getvalue()

def calculate_sku_wip_report(df_uploaded, of_list):
    from utils.database import get_connection
    from views.reportes import get_area_anterior
    from views.avances import PROCESSES
    
    conn = get_connection()
    if "Todas" in of_list:
        df_db_pzs = pd.read_sql_query("""
            SELECT p.of_number, p.no_pieza, p.cantidad, n.hojas, p.ruta, p.nido 
            FROM piezas p
            LEFT JOIN nidos n ON p.of_number = n.of_number AND p.nido = n.nido
        """, conn)
        df_avances = pd.read_sql_query("SELECT of_number, nido, no_pieza, area, SUM(cantidad) as cantidad FROM avances GROUP BY of_number, nido, no_pieza, area", conn)
        df_rechazos = pd.read_sql_query("SELECT of_number, nido, no_pieza, area, SUM(cantidad) as cantidad FROM rechazos GROUP BY of_number, nido, no_pieza, area", conn)
        
        c = conn.cursor()
        c.execute("""
            SELECT n.of_number, n.nido 
            FROM nidos n 
            LEFT JOIN avances a ON n.of_number = a.of_number AND n.nido = a.nido AND a.area = 'Corte'
            GROUP BY n.of_number, n.nido, n.hojas
            HAVING COUNT(DISTINCT a.hoja) >= n.hojas
        """)
        nidos_cortados = set((row[0], row[1]) for row in c.fetchall())
    else:
        placeholders = ",".join(["?"] * len(of_list))
        df_db_pzs = pd.read_sql_query(f"""
            SELECT p.of_number, p.no_pieza, p.cantidad, n.hojas, p.ruta, p.nido 
            FROM piezas p
            LEFT JOIN nidos n ON p.of_number = n.of_number AND p.nido = n.nido
            WHERE p.of_number IN ({placeholders})
        """, conn, params=tuple(of_list))
        df_avances = pd.read_sql_query(f"SELECT of_number, nido, no_pieza, area, SUM(cantidad) as cantidad FROM avances WHERE of_number IN ({placeholders}) GROUP BY of_number, nido, no_pieza, area", conn, params=tuple(of_list))
        df_rechazos = pd.read_sql_query(f"SELECT of_number, nido, no_pieza, area, SUM(cantidad) as cantidad FROM rechazos WHERE of_number IN ({placeholders}) GROUP BY of_number, nido, no_pieza, area", conn, params=tuple(of_list))
        
        c = conn.cursor()
        c.execute(f"""
            SELECT n.of_number, n.nido 
            FROM nidos n 
            LEFT JOIN avances a ON n.of_number = a.of_number AND n.nido = a.nido AND a.area = 'Corte'
            WHERE n.of_number IN ({placeholders})
            GROUP BY n.of_number, n.nido, n.hojas
            HAVING COUNT(DISTINCT a.hoja) >= n.hojas
        """, tuple(of_list))
        nidos_cortados = set((row[0], row[1]) for row in c.fetchall())
    conn.close()
    
    df_db_pzs["no_pieza"] = df_db_pzs["no_pieza"].astype(str).str.strip()
    df_avances["no_pieza"] = df_avances["no_pieza"].astype(str).str.strip()
    df_rechazos["no_pieza"] = df_rechazos["no_pieza"].astype(str).str.strip()
    
    df_db_pzs["total_requeridas"] = pd.to_numeric(df_db_pzs["cantidad"], errors="coerce").fillna(0) * pd.to_numeric(df_db_pzs["hojas"], errors="coerce").fillna(1)
    
    avances_nido_map = df_avances.set_index(["of_number", "nido", "no_pieza", "area"])["cantidad"].to_dict()
    rechazos_nido_map = df_rechazos.set_index(["of_number", "nido", "no_pieza", "area"])["cantidad"].to_dict()
    
    df_av_of = df_avances.groupby(["of_number", "no_pieza", "area"])["cantidad"].sum().reset_index()
    df_re_of = df_rechazos.groupby(["of_number", "no_pieza", "area"])["cantidad"].sum().reset_index()
    avances_of_map = df_av_of.set_index(["of_number", "no_pieza", "area"])["cantidad"].to_dict()
    rechazos_of_map = df_re_of.set_index(["of_number", "no_pieza", "area"])["cantidad"].to_dict()
    
    areas_wip = ["Diseñar", "Corte", "Rebabeo", "Doblez", "Barrenado", "Pintura", "Liberado", "Empaque"]
    report_rows = []
    
    for _, row in df_uploaded.iterrows():
        sku = str(row["SKU"]).strip()
        total_req = int(row["Total"])
        
        df_p_db = df_db_pzs[df_db_pzs["no_pieza"] == sku]
        
        wip_row = {
            "SKU": sku,
            "Total": total_req,
            "Piezas por Diseñar": 0,
            "Piezas por Cortar": 0,
            "Piezas por Rebabear": 0,
            "Piezas por Doblar": 0,
            "Piezas por Barrenar": 0,
            "Piezas por Pintar": 0,
            "Piezas por Liberar": 0,
            "Piezas por Empacar": 0
        }
        
        if df_p_db.empty:
            wip_row["Piezas por Diseñar"] = total_req
        else:
            sku_wip = {a: 0 for a in areas_wip}
            for of_num, grp_of in df_p_db.groupby("of_number"):
                for nido_num, grp_nido in grp_of.groupby("nido"):
                    is_cortado = (of_num, nido_num) in nidos_cortados
                    if not is_cortado:
                        req_nido = int(grp_nido["total_requeridas"].sum())
                        corte_av = avances_nido_map.get((of_num, nido_num, sku, "Corte"), 0)
                        sku_wip["Corte"] += max(0, req_nido - corte_av)
                
                ruta_str = str(grp_of["ruta"].iloc[0])
                ruta_proc = [p.strip() for p in ruta_str.split(",") if p.strip()]
                for idx_proc, area in enumerate(ruta_proc):
                    if area == "Corte":
                        continue
                    if idx_proc > 0:
                        area_ant = ruta_proc[idx_proc - 1]
                    else:
                        area_ant = None
                        
                    if area_ant == "Corte" or area_ant is None:
                        qty_in = avances_of_map.get((of_num, sku, "Corte"), 0)
                    else:
                        qty_in = avances_of_map.get((of_num, sku, area_ant), 0)
                        
                    qty_out = avances_of_map.get((of_num, sku, area), 0) + rechazos_of_map.get((of_num, sku, area), 0)
                    wip_area_val = max(0, qty_in - qty_out)
                    if area in sku_wip:
                        sku_wip[area] += wip_area_val
                        
            wip_row["Piezas por Cortar"] = sku_wip.get("Corte", 0)
            wip_row["Piezas por Rebabear"] = sku_wip.get("Rebabeo", 0)
            wip_row["Piezas por Doblar"] = sku_wip.get("Doblez", 0)
            wip_row["Piezas por Barrenar"] = sku_wip.get("Barrenado", 0)
            wip_row["Piezas por Pintar"] = sku_wip.get("Pintura", 0)
            wip_row["Piezas por Liberar"] = sku_wip.get("Liberado", 0)
            wip_row["Piezas por Empacar"] = sku_wip.get("Empaque", 0)
            
        report_rows.append(wip_row)
        
    return pd.DataFrame(report_rows)

def generate_sku_wip_report_excel(df_report):
    import io
    output = io.BytesIO()
    
    subtotales = {
        "SKU": "Sub-Totales",
        "Total": df_report["Total"].sum(),
        "Piezas por Diseñar": df_report["Piezas por Diseñar"].sum(),
        "Piezas por Cortar": df_report["Piezas por Cortar"].sum(),
        "Piezas por Rebabear": df_report["Piezas por Rebabear"].sum(),
        "Piezas por Doblar": df_report["Piezas por Doblar"].sum(),
        "Piezas por Barrenar": df_report["Piezas por Barrenar"].sum(),
        "Piezas por Pintar": df_report["Piezas por Pintar"].sum(),
        "Piezas por Liberar": df_report["Piezas por Liberar"].sum(),
        "Piezas por Empacar": df_report["Piezas por Empacar"].sum()
    }
    df_excel = pd.concat([df_report, pd.DataFrame([subtotales])], ignore_index=True)
    
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_excel.to_excel(writer, sheet_name="Estatus WIP", index=False)
        workbook = writer.book
        worksheet = writer.sheets["Estatus WIP"]
        
        fmt_header = workbook.add_format({
            "bold": True, "font_name": "Arial", "font_size": 10,
            "font_color": "#FFFFFF", "bg_color": "#EC2024",
            "align": "center", "valign": "vcenter", "border": 1
        })
        fmt_cell = workbook.add_format({
            "font_name": "Arial", "font_size": 9, "border": 1, "align": "center"
        })
        fmt_total = workbook.add_format({
            "bold": True, "font_name": "Arial", "font_size": 10,
            "bg_color": "#E2EFDA", "border": 1, "align": "center"
        })
        
        for col_idx, col_name in enumerate(df_excel.columns):
            worksheet.write(0, col_idx, col_name, fmt_header)
            
        num_rows = len(df_excel)
        for r_idx in range(1, num_rows + 1):
            is_totals_row = (r_idx == num_rows)
            fmt = fmt_total if is_totals_row else fmt_cell
            for c_idx in range(len(df_excel.columns)):
                val = df_excel.iloc[r_idx - 1, c_idx]
                if pd.isna(val):
                    worksheet.write_blank(r_idx, c_idx, "", fmt)
                else:
                    try:
                        num_val = float(val)
                        if num_val.is_integer():
                            num_val = int(num_val)
                        worksheet.write_number(r_idx, c_idx, num_val, fmt)
                    except (ValueError, TypeError):
                        worksheet.write(r_idx, c_idx, str(val), fmt)
                        
        for col_idx, col in enumerate(df_excel.columns):
            max_len = max(
                df_excel[col].astype(str).map(len).max(),
                len(str(col))
            ) + 3
            worksheet.set_column(col_idx, col_idx, max(max_len, 12))
            
    return output.getvalue()

def view_consultas():
    st.title("2. CONSULTAS Y REPORTES")

    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
        "📅 Avance del Día", 
        "📊 Avance Semanal", 
        "🔍 Trazabilidad", 
        "📉 Calidad (Rechazos)",
        "📦 Material Programado",
        "🏭 WIP en Piso (Reportes)",
        "📋 WIP por SKU / Req"
    ])

    # --- PESTAÑA 1: Avance del Día ---
    with tab1:
        st.subheader("Reporte Diario de Avances PLANTA METALES")
        selected_date = st.date_input("Selecciona el día a consultar:", datetime.today())
        
        # Format date as YYYY-MM-DD
        date_str = selected_date.strftime("%Y-%m-%d")
        
        # Fetch advances for that day
        query_dia = """
        SELECT of_number as OF, nido as Nido, no_pieza as Pieza, area as Área, 
               cantidad as Cantidad, operador as Operador, maquina as Máquina, timestamp as Fecha_Hora
        FROM avances 
        WHERE date(timestamp) = ?
        ORDER BY timestamp DESC
        """
        df_dia = fetch_data(query_dia, (date_str,))
        
        # Obtener los rechazos de ese mismo día
        query_rechazos_dia = """
        SELECT area as Área, sum(cantidad) as Cantidad
        FROM rechazos 
        WHERE date(timestamp) = ?
        GROUP BY area
        """
        df_rechazos_dia = fetch_data(query_rechazos_dia, (date_str,))
        rechazos_por_area = df_rechazos_dia.set_index('Área')['Cantidad'].to_dict() if not df_rechazos_dia.empty else {}
        
        if df_dia.empty:
            st.info(f"No hay registros de avance para el {date_str}.")
        else:
            # Agrupar por area
            avances_por_area = df_dia.groupby('Área')['Cantidad'].sum().to_dict()
            areas_orden = ["Ingenieria", "Corte", "Rebabeo", "Doblez", "Barrenado", "Liberado", "Empaque"]
            
            process_icons = {
                "Ingenieria": "💻",
                "Corte": "✂️",
                "Rebabeo": "⚙️",
                "Doblez": "📐",
                "Barrenado": "🔩",
                "Liberado": "✅",
                "Empaque": "📦"
            }

            # Formatear la fecha para que se vea bonita (ej. 30 / 06 / 2026)
            fecha_formateada = selected_date.strftime("%d / %m / %Y")
            st.markdown(
                f'''
                <div style="text-align: center; margin-bottom: 30px;">
                    <p style="margin: 0; font-size: 1.2rem; color: #555; font-weight: bold; text-transform: uppercase;">Resultados de Producción del Día</p>
                    <h1 style="margin: 0; font-size: 4rem; font-weight: 900; color: #111; font-family: 'Montserrat', sans-serif;">📅 {fecha_formateada}</h1>
                </div>
                ''', unsafe_allow_html=True
            )

            st.markdown("### 📊 Avances por Área")
            cols = st.columns(4)
            for i, proc in enumerate(areas_orden):
                with cols[i % 4]:
                    avance_val = avances_por_area.get(proc, 0)
                    rechazo_val = rechazos_por_area.get(proc, 0)
                    color = "#0056b3" if avance_val > 0 else "#6c757d"
                    icon = process_icons.get(proc, "🏭")
                    
                    # HTML para mostrar el numero de avance y a un lado el rechazo en pequeño siempre
                    rechazo_html = f'<span style="font-size: 1.2rem; color: #EC2024; font-weight: bold; margin-left: 5px;">/ {int(rechazo_val)}</span>'
                    
                    st.markdown(
                        f'''
                        <div style="background-color: #f8f9fa; border-top: 5px solid {color}; padding: 20px; border-radius: 8px; margin-bottom: 20px; text-align: center; box-shadow: 0 4px 6px rgba(0,0,0,0.1); position: relative;">
                            <div style="font-size: 2.2rem; margin-bottom: 5px;">{icon}</div>
                            <p style="margin: 0; font-size: 1.1rem; color: #555; font-weight: bold; text-transform: uppercase;">{proc}</p>
                            <h2 style="margin: 5px 0 0 0; font-size: 3rem; font-weight: 900; color: {color}; display: flex; align-items: baseline; justify-content: center;">
                                {int(avance_val):,} {rechazo_html}
                            </h2>
                        </div>
                        ''', unsafe_allow_html=True
                    )
            
            st.markdown("#### Detalle de Movimientos")
            st.dataframe(df_dia, use_container_width=True)
            
            csv = convert_df(df_dia)
            st.download_button(
                label="📥 Descargar Reporte del Día (CSV)",
                data=csv,
                file_name=f'avance_{date_str}.csv',
                mime='text/csv',
            )

    # --- PESTAÑA 2: Avance Semanal ---
    with tab2:
        st.subheader("Tendencia Semanal por Área (Últimos 7 días)")
        
        # Fecha hace 7 dias
        fecha_fin = datetime.today()
        fecha_inicio = fecha_fin - timedelta(days=6)
        
        query_semana = """
        SELECT date(timestamp) as Fecha, area as Área, sum(cantidad) as Total
        FROM avances 
        WHERE date(timestamp) BETWEEN ? AND ?
        GROUP BY date(timestamp), area
        ORDER BY date(timestamp)
        """
        df_semana = fetch_data(query_semana, (fecha_inicio.strftime("%Y-%m-%d"), fecha_fin.strftime("%Y-%m-%d")))
        
        if df_semana.empty:
            st.info("No hay registros en los últimos 7 días.")
        else:
            # Crear una gráfica por cada área encontrada
            areas_presentes = df_semana['Área'].unique()
            
            for area in areas_presentes:
                df_area = df_semana[df_semana['Área'] == area]
                fig = px.bar(
                    df_area, 
                    x='Fecha', 
                    y='Total', 
                    title=f"Avance en {area}",
                    text='Total',
                    color_discrete_sequence=['#EC2024']
                )
                fig.update_traces(textposition='outside')
                fig.update_layout(xaxis_type='category', margin=dict(t=40, b=10, l=10, r=10))
                st.plotly_chart(fig, use_container_width=True)

    # --- PESTAÑA 3: Trazabilidad ---
    with tab3:
        st.subheader("Buscador y Trazabilidad General")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            search_of = st.text_input("Buscar por OF:", "")
        with col2:
            search_area = st.selectbox("Filtrar por Área:", ["Todas", "Ingenieria", "Corte", "Rebabeo", "Doblez", "Barrenado", "Liberado", "Empaque"])
        with col3:
            tipo_mov = st.selectbox("Tipo de Movimiento:", ["Ambos", "Avances", "Rechazos"])

        # Armar la consulta
        query_traz = """
        SELECT 'Avance' as Tipo, of_number as OF, nido as Nido, no_pieza as Pieza, area as Área, 
               cantidad as Cantidad, operador as Operador, maquina as Máquina, timestamp as Fecha_Hora, '' as Motivo
        FROM avances
        """
        if tipo_mov in ["Ambos", "Rechazos"]:
            query_rech = """
            SELECT 'Rechazo' as Tipo, of_number as OF, nido as Nido, no_pieza as Pieza, area as Área, 
                   cantidad as Cantidad, operador as Operador, maquina as Máquina, timestamp as Fecha_Hora, motivo as Motivo
            FROM rechazos
            """
            if tipo_mov == "Rechazos":
                query_traz = query_rech
            else:
                query_traz += f" UNION ALL {query_rech}"

        # Aplicar filtros basicos
        df_traz = fetch_data(f"SELECT * FROM ({query_traz}) ORDER BY Fecha_Hora DESC")
        
        if search_of:
            df_traz = df_traz[df_traz['OF'].astype(str).str.contains(search_of, case=False, na=False)]
        if search_area != "Todas":
            df_traz = df_traz[df_traz['Área'] == search_area]

        st.dataframe(df_traz, use_container_width=True)
        csv_traz = convert_df(df_traz)
        st.download_button(
            label="📥 Descargar Trazabilidad (CSV)",
            data=csv_traz,
            file_name='trazabilidad.csv',
            mime='text/csv',
        )

    # --- PESTAÑA 4: Calidad ---
    with tab4:
        st.subheader("Análisis de Scrap y Rechazos")
        
        query_calidad = """
        SELECT r.of_number as OF, r.nido as Nido, r.no_pieza as Pieza, r.area as Área, 
               r.cantidad as Cantidad, r.motivo as Motivo, r.operador as Operador, 
               r.maquina as Máquina, r.timestamp as Fecha_Hora, p.nombre_pieza as Descripción
        FROM rechazos r
        LEFT JOIN piezas p ON r.of_number = p.of_number AND r.nido = p.nido AND r.no_pieza = p.no_pieza
        ORDER BY r.timestamp DESC
        """
        df_calidad = fetch_data(query_calidad)
        
        if df_calidad.empty:
            st.success("¡Excelentes noticias! No hay registros de piezas rechazadas.")
        else:
            # 1. Scrap Global
            total_scrap = df_calidad['Cantidad'].sum()
            
            st.markdown(
                f'''
                <div style="background-color: #fff0f0; border-top: 5px solid #dc3545; padding: 20px; border-radius: 8px; margin-bottom: 25px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); text-align: center;">
                    <p style="margin: 0; font-size: 1.2rem; color: #666; font-weight: bold; text-transform: uppercase;">📉 TOTAL DE SCRAP GENERADO (GLOBAL)</p>
                    <div style="margin: 5px 0 0 0; font-size: 4.5rem; font-weight: 900; color: #dc3545;">{total_scrap} <span style="font-size: 1.8rem; font-weight: bold; color: #555;">piezas</span></div>
                </div>
                ''', unsafe_allow_html=True
            )
            
            # 2. Separar por área
            st.markdown("### 🗂️ Scrap Registrado por Área")
            areas_list = ["Corte", "Rebabeo", "Doblez", "Barrenado", "Liberado", "Empaque"]
            cols = st.columns(3)
            
            process_icons = {
                "Corte": "✂️",
                "Rebabeo": "⚙️",
                "Doblez": "📐",
                "Barrenado": "🔩",
                "Liberado": "✅",
                "Empaque": "📦"
            }
            
            friendly_names = {
                "Corte": "Corte Láser",
                "Rebabeo": "Rebabeo / Lijado",
                "Doblez": "Doblez",
                "Barrenado": "Barrenado",
                "Liberado": "Liberado / Calidad",
                "Empaque": "Empaque / Embarque"
            }
            
            df_areas = df_calidad.groupby('Área')['Cantidad'].sum().to_dict()
            
            for idx, area in enumerate(areas_list):
                scrap_val = df_areas.get(area, 0)
                color = "#dc3545" if scrap_val > 0 else "#28a745"
                icon = process_icons.get(area, "🏭")
                pct = (scrap_val / total_scrap * 100) if total_scrap > 0 else 0
                label = friendly_names.get(area, area)
                
                with cols[idx % 3]:
                    st.markdown(
                        f'''
                        <div style="background-color: #f8f9fa; border-top: 5px solid {color}; padding: 15px; border-radius: 8px; margin-bottom: 20px; text-align: center; box-shadow: 0 4px 6px rgba(0,0,0,0.1); position: relative;">
                            <div style="position: absolute; top: 5px; right: 5px; background-color: #f1f3f5; color: #495057; padding: 2px 6px; border-radius: 10px; font-size: 0.75rem; font-weight: bold;">{pct:.1f}%</div>
                            <div style="font-size: 1.8rem; margin-bottom: 3px;">{icon}</div>
                            <p style="margin: 0; font-size: 0.85rem; color: #555; font-weight: bold; text-transform: uppercase;">{label}</p>
                            <h3 style="margin: 5px 0 0 0; font-size: 2.2rem; font-weight: 900; color: {color};">{scrap_val}</h3>
                        </div>
                        ''', unsafe_allow_html=True
                    )
            
            # 3. Detalle de piezas por área
            st.markdown("### 🔍 Detalle de Piezas en Scrap por Área")
            sel_area_scrap = st.selectbox(
                "Selecciona un área para ver el detalle de piezas en Scrap:",
                ["Selecciona un área..."] + [friendly_names[a] for a in areas_list],
                key="sel_area_scrap"
            )
            
            if sel_area_scrap != "Selecciona un área...":
                inv_friendly = {v: k for k, v in friendly_names.items()}
                tec_area = inv_friendly[sel_area_scrap]
                
                df_area_scrap = df_calidad[df_calidad['Área'] == tec_area].copy()
                
                if df_area_scrap.empty:
                    st.success(f"✅ ¡No hay registros de Scrap en el área de **{sel_area_scrap}**!")
                else:
                    cols_show = ["OF", "Nido", "Pieza", "Descripción", "Cantidad", "Motivo", "Operador", "Máquina", "Fecha_Hora"]
                    df_area_scrap = df_area_scrap[[c for c in cols_show if c in df_area_scrap.columns]]
                    st.dataframe(df_area_scrap, use_container_width=True, hide_index=True)
                    
                    csv_area_scrap = convert_df(df_area_scrap)
                    st.download_button(
                        label=f"📥 Descargar Detalle de Scrap - {sel_area_scrap} (CSV)",
                        data=csv_area_scrap,
                        file_name=f"Scrap_{tec_area}.csv",
                        mime='text/csv',
                        use_container_width=True,
                        type="primary"
                    )
                    
            st.markdown("---")
            st.markdown("### 📊 Gráficas de Análisis Global")
            
            col_chart1, col_chart2 = st.columns(2)
            with col_chart1:
                df_motivos = df_calidad.groupby('Motivo')['Cantidad'].sum().reset_index()
                fig_mot = px.pie(df_motivos, values='Cantidad', names='Motivo', title='Distribución de Motivos de Rechazo', hole=0.4)
                st.plotly_chart(fig_mot, use_container_width=True)
                
            with col_chart2:
                df_areas_g = df_calidad.groupby('Área')['Cantidad'].sum().reset_index()
                df_areas_g['Área'] = df_areas_g['Área'].map(friendly_names)
                fig_ar = px.bar(df_areas_g, x='Área', y='Cantidad', title='Piezas en Scrap por Área', text='Cantidad', color='Cantidad', color_continuous_scale="Reds")
                fig_ar.update_traces(textposition='outside')
                st.plotly_chart(fig_ar, use_container_width=True)
                
            st.markdown("#### 📋 Historial Completo de Rechazos (Global)")
            st.dataframe(df_calidad, use_container_width=True)
            csv_cal = convert_df(df_calidad)
            st.download_button(
                label="📥 Descargar Historial Global de Rechazos (CSV)",
                data=csv_cal,
                file_name='rechazos_global.csv',
                mime='text/csv',
            )

    # --- PESTAÑA 5: Material Programado ---
    with tab5:
        st.subheader("📦 Material Programado por Orden de Fabricación")
        st.markdown("Consulta exactamente qué piezas y qué cantidades están planificadas en cada OF, nido y proceso.")

        # ── Carga de datos planeados ──────────────────────────────────────
        df_mat = fetch_data("""
            SELECT
                p.of_number        AS OF,
                o.proyecto         AS Proyecto,
                o.programador      AS Programador,
                o.fecha            AS Fecha,
                p.nido             AS Nido,
                n.hojas            AS Hojas,
                p.no_pieza         AS [No. Parte],
                p.nombre_pieza     AS Descripción,
                p.cantidad         AS [Cant/Hoja],
                p.cantidad * n.hojas AS [Total Planeado],
                p.ruta             AS Ruta
            FROM piezas p
            JOIN nidos   n ON p.of_number = n.of_number AND p.nido = n.nido
            JOIN ordenes o ON p.of_number = o.of_number
            ORDER BY p.of_number, p.nido, p.no_pieza
        """)

        if df_mat.empty:
            st.warning("⚠️ No hay OFs cargadas en el sistema. Ve a Planeación para subir tu primer plan de producción.")
        else:
            # ── Filtros en cascada ────────────────────────────────────────
            col_f1, col_f2, col_f3 = st.columns(3)

            ofs_disponibles = sorted(df_mat["OF"].unique().tolist())
            with col_f1:
                sel_ofs_mat = st.multiselect(
                    "🗂️ Filtrar por OF:",
                    ["Todas"] + ofs_disponibles,
                    default=["Todas"],
                    key="mat_sel_of"
                )

            df_filt = df_mat.copy()
            if sel_ofs_mat and "Todas" not in sel_ofs_mat:
                df_filt = df_filt[df_filt["OF"].isin(sel_ofs_mat)]

            nidos_disp = sorted(df_filt["Nido"].unique().tolist())
            with col_f2:
                sel_nidos_mat = st.multiselect(
                    "📂 Filtrar por Nido:",
                    ["Todos"] + nidos_disp,
                    default=["Todos"],
                    key="mat_sel_nido"
                )

            if sel_nidos_mat and "Todos" not in sel_nidos_mat:
                df_filt = df_filt[df_filt["Nido"].isin(sel_nidos_mat)]

            # Filtro por Proceso (busca en la columna Ruta)
            all_procesos = ["Corte", "Rebabeo", "Doblez", "Barrenado", "Liberado", "Empaque"]
            with col_f3:
                sel_proceso_mat = st.selectbox(
                    "⚙️ Filtrar piezas que pasan por:",
                    ["Todos los procesos"] + all_procesos,
                    key="mat_sel_proceso"
                )

            if sel_proceso_mat != "Todos los procesos":
                df_filt = df_filt[df_filt["Ruta"].str.contains(sel_proceso_mat, na=False)]

            # ── Tarjetas Resumen ──────────────────────────────────────────
            total_piezas_unicas  = df_filt["No. Parte"].nunique()
            total_unidades       = int(df_filt["Total Planeado"].sum())
            total_nidos          = df_filt["Nido"].nunique()
            total_of_sel         = df_filt["OF"].nunique()

            c1, c2, c3, c4 = st.columns(4)
            tarjeta_style = (
                "background:#f8f9fa;border-top:5px solid {color};"
                "padding:18px;border-radius:8px;text-align:center;"
                "box-shadow:0 3px 6px rgba(0,0,0,.1);margin-bottom:12px"
            )
            for col, label, valor, color in [
                (c1, "OFs Seleccionadas",  total_of_sel,          "#0056b3"),
                (c2, "Nidos Programados",  total_nidos,           "#6f42c1"),
                (c3, "No. Partes Únicos",  total_piezas_unicas,   "#28a745"),
                (c4, "Total Unidades Plan",total_unidades,        "#EC2024"),
            ]:
                col.markdown(
                    f'<div style="{tarjeta_style.format(color=color)}">'
                    f'<p style="margin:0;font-size:.85rem;font-weight:bold;color:#555;text-transform:uppercase">{label}</p>'
                    f'<h2 style="margin:4px 0 0;font-size:2.6rem;font-weight:900;color:{color}">{valor}</h2>'
                    f'</div>',
                    unsafe_allow_html=True
                )

            # ── Tabla principal ───────────────────────────────────────────
            st.markdown("### 📋 Detalle de Material Programado")
            st.dataframe(
                df_filt,
                use_container_width=True,
                hide_index=True,
                height=400,
                column_config={
                    "Total Planeado": st.column_config.NumberColumn("Total Planeado", format="%d pzas"),
                    "Cant/Hoja":      st.column_config.NumberColumn("Cant/Hoja",      format="%d"),
                    "Hojas":          st.column_config.NumberColumn("# Hojas",         format="%d"),
                }
            )

            # ── Descarga CSV ──────────────────────────────────────────────
            st.markdown("---")
            col_dl1, col_dl2 = st.columns(2)

            with col_dl1:
                csv_mat = df_filt.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📥 Descargar CSV",
                    data=csv_mat,
                    file_name="Material_Programado.csv",
                    mime="text/csv",
                    use_container_width=True,
                )

            # ── Descarga XLSX ─────────────────────────────────────────────
            with col_dl2:
                def build_xlsx(df):
                    import io
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
                        wb = writer.book

                        # ── Formatos corporativos ──────────────────────────
                        fmt_header = wb.add_format({
                            "bold": True, "font_name": "Arial", "font_size": 10,
                            "font_color": "#FFFFFF", "bg_color": "#EC2024",
                            "align": "center", "valign": "vcenter",
                            "border": 1, "border_color": "#B0B0B0", "text_wrap": True
                        })
                        fmt_title = wb.add_format({
                            "bold": True, "font_name": "Arial", "font_size": 14,
                            "font_color": "#EC2024", "align": "left", "valign": "vcenter"
                        })
                        fmt_subtitle = wb.add_format({
                            "font_name": "Arial", "font_size": 9,
                            "font_color": "#555555", "align": "left"
                        })
                        fmt_cell = wb.add_format({
                            "font_name": "Arial", "font_size": 9,
                            "border": 1, "border_color": "#D3D3D3", "valign": "vcenter"
                        })
                        fmt_num = wb.add_format({
                            "font_name": "Arial", "font_size": 9,
                            "border": 1, "border_color": "#D3D3D3",
                            "valign": "vcenter", "align": "right", "num_format": "#,##0"
                        })
                        fmt_alt = wb.add_format({
                            "font_name": "Arial", "font_size": 9,
                            "bg_color": "#FFF5F5", "border": 1,
                            "border_color": "#D3D3D3", "valign": "vcenter"
                        })
                        fmt_num_alt = wb.add_format({
                            "font_name": "Arial", "font_size": 9,
                            "bg_color": "#FFF5F5", "border": 1,
                            "border_color": "#D3D3D3", "valign": "vcenter",
                            "align": "right", "num_format": "#,##0"
                        })
                        fmt_of_group = wb.add_format({
                            "bold": True, "font_name": "Arial", "font_size": 10,
                            "font_color": "#FFFFFF", "bg_color": "#1A1A2E",
                            "border": 1, "border_color": "#B0B0B0", "valign": "vcenter"
                        })
                        fmt_nido_group = wb.add_format({
                            "bold": True, "font_name": "Arial", "font_size": 9,
                            "font_color": "#FFFFFF", "bg_color": "#6f42c1",
                            "border": 1, "border_color": "#B0B0B0", "valign": "vcenter"
                        })

                        # ── Hoja 1: Detalle por OF / Nido / Pieza ─────────
                        ws = wb.add_worksheet("Detalle por OF")
                        ws.set_zoom(90)
                        ws.hide_gridlines(2)
                        ws.set_row(0, 30)
                        ws.set_row(1, 18)
                        ws.set_row(2, 18)

                        ws.merge_range("A1:K1", "SIGRAMA — Reporte de Material Programado", fmt_title)
                        ws.merge_range("A2:K2",
                            f"Generado: {datetime.now().strftime('%d/%m/%Y %H:%M')}   |   OFs: {', '.join(df['OF'].unique())}",
                            fmt_subtitle)
                        ws.write("A3", "", fmt_subtitle)

                        cols = ["OF", "Proyecto", "Programador", "Fecha", "Nido",
                                "Hojas", "No. Parte", "Descripción", "Cant/Hoja",
                                "Total Planeado", "Ruta"]
                        col_widths = [12, 18, 18, 12, 8, 7, 18, 40, 10, 14, 45]

                        start_row = 3
                        for c_idx, (col_name, width) in enumerate(zip(cols, col_widths)):
                            ws.write(start_row, c_idx, col_name, fmt_header)
                            ws.set_column(c_idx, c_idx, width)

                        data_row = start_row + 1
                        prev_of = None
                        prev_nido = None
                        for _, row in df.sort_values(["OF", "Nido", "No. Parte"]).iterrows():
                            alt = (data_row % 2 == 0)
                            # Fila de agrupación por OF
                            if row["OF"] != prev_of:
                                ws.merge_range(data_row, 0, data_row, 10,
                                               f"📁 Orden de Fabricación: {row['OF']}  —  {row['Proyecto']}", fmt_of_group)
                                data_row += 1
                                prev_of = row["OF"]
                                prev_nido = None

                            # Fila de agrupación por Nido
                            if row["Nido"] != prev_nido:
                                ws.merge_range(data_row, 0, data_row, 10,
                                               f"   📂 Nido: {row['Nido']}   ({row['Hojas']} hoja(s))", fmt_nido_group)
                                data_row += 1
                                prev_nido = row["Nido"]

                            vals = [
                                row["OF"], row["Proyecto"], row["Programador"], str(row["Fecha"]),
                                row["Nido"], row["Hojas"], row["No. Parte"], row["Descripción"],
                                row["Cant/Hoja"], row["Total Planeado"], row["Ruta"]
                            ]
                            num_cols = {5, 8, 9}  # Hojas, Cant/Hoja, Total Planeado
                            for c_idx, val in enumerate(vals):
                                if pd.isna(val):
                                    ws.write_blank(data_row, c_idx, "", fmt_alt if alt else fmt_cell)
                                elif c_idx in num_cols:
                                    try:
                                        num_val = float(val)
                                        if num_val.is_integer():
                                            num_val = int(num_val)
                                        ws.write_number(data_row, c_idx, num_val, fmt_num_alt if alt else fmt_num)
                                    except (ValueError, TypeError):
                                        ws.write(data_row, c_idx, str(val), fmt_alt if alt else fmt_cell)
                                else:
                                    cleaned_val = val
                                    if not isinstance(cleaned_val, (str, int, float, bool)):
                                        cleaned_val = str(cleaned_val)
                                    ws.write(data_row, c_idx, cleaned_val, fmt_alt if alt else fmt_cell)
                            data_row += 1

                        ws.freeze_panes(start_row + 1, 0)
                        ws.autofilter(start_row, 0, data_row - 1, len(cols) - 1)

                        # ── Hoja 2: Resumen por OF ─────────────────────────
                        ws2 = wb.add_worksheet("Resumen por OF")
                        ws2.hide_gridlines(2)
                        ws2.set_row(0, 30)
                        ws2.merge_range("A1:E1", "SIGRAMA — Resumen de Material por OF", fmt_title)

                        res_cols = ["OF", "Proyecto", "Nidos", "No. Partes Únicos", "Total Planeado"]
                        res_widths = [14, 22, 10, 20, 18]
                        for c_idx, (cn, cw) in enumerate(zip(res_cols, res_widths)):
                            ws2.write(2, c_idx, cn, fmt_header)
                            ws2.set_column(c_idx, c_idx, cw)

                        df_res = df.groupby(["OF", "Proyecto"]).agg(
                            Nidos=("Nido", "nunique"),
                            Partes=("No. Parte", "nunique"),
                            Total=("Total Planeado", "sum")
                        ).reset_index()

                        for r_idx, rw in df_res.iterrows():
                            alt = (r_idx % 2 == 0)
                            ws2.write(3 + r_idx, 0, rw["OF"],         fmt_alt if alt else fmt_cell)
                            ws2.write(3 + r_idx, 1, rw["Proyecto"],   fmt_alt if alt else fmt_cell)
                            ws2.write_number(3 + r_idx, 2, int(rw["Nidos"]),  fmt_num_alt if alt else fmt_num)
                            ws2.write_number(3 + r_idx, 3, int(rw["Partes"]), fmt_num_alt if alt else fmt_num)
                            ws2.write_number(3 + r_idx, 4, int(rw["Total"]),  fmt_num_alt if alt else fmt_num)

                        # Totales
                        tot_row = 3 + len(df_res)
                        fmt_tot = wb.add_format({
                            "bold": True, "font_name": "Arial", "font_size": 9,
                            "bg_color": "#EC2024", "font_color": "#FFFFFF",
                            "border": 1, "align": "right", "num_format": "#,##0"
                        })
                        ws2.merge_range(tot_row, 0, tot_row, 3, "TOTAL GENERAL", wb.add_format({
                            "bold": True, "font_name": "Arial", "bg_color": "#EC2024",
                            "font_color": "#FFFFFF", "border": 1, "align": "right"
                        }))
                        ws2.write_number(tot_row, 4, int(df["Total Planeado"].sum()), fmt_tot)

                    return output.getvalue()

                xlsx_bytes = build_xlsx(df_filt)
                st.download_button(
                    label="📊 Descargar Reporte XLSX",
                    data=xlsx_bytes,
                    file_name="Material_Programado_SIGRAMA.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                    type="primary"
                )

            # ── Gráfica: Top 10 partes por unidades planeadas ─────────────
            st.markdown("---")
            st.markdown("### 📊 Top 10 Números de Parte por Unidades Planeadas")
            df_top = (
                df_filt.groupby(["No. Parte", "Descripción"])["Total Planeado"]
                .sum().reset_index()
                .sort_values("Total Planeado", ascending=False)
                .head(10)
            )
            if not df_top.empty:
                fig_top = px.bar(
                    df_top, x="Total Planeado", y="No. Parte",
                    orientation="h",
                    text="Total Planeado",
                    color="Total Planeado",
                    color_continuous_scale="Blues",
                    title="Top 10 partes con mayor volumen programado"
                )
                fig_top.update_traces(textposition="outside")
                fig_top.update_layout(
                    yaxis=dict(autorange="reversed"),
                    height=400,
                    showlegend=False
                )
                st.plotly_chart(fig_top, use_container_width=True)

    # --- PESTAÑA 6: WIP en Piso (Reportes) ---
    with tab6:
        view_reportes()

    # --- PESTAÑA 7: WIP por SKU / Req ---
    with tab7:
        st.subheader("📋 Reporte de WIP por SKU / Requerimiento")
        st.markdown(
            "Este reporte te permite subir una lista de piezas (SKUs) y cantidades requeridas "
            "para comparar su avance actual y ubicar físicamente el WIP en las distintas estaciones de la planta."
        )
        
        col_pl, col_up = st.columns(2)
        with col_pl:
            st.markdown("##### Paso 1: Descarga la plantilla de requerimiento:")
            sample_excel = get_sample_req_excel()
            st.download_button(
                label="📥 Descargar Plantilla Excel",
                data=sample_excel,
                file_name="Plantilla_Requerimiento_WIP.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
        with col_up:
            st.markdown("##### Sube el archivo completado:")
            uploaded_file = st.file_uploader("Sube el Requerimiento (.xlsx o .csv):", type=["xlsx", "csv"], key="wip_req_file_uploader")
            
        if uploaded_file is not None:
            try:
                if uploaded_file.name.endswith(".csv"):
                    df_uploaded = pd.read_csv(uploaded_file)
                else:
                    df_uploaded = pd.read_excel(uploaded_file)
                    
                # Detectar columnas
                sku_col = None
                for col in df_uploaded.columns:
                    if str(col).strip().lower() in ["sku", "no_pieza", "parte", "no. parte", "artículo", "codigo", "código"]:
                        sku_col = col
                        break
                if sku_col is None:
                    sku_col = df_uploaded.columns[0]
                    
                total_col = None
                for col in df_uploaded.columns:
                    if str(col).strip().lower() in ["total", "cantidad", "cant", "req", "requerido", "volume", "qty", "cantidad requerida"]:
                        total_col = col
                        break
                if total_col is None:
                    total_col = df_uploaded.columns[1] if len(df_uploaded.columns) > 1 else None
                    
                if total_col is None:
                    st.error("⚠️ El archivo debe tener al menos dos columnas (SKU y Total).")
                else:
                    df_uploaded = df_uploaded[[sku_col, total_col]].dropna(subset=[sku_col]).copy()
                    df_uploaded.rename(columns={sku_col: "SKU", total_col: "Total"}, inplace=True)
                    df_uploaded["SKU"] = df_uploaded["SKU"].astype(str).str.strip()
                    df_uploaded["Total"] = pd.to_numeric(df_uploaded["Total"], errors="coerce").fillna(0).astype(int)
                    
                    st.markdown("---")
                    st.markdown("##### Paso 2: Selecciona las OFs para filtrar el estatus de producción:")
                    
                    from utils.database import get_all_ofs
                    all_ofs = get_all_ofs()
                    sel_ofs = st.multiselect(
                        "Selecciona las OFs (se buscarán los avances y nidos en estas órdenes):",
                        ["Todas"] + all_ofs,
                        default=["Todas"],
                        key="wip_req_ofs_select"
                    )
                    
                    if not sel_ofs:
                        st.warning("⚠️ Debes seleccionar al menos una OF o 'Todas' para proceder.")
                    else:
                        st.markdown("---")
                        st.markdown("##### Paso 3: Estatus de WIP Generado")
                        
                        with st.spinner("Calculando estatus de WIP por SKU..."):
                            df_report = calculate_sku_wip_report(df_uploaded, sel_ofs)
                            
                        # Métricas
                        diseños_pendientes = len(df_report[df_report["Piezas por Diseñar"] > 0])
                        total_piezas_req = df_report["Total"].sum()
                        
                        col_m1, col_m2 = st.columns(2)
                        with col_m1:
                            st.metric("Total de Piezas Requeridas", f"{total_piezas_req:,} pzs")
                        with col_m2:
                            st.metric("Diseños Pendientes (SKUs nuevos)", f"{diseños_pendientes} SKUs", delta=f"{diseños_pendientes} por diseñar" if diseños_pendientes > 0 else "Todo diseñado", delta_color="inverse" if diseños_pendientes > 0 else "normal")
                            
                        # Generar fila de Totales
                        subtotales = {
                            "SKU": "Sub-Totales",
                            "Total": df_report["Total"].sum(),
                            "Piezas por Diseñar": df_report["Piezas por Diseñar"].sum(),
                            "Piezas por Cortar": df_report["Piezas por Cortar"].sum(),
                            "Piezas por Rebabear": df_report["Piezas por Rebabear"].sum(),
                            "Piezas por Doblar": df_report["Piezas por Doblar"].sum(),
                            "Piezas por Barrenar": df_report["Piezas por Barrenar"].sum(),
                            "Piezas por Pintar": df_report["Piezas por Pintar"].sum(),
                            "Piezas por Liberar": df_report["Piezas por Liberar"].sum(),
                            "Piezas por Empacar": df_report["Piezas por Empacar"].sum()
                        }
                        df_display = pd.concat([df_report, pd.DataFrame([subtotales])], ignore_index=True)
                        
                        # Mostrar tabla
                        st.dataframe(df_display, use_container_width=True, hide_index=True, height=400)
                        
                        # Descarga
                        excel_report_bytes = generate_sku_wip_report_excel(df_report)
                        st.download_button(
                            label="📥 Descargar Reporte de Estatus de WIP (Excel)",
                            data=excel_report_bytes,
                            file_name="Reporte_Estatus_WIP_SKU.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=True,
                            type="primary"
                        )
            except Exception as e:
                st.error(f"❌ Error al procesar el archivo: {str(e)}")


def view_public_avance_diario():
    st.markdown(
        """
        <style>
        html, body, [data-testid="stAppViewContainer"] {
            zoom: 0.88 !important;
        }
        .block-container {
            padding-top: 0rem !important;
            padding-bottom: 0rem !important;
            margin-top: 0px !important;
        }
        header {
            visibility: hidden;
            height: 0px;
        }
        </style>
        """,
        unsafe_allow_html=True
    )
    
    dir_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    banner_path = os.path.join(dir_path, "assets", "banner.png")
    
    if os.path.exists(banner_path):
        col_b1, col_b2, col_b3 = st.columns([1, 3.7, 1])
        with col_b2:
            st.image(banner_path, use_container_width=True)
    else:
        st.info("SIGRAMA - PLANTA METALES")
    
    # Selector de fecha compacto en la misma línea que el título
    col_t, col_d = st.columns([3, 1])
    with col_d:
        selected_date = st.date_input("Fecha de Consulta:", datetime.today(), label_visibility="collapsed")
    
    date_str = selected_date.strftime("%Y-%m-%d")
    fecha_formateada = selected_date.strftime("%d/%m/%Y")
    
    with col_t:
        st.markdown(f'<h2 style="margin:0; font-weight:900; font-family:\'Montserrat\'">📅 Avances PLANTA METALES ({fecha_formateada})</h2>', unsafe_allow_html=True)
    
    # Fetch advances for that day
    query_dia = """
    SELECT of_number as OF, nido as Nido, no_pieza as Pieza, area as Área, 
           cantidad as Cantidad, operador as Operador, maquina as Máquina, timestamp as Fecha_Hora
    FROM avances 
    WHERE date(timestamp) = ?
    ORDER BY timestamp DESC
    """
    df_dia = fetch_data(query_dia, (date_str,))
    
    # Obtener los rechazos de ese mismo día
    query_rechazos_dia = """
    SELECT area as Área, sum(cantidad) as Cantidad
    FROM rechazos 
    WHERE date(timestamp) = ?
    GROUP BY area
    """
    df_rechazos_dia = fetch_data(query_rechazos_dia, (date_str,))
    rechazos_por_area = df_rechazos_dia.set_index('Área')['Cantidad'].to_dict() if not df_rechazos_dia.empty else {}
    
    if df_dia.empty:
        st.info(f"No hay registros de avance para el {date_str}.")
    else:
        avances_por_area = df_dia.groupby('Área')['Cantidad'].sum().to_dict()
        areas_orden = ["Ingenieria", "Corte", "Rebabeo", "Doblez", "Barrenado", "Liberado", "Empaque"]
        process_icons = {"Ingenieria": "💻", "Corte": "✂️", "Rebabeo": "⚙️", "Doblez": "📐", "Barrenado": "🔩", "Liberado": "✅", "Empaque": "📦"}
        
        # 7 columnas en una fila única
        cols = st.columns(7)
        for i, proc in enumerate(areas_orden):
            with cols[i]:
                avance_val = avances_por_area.get(proc, 0)
                rechazo_val = rechazos_por_area.get(proc, 0)
                color = "#0056b3" if avance_val > 0 else "#6c757d"
                icon = process_icons.get(proc, "🏭")
                rechazo_html = f'<span style="font-size: 0.9rem; color: #EC2024; font-weight: bold; margin-left: 2px;">/ {int(rechazo_val)}</span>'
                
                st.markdown(
                    f'''
                    <div style="background-color: #f8f9fa; border-top: 4px solid {color}; padding: 10px 5px; border-radius: 6px; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.08); margin-bottom: 10px;">
                        <div style="font-size: 1.4rem; margin-bottom: 2px;">{icon}</div>
                        <p style="margin: 0; font-size: 0.75rem; color: #666; font-weight: bold; text-transform: uppercase; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{proc}</p>
                        <h3 style="margin: 2px 0 0 0; font-size: 1.6rem; font-weight: 900; color: {color}; display: flex; align-items: baseline; justify-content: center; line-height: 1.1;">
                            {int(avance_val):,} {rechazo_html}
                        </h3>
                    </div>
                    ''', unsafe_allow_html=True
                )
        
        col_lbl, col_btn = st.columns([4, 1])
        with col_lbl:
            st.markdown("<p style='margin:0; font-weight:bold; font-size:1.0rem;'>📋 Detalle de Movimientos del Día</p>", unsafe_allow_html=True)
        with col_btn:
            csv = convert_df(df_dia)
            st.download_button(
                label="📥 Descargar CSV",
                data=csv,
                file_name=f'avance_{date_str}.csv',
                mime='text/csv',
                use_container_width=True
            )
            
        st.dataframe(df_dia, height=220, use_container_width=True)


def view_public_gantt():
    st.markdown('<h2 style="margin-top:0; margin-bottom:10px; font-weight:900; font-family:\'Montserrat\'">📅 Programa de Producción (Diagrama de Gantt)</h2>', unsafe_allow_html=True)
    st.markdown("Verde = Completado (100%), Amarillo = En Proceso, Gris = Pendiente (0%).")
    
    from utils.database import get_connection
    from views.produccion import to_date_safe
    
    conn = get_connection()
    df_pzs = pd.read_sql_query("""
        SELECT p.of_number, SUM(p.cantidad * n.hojas) as total_piezas
        FROM piezas p
        JOIN nidos n ON p.of_number = n.of_number AND p.nido = n.nido
        GROUP BY p.of_number
    """, conn)
    
    df_ordenes_gantt = pd.read_sql_query("""
        SELECT of_number, proyecto, programador, po, prioridad, calibre, proyecto_cliente, gantt_inicio, gantt_dias, gantt_avance
        FROM ordenes
    """, conn)
    
    df_total_hojas = pd.read_sql_query("SELECT of_number, SUM(hojas) as total_hojas FROM nidos GROUP BY of_number", conn)
    df_cortadas = pd.read_sql_query("""
        SELECT of_number, COUNT(DISTINCT nido || '||' || hoja) as hojas_cortadas 
        FROM avances 
        WHERE area = 'Corte' AND hoja IS NOT NULL
        GROUP BY of_number
    """, conn)
    conn.close()
    
    if df_ordenes_gantt.empty:
        st.info("⚠️ No se encontraron Órdenes de Fabricación cargadas en el sistema.")
        return
        
    total_hojas_map = df_total_hojas.set_index("of_number")["total_hojas"].to_dict()
    cortadas_map = df_cortadas.set_index("of_number")["hojas_cortadas"].to_dict()
    
    pct_map = {}
    for of_id in df_ordenes_gantt["of_number"]:
        tot_h = total_hojas_map.get(of_id, 0)
        cort_h = cortadas_map.get(of_id, 0)
        pct_map[of_id] = (cort_h / tot_h * 100) if tot_h > 0 else 0.0
        
    df_prog = df_ordenes_gantt.merge(df_pzs, on="of_number", how="left")
    df_prog["total_piezas"] = df_prog["total_piezas"].fillna(0).astype(int)
    
    df_prog["INICIO"] = df_prog["gantt_inicio"].apply(to_date_safe)
    df_prog["INICIO"] = df_prog["INICIO"].fillna(datetime.today().date())
    df_prog["DIAS"] = df_prog["gantt_dias"].fillna(1).astype(int)
    df_prog["AVANCE"] = df_prog["gantt_avance"].fillna("PENDIENTE").astype(str)
    
    def calc_final(row):
        start_dt = to_date_safe(row["INICIO"])
        if not start_dt:
            return None
        return start_dt + timedelta(days=int(row["DIAS"]) - 1)
        
    df_prog["FINAL APROXIMADO"] = df_prog.apply(calc_final, axis=1)
    
    def get_of_consolidated_details(row):
        parts = []
        if pd.notna(row["po"]) and str(row["po"]).strip():
            parts.append(f"PO: {str(row['po']).strip()}")
        if pd.notna(row["proyecto_cliente"]) and str(row["proyecto_cliente"]).strip():
            parts.append(f"Proy. Cliente: {str(row['proyecto_cliente']).strip()}")
        elif pd.notna(row["proyecto"]) and str(row["proyecto"]).strip():
            parts.append(f"Proy: {str(row['proyecto']).strip()}")
        if pd.notna(row["total_piezas"]) and row["total_piezas"] > 0:
            parts.append(f"Pzs: {int(row['total_piezas'])}")
        return " | ".join(parts) if parts else "Sin detalles"
        
    df_prog["INFORMACIÓN DE LA OF"] = df_prog.apply(get_of_consolidated_details, axis=1)
    
    df_display = df_prog[["of_number", "INFORMACIÓN DE LA OF", "total_piezas", "INICIO", "FINAL APROXIMADO", "AVANCE"]].copy()
    df_display.rename(columns={
        "of_number": "ORDENES DE FABRICACION",
        "total_piezas": "CANTIDAD PZS."
    }, inplace=True)
    
    def get_avance_real_emoji(of_id):
        pct = pct_map.get(of_id, 0.0)
        if pct >= 100.0:
            return f"🟢 {pct:.1f}%"
        elif pct > 0.0:
            return f"🟡 {pct:.1f}%"
        else:
            return f"⚪ {pct:.1f}%"
            
    df_display["AVANCE REAL (CORTE)"] = df_display["ORDENES DE FABRICACION"].map(get_avance_real_emoji)
    
    df_display = df_display[[
        "ORDENES DE FABRICACION", "INFORMACIÓN DE LA OF", "CANTIDAD PZS.", "INICIO", 
        "FINAL APROXIMADO", "AVANCE REAL (CORTE)", "AVANCE"
    ]]
    
    valid_rows = df_display[df_display["INICIO"].notna() & df_display["FINAL APROXIMADO"].notna()].copy()
    if not valid_rows.empty:
        valid_rows["INICIO"] = valid_rows["INICIO"].apply(to_date_safe)
        valid_rows["FINAL APROXIMADO"] = valid_rows["FINAL APROXIMADO"].apply(to_date_safe)
        
        db_min_date = valid_rows["INICIO"].min()
        db_max_date = valid_rows["FINAL APROXIMADO"].max()
        
        today = datetime.today().date()
        default_start = today - timedelta(days=7)
        default_end = today + timedelta(days=21)
        
        min_date = max(db_min_date, default_start)
        max_date = min(db_max_date, default_end)
        
        if min_date > max_date:
            min_date = db_min_date
            max_date = db_max_date
            
        date_range = pd.date_range(start=min_date, end=max_date)
        if len(date_range) > 45:
            date_range = date_range[:45]
            max_date = date_range[-1].date()
            
        months_es = {1:"ene", 2:"feb", 3:"mar", 4:"abr", 5:"may", 6:"jun", 7:"jul", 8:"ago", 9:"sep", 10:"oct", 11:"nov", 12:"dic"}
        
        date_cols = []
        date_col_mapping = {}
        for dt in date_range:
            col_name = f"{dt.day:02d}-{months_es[dt.month]}"
            date_cols.append(col_name)
            date_col_mapping[col_name] = dt.date()
            
        df_gantt_raw = df_display[["ORDENES DE FABRICACION", "INFORMACIÓN DE LA OF", "INICIO", "FINAL APROXIMADO", "AVANCE REAL (CORTE)"]].copy()
        df_gantt_raw["INICIO_DT"] = df_gantt_raw["INICIO"].apply(to_date_safe)
        df_gantt_raw["FINAL_DT"] = df_gantt_raw["FINAL APROXIMADO"].apply(to_date_safe)
        
        df_gantt_table = df_gantt_raw[
            (df_gantt_raw["INICIO_DT"].notna()) &
            (df_gantt_raw["FINAL_DT"].notna()) &
            (df_gantt_raw["INICIO_DT"] <= max_date) &
            (df_gantt_raw["FINAL_DT"] >= min_date)
        ].copy()
        
        for col in date_cols:
            df_gantt_table[col] = ""
            
        df_gantt_table["INICIO"] = df_gantt_table["INICIO_DT"].apply(lambda x: x.strftime("%d/%m/%Y") if pd.notna(x) else "")
        df_gantt_table["FINAL APROXIMADO"] = df_gantt_table["FINAL_DT"].apply(lambda x: x.strftime("%d/%m/%Y") if pd.notna(x) else "")
        df_gantt_table.drop(columns=["INICIO_DT", "FINAL_DT"], inplace=True)
        
        def style_gantt(df_to_style):
            styles = pd.DataFrame('', index=df_to_style.index, columns=df_to_style.columns)
            for idx, row in df_to_style.iterrows():
                of_id = row["ORDENES DE FABRICACION"]
                real_pct = pct_map.get(of_id, 0.0)
                
                row_orig = df_display.loc[idx]
                row_start = to_date_safe(row_orig["INICIO"])
                row_end = to_date_safe(row_orig["FINAL APROXIMADO"])
                
                if real_pct >= 100.0:
                    cell_style = "background-color: #28a745; color: #28a745;"
                elif real_pct > 0.0:
                    cell_style = "background-color: #ffc107; color: #ffc107;"
                else:
                    cell_style = "background-color: #a0aab2; color: #a0aab2;"
                    
                for col in date_cols:
                    col_dt = date_col_mapping[col]
                    if col_dt.weekday() in [5, 6]:
                        styles.at[idx, col] = "background-color: #e9ecef;"
                    if row_start and row_end and row_start <= col_dt <= row_end:
                        styles.at[idx, col] = cell_style
            return styles
            
        column_config_gantt = {
            "ORDENES DE FABRICACION": st.column_config.TextColumn("OF", width=100),
            "INFORMACIÓN DE LA OF": st.column_config.TextColumn("Información de la OF", width=220),
            "INICIO": st.column_config.TextColumn("Inicio", width=80),
            "FINAL APROXIMADO": st.column_config.TextColumn("Final", width=80),
            "AVANCE REAL (CORTE)": st.column_config.TextColumn("Avance", width=80)
        }
        for col in date_cols:
            column_config_gantt[col] = st.column_config.TextColumn(col, width=38)
            
        df_gantt_styled = df_gantt_table.style.apply(style_gantt, axis=None)
        st.dataframe(
            df_gantt_styled,
            column_config=column_config_gantt,
            use_container_width=True,
            hide_index=True,
            height=380
        )


def view_public_rotativo():
    import os
    import time
    from views.dashboard import view_dashboard
    from views.dashboard_global import view_dashboard_global
    from views.manufactura import view_manufactura
    
    # Inicializar el índice de pantalla en session_state si no existe
    if "rotativo_screen" not in st.session_state:
        st.session_state.rotativo_screen = 1
        
    current_screen = st.session_state.rotativo_screen
    
    # Definir subtítulo y calcular la siguiente pantalla (rotación de 6 pantallas)
    if current_screen == 1:
        subtitle = "1. Dashboard Principal"
        next_screen = 2
    elif current_screen == 2:
        subtitle = "2. Dashboard Global"
        next_screen = 3
    elif current_screen == 3:
        subtitle = "3. Programa de Producción"
        next_screen = 4
    elif current_screen == 4:
        subtitle = "4. Reporte Diario de Avances"
        next_screen = 5
    elif current_screen == 5:
        subtitle = "5. WIP en Piso (Reporte Global)"
        next_screen = 6
    else:
        subtitle = "6. Manufactura Inteligente"
        next_screen = 1
        
    st.markdown(
        """
        <style>
        html, body, [data-testid="stAppViewContainer"] {
            zoom: 0.88 !important;
        }
        .block-container {
            padding-top: 0rem !important;
            padding-bottom: 0rem !important;
            margin-top: 0px !important;
        }
        header {
            visibility: hidden;
            height: 0px;
        }
        </style>
        """,
        unsafe_allow_html=True
    )
    
    # Banner principal (Imagen del banner corporativo)
    dir_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    banner_path = os.path.join(dir_path, "assets", "banner.png")
    
    if os.path.exists(banner_path):
        col_b1, col_b2, col_b3 = st.columns([1, 3.7, 1])
        with col_b2:
            st.image(banner_path, use_container_width=True)
    else:
        st.info(f"TABLERO DE PLANTA — {subtitle}")
    
    # Mostrar la vista correspondiente
    if current_screen == 1:
        view_dashboard()
        
    elif current_screen == 2:
        view_dashboard_global()
        
    elif current_screen == 3:
        view_public_gantt()
        
    elif current_screen == 4:
        # Avance Diario
        date_str = datetime.today().strftime("%Y-%m-%d")
        fecha_formateada = datetime.today().strftime("%d/%m/%Y")
        
        st.markdown(f'<h2 style="margin-top:0; margin-bottom:10px; font-weight:900; font-family:\'Montserrat\'">📅 Avance Diario PLANTA METALES ({fecha_formateada})</h2>', unsafe_allow_html=True)
        
        query_dia = """
        SELECT of_number as OF, nido as Nido, no_pieza as Pieza, area as Área, 
               cantidad as Cantidad, operador as Operador, maquina as Máquina, timestamp as Fecha_Hora
        FROM avances 
        WHERE date(timestamp) = ?
        ORDER BY timestamp DESC
        """
        df_dia = fetch_data(query_dia, (date_str,))
        
        query_rechazos_dia = """
        SELECT area as Área, sum(cantidad) as Cantidad
        FROM rechazos 
        WHERE date(timestamp) = ?
        GROUP BY area
        """
        df_rechazos_dia = fetch_data(query_rechazos_dia, (date_str,))
        rechazos_por_area = df_rechazos_dia.set_index('Área')['Cantidad'].to_dict() if not df_rechazos_dia.empty else {}
        
        if df_dia.empty:
            st.info(f"No hay registros de avance para hoy ({fecha_formateada}).")
        else:
            avances_por_area = df_dia.groupby('Área')['Cantidad'].sum().to_dict()
            areas_orden = ["Ingenieria", "Corte", "Rebabeo", "Doblez", "Barrenado", "Liberado", "Empaque"]
            process_icons = {"Ingenieria": "💻", "Corte": "✂️", "Rebabeo": "⚙️", "Doblez": "📐", "Barrenado": "🔩", "Liberado": "✅", "Empaque": "📦"}
            
            # 7 columnas en una fila única
            cols = st.columns(7)
            for i, proc in enumerate(areas_orden):
                with cols[i]:
                    avance_val = avances_por_area.get(proc, 0)
                    rechazo_val = rechazos_por_area.get(proc, 0)
                    color = "#0056b3" if avance_val > 0 else "#6c757d"
                    icon = process_icons.get(proc, "🏭")
                    rechazo_html = f'<span style="font-size: 0.9rem; color: #EC2024; font-weight: bold; margin-left: 2px;">/ {int(rechazo_val)}</span>'
                    st.markdown(
                        f'''
                        <div style="background-color: #f8f9fa; border-top: 4px solid {color}; padding: 10px 5px; border-radius: 6px; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.08); margin-bottom: 10px;">
                            <div style="font-size: 1.4rem; margin-bottom: 2px;">{icon}</div>
                            <p style="margin: 0; font-size: 0.75rem; color: #666; font-weight: bold; text-transform: uppercase; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{proc}</p>
                            <h3 style="margin: 2px 0 0 0; font-size: 1.6rem; font-weight: 900; color: {color}; display: flex; align-items: baseline; justify-content: center; line-height: 1.1;">
                                {int(avance_val):,} {rechazo_html}
                            </h3>
                        </div>
                        ''', unsafe_allow_html=True
                    )
            
            st.markdown("<p style='margin-top:5px; margin-bottom:2px; font-weight:bold; font-size:0.95rem;'>📋 Últimos Movimientos del Día</p>", unsafe_allow_html=True)
            st.dataframe(df_dia, height=200, use_container_width=True)
            
    elif current_screen == 5:
        # WIP en Piso
        st.markdown('<h2 style="margin-top:0; margin-bottom:10px; font-weight:900; font-family:\'Montserrat\'">🏭 WIP en Piso (Trabajo en Proceso)</h2>', unsafe_allow_html=True)
        from views.reportes import get_global_wip_for_ofs
        wip_data = get_global_wip_for_ofs(["Todas"])
        
        if not wip_data:
            st.info("No hay registros de WIP activos.")
        else:
            # 7 columnas para WIP
            wip_areas = ["Corte", "Rebabeo", "Doblez", "Barrenado", "Pintura", "Liberado", "Empaque"]
            process_icons = {"Corte": "✂️", "Rebabeo": "⚙️", "Doblez": "📐", "Barrenado": "🔩", "Pintura": "🎨", "Liberado": "✅", "Empaque": "📦"}
            
            cols = st.columns(7)
            for i, proc in enumerate(wip_areas):
                with cols[i]:
                    wip_val = wip_data.get(proc, 0)
                    color = "#EC2024" if wip_val > 0 else "#28a745"
                    icon = process_icons.get(proc, "🏭")
                    
                    st.markdown(
                        f'''
                        <div style="background-color: #f8f9fa; border-top: 4px solid {color}; padding: 10px 5px; border-radius: 6px; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.08); margin-bottom: 10px;">
                            <div style="font-size: 1.4rem; margin-bottom: 2px;">{icon}</div>
                            <p style="margin: 0; font-size: 0.75rem; color: #666; font-weight: bold; text-transform: uppercase; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{proc}</p>
                            <h3 style="margin: 2px 0 0 0; font-size: 1.6rem; font-weight: 900; color: {color}; line-height: 1.1;">
                                {int(wip_val):,}
                            </h3>
                        </div>
                        ''', unsafe_allow_html=True
                    )
            
            # Gráfica de Pareto para el WIP
            df_wip = pd.DataFrame([{"Estación": k, "Piezas": v} for k, v in wip_data.items() if k not in ["Ingenieria"]])
            fig = px.bar(
                df_wip, x="Estación", y="Piezas",
                title="Distribución de Piezas en Espera", text="Piezas",
                color="Piezas", color_continuous_scale="Reds"
            )
            fig.update_layout(height=320, margin=dict(t=40, b=10, l=10, r=10), coloraxis_showscale=False)
            st.plotly_chart(fig, use_container_width=True)
            
    else:
        view_manufactura()
        
    # Avanzar la pantalla en session_state y forzar rerun tras esperar 15 segundos
    st.session_state.rotativo_screen = next_screen
    time.sleep(15)
    st.rerun()
