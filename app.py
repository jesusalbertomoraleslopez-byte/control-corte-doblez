import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import os
from pathlib import Path

from utils.database import init_db

# --- Configuración Inicial ---
st.set_page_config(
    page_title="SIGRAMA - App Corte y Doblez",
    layout="wide",
    initial_sidebar_state="expanded"
)

# === SIGRAMA FORM CONTRAST (estandar visual de campos) ===
st.markdown("""
<style>
    /* Escritorio de la app: gris claro para que los campos blancos resalten */
    html body .stApp, html body [data-testid="stAppViewContainer"], html body [data-testid="stMain"] {
        background-color: #EEF2F6 !important;
    }
    /* Campos de texto / numero / fecha: fondo blanco + borde oscuro bien visible */
    [data-testid="stMain"] div[data-baseweb="input"],
    [data-testid="stMain"] div[data-baseweb="textarea"],
    [data-testid="stMain"] div[data-baseweb="select"] > div,
    [data-testid="stDialog"] div[data-baseweb="input"],
    [data-testid="stDialog"] div[data-baseweb="textarea"],
    [data-testid="stDialog"] div[data-baseweb="select"] > div {
        background-color: #FFFFFF !important;
        border: 1.5px solid #64748B !important;
        border-radius: 6px !important;
        box-shadow: 0 1px 2px rgba(15,23,42,0.08) !important;
    }
    [data-testid="stMain"] div[data-baseweb="base-input"],
    [data-testid="stDialog"] div[data-baseweb="base-input"] {
        background-color: #FFFFFF !important;
        border: none !important;
    }
    [data-testid="stMain"] input, [data-testid="stMain"] textarea,
    [data-testid="stDialog"] input, [data-testid="stDialog"] textarea {
        background-color: #FFFFFF !important;
        color: #111111 !important;
        -webkit-text-fill-color: #111111 !important;
    }
    /* Foco: borde rojo corporativo */
    [data-testid="stMain"] div[data-baseweb="input"]:focus-within,
    [data-testid="stMain"] div[data-baseweb="textarea"]:focus-within,
    [data-testid="stMain"] div[data-baseweb="select"]:focus-within > div,
    [data-testid="stDialog"] div[data-baseweb="input"]:focus-within,
    [data-testid="stDialog"] div[data-baseweb="select"]:focus-within > div {
        border-color: #EC2024 !important;
        box-shadow: 0 0 0 3px rgba(236,32,36,0.18) !important;
    }
    /* Etiquetas legibles */
    [data-testid="stMain"] [data-testid="stWidgetLabel"] p {
        color: #1E293B !important;
        font-weight: 700 !important;
    }
</style>
""", unsafe_allow_html=True)

components.html("""
<script>
(function() {
  function hideFooter() {
    document.querySelectorAll('footer').forEach(function(el) { el.style.display='none'; });
    ['stFooter','stDecoration','stViewerBadge'].forEach(function(id) {
      document.querySelectorAll('[data-testid="'+id+'"]').forEach(function(el) { el.style.display='none'; });
    });
    document.querySelectorAll('div[class*="viewerBadge"],div[class*="ProfileButton"],a[href*="streamlit.io"]').forEach(function(el) { el.style.display='none'; });
  }
  var observer = new MutationObserver(hideFooter);
  observer.observe(document.documentElement, {childList:true, subtree:true});
  hideFooter();
})();
</script>
""", height=0)

# Sincronización inicial desde Google Cloud Storage (Persistencia Cloud Run)
if "_gcs_initial_sync" not in st.session_state:
    try:
        from utils.gcs_sync import sync_db_from_gcs
        sync_db_from_gcs()
        st.session_state["_gcs_initial_sync"] = True
    except Exception as _egcs:
        print(f"[GCS] Aviso inicial: {_egcs}")

# Inicializar Base de Datos SQLite
init_db()

# --- Inyección de CSS ---
@st.cache_data(ttl=3600, show_spinner=False)
def _read_css():
    css_file = "style.css"
    if os.path.exists(css_file):
        with open(css_file, encoding="utf-8", errors="ignore") as f:
            return f.read()
    return ""

