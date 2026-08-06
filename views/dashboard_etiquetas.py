import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import io

from utils.database import (
    get_connection,
    update_etiquetas_ordenes,
    save_db_to_excel,
    sync_and_push_db,
    get_local_today
)

def fetch_etiquetas_data():
    """Obtiene y consolida datos de órdenes, piezas y avances para el dashboard por etiquetas."""
    conn = get_connection()
    
    # 1. Órdenes con etiqueta
    df_ordenes = pd.read_sql_query("""
        SELECT of_number, proyecto, programador, fecha, po, calibre, prioridad, proyecto_cliente, etiqueta_proyecto
        FROM ordenes
    """, conn)
    
    # 2. Totales requeridos por OF
    df_piezas = pd.read_sql_query("""
        SELECT p.of_number, SUM(p.cantidad * COALESCE(n.hojas, 1)) as total_piezas
        FROM piezas p
        LEFT JOIN nidos n ON p.of_number = n.of_number AND p.nido = n.nido
        GROUP BY p.of_number
    """, conn)
    
    # 3. Avances registrados por OF y Área
    df_avances = pd.read_sql_query("""
        SELECT of_number, area, SUM(cantidad) as total_avances
        FROM avances
        GROUP BY of_number, area
    """, conn)
    
    conn.close()
    
    if df_ordenes.empty:
        return pd.DataFrame()
        
    df_ordenes["of_number"] = df_ordenes["of_number"].astype(str).str.strip()
    df_piezas["of_number"] = df_piezas["of_number"].astype(str).str.strip()
    df_avances["of_number"] = df_avances["of_number"].astype(str).str.strip()
    
    # Merge piezas totales
    df_master = df_ordenes.merge(df_piezas, on="of_number", how="left")
    df_master["total_piezas"] = df_master["total_piezas"].fillna(0).astype(int)
    
    # Calcular avances totales (suma de avances por OF)
    if not df_avances.empty:
        df_av_tot = df_avances.groupby("of_number")["total_avances"].sum().reset_index()
        df_master = df_master.merge(df_av_tot, on="of_number", how="left")
        df_master["total_avances"] = df_master["total_avances"].fillna(0).astype(int)
    else:
        df_master["total_avances"] = 0
        
    # Asignar Etiqueta por defecto si no tiene una definida
    def resolver_etiqueta(row):
        et = str(row.get("etiqueta_proyecto") or "").strip()
        if et and et.lower() not in ["none", "nan", "null"]:
            return et
        p_cli = str(row.get("proyecto_cliente") or "").strip()
        if p_cli and p_cli.lower() not in ["none", "nan", "null"]:
            return p_cli
        proy = str(row.get("proyecto") or "").strip()
        if proy and proy.lower() not in ["none", "nan", "null"]:
            return proy
        po_val = str(row.get("po") or "").strip()
        if po_val and po_val.lower() not in ["none", "nan", "null"]:
            return f"PO: {po_val}"
        return "Sin Etiqueta Asignada"

    df_master["Etiqueta"] = df_master.apply(resolver_etiqueta, axis=1)
    
    # Calcular % Progreso estimado por OF
    # Asumiendo 4 procesos promedio por pieza
    df_master["Progreso_OF"] = df_master.apply(
        lambda r: min(100.0, (r["total_avances"] / (r["total_piezas"] * 4) * 100)) if r["total_piezas"] > 0 else 0.0,
        axis=1
    ).round(1)
    
    return df_master


