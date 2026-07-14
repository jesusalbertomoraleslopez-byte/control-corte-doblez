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

def view_consultas():
    st.title("2. CONSULTAS Y REPORTES")

    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "📅 Avance del Día", 
        "📊 Avance Semanal", 
        "🔍 Trazabilidad", 
        "📉 Calidad (Rechazos)",
        "📦 Material Programado",
        "🏭 WIP en Piso (Reportes)"
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
                                if c_idx in num_cols:
                                    ws.write_number(data_row, c_idx, int(val), fmt_num_alt if alt else fmt_num)
                                else:
                                    ws.write(data_row, c_idx, val, fmt_alt if alt else fmt_cell)
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


def view_public_avance_diario():
    import base64
    import os
    
    # Obtener la ruta del logo de forma robusta
    dir_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    logo_path = os.path.join(dir_path, "assets", "logo.png")
    
    if os.path.exists(logo_path):
        try:
            with open(logo_path, "rb") as img_f:
                logo_base64 = base64.b64encode(img_f.read()).decode("utf-8")
            logo_html = f'<img src="data:image/png;base64,{logo_base64}" style="height: 45px; vertical-align: middle;">'
        except Exception:
            logo_html = '<span style="color: white; font-weight: bold; font-size: 20px;">SIGRAMA</span>'
    else:
        # Fallback si no existe el archivo física
        logo_html = """
        <div style="display: flex; align-items: center;">
            <svg width="45" height="45" viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg" style="margin-right: 15px;">
              <polygon points="0,0 100,0 100,15 0,30" fill="#EC2024" />
              <polygon points="0,40 100,25 100,75 0,60" fill="#EC2024" />
              <polygon points="0,70 100,85 100,100 0,100" fill="#EC2024" />
            </svg>
            <div style="display: flex; flex-direction: column;">
                <span style="font-family: 'Questrial', sans-serif; font-size: 12px; letter-spacing: 4px; color: white; line-height: 1; margin-bottom: -2px;">
                    industria
                </span>
                <span style="font-family: 'Montserrat', sans-serif; font-size: 24px; font-weight: 900; font-style: italic; color: white; line-height: 1;">
                    SIGRAMA
                </span>
            </div>
        </div>
        """
        
    # Establecer estilo del banner principal para la vista pública
    banner_html = f"""
    <div style="background: linear-gradient(135deg, #000000 0%, #222222 100%); 
                border-radius: 8px; padding: 25px 35px; margin-bottom: 25px; 
                box-shadow: 0 10px 20px rgba(0,0,0,0.1); position: relative; overflow: hidden;
                display: flex; justify-content: space-between; align-items: center;">
        <div style="display: flex; align-items: center;">
            {logo_html}
        </div>
        <div style="text-align: right;">
            <span style="font-family: 'Montserrat', sans-serif; font-size: 16px; font-weight: 700; color: #EC2024;">REPORTE PÚBLICO</span><br>
            <span style="font-family: 'Questrial', sans-serif; font-size: 11px; color: #aaa;">Monitoreo Diario de Planta</span>
        </div>
    </div>
    """
    st.markdown(banner_html, unsafe_allow_html=True)
    st.title("📅 Reporte Diario de Avances PLANTA METALES")
    
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


def view_public_rotativo():
    import base64
    import os
    import streamlit.components.v1 as components
    
    # 1. Obtener la ruta del logo de forma robusta
    dir_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    logo_path = os.path.join(dir_path, "assets", "logo.png")
    
    if os.path.exists(logo_path):
        try:
            with open(logo_path, "rb") as img_f:
                logo_base64 = base64.b64encode(img_f.read()).decode("utf-8")
            logo_html = f'<img src="data:image/png;base64,{logo_base64}" style="height: 45px; vertical-align: middle;">'
        except Exception:
            logo_html = '<span style="color: white; font-weight: bold; font-size: 20px;">SIGRAMA</span>'
    else:
        logo_html = '<span style="color: white; font-weight: bold; font-size: 20px;">SIGRAMA</span>'
        
    # Obtener la pantalla actual (1, 2 o 3)
    current_screen = st.query_params.get("screen", "1")
    
    # Definir subtítulo y calcular la siguiente pantalla
    if current_screen == "1":
        subtitle = "1. Reporte Diario de Avances"
        next_screen = "2"
    elif current_screen == "2":
        subtitle = "2. Tendencia Semanal"
        next_screen = "3"
    else:
        subtitle = "3. WIP en Piso (Reporte Global)"
        next_screen = "1"
        
    # Banner principal
    banner_html = f"""
    <div style="background: linear-gradient(135deg, #000000 0%, #222222 100%); 
                border-radius: 8px; padding: 25px 35px; margin-bottom: 25px; 
                box-shadow: 0 10px 20px rgba(0,0,0,0.1); position: relative; overflow: hidden;
                display: flex; justify-content: space-between; align-items: center;">
        <div style="display: flex; align-items: center;">
            {logo_html}
        </div>
        <div style="text-align: right;">
            <span style="font-family: 'Montserrat', sans-serif; font-size: 16px; font-weight: 700; color: #EC2024;">TABLERO DE PLANTA (ROTATIVO)</span><br>
            <span style="font-family: 'Questrial', sans-serif; font-size: 11px; color: #aaa;">{subtitle} — Rotación cada 15s</span>
        </div>
    </div>
    """
    st.markdown(banner_html, unsafe_allow_html=True)
    
    # Mostrar la vista correspondiente
    if current_screen == "1":
        st.title("📅 Reporte Diario de Avances PLANTA METALES")
        selected_date = st.date_input("Selecciona el día a consultar:", datetime.today())
        date_str = selected_date.strftime("%Y-%m-%d")
        
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
            st.info(f"No hay registros de avance para el {date_str}.")
        else:
            avances_por_area = df_dia.groupby('Área')['Cantidad'].sum().to_dict()
            areas_orden = ["Ingenieria", "Corte", "Rebabeo", "Doblez", "Barrenado", "Liberado", "Empaque"]
            process_icons = {"Ingenieria": "💻", "Corte": "✂️", "Rebabeo": "⚙️", "Doblez": "📐", "Barrenado": "🔩", "Liberado": "✅", "Empaque": "📦"}
            
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
            
    elif current_screen == "2":
        st.title("📊 Tendencia Semanal por Área (Últimos 7 días)")
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
            areas_presentes = df_semana['Área'].unique()
            for area in areas_presentes:
                df_area = df_semana[df_semana['Área'] == area]
                fig = px.bar(
                    df_area, x='Fecha', y='Total', title=f"Avance en {area}", text='Total',
                    color_discrete_sequence=['#EC2024']
                )
                fig.update_traces(textposition='outside')
                fig.update_layout(xaxis_type='category', margin=dict(t=40, b=10, l=10, r=10))
                st.plotly_chart(fig, use_container_width=True)
                
    else:
        st.title("🏭 WIP en Piso (Trabajo en Proceso)")
        view_reportes()
        
    # Script JS para refrescar y avanzar a la siguiente pantalla tras 15 segundos
    js_code = f"""
    <script>
    setTimeout(function() {{
        var url = new URL(window.parent.location.href);
        url.searchParams.set("screen", "{next_screen}");
        window.parent.location.href = url.toString();
    }}, 15000);
    </script>
    """
    components.html(js_code, height=0)
