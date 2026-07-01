import streamlit as st
import os

def view_manual():
    st.title("📖 5. MANUAL DE OPERACIÓN DEL SISTEMA")
    st.markdown("### Centro de Capacitación y Ayuda Operativa - SIGRAMA")
    st.markdown(
        """
        Este manual de usuario interactivo proporciona las directrices y pasos necesarios para la operación correcta del **Sistema de Control de Producción de Corte y Doblez**.
        A continuación, se describen los perfiles de usuario, el funcionamiento detallado de cada módulo y los procesos críticos en planta.
        """
    )
    
    st.markdown("---")
    
    # ─── 1. ROLES DE USUARIO ───
    st.header("👥 1. Perfiles y Roles de Usuario")
    st.markdown(
        """
        La aplicación está diseñada bajo una arquitectura de roles para separar las responsabilidades administrativas del registro directo en planta.
        
        *   **Perfil Administrador:**
            *   **Responsabilidad:** Control total de la planeación, configuración del sistema y auditoría.
            *   **Permisos Exclusivos:** Importar planes de producción (Excel), vaciar registros de la base de datos para iniciar nuevas OFs, realizar correcciones a registros existentes en planta y subir los logos corporativos.
            *   **Acceso:** Menú completo, incluyendo las secciones de *Mantenimiento* y *SGC*.
            
        *   **Perfil Operador:**
            *   **Responsabilidad:** Registrar en tiempo real el trabajo realizado en cada estación.
            *   **Permisos:** Cargar piezas avanzadas (correctas) y piezas rechazadas (scrap) seleccionando el motivo correspondiente. Ver el estatus de WIP de su área de trabajo.
            *   **Acceso:** Limitado principalmente a la sección de *Producción*.
        """
    )
    
    st.markdown("---")
    
    # ─── 2. DESCRIPCIÓN DE MÓDULOS ───
    st.header("🧭 2. Guía Detallada de Módulos")
    
    tab_dash, tab_reportes, tab_prod = st.tabs([
        "📊 Dashboards (Principal y Global)",
        "📅 Consultas y Reportes",
        "🛠️ Registro de Producción (Planta)"
    ])
    
    with tab_dash:
        st.subheader("Módulo 1: Dashboard Principal y Global")
        st.markdown(
            """
            *   **Indicadores Principales (KPIs):** Al inicio verás tarjetas de resumen con el total de Nidos cargados, Hojas totales, Piezas totales de la orden y el `% de Avance Global`.
            *   **Flujo WIP (Pipeline):** Gráfica de flujo secuencial en Plotly que detalla la cantidad de piezas acumuladas físicamente en cada proceso de producción (desde Ingeniería hasta Empaque).
            *   **Avance por Proceso:** Ruedas gráficas (Gráficos de Dona) interactivas que muestran el avance porcentual de cada estación. Al pasar el mouse por encima de ellas, se activa un efecto de re-escalado dinámico (zoom suave tipo Apple Dock).
            *   **Dashboard Global:** Permite consolidar e integrar múltiples OFs seleccionadas simultáneamente para tener una visión completa de la planta.
            """
        )
        
    with tab_reportes:
        st.subheader("Módulo 2: Consultas y Reportes")
        st.markdown(
            """
            *   **Avance del Día:** Enfocado en la productividad diaria. Presenta tarjetas tipo WIP por cada una de las 8 áreas mostrando el formato `[Avance] / [Rechazos en Rojo]`. Cuenta con calendario para ver días anteriores y detalle de movimientos.
            *   **Avance Semanal:** Gráficas de barras de los últimos 7 días por cada proceso para identificar caídas o picos de producción.
            *   **Trazabilidad General:** Buscador multifiltros que permite buscar cualquier movimiento histórico filtrando por número de OF, Área y tipo de movimiento (Avance/Rechazo).
            *   **Análisis de Calidad (Scrap):** Muestra donas con la distribución de los motivos de rechazo más comunes (ej. pieza rayada, doblez defectuoso) y qué área está generando la mayor merma.
            *   **Exportación:** Cada pestaña incluye un botón **📥 Descargar (CSV)** para procesar y analizar la información en Excel.
            """
        )
        
    with tab_prod:
        st.subheader("Módulo 3: Registro de Producción")
        st.markdown(
            """
            *   **Registro de Avance:** Los operadores ingresan su área, seleccionan la OF activa, el Nido, el número de pieza que están trabajando y capturan las unidades correctas, su nombre y la máquina utilizada.
            *   **Registro de Rechazos:** En caso de haber piezas dañadas, se debe capturar la cantidad en la sección de rechazos y seleccionar el motivo correspondiente del menú desplegable.
            *   **Correcciones:** Permite editar registros que se hayan ingresado incorrectamente por error humano en planta (disponible según permisos).
            """
        )
        
    st.markdown("---")
    
    # ─── 3. PROCESOS CLAVE ───
    st.header("⚙️ 3. Procesos Críticos de Operación")
    
    with st.expander("📥 Flujo Inicial: ¿Cómo cargar una nueva Orden de Fabricación (OF)?"):
        st.markdown(
            """
            Para iniciar una nueva producción:
            1. En la barra lateral, presione el botón **Limpiar Registros / Nueva OF**. *(Nota: Esto vaciará la base de datos activa, asegúrese de haber descargado los reportes previos)*.
            2. Vaya al **Dashboard Principal**. Verá el cargador de archivos de Excel.
            3. Descargue la plantilla de ejemplo si es necesario o suba su archivo de planeación directamente.
            4. El sistema normalizará automáticamente los números de nidos (ej. de 'Nido 1' a 'N01'), mapeará las piezas e inicializará el plan en la base de datos `sigrama.db`.
            """
        )
        
    with st.expander("📉 Gestión de Calidad y Registro de Mermas (Scrap)"):
        st.markdown(
            """
            Para registrar scrap en la planta:
            1. Ingrese a **3. PRODUCCIÓN (AVANCES POR ÁREA)**.
            2. Vaya a la sección de **Rechazos**.
            3. Seleccione la pieza afectada y capture la cantidad defectuosa.
            4. Es obligatorio seleccionar un **Motivo de Rechazo** (ej. "Rebaba", "Fuera de tolerancia", "Golpeada").
            5. Guarde el registro. Esto alimentará automáticamente el panel de calidad en Consultas.
            """
        )

    st.markdown("---")

    # ─── 4. DESCARGA DEL MANUAL EN PDF ───
    st.header("📥 Descarga del Manual del Sistema")
    st.markdown(
        """
        Si deseas tener esta documentación en un formato formal para imprimir, compartir con el personal de planta o guardarlo en tus archivos locales, puedes descargar la versión completa en formato PDF a continuación:
        """
    )
    
    manual_path = os.path.join(os.path.dirname(__file__), "..", "assets", "Manual_Sistema.pdf")
    
    if os.path.exists(manual_path):
        with open(manual_path, "rb") as f:
            pdf_bytes = f.read()
            
        st.download_button(
            label="📥 Descargar Manual del Sistema (PDF)",
            data=pdf_bytes,
            file_name="Manual_Usuario_SIGRAMA.pdf",
            mime="application/pdf",
            type="primary"
        )
    else:
        st.error("⚠️ El archivo PDF del manual no está disponible en este momento. Por favor, contacta al administrador del sistema.")
