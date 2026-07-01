import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from utils.database import get_active_of, get_dashboard_stats

# ─────────────────────────────────────────────
#  CONSTANTS
# ─────────────────────────────────────────────
PROCESSES = ["Ingenieria", "Corte", "Rebabeo", "Doblez", "Barrenado", "Pintura", "Liberado", "Empaque"]
PROCESS_LABELS = ["Ingeniería", "Corte Láser", "Rebabeo", "Doblez", "Barrenado", "Pintura", "Liberado", "Empaque"]
PROCESS_WEIGHTS = [0.03, 0.25, 0.10, 0.25, 0.10, 0.15, 0.05, 0.07]
PROCESS_COLORS = [
    "#FFD700",  # Ingeniería – gold
    "#00BFFF",  # Corte Láser – deep sky blue
    "#FF6347",  # Rebabeo – tomato
    "#DC143C",  # Doblez – crimson
    "#FF8C00",  # Barrenado - dark orange
    "#9370DB",  # Pintura – medium purple
    "#D2B48C",  # Liberado – tan
    "#32CD32",  # Empaque – lime green
]

RED   = "#EC2024"
BLACK = "#111111"
GRAY  = "#D2D3D5"
WHITE = "#FFFFFF"


# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────
def _card(label: str, value: str, color: str = RED, text_color: str = WHITE) -> str:
    return f"""
    <div style="
        background-color:{color}; 
        padding:20px; 
        border-radius:12px; 
        box-shadow:0 4px 6px rgba(0,0,0,0.1); 
        text-align:center;
        height: 100%;
        display: flex;
        flex-direction: column;
        justify-content: center;
    ">
        <div style="color:{text_color}; font-size:13px; font-family:'Montserrat',sans-serif;
                    font-weight:600; letter-spacing:0.5px; margin-bottom:6px;">
            {label}
        </div>
        <div style="color:{text_color}; font-size:28px; font-family:'Montserrat',sans-serif;
                    font-weight:700; line-height:1;">
            {value}
        </div>
    </div>"""


# ─────────────────────────────────────────────
#  SUB-SECTIONS
# ─────────────────────────────────────────────
def _render_top_metrics(total_nidos, total_hojas, total_piezas, avance_global):
    st.markdown(
        '<p style="font-family:Montserrat,sans-serif;font-weight:700;font-size:16px;'
        'color:#111111;margin-bottom:8px;letter-spacing:0.5px;">📊 INDICADORES PRINCIPALES</p>',
        unsafe_allow_html=True,
    )
    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(_card("TOTAL NIDOS", str(total_nidos), RED), unsafe_allow_html=True)
    c2.markdown(_card("TOTAL HOJAS", f"{total_hojas:,}", BLACK), unsafe_allow_html=True)
    c3.markdown(_card("TOTAL PIEZAS", f"{total_piezas:,}", "#1a1a2e"), unsafe_allow_html=True)
    c4.markdown(_card("% AVANCE GLOBAL", f"{avance_global:.1f}%", "#007a33"), unsafe_allow_html=True)


