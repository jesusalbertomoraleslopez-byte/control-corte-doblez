import streamlit as st

# ─────────────────────────────────────────────
#  CORPORATE COLORS
# ─────────────────────────────────────────────
RED   = "#EC2024"
BLACK = "#111111"
GRAY  = "#D2D3D5"
WHITE = "#FFFFFF"

# ─────────────────────────────────────────────
#  REUSABLE CARD HELPER
# ─────────────────────────────────────────────
def _benefit_card(icon: str, title: str, body: str, accent: str = RED) -> str:
    return f"""
    <div style="
        background:{WHITE};
        border-left: 5px solid {accent};
        border-radius: 8px;
        padding: 18px 16px;
        margin-bottom: 12px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.08);
        min-height: 130px;
    ">
        <div style="font-size:28px;margin-bottom:8px;">{icon}</div>
        <div style="font-family:Montserrat,sans-serif;font-weight:700;font-size:14px;
                    color:{BLACK};margin-bottom:6px;">{title}</div>
        <div style="font-family:Questrial,sans-serif;font-size:13px;color:#444;line-height:1.5;">
            {body}
        </div>
    </div>"""


def _tech_row(component: str, tech: str, purpose: str, bg: str = WHITE) -> str:
    return f"""
    <tr style="background:{bg};">
        <td style="padding:10px 14px;font-weight:700;color:{BLACK};
                   font-family:Montserrat,sans-serif;font-size:13px;">{component}</td>
        <td style="padding:10px 14px;text-align:center;">
            <span style="background:{RED};color:{WHITE};border-radius:20px;
                         padding:3px 12px;font-family:Montserrat,sans-serif;
                         font-size:12px;font-weight:600;">{tech}</span>
        </td>
        <td style="padding:10px 14px;font-family:Questrial,sans-serif;font-size:13px;color:#444;">
            {purpose}
        </td>
    </tr>"""