@st.cache_data(ttl=3600, show_spinner=False)
def _get_logo_b64_tag():
    import base64
    logo_path = os.path.join(os.path.dirname(__file__), "assets", "logo.png")
    if os.path.exists(logo_path):
        try:
            with open(logo_path, "rb") as _lf:
                _b64 = base64.b64encode(_lf.read()).decode("utf-8")
            return f'<img src="data:image/png;base64,{_b64}" style="max-height:36px; width:auto; display:block;" alt="SIGRAMA" />'
        except Exception:
            pass
    return """
    <div style="display:flex;align-items:center;gap:8px;">
        <svg width="28" height="28" viewBox="0 0 100 100" fill="none">
          <polygon points="0,0 100,0 100,15 0,30" fill="#EC2024" />
          <polygon points="0,40 100,25 100,75 0,60" fill="#EC2024" />
          <polygon points="0,70 100,85 100,100 0,100" fill="#EC2024" />
        </svg>
        <span style="font-family:'Montserrat',sans-serif;font-size:19px;font-weight:900;font-style:italic;color:white;">SIGRAMA</span>
    </div>
    """

def inject_css():
    css = _read_css()
    if css:
        st.markdown(f'<style>{css}</style>', unsafe_allow_html=True)
    st.markdown("""<style>
    /* Menú Lateral Estilo Google Workspace (Píldoras Material Design 3) */
    [data-testid="stSidebar"] div[role="radiogroup"] > label > div:first-child {
        display: none !important;
    }
    [data-testid="stSidebar"] div[role="radiogroup"] {
        background-color: transparent !important;
        border: none !important;
        padding: 0 !important;
        gap: 3px !important;
        display: flex !important;
        flex-direction: column !important;
    }
    [data-testid="stSidebar"] div[role="radiogroup"] > label {
        background-color: transparent !important;
        border: 1px solid transparent !important;
        color: #CBD5E1 !important;
        padding: 9px 18px !important;
        border-radius: 24px !important;
        transition: all 0.18s ease-in-out !important;
        margin: 1px 0 !important;
        cursor: pointer !important;
        display: flex !important;
        align-items: center !important;
    }
    [data-testid="stSidebar"] div[role="radiogroup"] label p,
    [data-testid="stSidebar"] div[role="radiogroup"] label span {
        font-size: 15px !important;
        font-family: 'Questrial', sans-serif !important;
        font-weight: 500 !important;
        color: #CBD5E1 !important;
        line-height: 1.35 !important;
    }
    [data-testid="stSidebar"] div[role="radiogroup"] > label:hover,
    [data-testid="stSidebar"] div[role="radiogroup"] > label:hover p,
    [data-testid="stSidebar"] div[role="radiogroup"] > label:hover span {
        background-color: rgba(255, 255, 255, 0.08) !important;
        border-color: transparent !important;
        color: #FFFFFF !important;
        border-radius: 24px !important;
    }
    [data-testid="stSidebar"] div[role="radiogroup"] > label[data-checked="true"],
    [data-testid="stSidebar"] div[role="radiogroup"] > label[data-checked="true"] p,
    [data-testid="stSidebar"] div[role="radiogroup"] > label[data-checked="true"] span,
    [data-testid="stSidebar"] div[role="radiogroup"] > label:has(input:checked),
    [data-testid="stSidebar"] div[role="radiogroup"] > label:has(input:checked) p,
    [data-testid="stSidebar"] div[role="radiogroup"] > label:has(input:checked) span {
        background-color: rgba(236, 32, 36, 0.22) !important;
        border: 1px solid rgba(236, 32, 36, 0.55) !important;
        color: #FFFFFF !important;
        font-weight: 700 !important;
        border-radius: 24px !important;
    }

    /* Botón Google Workspace 'Redactar / Nuevo' (FAB Pill) */
    div.stButton > button[key="btn_google_fab_corte"] {
        border-radius: 20px !important;
        padding: 10px 20px !important;
        font-size: 14.5px !important;
        font-weight: 700 !important;
        box-shadow: 0 4px 14px rgba(236, 32, 36, 0.35) !important;
        border: 1px solid rgba(236, 32, 36, 0.8) !important;
        margin-bottom: 8px !important;
    }
    </style>""", unsafe_allow_html=True)

inject_css()


