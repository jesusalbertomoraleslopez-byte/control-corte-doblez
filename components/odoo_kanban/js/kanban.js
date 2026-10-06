/**
 * CONTROLADOR KANBAN STREAMLIT - ODOO CRM
 * Arrastre y Soltar (Drag & Drop a 60 FPS) mediante SortableJS con comunicación bidireccional
 */

let sortableInstances = [];
let currentColumns = [];

// ==========================================================================
// 1. PROTOCOLO BIDIRECCIONAL STREAMLIT COMPONENT
// ==========================================================================
function sendValueToStreamlit(value) {
    window.parent.postMessage({
        isStreamlitMessage: true,
        type: "streamlit:setComponentValue",
        value: value
    }, "*");
}

function computeOptimalHeight() {
    const screenH = (window.screen && window.screen.availHeight) ? window.screen.availHeight : (window.innerHeight || 768);
    if (screenH <= 800) {
        return 580; // Altura optimizada para pantallas 1366x768 (evita que la barra inferior quede fuera)
    } else if (screenH <= 900) {
        return 630;
    } else {
        return 680;
    }
}

function sendFrameHeight(height) {
    const optimalH = height || computeOptimalHeight();
    window.parent.postMessage({
        isStreamlitMessage: true,
        type: "streamlit:setFrameHeight",
        height: optimalH
    }, "*");
}

function notifyComponentReady() {
    window.parent.postMessage({
        isStreamlitMessage: true,
        type: "streamlit:componentReady",
        apiVersion: 1
    }, "*");
}

// Escuchar evento de renderizado enviado por Python desde Streamlit
window.addEventListener("message", (event) => {
    if (event.data && event.data.type === "streamlit:render") {
        const { args } = event.data;
        if (args && args.columns) {
            currentColumns = args.columns;
            renderKanbanBoard(args.columns, args.total_count || 0);
            updateTopNavStageChips(args.columns);
            setupScrollControls();
            sendFrameHeight();
        }
    }
});

// Inicialización
document.addEventListener("DOMContentLoaded", () => {
    notifyComponentReady();
    setupScrollControls();
    sendFrameHeight();
});

window.addEventListener("resize", () => {
    sendFrameHeight();
});

