import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from utils.database import get_connection

@st.cache_data(ttl=60, show_spinner=False)
def load_global_data():
    """Cached global data load — refreshed every 60 seconds."""
    conn = get_connection()
    df_ofs = pd.read_sql_query("SELECT of_number, proyecto, fecha FROM ordenes", conn)
    
    query_piezas = """
        SELECT p.of_number, SUM(p.cantidad * n.hojas) as total_piezas
        FROM piezas p
        JOIN nidos n ON p.of_number = n.of_number AND p.nido = n.nido
        GROUP BY p.of_number
    """
    df_totales = pd.read_sql_query(query_piezas, conn)
    
    df_avances = pd.read_sql_query("SELECT of_number, area, cantidad, maquina, timestamp FROM avances", conn)
    df_rechazos = pd.read_sql_query("SELECT of_number, area, cantidad, maquina, timestamp FROM rechazos", conn)
    
    conn.close()
    
    return df_ofs, df_totales, df_avances, df_rechazos

def classify_shift(ts_str):
    if pd.isna(ts_str): return "Extra"
    try:
        ts = pd.to_datetime(ts_str)
        hour = ts.hour
        if 8 <= hour < 14: return "Mañana (8a-2p)"
        elif 14 <= hour < 15: return "Comida (2p-3p)"
        elif 15 <= hour < 18: return "Tarde (3p-6p)"
        else: return "Fuera de Horario"
    except:
        return "Desconocido"