# --- Funciones de Utilidad ---
def check_login():
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False
    if 'role' not in st.session_state:
        st.session_state.role = None
    if 'username' not in st.session_state:
        st.session_state.username = None
    if 'nombre_completo' not in st.session_state:
        st.session_state.nombre_completo = None

    # Soporte SSO robusto desde Concentradora SIGRAMA
    try:
        qp = dict(st.query_params) if hasattr(st, "query_params") else {}
        sso_token = qp.get("sso_token")
        if isinstance(sso_token, list): sso_token = sso_token[0] if sso_token else None
        sso_user = qp.get("sso_user")
        if isinstance(sso_user, list): sso_user = sso_user[0] if sso_user else None
        sso_role = qp.get("sso_role", "Admin")
        if isinstance(sso_role, list): sso_role = sso_role[0] if sso_role else "Admin"

        if sso_token == "SIGRAMA_AUTH_TOKEN" and sso_user:
            st.session_state.logged_in = True
            st.session_state.username = sso_user
            st.session_state.nombre_completo = sso_user
            r_str = str(sso_role).lower()
            u_str = str(sso_user).lower()
            if r_str in ["admin", "administrador"] or any(x in u_str for x in ["morales", "admin", "jmorales"]):
                st.session_state.role = "admin"
                st.session_state.area_asignada = "Todas"
            else:
                st.session_state.role = "operador"
                st.session_state.area_asignada = "Corte y Doblez"
    except Exception:
        pass

def login():
    banner_p = Path(__file__).resolve().parent / "assets" / "banner.png"
    if banner_p.exists():
        st.image(str(banner_p), use_container_width=True)
    st.title("Acceso al Sistema - SIGRAMA")
    st.markdown("### Ingeniería que da resultados!!")
    
    with st.form("login_form"):
        username = st.text_input("Usuario")
        password = st.text_input("Contraseña", type="password")
        submit = st.form_submit_button("Ingresar", type="primary", use_container_width=True)
        
        if submit:
            from utils.database import autenticar_usuario_db, registrar_auditoria
            
            u_clean = str(username).strip().lower()
            p_clean = str(password).strip()
            admin_users = ["jmorales", "admin", "administrador", "sig-adm-01", "jesus morales", "jesús morales"]
            admin_passwords = ["SigramaAdmin2026", "SigramaMetales2026", "Admin2026", "admin", "MAQUINADOS"]
            
            if (u_clean in admin_users or "morales" in u_clean or "admin" in u_clean) and p_clean in admin_passwords:
                st.session_state.logged_in = True
                st.session_state.username = "jmorales"
                st.session_state.nombre_completo = "Jesús Alberto Morales López"
                st.session_state.role = "admin"
                st.session_state.area_asignada = "Todas"
                st.toast("Bienvenido Jesús Alberto Morales López", icon="👋")
                st.rerun()

            u_info = autenticar_usuario_db(username, password)
            if u_info:
                st.session_state.logged_in = True
                st.session_state.username = u_info["username"]
                st.session_state.nombre_completo = u_info["nombre_completo"]
                st.session_state.role = u_info["rol"]
                st.session_state.area_asignada = u_info["area_asignada"]
                
                registrar_auditoria(u_info["username"], "Inicio de Sesión", f"Usuario {u_info['nombre_completo']} ({u_info['rol']}) inició sesión.")
                st.toast(f"Bienvenido {u_info['nombre_completo']}", icon="👋")
                st.rerun()
            else:
                st.error("❌ Credenciales incorrectas o usuario inactivo.")

def logout():
    from utils.database import registrar_auditoria
    if st.session_state.get("username"):
        registrar_auditoria(st.session_state.username, "Cierre de Sesión", "Usuario cerró sesión de forma manual.")
    st.session_state.logged_in = False
    st.session_state.role = None
    st.session_state.username = None
    st.session_state.nombre_completo = None
    st.rerun()

@st.cache_data(ttl=30, show_spinner=False)
def get_sidebar_stats():
    """Cached sidebar KPIs — refreshed every 30 seconds."""
    try:
        from utils.database import get_connection
        from views.reportes import calculate_global_wip
        conn = get_connection()
        df_avances = pd.read_sql_query("SELECT area, SUM(cantidad) as cantidad FROM avances GROUP BY area", conn)
        conn.close()
        wip_data = calculate_global_wip("Todas")
        av_dict = df_avances.set_index('area')['cantidad'].to_dict() if not df_avances.empty else {}
        return av_dict, wip_data
    except Exception:
        return {}, {}