def generate_excel_etiquetas_report(df_report):
    """Genera archivo de Excel estilizado para descargar reporte de etiquetas."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_report.to_excel(writer, sheet_name="Resumen Etiquetas", index=False)
        workbook = writer.book
        worksheet = writer.sheets["Resumen Etiquetas"]
        
        fmt_header = workbook.add_format({
            "bold": True, "font_name": "Arial", "font_size": 10,
            "font_color": "#FFFFFF", "bg_color": "#EC2024",
            "align": "center", "valign": "vcenter", "border": 1
        })
        fmt_cell = workbook.add_format({
            "font_name": "Arial", "font_size": 9, "border": 1, "align": "center"
        })
        
        for col_idx, col_name in enumerate(df_report.columns):
            worksheet.write(0, col_idx, col_name, fmt_header)
            
        for r_idx in range(1, len(df_report) + 1):
            for c_idx in range(len(df_report.columns)):
                val = df_report.iloc[r_idx - 1, c_idx]
                if pd.isna(val):
                    worksheet.write_blank(r_idx, c_idx, "", fmt_cell)
                else:
                    worksheet.write(r_idx, c_idx, str(val), fmt_cell)
                    
        for i, col in enumerate(df_report.columns):
            max_len = max(df_report[col].astype(str).map(len).max(), len(col)) + 3
            worksheet.set_column(i, i, min(max_len, 40))
            
    return output.getvalue()


def view_dashboard_etiquetas():
    st.markdown("## 🏷️ Dashboard #3: Supervisión y Control por Etiquetas (PO / Proyectos)")
    st.markdown("Supervisa y agrupa órdenes de fabricación (OFs) derivadas de una misma PO o proyecto bajo **Etiquetas Personalizadas**.")

    df_master = fetch_etiquetas_data()
    
    if df_master.empty:
        st.warning("⚠️ No hay órdenes de fabricación registradas en el sistema.")
        return

    # ── MÓDULO 1: Asignación y Gestión de Etiquetas Especiales ─────────────
    with st.expander("✏️ **Asignar o Cambiar Etiqueta Especial a Órdenes (OFs)**", expanded=False):
        st.markdown("Selecciona una o más OFs y asígnales un **Nombre Especial / Etiqueta de Proyecto** (ej. `PO-2026-X1 - Lote A`, `Proyecto Planta Norte`).")
        
        col_m1, col_m2 = st.columns([1.5, 2.5])
        with col_m1:
            proyectos_existentes = sorted(df_master["proyecto"].dropna().unique().tolist())
            sel_proj_gestion = st.selectbox("📂 Filtrar por Proyecto Maestro / PO:", ["Todos los Proyectos"] + proyectos_existentes, key="m_proj_sel")
            
            if sel_proj_gestion == "Todos los Proyectos":
                df_ofs_sub = df_master
            else:
                df_ofs_sub = df_master[df_master["proyecto"] == sel_proj_gestion]
                
            ofs_disponibles = df_ofs_sub["of_number"].tolist()
            sel_ofs_etiquetar = st.multiselect(
                "📍 Selecciona la(s) OF(s) a etiquetar:",
                ofs_disponibles,
                key="m_ofs_multisel"
            )
            
        with col_m2:
            nueva_etiqueta_input = st.text_input(
                "🏷️ Nombre Especial / Etiqueta del Proyecto:",
                placeholder="Ej. PO #9982 - Proyecto Estructuras Especiales",
                key="m_nueva_etiqueta_input"
            )
            
            # Mostrar etiquetas existentes como sugerencia rápida
            etiquetas_sugeridas = [e for e in df_master["Etiqueta"].unique() if e != "Sin Etiqueta Asignada"]
            if etiquetas_sugeridas:
                st.markdown("**Etiquetas existentes en sistema:**")
                st.caption(", ".join(etiquetas_sugeridas[:10]))
                
            if st.button("💾 Guardar Etiqueta Especial", type="primary", use_container_width=True, key="m_save_etiqueta_btn"):
                if not sel_ofs_etiquetar:
                    st.warning("⚠️ Selecciona al menos una OF.")
                elif not nueva_etiqueta_input.strip():
                    st.warning("⚠️ Escribe un nombre o etiqueta válida.")
                else:
                    update_etiquetas_ordenes(sel_ofs_etiquetar, nueva_etiqueta_input.strip())
                    st.success(f"✅ ¡Etiqueta `{nueva_etiqueta_input.strip()}` asignada correctamente a {len(sel_ofs_etiquetar)} OF(s)!")
                    st.rerun()

    st.markdown("---")

    # ── MÓDULO 2: Filtros Principales del Dashboard ─────────────────────────
    f_col1, f_col2, f_col3, f_col4 = st.columns([1.5, 1.5, 1.5, 2])
    
    with f_col1:
        filtro_estado = st.selectbox(
            "⚡ Estado del Proyecto:",
            ["🟡 En Proceso", "🟢 Terminados", "⚪ Pendientes / Abiertos", "Todos"],
            index=0,
            key="dash3_filtro_estado"
        )
    with f_col2:
        proyectos_lista = ["Todos los Proyectos"] + sorted(df_master["proyecto"].dropna().unique().tolist())
        filtro_proyecto = st.selectbox("📂 Proyecto / PO Original:", proyectos_lista, key="dash3_filtro_proyecto")
        
    with f_col3:
        etiquetas_lista = ["Todas las Etiquetas"] + sorted(df_master["Etiqueta"].dropna().unique().tolist())
        filtro_etiqueta = st.selectbox("🏷️ Etiqueta Especial:", etiquetas_lista, key="dash3_filtro_etiqueta")
        
    with f_col4:
        search_query = st.text_input("🔍 Buscar (OF, PO, Etiqueta...):", "", key="dash3_search")

    # Aplicar filtros al df_master
    df_filtrado = df_master.copy()
    
    if filtro_proyecto != "Todos los Proyectos":
        df_filtrado = df_filtrado[df_filtrado["proyecto"] == filtro_proyecto]
        
    if filtro_etiqueta != "Todas las Etiquetas":
        df_filtrado = df_filtrado[df_filtrado["Etiqueta"] == filtro_etiqueta]
        
    if search_query.strip():
        sq = search_query.strip().lower()
        df_filtrado = df_filtrado[
            df_filtrado["of_number"].str.lower().str.contains(sq) |
            df_filtrado["proyecto"].astype(str).str.lower().str.contains(sq) |
            df_filtrado["Etiqueta"].astype(str).str.lower().str.contains(sq) |
            df_filtrado["po"].astype(str).str.lower().str.contains(sq)
        ]

    # Consolidar grupo por Etiqueta
    grupos_etiquetas = []
    for etiqueta_name, grp in df_filtrado.groupby("Etiqueta"):
        tot_piezas = grp["total_piezas"].sum()
        tot_avances = grp["total_avances"].sum()
        num_ofs = len(grp)
        
        # % Avance acumulado del proyecto/etiqueta
        progreso_glob = min(100.0, (tot_avances / (tot_piezas * 4) * 100)) if tot_piezas > 0 else 0.0
        progreso_glob = round(progreso_glob, 1)
        
        estado_label = "⚪ Pendientes / Abiertos"
        if progreso_glob > 0:
            estado_label = "🟡 En Proceso"
        if progreso_glob >= 99.0:
            estado_label = "🟢 Terminados"
            
        proyectos_rel = ", ".join(grp["proyecto"].dropna().unique())
        pos_rel = ", ".join(grp["po"].dropna().unique())
        
        grupos_etiquetas.append({
            "Etiqueta": etiqueta_name,
            "Proyecto Maestro": proyectos_rel,
            "PO": pos_rel,
            "OFs": num_ofs,
            "Piezas Requeridas": tot_piezas,
            "Avances Registrados": tot_avances,
            "Progreso %": progreso_glob,
            "Estado": estado_label,
            "_grp_df": grp
        })
        
    df_etiquetas = pd.DataFrame(grupos_etiquetas)
    
    if not df_etiquetas.empty:
        if filtro_estado != "Todos":
            df_etiquetas = df_etiquetas[df_etiquetas["Estado"] == filtro_estado]

    if df_etiquetas.empty:
        st.info("ℹ️ No se encontraron proyectos o etiquetas que coincidan con los filtros seleccionados.")
        return

    # ── MÓDULO 3: KPIs Superiores ──────────────────────────────────────────
    tot_etiquetas = len(df_etiquetas)
    num_terminados = len(df_etiquetas[df_etiquetas["Estado"] == "🟢 Terminados"])
    num_en_proceso = len(df_etiquetas[df_etiquetas["Estado"] == "🟡 En Proceso"])
    num_pendientes = len(df_etiquetas[df_etiquetas["Estado"] == "⚪ Pendientes / Abiertos"])
    avg_progreso = df_etiquetas["Progreso %"].mean() if tot_etiquetas > 0 else 0.0

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Proyectos / Etiquetas", f"{tot_etiquetas} etiquetas")
    k2.metric("🟢 Terminados", f"{num_terminados} proyectos")
    k3.metric("🟡 En Proceso", f"{num_en_proceso} proyectos")
    k4.metric("⚪ Pendientes", f"{num_pendientes} proyectos")
    k5.metric("📈 Avance Promedio", f"{avg_progreso:.1f}%")

    st.markdown("---")

    # ── MÓDULO 4: Gráfica de Avance de Proyectos ─────────────────────────────
    g_col1, g_col2 = st.columns([2, 1])
    
    with g_col1:
        # Gráfica de barras horizontales de progreso por etiqueta
        df_sorted = df_etiquetas.sort_values("Progreso %", ascending=True)
        
        color_map_stat = {
            "🟢 Terminados": "#32CD32",
            "🟡 En Proceso": "#FFC107",
            "⚪ Pendientes / Abiertos": "#888888"
        }
        
        fig_bar = px.bar(
            df_sorted,
            y="Etiqueta",
            x="Progreso %",
            color="Estado",
            color_discrete_map=color_map_stat,
            orientation="h",
            text="Progreso %",
            title="<b>% Avance por Etiqueta / Proyecto</b>"
        )
        fig_bar.update_traces(texttemplate='%{text:.1f}%', textposition='outside')
        fig_bar.update_layout(
            xaxis=dict(range=[0, 115], title="% Avance Acumulado"),
            yaxis=dict(title="Etiqueta del Proyecto"),
            height=max(300, len(df_sorted) * 35),
            margin=dict(l=10, r=20, t=40, b=20)
        )
        st.plotly_chart(fig_bar, use_container_width=True)
        
    with g_col2:
        # Pie chart de distribución de estados
        fig_pie = px.pie(
            df_etiquetas,
            names="Estado",
            title="<b>Distribución de Estatus</b>",
            color="Estado",
            color_discrete_map=color_map_stat,
            hole=0.55
        )
        fig_pie.update_traces(textinfo='percent+label')
        fig_pie.update_layout(height=300, margin=dict(l=10, r=10, t=40, b=10), showlegend=False)
        st.plotly_chart(fig_pie, use_container_width=True)

    # ── MÓDULO 5: Tarjetas de Proyectos y Desglose de OFs ────────────────────
    st.markdown("---")
    st.markdown("### 📋 Tarjetas de Proyectos por Etiqueta")

    for _, row in df_etiquetas.iterrows():
        etiqueta_name = row["Etiqueta"]
        estado_label = row["Estado"]
        num_ofs = row["OFs"]
        pzs_req = row["Piezas Requeridas"]
        pzs_av = row["Avances Registrados"]
        prog_pct = row["Progreso %"]
        proyecto_origin = row["Proyecto Maestro"]
        po_origin = row["PO"]
        grp_df = row["_grp_df"]
        
        # Determinar color de badge
        if "Terminados" in estado_label:
            badge_bg = "#d4edda"
            badge_fg = "#155724"
            border_left_color = "#32CD32"
        elif "En Proceso" in estado_label:
            badge_bg = "#fff3cd"
            badge_fg = "#856404"
            border_left_color = "#FFC107"
        else:
            badge_bg = "#e2e3e5"
            badge_fg = "#383d41"
            border_left_color = "#888888"

        with st.container(border=True):
            head_col1, head_col2 = st.columns([3, 1])
            with head_col1:
                st.markdown(f"<h3 style='margin: 0; font-family: Montserrat; color: #111;'>🏷️ {etiqueta_name}</h3>", unsafe_allow_html=True)
                st.caption(f"**Proyecto Maestro:** {proyecto_origin} | **PO:** {po_origin or 'N/A'}")
            with head_col2:
                st.markdown(
                    f"<div style='text-align: right; padding-top: 5px;'>"
                    f"<span style='background-color: {badge_bg}; color: {badge_fg}; font-weight: bold; padding: 6px 14px; border-radius: 20px; font-size: 0.9rem; font-family: Montserrat; display: inline-block;'>"
                    f"{estado_label} ({prog_pct:.1f}%)"
                    f"</span></div>",
                    unsafe_allow_html=True
                )
                
            st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
            
            m_col1, m_col2, m_col3, m_col4 = st.columns([2.5, 1, 1.2, 1.2])
            with m_col1:
                st.caption(f"**Avance Global del Proyecto ({prog_pct:.1f}%)**")
                st.progress(min(1.0, max(0.0, float(prog_pct) / 100.0)))
            with m_col2:
                st.metric("OFs Unidas", f"{num_ofs} OFs")
            with m_col3:
                st.metric("Piezas Requeridas", f"{pzs_req:,} pzs")
            with m_col4:
                st.metric("Avances Totales", f"{pzs_av:,} pzs")
                
            with st.expander(f"📂 **Ver Desglose de las {num_ofs} OFs de esta Etiqueta (`{etiqueta_name}`)**"):
                df_ofs_card = grp_df[["of_number", "proyecto", "po", "calibre", "prioridad", "total_piezas", "total_avances", "Progreso_OF"]].rename(columns={
                    "of_number": "OF",
                    "proyecto": "Proyecto",
                    "po": "PO",
                    "calibre": "Calibre",
                    "prioridad": "Parcialidad / Prioridad",
                    "total_piezas": "Total Piezas",
                    "total_avances": "Avances Totales",
                    "Progreso_OF": "Progreso %"
                })
                
                st.dataframe(
                    df_ofs_card,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Progreso %": st.column_config.ProgressColumn("Progreso Estimado", min_value=0, max_value=100, format="%d%%")
                    }
                )

    # ── MÓDULO 6: Tabla General Resumen y Exportación a Excel ────────────────
    st.markdown("---")
    st.markdown("### 📥 Exportación de Informe Consolidado por Etiquetas")
    
    df_export = df_etiquetas[["Etiqueta", "Proyecto Maestro", "PO", "OFs", "Piezas Requeridas", "Avances Registrados", "Progreso %", "Estado"]].copy()
    
    col_d1, col_d2 = st.columns([3, 1])
    with col_d1:
        st.dataframe(df_export, use_container_width=True, hide_index=True)
    with col_d2:
        excel_bytes = generate_excel_etiquetas_report(df_export)
        st.download_button(
            label="📥 Descargar Reporte en Excel",
            data=excel_bytes,
            file_name=f"Reporte_Supervision_Etiquetas_{get_local_today().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            type="primary"
        )
