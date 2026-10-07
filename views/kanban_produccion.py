"""
=============================================================================
SISTEMA DE CONTROL DE CORTE Y DOBLEZ - INDUSTRIA SIGRAMA S.A. DE C.V.
Vista: Tablero Kanban Interactivo de Producción (Odoo-Style 60 FPS)
=============================================================================
"""

import os
import re
from pathlib import Path
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from utils.database import (
    get_kanban_production_data,
    marcar_avance_completo_area,
    get_todas_piezas,
    get_nidos,
    get_connection
)

KANBAN_COMPONENT_PATH = Path(__file__).resolve().parent.parent / "components" / "odoo_kanban"
_odoo_kanban_comp = components.declare_component("odoo_kanban_v2", path=str(KANBAN_COMPONENT_PATH))

# Configuración oficial de las 7 etapas de producción en planta
KANBAN_STAGES = [
    {
        "id": "stage_programada",
        "title": "📋 Programada",
        "short_title": "Programada",
        "icon": "📋",
        "db_status": "programada",
        "color": "#475569",
        "accent": "#F1F5F9"
    },
    {
        "id": "stage_corte",
        "title": "✂️ Corte Láser",
        "short_title": "Corte Láser",
        "icon": "✂️",
        "db_status": "corte",
        "color": "#0284C7",
        "accent": "#E0F2FE"
    },
    {
        "id": "stage_wip_doblez",
        "title": "📦 WIP Corte ➔ Doblez",
        "short_title": "WIP ➔ Doblez",
        "icon": "📦",
        "db_status": "wip_doblez",
        "color": "#D97706",
        "accent": "#FEF3C7"
    },
    {
        "id": "stage_doblez",
        "title": "📐 Doblez CNC",
        "short_title": "Doblez CNC",
        "icon": "📐",
        "db_status": "doblez",
        "color": "#7C3AED",
        "accent": "#EDE9FE"
    },
    {
        "id": "stage_wip_pintura",
        "title": "🎨 WIP Doblez ➔ Pintura",
        "short_title": "WIP ➔ Pintura",
        "icon": "🎨",
        "db_status": "wip_pintura",
        "color": "#DB2777",
        "accent": "#FCE7F3"
    },
    {
        "id": "stage_pintura",
        "title": "🖌️ Pintura",
        "short_title": "Pintura",
        "icon": "🖌️",
        "db_status": "pintura",
        "color": "#0D9488",
        "accent": "#CCFBF1"
    },
    {
        "id": "stage_liberado",
        "title": "🏁 Liberado / Final",
        "short_title": "Liberado",
        "icon": "🏁",
        "db_status": "liberado",
        "color": "#16A34A",
        "accent": "#DCFCE7"
    }
]

# Paleta de colores para post-its estilo Odoo
PALETA_COLORES = [
    {"id": "amarillo", "bg": "#FEF08A", "border": "#FDE047", "top": "#CA8A04"},
    {"id": "azul", "bg": "#BAE6FD", "border": "#7DD3FC", "top": "#0284C7"},
    {"id": "verde", "bg": "#BBF7D0", "border": "#86EFAC", "top": "#16A34A"},
    {"id": "naranja", "bg": "#FED7AA", "border": "#FDBA74", "top": "#EA580C"},
    {"id": "rojo", "bg": "#FECACA", "border": "#FCA5A5", "top": "#DC2626"},
    {"id": "morado", "bg": "#E9D5FF", "border": "#D8B4FE", "top": "#9333EA"}
]