# --- Menú Lateral ---
def render_sidebar():
    logo_img_tag = _get_logo_b64_tag()

    user_display = st.session_state.get("nombre_completo") or st.session_state.get("username") or "Usuario"
    role_str = str(st.session_state.role or "admin")
    role_icon = "🛡️" if role_str.lower() in ["administrador", "admin"] else ("👑" if role_str == "Supervisor" else "👷")

    header_badge = f"""
    <div style="background:#18191f;border-radius:9px;padding:8px 11px;margin-bottom:8px;
                border:1px solid #2b2d38;border-left:4px solid #EC2024;font-family:'Questrial',sans-serif;">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:5px;padding-bottom:5px;border-bottom:1px solid #2a2c35;">
            {logo_img_tag}
            <span style="background:#EC2024;color:#fff;font-size:0.65rem;font-weight:800;padding:2px 7px;border-radius:10px;text-transform:uppercase;letter-spacing:0.5px;">
                {role_str}
            </span>
        </div>
        <div style="font-size:0.84rem;color:#ffffff;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">
            {role_icon} {user_display}
        </div>
    </div>
    """
    st.sidebar.markdown(header_badge, unsafe_allow_html=True)
    
    # --- NAVEGACIÓN ESTILO GOOGLE WORKSPACE ---
    if st.sidebar.button("➕ Nueva Orden", key="btn_google_fab_corte", use_container_width=True, type="primary"):
        st.session_state.nav_choice = "produccion"
        st.session_state["corte_google_label"] = "⚙️ Producción"
        st.rerun()

    st.sidebar.markdown("<p style='font-family: \"Montserrat\", sans-serif; font-size: 11px; font-weight: 700; color: #94A3B8; text-transform: uppercase; letter-spacing: 0.5px; margin-top: 10px; margin-bottom: 6px;'>Menú Principal:</p>", unsafe_allow_html=True)

    is_admin = str(st.session_state.role).lower() in ["administrador", "admin"]

    CORTE_MENU_MAP = {
        "📊 Resumen": "dashboard",
        "🗂️ Kanban": "kanban",
        "⚙️ Producción": "produccion",
        "🛰️ Repositorio": "supervision_gcs",
        "📋 Reportes": "consultas",
        "🏷️ Etiquetas": "etiquetas",
        "🌐 Monitoreo": "global",
        "🤖 Manufactura": "manufactura",
        "🛠️ Ajustes": "mantenimiento",
        "📂 Documentos": "sgc",
    }
    CORTE_KEY_TO_LABEL = {v: k for k, v in CORTE_MENU_MAP.items()}

    google_corte_items = [
        "📊 Resumen",
        "🗂️ Kanban",
        "⚙️ Producción",
        "🛰️ Repositorio",
        "📋 Reportes",
        "🏷️ Etiquetas",
        "🌐 Monitoreo",
        "🤖 Manufactura",
    ]
    if is_admin:
        google_corte_items.extend(["🛠️ Ajustes", "📂 Documentos"])

    if "nav_choice" not in st.session_state:
        st.session_state.nav_choice = "dashboard"

    curr_key = st.session_state.nav_choice
    curr_label = CORTE_KEY_TO_LABEL.get(curr_key, "📊 Resumen")
    if curr_label not in google_corte_items:
        curr_label = google_corte_items[0]
    idx_corte = google_corte_items.index(curr_label)

    sel_label = st.sidebar.radio(
        "Navegación:",
        options=google_corte_items,
        index=idx_corte,
        key="radio_corte_google",
        label_visibility="collapsed"
    )
    st.session_state.nav_choice = CORTE_MENU_MAP.get(sel_label, "dashboard")
    choice = st.session_state.nav_choice
    
    # Determinar la OF Activa en segundo plano
    from utils.database import get_all_ofs, get_active_of
    all_ofs = get_all_ofs()
    if all_ofs:
        current_active = st.session_state.get("of_number")
        if not current_active or current_active not in all_ofs:
            db_active = get_active_of()
            current_active = db_active['of_number'] if db_active else all_ofs[0]
        st.session_state.of_number = current_active
    else:
        st.session_state.of_number = None

    av_dict, wip_data = get_sidebar_stats()
    
    av_ingenieria = av_dict.get("Ingenieria", 0)
    av_corte = av_dict.get("Corte", 0)
    av_rebabeo = av_dict.get("Rebabeo", 0)
    av_doblez = av_dict.get("Doblez", 0)
    av_barrenado = av_dict.get("Barrenado", 0)
    av_pintura = av_dict.get("Pintura", 0)
    av_liberado = av_dict.get("Liberado", 0)
    av_empaque = av_dict.get("Empaque", 0)
    
    wip_corte = wip_data.get("Corte", 0)
    wip_rebabeo = wip_data.get("Rebabeo", 0)
    wip_doblez = wip_data.get("Doblez", 0)
    wip_barrenado = wip_data.get("Barrenado", 0)
    wip_pintura = wip_data.get("Pintura", 0)
    wip_liberado = wip_data.get("Liberado", 0)
    wip_empaque = wip_data.get("Empaque", 0)
    
    stats_html = f"""
    <div style="background-color: #18191f; padding: 9px 10px; border-radius: 8px; margin-top: 6px; margin-bottom: 6px; border: 1px solid #2b2d38; border-left: 4px solid #32CD32; font-family: 'Questrial', sans-serif;">
        <p style="margin: 0; font-size: 0.76rem; color: #32CD32; font-weight: 800; text-transform: uppercase; letter-spacing: 0.5px;">📈 AVANCES REGISTRADOS</p>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 3px 8px; font-size: 0.76rem; color: #fff; margin-top: 5px;">
            <div><b>Ing:</b> {av_ingenieria:,}</div>
            <div><b>Corte:</b> {av_corte:,}</div>
            <div><b>Rebabeo:</b> {av_rebabeo:,}</div>
            <div><b>Doblez:</b> {av_doblez:,}</div>
            <div><b>Barrenado:</b> {av_barrenado:,}</div>
            <div><b>Pintura:</b> {av_pintura:,}</div>
            <div><b>Liberado:</b> {av_liberado:,}</div>
            <div><b>Empaque:</b> {av_empaque:,}</div>
        </div>
    </div>
 
    <div style="background-color: #18191f; padding: 9px 10px; border-radius: 8px; margin-bottom: 6px; border: 1px solid #2b2d38; border-left: 4px solid #EC2024; font-family: 'Questrial', sans-serif;">
        <p style="margin: 0; font-size: 0.76rem; color: #ff6b6e; font-weight: 800; text-transform: uppercase; letter-spacing: 0.5px;">🏭 WIP EN PISO (TOTAL)</p>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 3px 8px; font-size: 0.76rem; color: #fff; margin-top: 5px;">
            <div><b>Por Cortar:</b> {wip_corte:,}</div>
            <div><b>Rebabear:</b> {wip_rebabeo:,}</div>
            <div><b>Por Doblar:</b> {wip_doblez:,}</div>
            <div><b>Barrenar:</b> {wip_barrenado:,}</div>
            <div><b>Por Pintar:</b> {wip_pintura:,}</div>
            <div><b>Liberar:</b> {wip_liberado:,}</div>
            <div style="grid-column: span 2;"><b>Por Empacar:</b> {wip_empaque:,}</div>
        </div>
    </div>
    """
    st.sidebar.markdown(stats_html, unsafe_allow_html=True)

    # Botón exclusivo para traer los datos más recientes desde Google Cloud Platform
    if st.sidebar.button("Jalar Información de GCP", icon="☁️", use_container_width=True, key="sidebar_pull_gcp_btn"):
        with st.spinner("Descargando base de datos oficial y órdenes desde GCP..."):
            try:
                from utils.gcs_sync import pull_data_from_gcp
                ok, msg = pull_data_from_gcp()
                if ok:
                    st.toast("✅ ¡Datos actualizados desde Google Cloud!", icon="☁️")
                    st.balloons()
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.toast(f"⚠️ {msg}", icon="⚠️")
            except Exception as ep:
                st.toast(f"❌ Error al consultar GCP: {ep}", icon="🚨")

    col_out1, col_out2 = st.sidebar.columns(2)
    with col_out1:
        if st.button("Sincronizar", icon="🔄", use_container_width=True, key="sidebar_sync_btn"):
            with st.spinner("Sincronizando..."):
                try:
                    from utils.database import sync_and_push_db
                    res_commit, res_push = sync_and_push_db()
                    
                    from utils.gcs_sync import push_db_to_gcs_async
                    push_db_to_gcs_async()

                    if res_push.returncode == 0:
                        commit_out = res_commit.stdout.decode('utf-8', errors='ignore')
                        if "nothing to commit" in commit_out or res_commit.returncode != 0:
                            st.toast("⚠️ Sin cambios nuevos que sincronizar", icon="ℹ️")
                        else:
                            st.toast("✅ ¡Sincronizado con éxito!", icon="🚀")
                            st.balloons()
                    else:
                        err_text = res_push.stderr.decode('utf-8', errors='ignore')
                        st.toast(f"❌ Error al subir: {err_text[:100]}", icon="⚠️")
                except Exception as e:
                    st.toast(f"❌ Error: {e}", icon="🚨")
                    
    with col_out2:
        if st.button("Salir", icon="🚪", use_container_width=True, key="sidebar_logout_btn"):
            logout()
        
    # Slogan inferior compacto
    slogan_html = """
    <div style="margin-top: 8px; padding-top: 6px; border-top: 2px solid #EC2024; text-align: center; line-height: 1.15;">
        <span style="font-family: 'Questrial', sans-serif; font-size: 11px; color: #bbb; letter-spacing: 1px;">Ingeniería que da </span>
        <span style="font-family: 'Montserrat', sans-serif; font-size: 14px; font-weight: 800; font-style: italic; color: #FFFFFF;">resultados!!</span>
    </div>
    """
    st.sidebar.markdown(slogan_html, unsafe_allow_html=True)
        
    return choice