// ==========================================================================
// 2. RENDERIZADO DEL TABLERO KANBAN CON SORTABLEJS
// ==========================================================================
function renderKanbanBoard(columns, totalCount) {
    const boardContainer = document.getElementById("kanbanBoard");
    if (!boardContainer) return;

    // Destruir instancias previas
    sortableInstances.forEach(inst => inst.destroy());
    sortableInstances = [];
    boardContainer.innerHTML = "";

    if (localStorage.getItem("sigrama_kanban_compact") === "true") {
        boardContainer.classList.add("compact-mode");
    }

    const foldedStages = JSON.parse(localStorage.getItem("sigrama_folded_stages") || "[]");

    columns.forEach(col => {
        const isFolded = foldedStages.includes(col.id);
        const columnEl = document.createElement("div");
        columnEl.className = `kanban-column ${isFolded ? "folded" : ""}`;
        columnEl.dataset.stageId = col.id;

        const formattedTotal = new Intl.NumberFormat('es-MX', {
            style: 'currency',
            currency: 'MXN',
            maximumFractionDigits: 0
        }).format(col.total_monto || 0);

        columnEl.innerHTML = `
            <div class="column-header">
                <div class="column-top-bar" style="background-color: ${col.color};"></div>
                <div class="column-title-row">
                    <span class="column-title" style="color: ${col.accent};">
                        <span>${col.icon}</span> ${col.short_title}
                    </span>
                    <div class="column-actions">
                        <span class="column-badge" id="badge-${col.id}">${col.cards.length}</span>
                        <button class="column-fold-btn" onclick="toggleFoldStage('${col.id}', event)" title="${isFolded ? 'Expandir columna' : 'Contraer columna'}">${isFolded ? '▶' : '◀'}</button>
                    </div>
                </div>
                <div class="column-metrics-row">
                    <span style="font-size: 11px; color: #64748B;">Subtotal:</span>
                    <span class="column-total">${formattedTotal}</span>
                </div>
                <div class="column-progress-bar">
                    <div class="column-progress-fill" style="width: ${Math.min(100, (col.cards.length / Math.max(1, totalCount)) * 260)}%; background-color: ${col.color};"></div>
                </div>
            </div>
            <div class="kanban-cards-dropzone" id="dropzone-${col.id}" data-stage-id="${col.id}" data-db-status="${col.db_status}"></div>
        `;

        // Al hacer clic sobre una columna contraída se vuelve a expandir automáticamente
        columnEl.addEventListener("click", (e) => {
            if (columnEl.classList.contains("folded")) {
                toggleFoldStage(col.id, e);
            }
        });

        const dropzoneEl = columnEl.querySelector(".kanban-cards-dropzone");

        col.cards.forEach(card => {
            const cardEl = createCardElement(card);
            dropzoneEl.appendChild(cardEl);
        });

        boardContainer.appendChild(columnEl);

        // ==================================================================
        // SORTABLE JS - ARRASTRE FLUIDO A 60 FPS
        // ==================================================================
        const sortable = new Sortable(dropzoneEl, {
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

                // Si la tarjeta cambió de columna
                if (fromColId !== toColId) {
                    // Notificar inmediatamente a Python (Streamlit)
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
    });
}

// ==========================================================================
// 3. TARJETAS POST-IT
// ==========================================================================
function createCardElement(card) {
    const cardEl = document.createElement("div");
    cardEl.className = "postit-card";
    cardEl.dataset.reqId = card.id;

    cardEl.style.backgroundColor = card.bg_color || "#FEF08A";
    cardEl.style.borderColor = card.border_color || "#FDE047";
    cardEl.style.borderTopColor = card.top_color || "#CA8A04";

    const formattedMonto = card.moneda === 'Pzs'
        ? `${(card.monto || 0).toLocaleString('es-MX')} Pzs`
        : new Intl.NumberFormat('es-MX', {
            style: 'currency',
            currency: card.moneda || 'MXN'
        }).format(card.monto || 0);

    const poTag = card.folio_po 
        ? `<span class="card-po-badge">📦 ${card.folio_po}</span>` 
        : "";

    const solTag = card.folio_solicitud 
        ? `<span class="card-sol-tag">${card.folio_solicitud}</span>` 
        : "";

    const priorityStars = card.prioridad === "Urgente" || card.prioridad === "Alta" 
        ? "⭐⭐⭐" 
        : (card.prioridad === "Media" ? "⭐⭐☆" : "⭐☆☆");

    const metaRight = card.moneda === 'Pzs'
        ? `📑 ${card.num_nidos || card.num_cotizaciones || 0} nidos`
        : `📑 ${card.num_cotizaciones || 0} cotiz.`;

    const btnLabel = card.moneda === 'Pzs' ? '🔍 Ver Detalle OF' : '👁️ Abrir Expediente';

    cardEl.innerHTML = `
        <div>
            <div class="card-header">
                <span class="card-folio">📌 ${card.id}</span>
                ${solTag}
            </div>
            <div class="card-title">${escapeHtml(card.descripcion || "Sin descripción")}</div>
        </div>
        <div>
            <div class="card-amount-row">
                <span class="card-amount">⚙️ ${formattedMonto}</span>
                ${poTag}
            </div>
            <div class="card-user-row">
                <span style="background-color:${card.avatar_bg || '#6366F1'}; color:#FFFFFF; width:18px; height:18px; border-radius:50%; display:inline-flex; align-items:center; justify-content:center; font-size:9px; font-weight:800;">
                    ${card.initials || 'SG'}
                </span>
                <span><strong>${escapeHtml(card.solicitante || 'Sin asignar')}</strong> ${card.area ? `&bull; 📍 ${escapeHtml(card.area)}` : ''}</span>
            </div>
            <div class="card-footer-meta">
                <span>${priorityStars} ${card.prioridad}</span>
                <span style="font-weight:700;">${metaRight}</span>
            </div>
            <button class="card-open-btn" onclick="openExpedienteModal('${card.id}')">
                ${btnLabel}
            </button>
        </div>
    `;

    // Doble clic abre el expediente
    cardEl.addEventListener("dblclick", (e) => {
        e.stopPropagation();
        openExpedienteModal(card.id);
    });

    return cardEl;
}

function openExpedienteModal(reqId) {
    // Notificar a Streamlit para abrir la modal nativa @st.dialog
    sendValueToStreamlit({
        action: "open_modal",
        event_id: Date.now() + "_" + Math.random().toString(36).substring(2, 9),
        req_id: reqId
    });
}

function escapeHtml(text) {
    const div = document.createElement("div");
    div.innerText = text;
    return div.innerHTML;
}

// ==========================================================================
// 4. PLEGAR / CONTRAER COLUMNA (ESTILO ODOO CRM)
// ==========================================================================
window.toggleFoldStage = function(stageId, event) {
    if (event) {
        event.stopPropagation();
    }
    const colEl = document.querySelector(`.kanban-column[data-stage-id="${stageId}"]`);
    if (!colEl) return;

    const isNowFolded = colEl.classList.toggle("folded");

    // Actualizar icono y tooltip del botón
    const btn = colEl.querySelector(".column-fold-btn");
    if (btn) {
        btn.textContent = isNowFolded ? "▶" : "◀";
        btn.title = isNowFolded ? "Expandir columna" : "Contraer columna";
    }

    // Persistir estado en localStorage del navegador del usuario
    try {
        let stored = JSON.parse(localStorage.getItem("sigrama_folded_stages") || "[]");
        if (!Array.isArray(stored)) stored = [];
        if (isNowFolded) {
            if (!stored.includes(stageId)) stored.push(stageId);
        } else {
            stored = stored.filter(id => id !== stageId);
        }
        localStorage.setItem("sigrama_folded_stages", JSON.stringify(stored));
    } catch (err) {
        console.warn("No se pudo guardar estado plegado en localStorage:", err);
    }
};

// ==========================================================================
// 5. NAVEGACIÓN RÁPIDA SUPERIOR Y CONTROLES DE DESPLAZAMIENTO (SCROLL)
// ==========================================================================
function updateTopNavStageChips(columns) {
    const chipsContainer = document.getElementById("navStageChips");
    if (!chipsContainer) return;
    chipsContainer.innerHTML = "";

    columns.forEach(col => {
        const chip = document.createElement("button");
        chip.className = "nav-stage-chip";
        chip.innerHTML = `<span>${col.icon}</span> <span>${col.short_title}</span> <strong style="background:#E2E8F0; padding:1px 5px; border-radius:10px; font-size:9.5px; color:#1E293B;">${col.cards.length}</strong>`;
        chip.title = `Saltar directamente a la columna ${col.short_title}`;
        chip.onclick = (e) => {
            e.preventDefault();
            const colEl = document.querySelector(`.kanban-column[data-stage-id="${col.id}"]`);
            if (colEl) {
                colEl.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' });
            }
        };
        chipsContainer.appendChild(chip);
    });
}

let scrollControlsInitialized = false;

function setupScrollControls() {
    if (scrollControlsInitialized) return;
    scrollControlsInitialized = true;

    const btnLeft = document.getElementById("btnScrollLeft");
    const btnRight = document.getElementById("btnScrollRight");
    const btnCompact = document.getElementById("btnToggleCompact");
    const wrapper = document.getElementById("kanbanScrollWrapper");
    const boardEl = document.getElementById("kanbanBoard");
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
        const isCompact = localStorage.getItem("sigrama_kanban_compact") === "true";
        if (isCompact) {
            boardEl.classList.add("compact-mode");
            btnCompact.textContent = "📐 Estándar";
            btnCompact.title = "Volver al ancho estándar de 280px";
        }
        btnCompact.onclick = (e) => {
            e.preventDefault();
            const nowCompact = boardEl.classList.toggle("compact-mode");
            btnCompact.textContent = nowCompact ? "📐 Estándar" : "📐 Compacto";
            btnCompact.title = nowCompact ? "Volver al ancho estándar de 280px" : "Alternar ancho compacto para ver todas las columnas";
            localStorage.setItem("sigrama_kanban_compact", nowCompact ? "true" : "false");
        };
    }

    // Scroll con la rueda del ratón (wheel): desplaza horizontalmente si se gira en cabeceras o fondo
    wrapper.addEventListener('wheel', (e) => {
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
    }, { passive: true });
}
