import streamlit as st
import pandas as pd
import sqlite3
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta

def get_connection():
    return sqlite3.connect("sigrama.db")

def fetch_data(query, params=()):
    conn = get_connection()
    df = pd.read_sql(query, conn, params=params)
    conn.close()
    return df

def convert_df(df):
    return df.to_csv(index=False).encode('utf-8')

def view_consultas():
    st.title("2. CONSULTAS Y REPORTES")

    tab1, tab2, tab3, tab4 = st.tabs([
        "📅 Avance del Día", 
        "📊 Avance Semanal", 
        "🔍 Trazabilidad", 
        "📉 Calidad (Rechazos)"
    ])

    # --- PESTAÑA 1: Avance del Día ---
    with tab1:
        st.subheader("Reporte Diario de Avances")
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
            areas_orden = ["Ingenieria", "Corte", "Rebabeo", "Doblez", "Barrenado", "Pintura", "Liberado", "Empaque"]
            
            process_icons = {
                "Ingenieria": "💻",
                "Corte": "✂️",
                "Rebabeo": "⚙️",
                "Doblez": "📐",
                "Barrenado": "🔩",
                "Pintura": "🎨",
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
            search_area = st.selectbox("Filtrar por Área:", ["Todas", "Ingenieria", "Corte", "Rebabeo", "Doblez", "Barrenado", "Pintura", "Liberado", "Empaque"])
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
        SELECT of_number as OF, nido as Nido, no_pieza as Pieza, area as Área, 
               cantidad as Cantidad, motivo as Motivo, operador as Operador, timestamp as Fecha_Hora
        FROM rechazos
        ORDER BY timestamp DESC
        """
        df_calidad = fetch_data(query_calidad)
        
        if df_calidad.empty:
            st.success("¡Excelentes noticias! No hay registros de piezas rechazadas.")
        else:
            col_chart1, col_chart2 = st.columns(2)
            
            with col_chart1:
                # Grafica por motivo
                df_motivos = df_calidad.groupby('Motivo')['Cantidad'].sum().reset_index()
                fig_mot = px.pie(df_motivos, values='Cantidad', names='Motivo', title='Rechazos por Motivo', hole=0.4)
                st.plotly_chart(fig_mot, use_container_width=True)
                
            with col_chart2:
                # Grafica por area
                df_areas = df_calidad.groupby('Área')['Cantidad'].sum().reset_index()
                fig_ar = px.bar(df_areas, x='Área', y='Cantidad', title='Rechazos por Área', text='Cantidad')
                fig_ar.update_traces(textposition='outside')
                st.plotly_chart(fig_ar, use_container_width=True)
                
            st.markdown("#### Detalle de Piezas Rechazadas")
            st.dataframe(df_calidad, use_container_width=True)
            csv_cal = convert_df(df_calidad)
            st.download_button(
                label="📥 Descargar Reporte de Rechazos (CSV)",
                data=csv_cal,
                file_name='rechazos.csv',
                mime='text/csv',
            )