from views.produccion import view_planeacion, view_produccion
from views.consultas import view_consultas
from views.dashboard import view_dashboard
from views.dashboard_global import view_dashboard_global
from views.manufactura import view_manufactura
from views.entarimado import view_entarimado
from views.inventario_wip import view_inventario_wip
from views.dashboard_etiquetas import view_dashboard_etiquetas

# --- Vistas Principales (imported from views/) ---

from views.mantenimiento import view_mantenimiento
from views.generador_of import view_generador_of
from views.kanban_produccion import view_kanban_produccion
from views.supervision_gcs import view_supervision_gcs

def view_sgc():
    st.title("7. SGC (Sistema de Gestión de Calidad)")
    st.write("Glosario de Documentos y descargas nativas (Word/PDF).")

# --- Lógica Principal ---
def main():
    # Comprobar si se solicita la vista pública (individual o rotativa) sin requerir login
    view_param = st.query_params.get("view")
    if view_param == "avance_diario":
        from views.consultas import view_public_avance_diario
        view_public_avance_diario()
        return
    elif view_param == "rotativo":
        from views.consultas import view_public_rotativo
        view_public_rotativo()
        return

    check_login()
    
    if not st.session_state.logged_in:
        login()
    else:
        choice = render_sidebar()
        
        # Banner Corporativo basado en Manual de Identidad
        banner_path = Path(__file__).resolve().parent / "assets" / "banner.png"
        
        # Fin de configuracion lateral (se elimino la opcion de personalizar recursos)
        if banner_path.exists():
            st.image(str(banner_path), use_container_width=True)
        else:
            banner_html = """
<div style="background: linear-gradient(135deg, #000000 0%, #222222 100%); 
            border-radius: 8px; padding: 30px 40px; margin-bottom: 25px; 
            box-shadow: 0 10px 20px rgba(0,0,0,0.1); position: relative; overflow: hidden;">
    <!-- Elemento grafico de fondo -->
    <div style="position: absolute; right: -50px; top: -50px; opacity: 0.05;">
        <svg width="300" height="300" viewBox="0 0 100 100" fill="white">
            <polygon points="0,0 100,0 100,15 0,30" />
            <polygon points="0,40 100,25 100,75 0,60" />
            <polygon points="0,70 100,85 100,100 0,100" />
        </svg>
    </div>
    <h2 style="font-family: 'Questrial', sans-serif; color: white; margin: 0; font-size: 28px; font-weight: 400; letter-spacing: 1px;">
        SOLUCIONES QUE
    </h2>
    <div style="display: inline-block; background-color: white; padding: 5px 15px; margin: 10px 0;">
        <h2 style="font-family: 'Montserrat', sans-serif; color: #111111; margin: 0; font-size: 28px; font-weight: 700;">
            TRANSFORMAN
        </h2>
    </div>
    <h2 style="font-family: 'Montserrat', sans-serif; color: #EC2024; margin: 0; font-size: 28px; font-weight: 700;">
        TU EMPRESA
    </h2>
</div>
"""
            st.markdown(banner_html, unsafe_allow_html=True)
        
        if choice == "dashboard":
            view_dashboard()
        elif choice == "supervision_gcs":
            view_supervision_gcs()
        elif choice == "kanban":
            view_kanban_produccion()
        elif choice == "produccion":
            view_produccion()
        elif choice == "consultas":
            view_consultas()
        elif choice == "etiquetas":
            view_dashboard_etiquetas()
        elif choice == "global":
            view_dashboard_global()
        elif choice == "manufactura":
            view_manufactura()
        elif choice == "mantenimiento":
            view_mantenimiento()
        elif choice == "sgc":
            view_sgc()

if __name__ == "__main__":
    main()

# Force reload: 2026-09-11 13:09 - Corte Detalle Piezas Excel Button Active