def view_dashboard_global():
    st.markdown("## 🌐 1.2 Dashboard Global de Producción")
    st.markdown("Monitoreo general de Productividad, Avances Diarios y Desempeño en Piso (Todas las OFs).")
    
    df_ofs, df_totales, df_avances, df_rechazos = load_global_data()
    
    if df_ofs.empty:
        st.warning("No hay datos de producción en el sistema.")
        return
        
    # KPIs
    piezas_totales_req = df_totales['total_piezas'].sum() if not df_totales.empty else 0
    piezas_procesadas = df_avances['cantidad'].sum() if not df_avances.empty else 0
    scrap_generado = df_rechazos['cantidad'].sum() if not df_rechazos.empty else 0
    
    aprovechamiento = 100.0
    if (piezas_procesadas + scrap_generado) > 0:
        aprovechamiento = (piezas_procesadas / (piezas_procesadas + scrap_generado)) * 100
        
    c1, c2, c3, c4 = st.columns(4)
    def render_kpi(label, val, col, color="#EC2024", subtitle="", is_html=False):
        val_content = val
        if not is_html:
            val_content = f'<h2 style="margin: 5px 0 0 0; font-size: 2.5rem; font-weight: 900; color: #111;">{val}</h2>'
        col.markdown(
            f'''
            <div style="background-color: #f8f9fa; border-top: 5px solid {color}; padding: 15px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); text-align: center; min-height: 170px; display: flex; flex-direction: column; justify-content: space-between;">
                <div>
                    <p style="margin: 0; font-size: 0.85rem; color: #555; font-weight: bold; text-transform: uppercase; letter-spacing: 0.5px;">{label}</p>
                    {val_content}
                </div>
                <p style="margin: 5px 0 0 0; font-size: 0.75rem; color: #888;">{subtitle}</p>
            </div>
            ''', unsafe_allow_html=True
        )
    
    # Calcular avances por área para el desglose — vectorizado con groupby
    processes = ["Ingenieria", "Corte", "Rebabeo", "Doblez", "Barrenado", "Liberado", "Empaque"]
    area_avances = {}
    if not df_avances.empty:
        area_av = df_avances.groupby('area')['cantidad'].sum().to_dict()
        for p in processes:
            area_avances[p] = area_av.get(p, 0)
    else:
        for p in processes:
            area_avances[p] = 0
            
    # Formato de cuadrícula en 2 columnas para el KPI
    val_html = '<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 4px; font-size: 0.8rem; text-align: left; margin: 10px 0; padding: 0 5px; color: #333;">'
    for p in processes:
        display_name = p
        if p == "Ingenieria": display_name = "Ingeniería"
        val_html += f'<div><b>{display_name}:</b> {area_avances.get(p, 0):,}</div>'
    val_html += '</div>'
    
    render_kpi("Órdenes Totales", len(df_ofs), c1, subtitle="Cargadas en sistema")
    render_kpi("Piezas Solicitadas", f"{piezas_totales_req:,.0f}", c2, color="#00BFFF", subtitle="Total a producir")
    render_kpi("Avances Registrados", val_html, c3, color="#32CD32", subtitle="Avance por proceso/área", is_html=True)
    render_kpi("Aprovechamiento", f"{aprovechamiento:.1f}%", c4, color="#FF8C00", subtitle=f"Scrap: {scrap_generado} pzs")

    st.markdown("---")
    
    colA, colB, colC = st.columns([1.2, 1.2, 1.5])
    
    # 1. Estado de Producciones (Dona) — vectorizado con merge + groupby
    if not df_totales.empty and not df_avances.empty:
        tot_by_of = df_totales.set_index('of_number')['total_piezas']
        av_by_of = df_avances.groupby('of_number')['cantidad'].sum()
        df_of_estado_list = []
        for of in df_ofs['of_number']:
            tot = tot_by_of.get(of, 0)
            av = av_by_of.get(of, 0)
            estado = "Pendiente"
            if av > 0: estado = "En Proceso"
            if av >= (tot * 4) and tot > 0: estado = "Completada"
            df_of_estado_list.append({"OF": of, "Estado": estado})
    else:
        df_of_estado_list = [{"OF": of, "Estado": "Pendiente"} for of in df_ofs['of_number']]
    
    df_of_estado = pd.DataFrame(df_of_estado_list)
    estado_counts = df_of_estado['Estado'].value_counts().reset_index()
    estado_counts.columns = ['Estado', 'Cantidad']
    
    fig1 = px.pie(estado_counts, names='Estado', values='Cantidad', hole=0.6, 
                  color='Estado', color_discrete_map={"Completada": "#32CD32", "En Proceso": "#FFC107", "Pendiente": "#EC2024"})
    fig1.update_traces(textposition='inside', textinfo='percent+label')
    fig1.update_layout(title_text="<b>ESTADO DE OFs</b>", title_x=0.5, margin=dict(t=40, b=10, l=10, r=10), height=250, showlegend=False)
    colA.plotly_chart(fig1, use_container_width=True)
    
    # 2. Distribución por Horario
    if not df_avances.empty:
        df_avances['Turno'] = df_avances['timestamp'].apply(classify_shift)
        turno_counts = df_avances.groupby('Turno')['cantidad'].sum().reset_index()
        
        fig2 = px.pie(turno_counts, names='Turno', values='cantidad', hole=0.6,
                      color='Turno', color_discrete_map={"Mañana (8a-2p)": "#00BFFF", "Tarde (3p-6p)": "#FF8C00", "Comida (2p-3p)": "#D2D3D5", "Fuera de Horario": "#111111", "Extra": "#888888"})
        fig2.update_traces(textposition='inside', textinfo='percent+label')
        fig2.update_layout(title_text="<b>PRODUCTIVIDAD POR HORARIO</b>", title_x=0.5, margin=dict(t=40, b=10, l=10, r=10), height=250, showlegend=False)
        colB.plotly_chart(fig2, use_container_width=True)
    
    # 3. Tendencia Diaria por Área
    if not df_avances.empty:
        df_avances['Fecha'] = pd.to_datetime(df_avances['timestamp']).dt.date
        df_avances['Área'] = df_avances['area'].replace({
            "Ingenieria": "Ingeniería",
            "Corte": "Corte",
            "Rebabeo": "Rebabeo",
            "Doblez": "Doblez",
            "Barrenado": "Barrenado",
            "Pintura": "Pintura",
            "Liberado": "Liberado",
            "Empaque": "Empaque"
        })
        
        # Agrupar por fecha y área para separar las líneas
        tendencia = df_avances.groupby(['Fecha', 'Área'])['cantidad'].sum().reset_index()
        
        color_map = {
            "Ingeniería": "#FFD700",  # Gold
            "Corte": "#00BFFF",        # Deep Sky Blue
            "Rebabeo": "#FF6347",      # Tomato
            "Doblez": "#DC143C",       # Crimson
            "Barrenado": "#FF8C00",    # Dark Orange
            "Pintura": "#9370DB",      # Medium Purple
            "Liberado": "#D2B48C",     # Tan
            "Empaque": "#32CD32"       # Lime Green
        }
        
        fig3 = px.line(
            tendencia, 
            x='Fecha', 
            y='cantidad', 
            color='Área', 
            markers=True, 
            line_shape='spline',
            color_discrete_map=color_map
        )
        fig3.update_traces(marker=dict(size=6))
        fig3.update_layout(
            title_text="<b>TENDENCIA DIARIA POR ÁREA (Pzs)</b>", 
            title_x=0.5, 
            margin=dict(t=40, b=10, l=10, r=10), 
            height=250,
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=-0.4,
                xanchor="center",
                x=0.5,
                title=None
            )
        )
        colC.plotly_chart(fig3, use_container_width=True)

    st.markdown("---")
    
    # Bottom Row: Tabla de Máquinas y Listado de OFs
    col_t1, col_t2 = st.columns([1, 2])
    
    with col_t1:
        st.markdown("### 🖥️ Resumen por Máquina")
        if not df_avances.empty:
            maq_av = df_avances.groupby('maquina')['cantidad'].sum().reset_index()
            maq_rec = df_rechazos.groupby('maquina')['cantidad'].sum().reset_index() if not df_rechazos.empty else pd.DataFrame(columns=['maquina', 'cantidad'])
            
            df_maq = pd.merge(maq_av, maq_rec, on='maquina', how='left', suffixes=('_buenas', '_malas'))
            df_maq['cantidad_malas'] = df_maq['cantidad_malas'].fillna(0)
            df_maq['aprovechamiento'] = (df_maq['cantidad_buenas'] / (df_maq['cantidad_buenas'] + df_maq['cantidad_malas']) * 100).round(1)
            
            # Formato
            df_maq = df_maq.sort_values(by='cantidad_buenas', ascending=False)
            df_maq['aprovechamiento'] = df_maq['aprovechamiento'].astype(str) + "%"
            
            df_maq = df_maq.rename(columns={"maquina": "Máquina", "cantidad_buenas": "Producidas", "cantidad_malas": "Scrap", "aprovechamiento": "Aprovechamiento"})
            st.dataframe(df_maq, use_container_width=True, hide_index=True)

    with col_t2:
        col_lt1, col_lt2 = st.columns([1.2, 1])
        with col_lt1:
            st.markdown("### 📋 Listado de Producciones")
        with col_lt2:
            filtro_estado = st.selectbox(
                "Filtrar Estado:",
                ["🟡 En Proceso", "🔴 Pendiente", "🟢 Completada", "Todos"],
                index=0,
                key="listado_prod_filtro_estado"
            )
            
        # Vectorizado: merge + groupby en lugar de loop por OF
        tot_by_of = df_totales.set_index('of_number')['total_piezas'] if not df_totales.empty else pd.Series(dtype=float)
        av_by_of = df_avances.groupby('of_number')['cantidad'].sum() if not df_avances.empty else pd.Series(dtype=float)
        
        listado = []
        for _, row in df_ofs.iterrows():
            of = row['of_number']
            proy = row['proyecto']
            tot = int(tot_by_of.get(of, 0))
            av = int(av_by_of.get(of, 0))
            
            progreso = min(100.0, (av / (tot * 4) * 100)) if tot > 0 else 0
            
            estado = "🔴 Pendiente"
            if progreso > 0: estado = "🟡 En Proceso"
            if progreso >= 99: estado = "🟢 Completada"
            
            listado.append({
                "OF": of,
                "Proyecto": proy,
                "Piezas": tot,
                "Estado": estado,
                "Progreso %": round(progreso, 1)
            })
            
        df_listado = pd.DataFrame(listado)
        if not df_listado.empty and filtro_estado != "Todos":
            df_listado = df_listado[df_listado["Estado"] == filtro_estado]

        st.dataframe(
            df_listado, 
            use_container_width=True, 
            hide_index=True,
            column_config={
                "Progreso %": st.column_config.ProgressColumn("Progreso Estimado", min_value=0, max_value=100, format="%d%%")
            }
        )