def _render_wip_flow(pcts: list[float]):
    """Horizontal WIP flow using Plotly shapes & annotations."""
    st.markdown(
        '<p style="font-family:Montserrat,sans-serif;font-weight:700;font-size:16px;'
        'color:#111111;margin-top:24px;margin-bottom:4px;letter-spacing:0.5px;">🔄 FLUJO WIP – PIPELINE DE PRODUCCIÓN</p>',
        unsafe_allow_html=True,
    )

    n = len(PROCESSES)
    fig = go.Figure()

    box_w, box_h = 0.9, 0.6
    spacing = 1.4

    for i, (label, pct, color) in enumerate(zip(PROCESS_LABELS, pcts, PROCESS_COLORS)):
        x0 = i * spacing
        x1 = x0 + box_w
        y0, y1 = 0.0, box_h

        # Box
        fig.add_shape(
            type="rect", x0=x0, y0=y0, x1=x1, y1=y1,
            fillcolor=color, opacity=0.85,
            line=dict(color="#cccccc", width=1),
        )

        # Label
        fig.add_annotation(
            x=(x0 + x1) / 2, y=0.3,
            text=label, showarrow=False,
            font=dict(size=11, color=WHITE, family="Questrial"),
        )
        # Percentage
        fig.add_annotation(
            x=(x0 + x1) / 2, y=0.1,
            text=f"{pct:.1f}%", showarrow=False,
            font=dict(size=14, color=WHITE, family="Montserrat", weight="bold"),
        )

        # Arrow connecting to next box
        if i < n - 1:
            fig.add_annotation(
                x=x1 + 0.25, y=0.3,
                ax=x1, ay=0.3,
                xref="x", yref="y", axref="x", ayref="y",
                showarrow=True, arrowhead=2, arrowsize=1.5, arrowwidth=2, arrowcolor="#aaaaaa"
            )

    fig.update_layout(
        xaxis=dict(visible=False, range=[-0.2, (n - 1) * spacing + box_w + 0.2]),
        yaxis=dict(visible=False, range=[-0.2, box_h + 0.3]),
        margin=dict(l=0, r=0, t=10, b=0),
        height=140,
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
def _render_progress_table(pcts: list[float], avance_pzs: list[int], total_piezas: int, total_nidos: int, total_partes: int):
    st.markdown(
        '<p style="font-family:Montserrat,sans-serif;font-weight:700;font-size:16px;'
        'color:#111111;margin-top:24px;margin-bottom:4px;letter-spacing:0.5px;">📋 TABLA DE PROGRESO POR PROCESO</p>',
        unsafe_allow_html=True,
    )

    avance_total_valor = sum(p / 100 * w for p, w in zip(pcts, PROCESS_WEIGHTS)) * 100

    rows_html = ""
    for i, (proc, label, w, pct, pzs) in enumerate(
        zip(PROCESSES, PROCESS_LABELS, PROCESS_WEIGHTS, pcts, avance_pzs)
    ):
        faltante = max(0.0, 100.0 - pct)
        valor_pct = w * 100
        avance_valor = pct / 100 * valor_pct
        bg = "#f8f8f8" if i % 2 == 0 else WHITE

        bar_width = int(pct)
        bar_html = (
            f'<div style="background:#e0e0e0;border-radius:4px;height:8px;width:100%;">'
            f'<div style="background:{PROCESS_COLORS[i]};width:{bar_width}%;height:8px;border-radius:4px;"></div>'
            f"</div>"
        )
        
        # Lógica dinámica: Corte usa Nidos, Ingeniería usa Partes, lo demás Piezas
        if proc == "Ingenieria":
            unidad_texto = f"{total_partes:,} (Partes)"
            avance_texto = f"{pzs:,} (Partes)"
        elif proc == "Corte":
            unidad_texto = f"{total_nidos:,} (Nidos)"
            avance_texto = f"{pzs:,} (Nidos)"
        else:
            unidad_texto = f"{total_piezas:,} (Pzs)"
            avance_texto = f"{pzs:,} (Pzs)"

        rows_html += f"""
        <tr style="background:{bg};">
            <td style="padding:8px 12px;font-weight:600;color:{BLACK};font-family:Questrial,sans-serif;">{label}</td>
            <td style="padding:8px 12px;text-align:center;">{unidad_texto}</td>
            <td style="padding:8px 12px;text-align:center;">{avance_texto}</td>
            <td style="padding:8px 12px;text-align:center;">{bar_html}<span style="font-size:11px;">{pct:.1f}%</span></td>
            <td style="padding:8px 12px;text-align:center;color:{RED};">{faltante:.1f}%</td>
            <td style="padding:8px 12px;text-align:center;">{valor_pct:.0f}%</td>
            <td style="padding:8px 12px;text-align:center;font-weight:700;">{avance_valor:.2f}%</td>
        </tr>"""

    # Totals row
    total_faltante = max(0.0, 100.0 - avance_total_valor)
    rows_html += f"""
    <tr style="background:#111111;color:white;">
        <td style="padding:10px 12px;font-weight:700;font-family:Montserrat,sans-serif;">AVANCE TOTAL</td>
        <td style="padding:10px 12px;text-align:center;font-weight:700;">{total_piezas:,} (Pzs)</td>
        <td style="padding:10px 12px;text-align:center;font-weight:700;">—</td>
        <td style="padding:10px 12px;text-align:center;font-weight:700;">—</td>
        <td style="padding:10px 12px;text-align:center;font-weight:700;color:#FF6B6B;">{total_faltante:.1f}%</td>
        <td style="padding:10px 12px;text-align:center;font-weight:700;">100%</td>
        <td style="padding:10px 12px;text-align:center;font-weight:700;color:#32CD32;">{avance_total_valor:.2f}%</td>
    </tr>"""

    table_html = f"""
    <div style="overflow-x:auto;border-radius:10px;box-shadow:0 2px 8px rgba(0,0,0,0.1);margin-bottom:20px;">
    <table style="width:100%;border-collapse:collapse;font-family:Questrial,sans-serif;font-size:13px;">
        <thead>
            <tr style="background:{RED};color:{WHITE};">
                <th style="padding:10px 12px;text-align:left;font-family:Montserrat,sans-serif;">PROCESOS</th>
                <th style="padding:10px 12px;text-align:center;font-family:Montserrat,sans-serif;">PIEZAS</th>
                <th style="padding:10px 12px;text-align:center;font-family:Montserrat,sans-serif;">AVANCE (PZS)</th>
                <th style="padding:10px 12px;text-align:center;font-family:Montserrat,sans-serif;">% AVANCE</th>
                <th style="padding:10px 12px;text-align:center;font-family:Montserrat,sans-serif;">% FALTANTE</th>
                <th style="padding:10px 12px;text-align:center;font-family:Montserrat,sans-serif;">VALOR</th>
                <th style="padding:10px 12px;text-align:center;font-family:Montserrat,sans-serif;">AVANCE TOTAL</th>
            </tr>
        </thead>
        <tbody>{rows_html}</tbody>
    </table>
    </div>"""

    st.markdown(table_html, unsafe_allow_html=True)


def _render_donut_row(pcts: list[float], overall_pct: float):
    st.markdown(
        '''
        <style>
        div[data-testid="stPlotlyChart"] {
            transition: transform 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275);
        }
        div[data-testid="stPlotlyChart"]:hover {
            transform: scale(1.12);
            z-index: 10;
        }
        </style>
        <p style="font-family:Montserrat,sans-serif;font-weight:700;font-size:16px;color:#111111;margin-top:24px;margin-bottom:4px;letter-spacing:0.5px;">🍩 AVANCE POR PROCESO</p>
        ''',
        unsafe_allow_html=True,
    )

    num_procs = len(PROCESS_LABELS)
    # num_procs small donuts + 1 large overall donut
    left_col, right_col = st.columns([num_procs, 2])

    with left_col:
        mini_cols = st.columns(num_procs)
        for i, (pct, color, label) in enumerate(zip(pcts, PROCESS_COLORS, PROCESS_LABELS)):
            remaining = max(0.0, 100.0 - pct)
            fig = go.Figure(
                go.Pie(
                    values=[pct, remaining],
                    hole=0.62,
                    marker=dict(colors=[color, "#e8e8e8"]),
                    textinfo="none",
                    hovertemplate=f"<b>{label}</b><br>Avance: {pct:.1f}%<extra></extra>",
                    showlegend=False,
                )
            )
            fig.add_annotation(
                x=0.5, y=0.5,
                text=f"<b>{pct:.0f}%</b>",
                showarrow=False,
                font=dict(size=15, color=BLACK, family="Montserrat"),
                xref="paper", yref="paper",
            )
            fig.update_layout(
                height=180,
                margin=dict(l=0, r=0, t=35, b=0),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                title=dict(
                    text=f"{label}",
                    x=0.5, y=0.98,
                    font=dict(size=11, family="Questrial", color=BLACK),
                ),
            )
            with mini_cols[i]:
                st.plotly_chart(fig, use_container_width=True, key=f"donut_{i}")

    with right_col:
        remaining_overall = max(0.0, 100.0 - overall_pct)
        fig2 = go.Figure(
            go.Pie(
                values=[overall_pct, remaining_overall],
                hole=0.65,
                marker=dict(colors=[RED, "#e8e8e8"]),
                textinfo="none",
                hovertemplate=f"<b>Avance Global</b><br>{overall_pct:.1f}%<extra></extra>",
                showlegend=False,
            )
        )
        fig2.add_annotation(
            x=0.5, y=0.5,
            text=f"<b>{overall_pct:.1f}%</b>",
            showarrow=False,
            font=dict(size=18, color=RED, family="Montserrat"),
            xref="paper", yref="paper",
        )
        fig2.update_layout(
            height=220,
            margin=dict(l=0, r=0, t=10, b=10),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            title=dict(
                text="<b>AVANCE<br>GLOBAL</b>",
                x=0.5, y=0.95,
                font=dict(size=11, family="Montserrat", color=BLACK),
            ),
        )
        st.plotly_chart(fig2, key="overall_donut_chart")


# ─────────────────────────────────────────────
#  MAIN VIEW
# ─────────────────────────────────────────────
def view_dashboard():
    st.markdown("## 📊 Dashboard Principal")

    # Obtener orden activa
    active_of = get_active_of()

    # ── Top Filters ──────────────────────────────────────────────
    from utils.database import get_connection
    conn = get_connection()
    df_ofs = pd.read_sql_query("SELECT of_number, proyecto FROM ordenes", conn)
    conn.close()
    
    if df_ofs.empty:
        st.warning("⚠️ No hay Órdenes de Fabricación registradas en el sistema.")
        return
        
    proyectos = ["Todos"] + [p for p in df_ofs['proyecto'].dropna().unique() if p.strip()]
    
    col_p, col_o = st.columns(2)
    with col_p:
        sel_proyecto = st.selectbox("📂 Proyecto (PO):", proyectos, key="dash_proj")
        
    # Filter OFs based on Project
    if sel_proyecto == "Todos":
        ofs_disponibles = df_ofs['of_number'].tolist()
    else:
        ofs_disponibles = df_ofs[df_ofs['proyecto'] == sel_proyecto]['of_number'].tolist()
        
    with col_o:
        sel_ofs = st.multiselect("⚙️ Órdenes de Fabricación (OF):", ["Todas"] + ofs_disponibles, default=["Todas"], key="dash_ofs")
        
    # Determine the final list of OFs to query
    if not sel_ofs:
        of_list = []
        of_display = "Ninguna"
        proy_display = "—"
    elif "Todas" in sel_ofs:
        of_list = ["Todas"] # get_dashboard_stats handles "Todas"
        of_display = "Múltiples OFs" if sel_proyecto == "Todos" else f"Múltiples OFs ({sel_proyecto})"
        proy_display = sel_proyecto
    else:
        of_list = sel_ofs
        if len(sel_ofs) == 1:
            of_display = sel_ofs[0]
            # Try to get project for this OF
            proy = df_ofs[df_ofs['of_number'] == sel_ofs[0]]['proyecto'].iloc[0] if not df_ofs[df_ofs['of_number'] == sel_ofs[0]].empty else "—"
            proy_display = proy
        else:
            of_display = "Varias OFs seleccionadas"
            proy_display = sel_proyecto if sel_proyecto != "Todos" else "Varios"

    # ── Calculate Stats ──────────────────────────────────────────
    stats = get_dashboard_stats(of_list)
    
    total_nidos = stats["total_nidos"]
    total_hojas = stats["total_hojas"]
    total_piezas = stats["total_piezas"]
    total_partes = stats["total_partes"]

    # ── Compute per-process percentages ─────────────────────────
    pcts = [stats["avances_pct"].get(area, 0.0) for area in PROCESSES]
    avance_pzs = [stats["avances_pzs"].get(area, 0) for area in PROCESSES]
    overall_pct = sum(p / 100 * w for p, w in zip(pcts, PROCESS_WEIGHTS)) * 100
    overall_pct = round(overall_pct, 2)

    # ── OF Banner ───────────────────────────────────────────────
    st.markdown(
        f"""
        <div style="background:{BLACK};color:{WHITE};border-radius:8px;
                    padding:12px 20px;margin-bottom:18px;display:flex;
                    align-items:center;gap:20px;flex-wrap:wrap;">
            <span style="font-family:Montserrat,sans-serif;font-weight:700;font-size:16px;">
                OF: <b style="color:{RED};">{of_display}</b>
            </span>
            <span style="font-family:Questrial,sans-serif;font-size:14px;color:{GRAY};">
                Proyecto: <b style="color:white;">{proy_display}</b>
            </span>
            <span style="font-family:Questrial,sans-serif;font-size:14px;color:{GRAY};">
                Filtro Activo: <b style="color:white;">Personalizado</b>
            </span>
        </div>""",
        unsafe_allow_html=True,
    )

    # ── 1. Top Metrics ───────────────────────────────────────────
    _render_top_metrics(total_nidos, total_hojas, total_piezas, overall_pct)

    st.markdown("<div style='margin:20px 0;'></div>", unsafe_allow_html=True)

    # ── 2. WIP Flow ──────────────────────────────────────────────
    _render_wip_flow(pcts)

    st.markdown("<div style='margin:20px 0;'></div>", unsafe_allow_html=True)

    # ── 3. Progress Table ────────────────────────────────────────
    _render_progress_table(pcts, avance_pzs, total_piezas, total_nidos, total_partes)

    # ── 4 & 5. Donut Charts ──────────────────────────────────────
    _render_donut_row(pcts, overall_pct)
