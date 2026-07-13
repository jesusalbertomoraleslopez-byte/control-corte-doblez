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
def inject_css():
    css_file = "style.css"
    if os.path.exists(css_file):
        with open(css_file) as f:
            st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)
            
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

def get_sidebar_stats():
    try:
        from utils.database import get_connection
        from views.reportes import calculate_global_wip
        conn = get_connection()
        df_avances = pd.read_sql_query("SELECT area, SUM(cantidad) as cantidad FROM avances GROUP BY area", conn)
        wip_data = calculate_global_wip("Todas")
        conn.close()
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
        
    st.sidebar.markdown(f"**Usuario:** {st.session_state.role}")
    
    menu = [
        "1. DASHBOARD PRINCIPAL",
        "1.2 DASHBOARD GLOBAL",
        "2. CONSULTAS Y REPORTES",
        "3. PLANEACIÓN",
        "4. CONTROL DE PRODUCCIÓN",
        "5. MANUFACTURA INTELIGENTE Y MANUAL"
    ]
    
    if st.session_state.role == "Administrador":
        menu.extend([
            "6. MANTENIMIENTO",
            "7. SGC (Oculto - Solo Admin)"
        ])
        
    choice = st.sidebar.radio("Navegación", menu)
    
    st.sidebar.markdown("---")
    
    # Selector Global de OF Activa
    from utils.database import get_all_ofs, get_active_of
    all_ofs = get_all_ofs()
    if all_ofs:
        current_active = st.session_state.get("of_number")
        if not current_active:
            db_active = get_active_of()
            current_active = db_active['of_number'] if db_active else all_ofs[0]
            
        default_idx = 0
        if current_active in all_ofs:
            default_idx = all_ofs.index(current_active)
            
        selected_of = st.sidebar.selectbox(
            "🔍 Orden Activa (OF):",
            all_ofs,
            index=default_idx,
            key="sidebar_of_selector"
        )
        st.session_state.of_number = selected_of
    else:
        st.sidebar.info("ℹ️ No hay OFs cargadas.")
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
            <div><b>Empaque:</b> {av_empaque:,}</div>
        </div>
    </div>

    <div style="background-color: #1a1a1a; padding: 12px; border-radius: 8px; margin-bottom: 12px; border-left: 4px solid #EC2024; font-family: 'Questrial', sans-serif;">
        <p style="margin: 0; font-size: 0.82rem; color: #aaa; font-weight: bold; text-transform: uppercase; letter-spacing: 0.5px;">🏭 WIP EN PISO (TOTAL)</p>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 6px; font-size: 0.75rem; color: #fff; margin-top: 8px;">
            <div><b>Corte:</b> {wip_corte:,}</div>
            <div><b>Rebabeo:</b> {wip_rebabeo:,}</div>
            <div><b>Doblez:</b> {wip_doblez:,}</div>
            <div><b>Barrenado:</b> {wip_barrenado:,}</div>
            <div><b>Pintura:</b> {wip_pintura:,}</div>
            <div><b>Liberado:</b> {wip_liberado:,}</div>
            <div style="grid-column: span 2;"><b>Empaque:</b> {wip_empaque:,}</div>
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
                    import subprocess
                    import datetime
                    from utils.database import EXCEL_DB_PATH, save_db_to_excel
                    save_db_to_excel()
                    
                    # Configurar identidad de git (requerido en contenedores sin config global)
                    subprocess.run(["git", "config", "user.email", "bot@sigrama.com"], capture_output=True)
                    subprocess.run(["git", "config", "user.name", "Sigrama Bot"], capture_output=True)
                    
                    subprocess.run(["git", "add", EXCEL_DB_PATH], capture_output=True, timeout=15)
                    res_commit = subprocess.run(
                        ["git", "commit", "-m", f"Manual-sync sidebar {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"],
                        capture_output=True, timeout=15
                    )
                    # Intentar usar token de secrets para cambiar a HTTPS si está configurado
                    try:
                        token = st.secrets.get("GITHUB_TOKEN")
                        if token:
                            url = f"https://{token}@github.com/jesusalbertomoraleslopez-byte/control-corte-doblez.git"
                            subprocess.run(["git", "remote", "set-url", "origin", url], capture_output=True)
                    except Exception:
                        pass

                    # Intentar pull con rebase para evitar errores de sincronización por commits remotos más nuevos
                    subprocess.run(
                        ["git", "pull", "--rebase", "origin", "main"],
                        capture_output=True, timeout=30
                    )
                    
                    res_push = subprocess.run(
                        ["git", "-c", "core.sshCommand=ssh -o StrictHostKeyChecking=no", "push", "origin", "main"],
                        capture_output=True, timeout=30
                    )
                    
                    if res_push.returncode == 0:
                        commit_msg = res_commit.stdout.decode('utf-8', errors='ignore').strip()
                        if "nothing to commit" in res_commit.stdout.decode('utf-8', errors='ignore') or res_commit.returncode != 0:
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

# --- Vistas Principales (imported from views/) ---

from views.mantenimiento import view_mantenimiento

def view_sgc():
    st.title("7. SGC (Sistema de Gestión de Calidad)")
    st.write("Glosario de Documentos y descargas nativas (Word/PDF).")

# --- Lógica Principal ---
def main():
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
        
        if choice == "1. DASHBOARD PRINCIPAL":
            view_dashboard()
        elif choice == "1.2 DASHBOARD GLOBAL":
            view_dashboard_global()
        elif choice == "2. CONSULTAS Y REPORTES":
            view_consultas()
        elif choice == "3. PLANEACIÓN":
            view_planeacion()
        elif choice == "4. CONTROL DE PRODUCCIÓN":
            view_produccion()
        elif choice == "5. MANUFACTURA INTELIGENTE Y MANUAL":
            view_manufactura()
        elif choice == "6. MANTENIMIENTO":
            view_mantenimiento()
        elif choice == "7. SGC (Oculto - Solo Admin)":
            view_sgc()

if __name__ == "__main__":
    main()
 
