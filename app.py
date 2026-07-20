import streamlit as st
import pandas as pd
import os

from utils.database import init_db

# --- Configuración Inicial ---
st.set_page_config(
    page_title="SIGRAMA - App Corte y Doblez",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Inicializar Base de Datos SQLite
init_db()

# --- Inyección de CSS ---
def _read_css():
    css_file = "style.css"
    if os.path.exists(css_file):
        with open(css_file) as f:
            return f.read()
    return ""

def inject_css():
    css = _read_css()
    if css:
        st.markdown(f'<style>{css}</style>', unsafe_allow_html=True)
            
inject_css()

# --- Funciones de Utilidad ---
def check_login():
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False
    if 'role' not in st.session_state:
        st.session_state.role = None

def login():
    st.title("Acceso al Sistema - SIGRAMA")
    st.markdown("### Ingeniería que da resultados!!")
    
    with st.form("login_form"):
        username = st.text_input("Usuario")
        password = st.text_input("Contraseña", type="password")
        submit = st.form_submit_button("Ingresar")
        
        if submit:
            if username == "admin" and password == "admin":
                st.session_state.logged_in = True
                st.session_state.role = "Administrador"
                st.rerun()
            elif username == "operador" and password == "123":
                st.session_state.logged_in = True
                st.session_state.role = "Operador"
                st.rerun()
            else:
                st.error("Credenciales incorrectas")

def logout():
    st.session_state.logged_in = False
    st.session_state.role = None
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
    logo_path = os.path.join(os.path.dirname(__file__), "assets", "logo.png")
    if os.path.exists(logo_path):
        st.sidebar.image(logo_path, use_container_width=True)
    else:
        # Logo SVG de respaldo
        logo_html = """
        <div style="display: flex; align-items: center; margin-bottom: 25px;">
            <svg width="45" height="45" viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg" style="margin-right: 12px; margin-top: 5px;">
              <polygon points="0,0 100,0 100,15 0,30" fill="#EC2024" />
              <polygon points="0,40 100,25 100,75 0,60" fill="#EC2024" />
              <polygon points="0,70 100,85 100,100 0,100" fill="#EC2024" />
            </svg>
            <div style="display: flex; flex-direction: column; justify-content: center; margin-top: -2px;">
                <span style="font-family: 'Questrial', sans-serif; font-size: 14px; letter-spacing: 4px; color: white; line-height: 1; margin-bottom: -4px;">
                    industria
                </span>
                <span style="font-family: 'Montserrat', sans-serif; font-size: 26px; font-weight: 900; font-style: italic; color: white; line-height: 1;">
                    SIGRAMA
                </span>
            </div>
        </div>
        """
        st.sidebar.markdown(logo_html, unsafe_allow_html=True)
        
    role_icon = "🛡️" if st.session_state.role == "Administrador" else "👷"
    user_badge = f"""
    <div style="background:#1e1e1e;border-radius:8px;padding:8px 12px;margin-bottom:12px;
                border-left:3px solid #EC2024;font-family:'Questrial',sans-serif;">
        <span style="font-size:0.65rem;color:#888;letter-spacing:2px;text-transform:uppercase;">
            Usuario activo
        </span><br>
        <span style="font-size:0.95rem;color:#fff;font-weight:600;">
            {role_icon} {st.session_state.role}
        </span>
    </div>
    """
    st.sidebar.markdown(user_badge, unsafe_allow_html=True)
    
    # Definición del menú con íconos y nombres mejorados
    MENU_ITEMS = [
        {"key": "dashboard",     "icon": "📊", "label": "Panel de Control",          "admin_only": False},
        {"key": "global",        "icon": "🌐", "label": "Monitoreo Global",          "admin_only": False},
        None,  # separador
        {"key": "consultas",     "icon": "📋", "label": "Consultas y Reportes",     "admin_only": False},
        {"key": "planeacion",    "icon": "📅", "label": "Planeación de Corte",       "admin_only": False},
        None,  # separador
        {"key": "produccion",    "icon": "⚙️",  "label": "Control de Producción",   "admin_only": False},
        {"key": "manufactura",   "icon": "🤖", "label": "Manufactura Inteligente",  "admin_only": False},
        {"key": "entarimado",    "icon": "📦", "label": "Entarimado y Embarque",    "admin_only": False},
        None,  # separador
        {"key": "mantenimiento", "icon": "🛠️", "label": "Mantenimiento / Admin",     "admin_only": True},
        {"key": "sgc",           "icon": "📂", "label": "Documentos SGC",            "admin_only": True},
    ]

    is_admin = st.session_state.role == "Administrador"

    # Inicializar selección activa
    if "nav_choice" not in st.session_state:
        st.session_state.nav_choice = "dashboard"

    current = st.session_state.nav_choice

    sep_count = 0
    for item in MENU_ITEMS:
        if item is None:
            sep_count += 1
            st.sidebar.markdown('<hr style="border:none;border-top:1px solid #333;margin:6px 0;">', unsafe_allow_html=True)
            continue
        if item["admin_only"] and not is_admin:
            continue
        is_active = current == item["key"]
        
        # Render como botón Streamlit para capturar clics (con clase primaria si está activo)
        btn_key = f"nav_btn_{item['key']}"
        btn_type = "primary" if is_active else "secondary"
        if st.sidebar.button(
            f"{item['icon']}  {item['label']}",
            key=btn_key,
            use_container_width=True,
            type=btn_type,
            help=item['label']
        ):
            st.session_state.nav_choice = item["key"]
            st.rerun()

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
    st.sidebar.markdown("---")

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
    <div style="background-color: #1a1a1a; padding: 12px; border-radius: 8px; margin-bottom: 12px; border-left: 4px solid #32CD32; font-family: 'Questrial', sans-serif;">
        <p style="margin: 0; font-size: 0.82rem; color: #aaa; font-weight: bold; text-transform: uppercase; letter-spacing: 0.5px;">📈 AVANCES REGISTRADOS</p>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 6px; font-size: 0.75rem; color: #fff; margin-top: 8px;">
            <div><b>Ingeniería:</b> {av_ingenieria:,}</div>
            <div><b>Corte:</b> {av_corte:,}</div>
            <div><b>Rebabeo:</b> {av_rebabeo:,}</div>
            <div><b>Doblez:</b> {av_doblez:,}</div>
            <div><b>Barrenado:</b> {av_barrenado:,}</div>
            <div><b>Pintura:</b> {av_pintura:,}</div>
            <div><b>Liberado:</b> {av_liberado:,}</div>
            <div style="grid-column: span 2;"><b>Empaque:</b> {av_empaque:,}</div>
        </div>
    </div>
 
    <div style="background-color: #1a1a1a; padding: 12px; border-radius: 8px; margin-bottom: 12px; border-left: 4px solid #EC2024; font-family: 'Questrial', sans-serif;">
        <p style="margin: 0; font-size: 0.82rem; color: #aaa; font-weight: bold; text-transform: uppercase; letter-spacing: 0.5px;">🏭 WIP EN PISO (TOTAL)</p>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 6px; font-size: 0.75rem; color: #fff; margin-top: 8px;">
            <div><b>Por Cortar:</b> {wip_corte:,}</div>
            <div><b>Por Rebabear:</b> {wip_rebabeo:,}</div>
            <div><b>Por Doblar:</b> {wip_doblez:,}</div>
            <div><b>Por Barrenar:</b> {wip_barrenado:,}</div>
            <div><b>Por Pintar:</b> {wip_pintura:,}</div>
            <div><b>Por Liberar:</b> {wip_liberado:,}</div>
            <div style="grid-column: span 2;"><b>Por Empacar:</b> {wip_empaque:,}</div>
        </div>
    </div>
    """
    st.sidebar.markdown(stats_html, unsafe_allow_html=True)
    
    st.sidebar.markdown("---")

    col_out1, col_out2 = st.sidebar.columns(2)
    with col_out1:
        if st.button("🔄 Sincronizar", use_container_width=True, key="sidebar_sync_btn"):
            with st.spinner("Sincronizando..."):
                try:
                    from utils.database import sync_and_push_db
                    res_commit, res_push = sync_and_push_db()
                    
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
        if st.button("🚪 Salir", use_container_width=True, key="sidebar_logout_btn"):
            logout()
        
    # Slogan inferior
    slogan_path = os.path.join(os.path.dirname(__file__), "assets", "slogan.png")
    if os.path.exists(slogan_path):
        st.sidebar.image(slogan_path, use_container_width=True)
    else:
        slogan_html = """
        <div style="margin-top: 50px; text-align: left;">
            <span style="font-family: 'Questrial', sans-serif; font-size: 14px; color: white;">Ingeniería que da</span><br>
            <span style="font-family: 'Montserrat', sans-serif; font-size: 24px; font-weight: 700; font-style: italic; color: white;">resultados!!</span>
            <div style="width: 100%; height: 2px; background-color: #EC2024; margin-top: 5px;"></div>
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

# --- Vistas Principales (imported from views/) ---

from views.mantenimiento import view_mantenimiento

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
        import os
        banner_path = os.path.join(os.path.dirname(__file__), "assets", "banner.png")
        
        # Fin de configuracion lateral (se elimino la opcion de personalizar recursos)
        if os.path.exists(banner_path):
            st.image(banner_path, use_container_width=True)
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
        elif choice == "global":
            view_dashboard_global()
        elif choice == "consultas":
            view_consultas()
        elif choice == "planeacion":
            view_planeacion()
        elif choice == "produccion":
            view_produccion()
        elif choice == "manufactura":
            view_manufactura()
        elif choice == "entarimado":
            view_entarimado()
        elif choice == "mantenimiento":
            view_mantenimiento()
        elif choice == "sgc":
            view_sgc()

if __name__ == "__main__":
    main()

# Force reload: 2026-07-17 15:24