# ─────────────────────────────────────────────
#  TAB 1 – JUSTIFICACIÓN INDUSTRIA 4.0
# ─────────────────────────────────────────────
def _tab_justificacion():
    st.markdown(
        f"""
        <div style="background:linear-gradient(135deg,{BLACK} 0%,#2a0a0a 100%);
                    border-radius:12px;padding:28px 32px;margin-bottom:24px;">
            <h2 style="color:{WHITE};font-family:Montserrat,sans-serif;margin:0 0 8px;">
                🏭 SIGRAMA — Manufactura Inteligente
            </h2>
            <p style="color:{GRAY};font-family:Questrial,sans-serif;font-size:15px;margin:0;">
                Conectando la producción física con el mundo digital a través de Industria 4.0
            </p>
        </div>""",
        unsafe_allow_html=True,
    )

    col_l, col_r = st.columns([3, 2])

    with col_l:
        st.markdown(
            f"""
            <h3 style="font-family:Montserrat,sans-serif;color:{RED};font-size:18px;">
                ¿Por qué Industria 4.0?
            </h3>
            <p style="font-family:Questrial,sans-serif;font-size:14px;color:#333;line-height:1.7;">
                SIGRAMA ha identificado que los procesos de <b>corte láser, rebabeo y doblez</b>
                representan el corazón de su cadena de valor. Sin embargo, la gestión tradicional
                basada en papel genera:
            </p>
            <ul style="font-family:Questrial,sans-serif;font-size:14px;color:#333;line-height:1.9;">
                <li>⏱️ <b>Pérdida de visibilidad en tiempo real</b> del estado de cada pieza</li>
                <li>📋 <b>Rastreo manual</b> de Órdenes de Fabricación (OF) en hojas de cálculo dispersas</li>
                <li>🔴 <b>Acumulación de WIP</b> (Work In Progress) no controlado entre estaciones</li>
                <li>❌ <b>Errores humanos</b> en conteo y registro de avances por operador</li>
                <li>📊 <b>Ausencia de datos históricos</b> para análisis de tendencias y OEE</li>
            </ul>
            <p style="font-family:Questrial,sans-serif;font-size:14px;color:#333;line-height:1.7;">
                Esta aplicación nace como respuesta directa a esas brechas operativas,
                digitalizando el seguimiento de producción sin reemplazar los procesos
                físicos existentes.
            </p>""",
            unsafe_allow_html=True,
        )

    with col_r:
        st.markdown(
            f"""
            <div style="background:#f9f9f9;border-radius:12px;padding:20px;border:1px solid {GRAY};">
                <h4 style="font-family:Montserrat,sans-serif;color:{BLACK};margin-top:0;">
                    🔗 Concepto Digital Twin
                </h4>
                <p style="font-family:Questrial,sans-serif;font-size:13px;color:#444;line-height:1.7;">
                    Esta app actúa como un <b>gemelo digital</b> del piso de producción:
                    cada pieza física tiene su representación digital en el sistema.
                </p>
                <div style="background:{BLACK};color:{WHITE};border-radius:8px;
                            padding:12px;margin:12px 0;font-family:Questrial,sans-serif;font-size:12px;">
                    <b>Pieza Física</b> →  Troqueladora<br>
                    <b style="color:{RED};">↕ Sincronización</b><br>
                    <b>Registro Digital</b> → Dashboard WIP
                </div>
                <p style="font-family:Questrial,sans-serif;font-size:13px;color:#444;line-height:1.7;">
                    Cada avance registrado por el operador actualiza en tiempo real los
                    indicadores de flujo, porcentaje de avance y tablas de progreso.
                </p>
            </div>

            <div style="background:{RED};border-radius:12px;padding:20px;margin-top:14px;">
                <h4 style="font-family:Montserrat,sans-serif;color:{WHITE};margin-top:0;">
                    🎯 Objetivo Central
                </h4>
                <p style="font-family:Questrial,sans-serif;font-size:13px;color:{WHITE};
                           line-height:1.7;margin:0;">
                    Lograr <b>trazabilidad completa</b> de cada nido y cada pieza,
                    desde Ingeniería hasta Entrega, con datos confiables para
                    la toma de decisiones y el cumplimiento del SGC.
                </p>
            </div>""",
            unsafe_allow_html=True,
        )

    st.markdown(
        f"""
        <div style="background:#fffbe6;border:1px solid #FFD700;border-radius:8px;
                    padding:16px 20px;margin-top:10px;">
            <b style="font-family:Montserrat,sans-serif;color:{BLACK};">💡 ¿Cómo funciona esta app?</b>
            <ol style="font-family:Questrial,sans-serif;font-size:14px;color:#333;
                       margin-top:10px;line-height:1.8;">
                <li>El programador sube el <b>Plan de Producción</b> en Excel (Nidos + Piezas)</li>
                <li>El sistema genera automáticamente la <b>Orden de Fabricación (OF)</b></li>
                <li>Cada jefe de área registra sus <b>avances por proceso</b> en tiempo real</li>
                <li>El Dashboard calcula el <b>WIP, % de avance ponderado</b> y genera reportes</li>
                <li>El gerente obtiene visibilidad instantánea del estado de producción</li>
            </ol>
        </div>""",
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────
#  TAB 2 – BENEFICIOS ESTRATÉGICOS
# ─────────────────────────────────────────────
def _tab_beneficios():
    st.markdown(
        f"""
        <div style="background:linear-gradient(135deg,{RED} 0%,#8b0000 100%);
                    border-radius:12px;padding:22px 28px;margin-bottom:20px;">
            <h2 style="color:{WHITE};font-family:Montserrat,sans-serif;margin:0 0 6px;">
                🚀 Beneficios Estratégicos del Proyecto
            </h2>
            <p style="color:rgba(255,255,255,0.8);font-family:Questrial,sans-serif;font-size:14px;margin:0;">
                Impacto real en la operación, la calidad y la competitividad de SIGRAMA
            </p>
        </div>""",
        unsafe_allow_html=True,
    )

    col1, col2, col3 = st.columns(3)

    benefits = [
        (
            "📡", "Visibilidad en Tiempo Real",
            "Monitoreo instantáneo del flujo de producción: saber exactamente dónde "
            "está cada pieza en el proceso, sin esperar reportes manuales al final del turno.",
            "#00BFFF",
        ),
        (
            "📉", "Reducción del WIP Acumulado",
            "Identificar cuellos de botella entre estaciones antes de que generen "
            "retrasos críticos. El indicador de WIP alerta sobre material en tránsito "
            "no procesado.",
            "#32CD32",
        ),
        (
            "🔍", "Trazabilidad Completa",
            "Cada nido (N01, N02...) y cada pieza tiene un registro digital único. "
            "Se puede consultar su historia completa: cuándo avanzó, en qué área y quién lo registró.",
            "#FFD700",
        ),
        (
            "📋", "Reducción de Errores en OF",
            "Eliminar la transcripción manual de datos entre papel, Excel y sistemas. "
            "La OF se genera automáticamente desde el archivo cargado, reduciendo errores de captura.",
            "#FF6347",
        ),
        (
            "📊", "Decisiones Basadas en Datos",
            "Los indicadores ponderados (% avance por área con pesos reales) dan al "
            "gerente una visión objetiva del avance real, no subjetiva. Datos históricos "
            "para análisis de tendencias.",
            "#9370DB",
        ),
        (
            "✅", "Cumplimiento SGC",
            "La generación automática de reportes en PDF y Word garantiza documentación "
            "completa para auditorías del Sistema de Gestión de Calidad. Evidencia digital "
            "de cada OF.",
            "#DC143C",
        ),
    ]

    cols = [col1, col2, col3]
    for idx, (icon, title, body, accent) in enumerate(benefits):
        with cols[idx % 3]:
            st.markdown(_benefit_card(icon, title, body, accent), unsafe_allow_html=True)

    # KPI summary bar
    st.markdown(
        f"""
        <div style="background:{BLACK};border-radius:10px;padding:20px 24px;
                    margin-top:16px;display:flex;flex-wrap:wrap;gap:12px;justify-content:space-around;">
            <div style="text-align:center;">
                <div style="font-family:Montserrat,sans-serif;font-size:32px;font-weight:700;color:{RED};">
                    -80%
                </div>
                <div style="font-family:Questrial,sans-serif;font-size:12px;color:{GRAY};">
                    Tiempo de reporte manual
                </div>
            </div>
            <div style="text-align:center;">
                <div style="font-family:Montserrat,sans-serif;font-size:32px;font-weight:700;color:#32CD32;">
                    100%
                </div>
                <div style="font-family:Questrial,sans-serif;font-size:12px;color:{GRAY};">
                    Trazabilidad por pieza
                </div>
            </div>
            <div style="text-align:center;">
                <div style="font-family:Montserrat,sans-serif;font-size:32px;font-weight:700;color:#FFD700;">
                    7
                </div>
                <div style="font-family:Questrial,sans-serif;font-size:12px;color:{GRAY};">
                    Procesos monitoreados
                </div>
            </div>
            <div style="text-align:center;">
                <div style="font-family:Montserrat,sans-serif;font-size:32px;font-weight:700;color:#00BFFF;">
                    ∞
                </div>
                <div style="font-family:Questrial,sans-serif;font-size:12px;color:{GRAY};">
                    OFs históricas almacenables
                </div>
            </div>
        </div>""",
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────
#  TAB 3 – STACK TECNOLÓGICO
# ─────────────────────────────────────────────
def _tab_stack():
    st.markdown(
        f"""
        <div style="background:linear-gradient(135deg,#1a1a2e 0%,{BLACK} 100%);
                    border-radius:12px;padding:22px 28px;margin-bottom:20px;">
            <h2 style="color:{WHITE};font-family:Montserrat,sans-serif;margin:0 0 6px;">
                ⚙️ Stack Tecnológico del Sistema
            </h2>
            <p style="color:rgba(255,255,255,0.7);font-family:Questrial,sans-serif;font-size:14px;margin:0;">
                Tecnologías seleccionadas para máxima eficiencia, portabilidad y escalabilidad
            </p>
        </div>""",
        unsafe_allow_html=True,
    )

    tech_data = [
        ("Frontend / Backend", "Python + Streamlit", "Interfaz web interactiva sin necesidad de servidor dedicado"),
        ("Procesamiento de Datos", "Pandas + OpenPyxl", "Lectura, transformación y análisis de archivos Excel"),
        ("Visualización", "Plotly", "Gráficas interactivas de dona, barras y diagramas de flujo WIP"),
        ("Generación de Documentos", "FPDF2 + python-docx", "Exportación de reportes en formato PDF y Word"),
        ("Almacenamiento Temporal", "Streamlit Session State", "Estado de sesión del usuario por OF activa"),
        ("Identidad Corporativa", "CSS Injection + Google Fonts", "Paleta SIGRAMA (#EC2024/#111111), tipografías Questrial/Montserrat"),
    ]

    rows_html = ""
    for i, (comp, tech, purpose) in enumerate(tech_data):
        bg = "#f8f8f8" if i % 2 == 0 else WHITE
        rows_html += _tech_row(comp, tech, purpose, bg)

    table_html = f"""
    <div style="overflow-x:auto;border-radius:10px;
                box-shadow:0 2px 12px rgba(0,0,0,0.1);margin-bottom:24px;">
    <table style="width:100%;border-collapse:collapse;font-size:13px;">
        <thead>
            <tr style="background:{RED};color:{WHITE};">
                <th style="padding:12px 14px;text-align:left;
                           font-family:Montserrat,sans-serif;">COMPONENTE</th>
                <th style="padding:12px 14px;text-align:center;
                           font-family:Montserrat,sans-serif;">TECNOLOGÍA</th>
                <th style="padding:12px 14px;text-align:left;
                           font-family:Montserrat,sans-serif;">PROPÓSITO</th>
            </tr>
        </thead>
        <tbody>{rows_html}</tbody>
    </table>
    </div>"""

    st.markdown(table_html, unsafe_allow_html=True)

    # Industry 4.0 pillars
    st.markdown(
        f"""
        <h3 style="font-family:Montserrat,sans-serif;color:{BLACK};font-size:17px;margin-bottom:12px;">
            🏗️ Pilares de Industria 4.0 en este Proyecto
        </h3>""",
        unsafe_allow_html=True,
    )

    pillars = [
        ("🌐", "IoT & Conectividad", "#00BFFF",
         "Aunque la app funciona de forma local, está diseñada para integrarse "
         "con sensores y lectores de código en línea de producción en una fase futura."),
        ("📊", "Big Data & Analytics", "#FFD700",
         "Cada OF cargada genera un registro de datos estructurado. La acumulación "
         "de múltiples OFs permite análisis estadísticos de eficiencia por proceso."),
        ("☁️", "Cloud Ready", "#32CD32",
         "Al estar desarrollado en Python + Streamlit, el sistema puede desplegarse "
         "en cualquier plataforma cloud (Azure, AWS, GCP) con configuración mínima."),
        ("🤖", "Automatización", RED,
         "La generación automática de Órdenes de Fabricación, reportes PDF/Word y "
         "cálculos de avance ponderado elimina trabajo manual repetitivo y propenso a errores."),
    ]

    cols = st.columns(4)
    for i, (icon, title, color, desc) in enumerate(pillars):
        with cols[i]:
            st.markdown(
                f"""
                <div style="background:{BLACK};border-top:4px solid {color};
                            border-radius:8px;padding:16px 14px;min-height:180px;">
                    <div style="font-size:26px;margin-bottom:8px;">{icon}</div>
                    <div style="font-family:Montserrat,sans-serif;font-weight:700;
                                font-size:13px;color:{WHITE};margin-bottom:8px;">{title}</div>
                    <div style="font-family:Questrial,sans-serif;font-size:12px;
                                color:{GRAY};line-height:1.5;">{desc}</div>
                </div>""",
                unsafe_allow_html=True,
            )

    st.markdown(
        f"""
        <div style="background:#f0f8ff;border:1px solid #00BFFF;border-radius:8px;
                    padding:16px 20px;margin-top:20px;">
            <b style="font-family:Montserrat,sans-serif;color:{BLACK};font-size:14px;">
                📌 Roadmap Tecnológico
            </b>
            <p style="font-family:Questrial,sans-serif;font-size:13px;color:#333;
                      margin-top:10px;line-height:1.7;margin-bottom:0;">
                En fases posteriores, SIGRAMA podrá escalar este sistema integrando
                <b>lectores de código de barras/QR</b> en cada estación de trabajo para
                registro automático de avances, conectar con el <b>ERP</b> para trazabilidad
                end-to-end, y activar <b>alertas automáticas</b> por correo o WhatsApp cuando
                el WIP supera umbrales críticos. El stack actual está diseñado para soportar
                estas extensiones sin rediseño arquitectural.
            </p>
        </div>""",
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────
#  MAIN VIEW
# ─────────────────────────────────────────────
def view_manufactura():
    st.markdown(
        f"""
        <h1 style="font-family:Montserrat,sans-serif;color:{BLACK};margin-bottom:4px;">
            🏭 MANUFACTURA INTELIGENTE
        </h1>
        <p style="font-family:Questrial,sans-serif;color:#666;font-size:14px;margin-bottom:20px;">
            Industria 4.0 · Digital Twin · Stack Tecnológico · Beneficios Estratégicos
        </p>""",
        unsafe_allow_html=True,
    )

    tab1, tab2, tab3 = st.tabs([
        "🏭 Justificación Industria 4.0",
        "🚀 Beneficios Estratégicos",
        "⚙️ Stack Tecnológico",
    ])

    with tab1:
        _tab_justificacion()

    with tab2:
        _tab_beneficios()

    with tab3:
        _tab_stack()
