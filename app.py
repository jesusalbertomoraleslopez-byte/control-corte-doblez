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
        "3. PRODUCCIÓN (AVANCES POR ÁREA)",
        "4. MANUFACTURA INTELIGENTE",
        "5. MANUAL DEL SISTEMA"
    ]
    
    if st.session_state.role == "Administrador":
        menu.extend([
            "6. MANTENIMIENTO",
            "7. SGC (Oculto - Solo Admin)"
        ])
        
    choice = st.sidebar.radio("Navegación", menu)
    
    st.sidebar.markdown("---")
    st.sidebar.markdown("**🗑️ Acciones Rápidas**")
    if st.sidebar.button("🗑️ Limpiar Registros / Nueva OF", use_container_width=True):
        keys_to_clear = ['production_data', 'of_number', 'wip_data',
                         'input_proyecto', 'input_programador', 'uploaded_excel']
        for k in keys_to_clear:
            if k in st.session_state:
                del st.session_state[k]
        st.rerun()
    
    st.sidebar.markdown("---")
    if st.sidebar.button("Cerrar Sesión"):
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

from views.produccion import view_produccion
from views.consultas import view_consultas
from views.dashboard import view_dashboard
from views.dashboard_global import view_dashboard_global
from views.manufactura import view_manufactura
from views.manual import view_manual

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
        
        # Opcion para subir imagenes y recursos en el sidebar
        with st.sidebar.expander("🖼️ Personalizar Recursos"):
            uploaded_logo = st.file_uploader("Logo (Superior Izquierda)", type=['png', 'jpg', 'jpeg'], key='logo_up')
            if uploaded_logo is not None:
                os.makedirs(os.path.dirname(banner_path), exist_ok=True)
                with open(os.path.join(os.path.dirname(__file__), "assets", "logo.png"), "wb") as f:
                    f.write(uploaded_logo.getbuffer())
                st.success("Logo actualizado!")
                st.rerun()
 
            uploaded_banner = st.file_uploader("Banner (Principal)", type=['png', 'jpg', 'jpeg'], key='banner_up')
            if uploaded_banner is not None:
                os.makedirs(os.path.dirname(banner_path), exist_ok=True)
                with open(banner_path, "wb") as f:
                    f.write(uploaded_banner.getbuffer())
                st.success("Banner actualizado!")
                st.rerun()
                
            uploaded_slogan = st.file_uploader("Slogan (Inferior Izquierda)", type=['png', 'jpg', 'jpeg'], key='slogan_up')
            if uploaded_slogan is not None:
                os.makedirs(os.path.dirname(banner_path), exist_ok=True)
                with open(os.path.join(os.path.dirname(__file__), "assets", "slogan.png"), "wb") as f:
                    f.write(uploaded_slogan.getbuffer())
                st.success("Slogan actualizado!")
                st.rerun()

            uploaded_manual = st.file_uploader("Manual de Usuario (PDF)", type=['pdf'], key='manual_up')
            if uploaded_manual is not None:
                os.makedirs(os.path.dirname(banner_path), exist_ok=True)
                with open(os.path.join(os.path.dirname(__file__), "assets", "Manual_Sistema.pdf"), "wb") as f:
                    f.write(uploaded_manual.getbuffer())
                st.success("Manual de usuario actualizado!")
                st.rerun()
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
        elif choice == "3. PRODUCCIÓN (AVANCES POR ÁREA)":
            view_produccion()
        elif choice == "4. MANUFACTURA INTELIGENTE":
            view_manufactura()
        elif choice == "5. MANUAL DEL SISTEMA":
            view_manual()
        elif choice == "6. MANTENIMIENTO":
            view_mantenimiento()
        elif choice == "7. SGC (Oculto - Solo Admin)":
            view_sgc()

if __name__ == "__main__":
    main()
 
