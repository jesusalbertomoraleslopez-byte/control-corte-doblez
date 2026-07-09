import streamlit as st
import pandas as pd
import sqlite3
from utils.database import get_connection, clear_avances_rechazos, clear_plans_keep_catalog, clear_db

def get_stats():
    conn = get_connection()
    c = conn.cursor()
    
    c.execute("SELECT count(*) FROM ordenes")
    total_ofs = c.fetchone()[0]
    
    c.execute("SELECT count(*) FROM nidos")
    total_nidos = c.fetchone()[0]
    
    c.execute("SELECT count(*) FROM piezas")
    total_piezas = c.fetchone()[0]
    
    c.execute("SELECT count(*) FROM avances")
    total_avances = c.fetchone()[0]
    
    c.execute("SELECT count(*) FROM rechazos")
    total_rechazos = c.fetchone()[0]
    
    conn.close()
    return {
        "ofs": total_ofs,
        "nidos": total_nidos,
        "piezas": total_piezas,
        "avances": total_avances,
        "rechazos": total_rechazos
    }

def get_catalog():
    conn = get_connection()
    df = pd.read_sql_query(
        "SELECT DISTINCT no_pieza as [No. Pieza], nombre_pieza as [Descripción], ruta as [Procesos/Ruta] FROM piezas WHERE no_pieza IS NOT NULL AND no_pieza != ''",
        conn
    )
    conn.close()
    return df

def convert_df(df):
    return df.to_csv(index=False).encode('utf-8')

