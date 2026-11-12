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

from utils.database import (
    get_kanban_production_data,
    marcar_avance_completo_area,
    get_todas_piezas,
    get_nidos,
    get_connection
)

KANBAN_COMPONENT_PATH = Path(__file__).resolve().parent.parent / "components" / "odoo_kanban"


@st.cache_resource
def _get_odoo_kanban_v2():
    """Registra el tablero Kanban con st.components.v2 (inline por WebSocket, inmune a 404 en Cloud Run)."""
    css_raw = (KANBAN_COMPONENT_PATH / "css" / "odoo_theme.css").read_text(encoding="utf-8")
    css_v2 = (
        css_raw
        .replace(":root {", ":host {")
        .replace("body {", ".kanban-root {")
        .replace("height: 100vh;", "height: 650px;")
    )

    sortable_js = (KANBAN_COMPONENT_PATH / "js" / "sortable.min.js").read_text(encoding="utf-8")

    html_v2 = """
    <div class="kanban-root">
        <div class="kanban-top-nav-bar" id="kanbanTopNavBar">
            <div class="nav-scroll-group">
                <button class="nav-scroll-btn" id="btnScrollLeft" title="Desplazar a la izquierda (fases previas)">◀</button>
                <button class="nav-scroll-btn" id="btnToggleCompact" title="Alternar entre ancho compacto o estándar">📐 Compacto</button>
                <div class="nav-stage-chips" id="navStageChips"></div>
                <button class="nav-scroll-btn" id="btnScrollRight" title="Desplazar a la derecha (fases siguientes)">▶</button>
            </div>
            <div class="nav-info-group">
                <span class="nav-scroll-hint">💡 Clic en cualquier fase para saltar directo a ella</span>
            </div>
        </div>
        <div class="kanban-layout-wrapper" id="kanbanLayoutWrapper">
            <div class="kanban-scroll-wrapper" id="kanbanScrollWrapper">
                <div class="kanban-board-container" id="kanbanBoard"></div>
            </div>
            <div class="kanban-fixed-dock" id="kanbanFixedDock"></div>
        </div>
    </div>
    """

    kanban_js = """
    export default function(component) {
        const { data, setTriggerValue, parentElement } = component;
        const columns = (data && data.columns) ? data.columns : [];
        const totalCount = (data && data.total_count) ? data.total_count : 0;
        const SortableLib = window.Sortable;
        let sortableInstances = [];

        function sendValueToStreamlit(value) {
            setTriggerValue("kanban_event", value);
        }

        function openExpedienteModal(reqId) {
            sendValueToStreamlit({
                action: "open_modal",
                event_id: Date.now() + "_" + Math.random().toString(36).substring(2, 9),
                req_id: reqId
            });
        }

        function escapeHtml(text) {
            const div = document.createElement("div");
            div.innerText = text == null ? "" : String(text);
            return div.innerHTML;
        }

        function toggleFoldStage(stageId, event) {
            if (event) event.stopPropagation();
            const colEl = parentElement.querySelector(`.kanban-column[data-stage-id="${stageId}"]`);
            if (!colEl) return;

            const isNowFolded = colEl.classList.toggle("folded");
            const btn = colEl.querySelector(".column-fold-btn");
            if (btn) {
                btn.textContent = isNowFolded ? "▶" : "◀";
                btn.title = isNowFolded ? "Expandir columna" : "Contraer columna";
            }

            try {
                let stored = JSON.parse(localStorage.getItem("sigrama_folded_stages") || "[]");
                if (!Array.isArray(stored)) stored = [];
                if (isNowFolded) {
                    if (!stored.includes(stageId)) stored.push(stageId);
                } else {
                    stored = stored.filter(id => id !== stageId);
                }
                localStorage.setItem("sigrama_folded_stages", JSON.stringify(stored));
            } catch (err) {}
        }

        function setupSortableOnDropzone(dropzoneEl) {
            if (!SortableLib || !dropzoneEl) return;
            const sortable = new SortableLib(dropzoneEl, {
                group: "odoo_kanban_group",
                animation: 180,
                ghostClass: "sortable-ghost",
                chosenClass: "sortable-chosen",
                dragClass: "sortable-drag",
                fallbackTolerance: 3,
                scroll: true,
                scrollSensitivity: 80,
                scrollSpeed: 15,
                bubbleScroll: true,
                onEnd: function (evt) {
                    const itemEl = evt.item;
                    const fromColId = evt.from.dataset.stageId;
                    const toColId = evt.to.dataset.stageId;
                    const reqId = itemEl.dataset.reqId;
                    const newDbStatus = evt.to.dataset.dbStatus;
                    if (fromColId !== toColId) {
                        sendValueToStreamlit({
                            action: "move_stage",
                            event_id: Date.now() + "_" + Math.random().toString(36).substring(2, 9),
                            req_id: reqId,
                            old_stage: fromColId,
                            new_stage: toColId,
                            new_db_status: newDbStatus
                        });
                    }
                }
            });
            sortableInstances.push(sortable);
        }

        function createCardElement(card) {
            const cardEl = document.createElement("div");
            cardEl.className = "postit-card";
            cardEl.dataset.reqId = card.id;
            cardEl.style.backgroundColor = card.bg_color || "#FEF08A";
            cardEl.style.borderColor = card.border_color || "#FDE047";
            cardEl.style.borderTopColor = card.top_color || "#CA8A04";

            const formattedMonto = card.moneda === 'Pzs'
                ? `${(card.monto || 0).toLocaleString('es-MX')} Pzs`
                : new Intl.NumberFormat('es-MX', { style: 'currency', currency: card.moneda || 'MXN' }).format(card.monto || 0);

            const poTag = card.folio_po ? `<span class="card-po-badge">📦 ${escapeHtml(card.folio_po)}</span>` : "";
            const solTag = card.folio_solicitud ? `<span class="card-sol-tag">${escapeHtml(card.folio_solicitud)}</span>` : "";
            const priorityStars = (card.prioridad === "Urgente" || card.prioridad === "Alta")
                ? "⭐⭐⭐"
                : (card.prioridad === "Media" ? "⭐⭐☆" : "⭐☆☆");
            const metaRight = card.moneda === 'Pzs'
                ? `📑 ${card.num_nidos || card.num_cotizaciones || 0} nidos`
                : `📑 ${card.num_cotizaciones || 0} cotiz.`;
            const btnLabel = card.moneda === 'Pzs' ? '🔍 Ver Detalle OF' : '👁️ Abrir Expediente';

            cardEl.innerHTML = `
                <div>
                    <div class="card-header">
                        <span class="card-folio">📌 ${escapeHtml(card.id)}</span>
                        ${solTag}
                    </div>
                    <div class="card-title">${card.descripcion || "Sin descripción"}</div>
                </div>
                <div>
                    <div class="card-amount-row">
                        <span class="card-amount">⚙️ ${formattedMonto}</span>
                        ${poTag}
                    </div>
                    <div class="card-user-row">
                        <span style="background-color:${card.avatar_bg || '#6366F1'}; color:#FFFFFF; width:18px; height:18px; border-radius:50%; display:inline-flex; align-items:center; justify-content:center; font-size:9px; font-weight:800;">
                            ${escapeHtml(card.initials || 'SG')}
                        </span>
                        <span><strong>${escapeHtml(card.solicitante || 'Sin asignar')}</strong> ${card.area ? `&bull; 📍 ${escapeHtml(card.area)}` : ''}</span>
                    </div>
                    <div class="card-footer-meta">
                        <span>${priorityStars} ${escapeHtml(card.prioridad || '')}</span>
                        <span style="font-weight:700;">${metaRight}</span>
                    </div>
                    <button class="card-open-btn" type="button">${btnLabel}</button>
                </div>
            `;

            const openBtn = cardEl.querySelector(".card-open-btn");
            if (openBtn) {
                openBtn.addEventListener("click", (e) => {
                    e.stopPropagation();
                    openExpedienteModal(card.id);
                });
            }
            cardEl.addEventListener("dblclick", (e) => {
                e.stopPropagation();
                openExpedienteModal(card.id);
            });
            return cardEl;
        }

        function renderKanbanBoard() {
            const boardContainer = parentElement.getElementById("kanbanBoard");
            const fixedDockContainer = parentElement.getElementById("kanbanFixedDock");
            if (!boardContainer) return;

            sortableInstances.forEach(inst => { try { inst.destroy(); } catch (e) {} });
            sortableInstances = [];
            boardContainer.innerHTML = "";
            if (fixedDockContainer) fixedDockContainer.innerHTML = "";

            try {
                if (localStorage.getItem("sigrama_kanban_compact") === "true") {
                    boardContainer.classList.add("compact-mode");
                }
            } catch (e) {}

            let foldedStages = [];
            try {
                foldedStages = JSON.parse(localStorage.getItem("sigrama_folded_stages") || "[]");
                if (!Array.isArray(foldedStages)) foldedStages = [];
            } catch (e) {}

            const activeColumns = columns.filter(col => col.db_status !== "liberado");
            const finishedColumn = columns.find(col => col.db_status === "liberado");

            activeColumns.forEach(col => {
                const isFolded = foldedStages.includes(col.id);
                const columnEl = document.createElement("div");
                columnEl.className = `kanban-column ${isFolded ? "folded" : ""}`;
                columnEl.dataset.stageId = col.id;
                const formattedTotal = `${(col.total_monto || 0).toLocaleString('es-MX')} Pzs`;

                columnEl.innerHTML = `
                    <div class="column-header">
                        <div class="column-top-bar" style="background-color: ${col.color};"></div>
                        <div class="column-title-row">
                            <span class="column-title">
                                <span class="column-icon-badge" style="background-color: ${col.color}; color: #FFFFFF;">${col.icon}</span>
                                <span class="column-title-text">${escapeHtml(col.short_title)}</span>
                            </span>
                            <div class="column-actions">
                                <span class="column-badge" id="badge-${col.id}">${col.cards.length}</span>
                                <button class="column-fold-btn" type="button" title="${isFolded ? 'Expandir columna' : 'Contraer columna'}">${isFolded ? '▶' : '◀'}</button>
                            </div>
                        </div>
                        <div class="column-metrics-row">
                            <span>En Proceso:</span>
                            <span class="column-total">${formattedTotal}</span>
                        </div>
                        <div class="column-progress-bar">
                            <div class="column-progress-fill" style="width: ${Math.min(100, (col.cards.length / Math.max(1, totalCount)) * 100)}%; background-color: ${col.color};"></div>
                        </div>
                    </div>
                    <div class="kanban-cards-dropzone" id="dropzone-${col.id}" data-stage-id="${col.id}" data-db-status="${col.db_status}"></div>
                `;

                const foldBtn = columnEl.querySelector(".column-fold-btn");
                if (foldBtn) {
                    foldBtn.addEventListener("click", (e) => toggleFoldStage(col.id, e));
                }
                columnEl.addEventListener("click", (e) => {
                    if (columnEl.classList.contains("folded")) {
                        toggleFoldStage(col.id, e);
                    }
                });

                const dropzoneEl = columnEl.querySelector(".kanban-cards-dropzone");
                col.cards.forEach(card => dropzoneEl.appendChild(createCardElement(card)));
                boardContainer.appendChild(columnEl);
                setupSortableOnDropzone(dropzoneEl);
            });

            if (finishedColumn && fixedDockContainer) {
                const formattedTotalFinished = `${(finishedColumn.total_monto || 0).toLocaleString('es-MX')} Pzs`;
                fixedDockContainer.innerHTML = `
                    <div class="fixed-dock-banner">
                        <span>🎯 Arrastra aquí para Terminar OF</span>
                    </div>
                    <div class="column-header">
                        <div class="column-top-bar" style="background-color: #16A34A;"></div>
                        <div class="column-title-row">
                            <span class="column-title">
                                <span class="column-icon-badge" style="background-color: #16A34A; color: #FFFFFF;">${finishedColumn.icon}</span>
                                <span class="column-title-text" style="color: #14532D !important;">${escapeHtml(finishedColumn.short_title)}</span>
                            </span>
                            <div class="column-actions">
                                <span class="column-badge" style="background-color: #16A34A; border-color: #16A34A;" id="badge-${finishedColumn.id}">${finishedColumn.cards.length}</span>
                            </div>
                        </div>
                        <div class="column-metrics-row">
                            <span>Total Liberadas:</span>
                            <span class="column-total" style="color: #16A34A !important;">${formattedTotalFinished}</span>
                        </div>
                        <div class="column-progress-bar">
                            <div class="column-progress-fill" style="width: 100%; background-color: #16A34A;"></div>
                        </div>
                    </div>
                    <div class="kanban-cards-dropzone" id="dropzone-${finishedColumn.id}" data-stage-id="${finishedColumn.id}" data-db-status="${finishedColumn.db_status}"></div>
                `;

                const finishedDropzoneEl = fixedDockContainer.querySelector(".kanban-cards-dropzone");
                finishedColumn.cards.forEach(card => finishedDropzoneEl.appendChild(createCardElement(card)));
                setupSortableOnDropzone(finishedDropzoneEl);
            }
        }

        function updateTopNavStageChips() {
            const chipsContainer = parentElement.getElementById("navStageChips");
            if (!chipsContainer) return;
            chipsContainer.innerHTML = "";

            columns.forEach(col => {
                const isLiberado = col.db_status === "liberado";
                const chip = document.createElement("button");
                chip.type = "button";
                chip.className = `nav-stage-chip ${isLiberado ? "chip-terminal" : ""}`;
                chip.innerHTML = `<span>${col.icon}</span> <span>${escapeHtml(col.short_title)}</span> <strong style="background:${isLiberado ? '#DCFCE7' : '#E2E8F0'}; padding:1px 5px; border-radius:10px; font-size:9.5px; color:${isLiberado ? '#166534' : '#1E293B'};">${col.cards.length}</strong>`;
                chip.title = isLiberado ? "Ver ventana fija de Terminadas / Liberado" : `Saltar directamente a la columna ${col.short_title}`;
                chip.onclick = (e) => {
                    e.preventDefault();
                    if (isLiberado) {
                        const dockEl = parentElement.getElementById("kanbanFixedDock");
                        if (dockEl) dockEl.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' });
                    } else {
                        const colEl = parentElement.querySelector(`.kanban-column[data-stage-id="${col.id}"]`);
                        if (colEl) colEl.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' });
                    }
                };
                chipsContainer.appendChild(chip);
            });
        }

        function setupScrollControls() {
            const btnLeft = parentElement.getElementById("btnScrollLeft");
            const btnRight = parentElement.getElementById("btnScrollRight");
            const btnCompact = parentElement.getElementById("btnToggleCompact");
            const wrapper = parentElement.getElementById("kanbanScrollWrapper");
            const boardEl = parentElement.getElementById("kanbanBoard");
            if (!wrapper) return;

            if (btnLeft) {
                btnLeft.onclick = (e) => {
                    e.preventDefault();
                    wrapper.scrollBy({ left: -320, behavior: 'smooth' });
                };
            }
            if (btnRight) {
                btnRight.onclick = (e) => {
                    e.preventDefault();
                    wrapper.scrollBy({ left: 320, behavior: 'smooth' });
                };
            }
            if (btnCompact && boardEl) {
                try {
                    const isCompact = localStorage.getItem("sigrama_kanban_compact") === "true";
                    if (isCompact) {
                        boardEl.classList.add("compact-mode");
                        btnCompact.textContent = "📐 Estándar";
                        btnCompact.title = "Volver al ancho estándar de 280px";
                    }
                } catch (e) {}
                btnCompact.onclick = (e) => {
                    e.preventDefault();
                    const nowCompact = boardEl.classList.toggle("compact-mode");
                    btnCompact.textContent = nowCompact ? "📐 Estándar" : "📐 Compacto";
                    btnCompact.title = nowCompact ? "Volver al ancho estándar de 280px" : "Alternar ancho compacto para ver todas las columnas";
                    try { localStorage.setItem("sigrama_kanban_compact", nowCompact ? "true" : "false"); } catch (err) {}
                };
            }

            wrapper.onwheel = (e) => {
                const dropzone = e.target.closest('.kanban-cards-dropzone');
                if (dropzone) {
                    const atTop = dropzone.scrollTop <= 0 && e.deltaY < 0;
                    const atBottom = (dropzone.scrollTop + dropzone.clientHeight >= dropzone.scrollHeight - 2) && e.deltaY > 0;
                    if (atTop || atBottom || e.shiftKey) {
                        wrapper.scrollLeft += e.deltaY;
                    }
                } else {
                    wrapper.scrollLeft += (e.deltaY || e.deltaX);
                }
            };
        }

        renderKanbanBoard();
        updateTopNavStageChips();
        setupScrollControls();

        return () => {
            sortableInstances.forEach(inst => { try { inst.destroy(); } catch (e) {} });
            sortableInstances = [];
        };
    }
    """

    full_js = f"if (!window.Sortable) {{\n{sortable_js}\n}}\n{kanban_js}"

    return st.components.v2.component(
        "odoo_kanban_v2",
        html=html_v2,
        css=css_v2,
        js=full_js,
        isolate_styles=True,
    )

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
        <span style="font-family: 'Montserrat', sans-serif; color: #FFFFFF !important; margin: 0; font-size: 24px; font-weight: 700; display: block;">
            🗂️ Tablero Kanban Interactivo de Producción
        </span>
        <span style="font-family: 'Questrial', sans-serif; color: #E2E8F0 !important; margin: 5px 0 0 0; font-size: 14px; display: block;">
            Flujo de valor continuo estilo Odoo: Arrastre tarjetas para dar avance completo automático por área (Corte ➔ WIP Doblez ➔ Doblez ➔ WIP Pintura ➔ Pintura ➔ Liberado).
        </span>
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

    # 4. Renderizar componente SortableJS mediante st.components.v2 (inmune a 404 en Cloud Run)
    _odoo_kanban_comp = _get_odoo_kanban_v2()
    _comp_res = _odoo_kanban_comp(
        data={
            "columns": kanban_columns_payload,
            "total_count": len(ofs_filtradas),
        },
        key="odoo_kanban_corte_doblez",
        on_kanban_event_change=lambda: None,
    )
    kanban_event = getattr(_comp_res, "kanban_event", None)

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