@st.dialog("📋 Detalle de Orden de Fabricación", width="large")
def modal_detalle_of(of_number: str):
    """Modal interactivo para inspeccionar nidos, piezas y avance de la OF."""
    st.markdown(f"""
    <div style="background: linear-gradient(135deg, #1e1e1e 0%, #111111 100%); 
                padding: 14px 20px; border-radius: 8px; border-left: 5px solid #EC2024; margin-bottom: 15px;">
        <span style="font-size: 20px; font-weight: 800; color: #FFFFFF;">📁 Orden de Fabricación: {of_number}</span>
    </div>
    """, unsafe_allow_html=True)

    df_pzs = get_todas_piezas(of_number)
    df_nid = get_nidos(of_number)

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Total Nidos", len(df_nid))
    with c2:
        tot_hojas = int(df_nid['hojas'].sum()) if not df_nid.empty and 'hojas' in df_nid else 0
        st.metric("Total Hojas", tot_hojas)
    with c3:
        tot_piezas = int((df_pzs['cantidad'] * df_pzs['hojas']).sum()) if not df_pzs.empty else 0
        st.metric("Total Piezas", tot_piezas)
    with c4:
        partes_unicas = df_pzs['no_pieza'].nunique() if not df_pzs.empty else 0
        st.metric("Partes Únicas", partes_unicas)

    st.markdown("#### ⚡ Acciones Rápidas de Avance Completo:")
    col_b1, col_b2, col_b3, col_b4 = st.columns(4)
    with col_b1:
        if st.button("✂️ 100% Corte", use_container_width=True, key=f"btn_corte_{of_number}"):
            marcar_avance_completo_area(of_number, "Corte", operador="Modal")
            st.toast(f"✅ {of_number}: Corte marcado al 100%", icon="✂️")
            st.rerun()
    with col_b2:
        if st.button("📐 100% Doblez", use_container_width=True, key=f"btn_doblez_{of_number}"):
            marcar_avance_completo_area(of_number, "Corte", operador="Modal")
            marcar_avance_completo_area(of_number, "Doblez", operador="Modal")
            st.toast(f"✅ {of_number}: Corte y Doblez marcados al 100%", icon="📐")
            st.rerun()
    with col_b3:
        if st.button("🖌️ 100% Pintura", use_container_width=True, key=f"btn_pintura_{of_number}"):
            marcar_avance_completo_area(of_number, "Corte", operador="Modal")
            marcar_avance_completo_area(of_number, "Doblez", operador="Modal")
            marcar_avance_completo_area(of_number, "Pintura", operador="Modal")
            st.toast(f"✅ {of_number}: Corte, Doblez y Pintura al 100%", icon="🖌️")
            st.rerun()
    with col_b4:
        if st.button("🏁 Liberar 100%", use_container_width=True, key=f"btn_liberar_{of_number}"):
            marcar_avance_completo_area(of_number, "Corte", operador="Modal")
            marcar_avance_completo_area(of_number, "Doblez", operador="Modal")
            marcar_avance_completo_area(of_number, "Pintura", operador="Modal")
            marcar_avance_completo_area(of_number, "Liberado", operador="Modal")
            st.toast(f"✅ {of_number}: Orden totalmente liberada", icon="🏁")
            st.rerun()

    st.markdown("---")
    tab_pzs, tab_nids = st.tabs(["🧩 Desglose de Piezas", "📑 Nidos y Hojas"])
    with tab_pzs:
        if not df_pzs.empty:
            df_disp = df_pzs.copy()
            df_disp['Pzs Totales'] = df_disp['cantidad'] * df_disp['hojas']
            st.dataframe(
                df_disp[['no_pieza', 'nombre_pieza', 'nido', 'hojas', 'cantidad', 'Pzs Totales', 'ruta']],
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info("No se encontraron piezas registradas para esta OF.")
    with tab_nids:
        if not df_nid.empty:
            st.dataframe(df_nid, use_container_width=True, hide_index=True)


def view_kanban_produccion():
    st.markdown('''
    <div style="background: linear-gradient(135deg, #1e1e1e 0%, #111111 100%); 
                padding: 18px 24px; border-radius: 10px; border-left: 5px solid #EC2024; margin-bottom: 20px;">
        <div style="font-family: 'Montserrat', sans-serif; color: #FFFFFF !important; margin: 0; font-size: 24px; font-weight: 700;">
            🗂️ Tablero Kanban Interactivo de Producción
        </div>
        <p style="font-family: 'Questrial', sans-serif; color: #bbb; margin: 5px 0 0 0; font-size: 14px;">
            Flujo de valor continuo estilo Odoo: Arrastre tarjetas para dar avance completo automático por área (Corte ➔ WIP Doblez ➔ Doblez ➔ WIP Pintura ➔ Pintura ➔ Liberado).
        </p>
    </div>
    ''', unsafe_allow_html=True)

    # 1. Cargar datos de producción
    ofs_data = get_kanban_production_data()
    if not ofs_data:
        st.warning("⚠️ No se encontraron Órdenes de Fabricación en la base de datos.")
        return

    # 2. Barra de filtros
    f_col1, f_col2, f_col3, f_col4 = st.columns([2, 1.5, 1.5, 1])
    with f_col1:
        busqueda = st.text_input("🔍 Buscar por OF, PO o Proyecto:", value="", placeholder="Ej. 00086, 2608, P7...")
    with f_col2:
        prioridades_disp = ["Todas"] + sorted(list({o["prioridad"] for o in ofs_data if o["prioridad"]}))
        f_prio = st.selectbox("Prioridad:", prioridades_disp)
    with f_col3:
        calibres_disp = ["Todos"] + sorted(list({o["calibre"] for o in ofs_data if o["calibre"]}))
        f_cal = st.selectbox("Calibre / Espesor:", calibres_disp)
    with f_col4:
        st.write("")
        st.write("")
        if st.button("🔄 Refrescar", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    # Filtrar OFs
    ofs_filtradas = []
    for of in ofs_data:
        if busqueda:
            b_low = busqueda.lower()
            match_txt = (b_low in of["of_number"].lower() or 
                         b_low in of["folio_po"].lower() or 
                         b_low in of["proyecto"].lower() or 
                         b_low in of["etiqueta"].lower())
            if not match_txt:
                continue
        if f_prio != "Todas" and of["prioridad"] != f_prio:
            continue
        if f_cal != "Todos" and of["calibre"] != f_cal:
            continue
        ofs_filtradas.append(of)

    # 3. Construir Payload para el Componente Kanban
    kanban_columns_payload = []
    avatar_colors = ["#6366F1", "#8B5CF6", "#0D9488", "#D97706", "#DB2777", "#2563EB", "#059669"]

    for stage_def in KANBAN_STAGES:
        s_id = stage_def["id"]
        s_status = stage_def["db_status"]
        
        cards = []
        col_total_piezas = 0

        # Tarjetas asignadas a esta columna
        ofs_en_etapa = [o for o in ofs_filtradas if o["stage"] == s_status]

        for of in ofs_en_etapa:
            of_id = of["of_number"]
            tot_pzs = of["total_piezas"]
            col_total_piezas += tot_pzs

            # Selección de color de post-it
            color_idx = abs(hash(of_id)) % len(PALETA_COLORES)
            palette = PALETA_COLORES[color_idx]

            # Iniciales para avatar
            proy_clean = of["proyecto"] or of["of_number"]
            initials = proy_clean[:2].upper() if len(proy_clean) >= 2 else "OF"
            avatar_bg = avatar_colors[abs(hash(of_id)) % len(avatar_colors)]

            # Descripción de la tarjeta
            desc_partes = []
            if of["proyecto"]:
                desc_partes.append(f"<b>Proy:</b> {of['proyecto']}")
            if of["etiqueta"]:
                desc_partes.append(f"<b>Ref:</b> {of['etiqueta']}")
            if of["calibre"]:
                desc_partes.append(f"<b>Cal:</b> {of['calibre']}")
            desc_html = " &bull; ".join(desc_partes) if desc_partes else "Sin descripción"

            cards.append({
                "id": of_id,
                "folio_solicitud": of["proyecto"][:20] if of["proyecto"] else of_id,
                "descripcion": desc_html,
                "monto": tot_pzs,
                "moneda": "Pzs",
                "solicitante": of["calibre"] or "Lámina",
                "area": f"Corte: {of['pct_corte']}% | Dob: {of['pct_doblez']}%",
                "prioridad": of["prioridad"],
                "num_cotizaciones": of["total_nidos"],
                "num_nidos": of["total_nidos"],
                "num_hojas": of["total_hojas"],
                "folio_po": of["folio_po"],
                "color_id": palette["id"],
                "bg_color": palette["bg"],
                "border_color": palette["border"],
                "top_color": palette["top"],
                "initials": initials,
                "avatar_bg": avatar_bg
            })

        kanban_columns_payload.append({
            "id": s_id,
            "short_title": stage_def["short_title"],
            "icon": stage_def["icon"],
            "db_status": s_status,
            "color": stage_def["color"],
            "accent": stage_def["accent"],
            "total_monto": col_total_piezas,
            "cards": cards
        })

    # Barra informativa de alto contraste
    st.markdown("""
    <div style="background: #FFFFFF; border: 1px solid #CBD5E1; border-left: 5px solid #EC2024; padding: 10px 16px; border-radius: 6px; margin-bottom: 12px; font-size: 13px; color: #0F172A; box-shadow: 0 1px 3px rgba(0,0,0,0.05);">
        🖐️ <b>Avance en 1 Arrastre:</b> Desplace tarjetas entre procesos para actualizar el avance en piso. <b>🎯 Ventana Fija a la Derecha:</b> Arrastre cualquier OF directamente al panel verde <b>🏁 Liberado</b> para registrar el avance al 100% (Corte, Doblez y Pintura) al instante sin necesidad de scroll.
    </div>
    """, unsafe_allow_html=True)

    # 4. Renderizar componente SortableJS
    kanban_event = _odoo_kanban_comp(
        columns=kanban_columns_payload,
        total_count=len(ofs_filtradas),
        key="odoo_kanban_corte_doblez",
        default=None
    )

    # 5. Captura y ejecución de eventos interactivos
    if kanban_event and isinstance(kanban_event, dict):
        event_id = kanban_event.get("event_id")
        last_event_id = st.session_state.get("_last_processed_kanban_corte_doblez_id")

        if event_id and event_id != last_event_id:
            st.session_state["_last_processed_kanban_corte_doblez_id"] = event_id
            action = kanban_event.get("action")

            if action == "move_stage":
                target_of = kanban_event.get("req_id")
                new_db_status = kanban_event.get("new_db_status")

                if target_of and new_db_status:
                    if new_db_status in ["wip_doblez", "doblez"]:
                        marcar_avance_completo_area(target_of, "Corte", operador="Kanban")
                        st.toast(f"✅ {target_of}: Corte Láser marcado al 100%", icon="✂️")
                    elif new_db_status in ["wip_pintura", "pintura"]:
                        marcar_avance_completo_area(target_of, "Corte", operador="Kanban")
                        marcar_avance_completo_area(target_of, "Doblez", operador="Kanban")
                        st.toast(f"✅ {target_of}: Corte y Doblez al 100%", icon="📐")
                    elif new_db_status == "liberado":
                        marcar_avance_completo_area(target_of, "Corte", operador="Kanban")
                        marcar_avance_completo_area(target_of, "Doblez", operador="Kanban")
                        marcar_avance_completo_area(target_of, "Pintura", operador="Kanban")
                        marcar_avance_completo_area(target_of, "Liberado", operador="Kanban")
                        st.toast(f"✅ {target_of}: Orden 100% completada y liberada", icon="🏁")
                    elif new_db_status == "corte":
                        st.toast(f"ℹ️ {target_of} en proceso de Corte Láser", icon="✂️")

                    st.rerun()

            elif action == "open_modal":
                target_of = kanban_event.get("req_id")
                if target_of:
                    modal_detalle_of(target_of)