def view_mantenimiento():
    st.title("🛠️ 6. MANTENIMIENTO DEL SISTEMA")
    st.markdown("### Panel de Control Administrativo y Limpieza de Datos")
    st.markdown(
        """
        Esta sección permite realizar acciones de limpieza, re-inicialización y respaldo del catálogo de piezas de la planta. 
        **Solo el personal administrador debe tener acceso a este módulo.**
        """
    )
    
    stats = get_stats()
    
    # Mostrar estadísticas actuales de la base de datos
    st.markdown("#### 📊 Estatus de la Base de Datos Actual")
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("OFs Cargadas", stats["ofs"])
    col2.metric("Nidos Totales", stats["nidos"])
    col3.metric("Piezas Catalogadas", stats["piezas"])
    col4.metric("Registros Avance", stats["avances"])
    col5.metric("Registros Rechazo", stats["rechazos"])
    
    st.markdown("---")
    
    st.header("✏️ Modificar Datos de las Órdenes de Fabricación (OF)")
    st.markdown("Selecciona una OF para actualizar su información general:")
    
    # Obtener todas las OFs con su info
    conn = get_connection()
    df_ofs = pd.read_sql_query("SELECT * FROM ordenes ORDER BY of_number ASC", conn)
    conn.close()
    
    if df_ofs.empty:
        st.info("ℹ️ No hay Órdenes de Fabricación en la base de datos para modificar.")
    else:
        of_list = df_ofs["of_number"].tolist()
        selected_of_mod = st.selectbox("Selecciona OF a modificar", of_list, key="of_mod_selector")
        
        # Buscar la fila seleccionada
        of_row = df_ofs[df_ofs["of_number"] == selected_of_mod].iloc[0]
        
        # Crear formulario para edición
        with st.form("edit_of_form"):
            col_m1, col_m2 = st.columns(2)
            with col_m1:
                new_proyecto = st.text_input("Nombre del Proyecto", value=str(of_row.get("proyecto", "") or ""))
                new_fecha = st.text_input("Fecha de Producción", value=str(of_row.get("fecha", "") or ""))
                new_programador = st.text_input("Programador", value=str(of_row.get("programador", "") or ""))
                new_po = st.text_input("PO", value=str(of_row.get("po", "") or ""))
            with col_m2:
                new_prioridad = st.text_input("PRIORIDAD", value=str(of_row.get("prioridad", "") or ""))
                new_calibre = st.text_input("CALIBRE", value=str(of_row.get("calibre", "") or ""))
                new_proyecto_cliente = st.text_input("Nombre del Proyecto de Cliente", value=str(of_row.get("proyecto_cliente", "") or ""))
                new_descripcion_pronest = st.text_input("Descripción de OF Pronest", value=str(of_row.get("descripcion_pronest", "") or ""))
                
            submitted = st.form_submit_button("💾 Guardar Cambios en la OF", type="primary", use_container_width=True)
            if submitted:
                # Actualizar base de datos
                conn = get_connection()
                c = conn.cursor()
                c.execute("""
                    UPDATE ordenes 
                    SET proyecto = ?, programador = ?, fecha = ?, po = ?, prioridad = ?, calibre = ?, proyecto_cliente = ?, descripcion_pronest = ?
                    WHERE of_number = ?
                """, (new_proyecto, new_programador, new_fecha, new_po, new_prioridad, new_calibre, new_proyecto_cliente, new_descripcion_pronest, selected_of_mod))
                conn.commit()
                conn.close()
                
                # Si la OF que modificamos es la activa en sesión, actualizar el session_state también!
                if st.session_state.get("of_number") == selected_of_mod:
                    if st.session_state.get("production_data") is not None:
                        st.session_state.production_data["proyecto"] = new_proyecto
                        st.session_state.production_data["programador"] = new_programador
                        st.session_state.production_data["fecha"] = new_fecha
                        st.session_state.production_data["po"] = new_po
                        st.session_state.production_data["prioridad"] = new_prioridad
                        st.session_state.production_data["calibre"] = new_calibre
                        st.session_state.production_data["proyecto_cliente"] = new_proyecto_cliente
                        st.session_state.production_data["descripcion_pronest"] = new_descripcion_pronest
                
                st.success(f"✅ ¡Datos de la orden {selected_of_mod} actualizados correctamente!")
                st.rerun()

    st.markdown("---")
    
    col_reset, col_plans, col_delete = st.columns(3)
    
    # --- RESETEAR REGISTROS ---
    with col_reset:
        st.subheader("🔄 Resetear Avances y Rechazos")
        st.info(
            """
            **¿Qué hace esta opción?**
            - Borra todos los avances reportados por los operadores.
            - Borra todos los rechazos (scrap) reportados.
            - **Mantiene intactos** la OF activa, los nidos y las piezas actuales.
            
            *Ideal para reiniciar mediciones sobre la misma orden cargada.*
            """
        )
        
        # Confirmación de seguridad
        confirm_reset = st.checkbox("Confirmar resetear avances/rechazos", key="confirm_reset_chk")
        
        if st.button("🗑️ Resetear Avances/Rechazos", type="primary", disabled=not confirm_reset, use_container_width=True):
            try:
                clear_avances_rechazos()
                st.success("✅ ¡Avances y rechazos eliminados con éxito!")
                st.rerun()
            except Exception as e:
                st.error(f"Error al resetear registros: {e}")
                
    # --- LIMPIAR PLANES MANTENIENDO CATALOGO ---
    with col_plans:
        st.subheader("📋 Limpiar Planes (Mantener Catálogo)")
        st.info(
            """
            **¿Qué hace esta opción?**
            - Borra avances, rechazos, nidos y las órdenes de fabricación (OFs).
            - **Conserva el catálogo de piezas** con las rutas y procesos que ya configuraste.
            
            *Ideal para limpiar el plan de trabajo actual pero sin perder el historial de rutas de las piezas.*
            """
        )
        
        # Confirmación de seguridad
        confirm_plans = st.checkbox("Confirmar limpiar planes de trabajo", key="confirm_plans_chk")
        
        if st.button("🗑️ Limpiar Planes (Mantener Piezas)", type="primary", disabled=not confirm_plans, use_container_width=True):
            try:
                clear_plans_keep_catalog()
                
                # Limpiar variables de sesión relacionadas
                keys_to_clear = ['production_data', 'of_number', 'wip_data',
                                 'input_proyecto', 'input_programador', 'uploaded_excel']
                for k in keys_to_clear:
                    if k in st.session_state:
                        del st.session_state[k]
                        
                st.success("✅ Planes de trabajo, nidos y registros eliminados. El catálogo de piezas se conservó.")
                st.rerun()
            except Exception as e:
                st.error(f"Error al limpiar planes: {e}")
                
    # --- ELIMINAR TODO ---
    with col_delete:
        st.subheader("🚨 Eliminar Todo (Base en Blanco)")
        st.warning(
            """
            **¿Qué hace esta opción?**
            - Borra por completo toda la base de datos (`sigrama.db`).
            - Elimina órdenes de fabricación, nidos, catálogo de piezas e historiales.
            - Restablece el sistema a un estado inicial limpio.
            
            *Úselo únicamente si desea limpiar el sistema por completo desde cero.*
            """
        )
        
        # Confirmación de seguridad
        confirm_all = st.checkbox("Confirmar borrar TODO el sistema", key="confirm_all_chk")
        
        if st.button("🚨 Borrar Todo el Sistema", type="primary", disabled=not confirm_all, use_container_width=True):
            try:
                clear_db()
                
                # Limpiar variables de sesión relacionadas
                keys_to_clear = ['production_data', 'of_number', 'wip_data',
                                 'input_proyecto', 'input_programador', 'uploaded_excel']
                for k in keys_to_clear:
                    if k in st.session_state:
                        del st.session_state[k]
                        
                st.success("🚨 ¡Toda la base de datos ha sido borrada! El sistema ha vuelto a su estado inicial.")
                st.rerun()
            except Exception as e:
                st.error(f"Error al vaciar la base de datos: {e}")

    st.markdown("---")
    
    # --- RESPALDO DEL CATALOGO ---
    st.header("📥 Respaldar Catálogo de Piezas y Rutas")
    st.markdown(
        """
        Descarga el catálogo maestro de piezas que se encuentra guardado en la base de datos.
        Este archivo contiene los códigos de las piezas, sus descripciones y los procesos/rutas que han sido configurados históricamente.
        """
    )
    
    df_cat = get_catalog()
    
    if df_cat.empty:
        st.info("ℹ️ No hay piezas catalogadas en el sistema para respaldar.")
    else:
        col_stat, col_dl = st.columns([1, 3])
        with col_stat:
            st.metric("Total de Piezas Únicas", len(df_cat))
            
        with col_dl:
            csv_cat = convert_df(df_cat)
            st.download_button(
                label="📥 Descargar Catálogo de Piezas y Rutas (CSV)",
                data=csv_cat,
                file_name="Catalogo_Piezas_SIGRAMA.csv",
                mime="text/csv",
                type="secondary",
                use_container_width=True
            )
            
        with st.expander("🔍 Vista Previa del Catálogo a Respaldar"):
            st.dataframe(df_cat, use_container_width=True, height=250)
