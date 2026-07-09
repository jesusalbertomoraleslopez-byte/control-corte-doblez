import streamlit as st
import pandas as pd
import sqlite3
from utils.database import get_connection, clear_avances_rechazos, clear_plans_keep_catalog, clear_db, get_personal_prenomina

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
        # Renombrar columnas para mostrar nombres bonitos y profesionales
        rename_map = {
            "of_number": "OF",
            "proyecto": "Proyecto",
            "fecha": "Fecha de Producción",
            "programador": "Programador",
            "po": "PO",
            "prioridad": "Prioridad",
            "calibre": "Calibre",
            "proyecto_cliente": "Proyecto Cliente",
            "descripcion_pronest": "Descripción Pronest"
        }
        df_display = df_ofs.rename(columns=rename_map)
        
        # Configuración de columnas
        col_configs = {
            "OF": st.column_config.TextColumn("Orden de Fabricación (OF)", disabled=True),
            "Proyecto": st.column_config.TextColumn("Proyecto", disabled=False),
            "Fecha de Producción": st.column_config.TextColumn("Fecha de Producción", disabled=False),
            "Programador": st.column_config.TextColumn("Programador", disabled=False),
            "PO": st.column_config.TextColumn("PO", disabled=False),
            "Prioridad": st.column_config.TextColumn("Prioridad", disabled=False),
            "Calibre": st.column_config.TextColumn("Calibre", disabled=False),
            "Proyecto Cliente": st.column_config.TextColumn("Proyecto Cliente", disabled=False),
            "Descripción Pronest": st.column_config.TextColumn("Descripción Pronest", disabled=False),
        }
        
        edited_df = st.data_editor(
            df_display,
            column_config=col_configs,
            use_container_width=True,
            hide_index=True,
            key="editor_ordenes_mantenimiento"
        )
        
        if st.button("💾 Guardar Cambios en las OFs", type="primary", use_container_width=True):
            conn = get_connection()
            c = conn.cursor()
            try:
                for _, row in edited_df.iterrows():
                    c.execute("""
                        UPDATE ordenes 
                        SET proyecto = ?, programador = ?, fecha = ?, po = ?, prioridad = ?, calibre = ?, proyecto_cliente = ?, descripcion_pronest = ?
                        WHERE of_number = ?
                    """, (
                        row["Proyecto"], 
                        row["Programador"], 
                        row["Fecha de Producción"], 
                        row["PO"], 
                        row["Prioridad"], 
                        row["Calibre"], 
                        row["Proyecto Cliente"], 
                        row["Descripción Pronest"],
                        row["OF"]
                    ))
                conn.commit()
                
                # Si la OF activa en sesión fue modificada, actualizar el session_state
                active_of = st.session_state.get("of_number")
                if active_of:
                    row_active = edited_df[edited_df["OF"] == active_of]
                    if not row_active.empty and st.session_state.get("production_data") is not None:
                        r = row_active.iloc[0]
                        st.session_state.production_data["proyecto"] = r["Proyecto"]
                        st.session_state.production_data["programador"] = r["Programador"]
                        st.session_state.production_data["fecha"] = r["Fecha de Producción"]
                        st.session_state.production_data["po"] = r["PO"]
                        st.session_state.production_data["prioridad"] = r["Prioridad"]
                        st.session_state.production_data["calibre"] = r["Calibre"]
                        st.session_state.production_data["proyecto_cliente"] = r["Proyecto Cliente"]
                        st.session_state.production_data["descripcion_pronest"] = r["Descripción Pronest"]
                        
                st.success("✅ ¡Datos de todas las Órdenes de Fabricación actualizados con éxito!")
                st.rerun()
            except Exception as e:
                st.error(f"Error al guardar cambios: {e}")
            finally:
                conn.close()

    st.markdown("---")
    st.header("🗑️ Eliminar una Orden de Fabricación (OF) Específica")
    st.markdown(
        """
        Si necesitas dar de baja una OF para volverla a cargar debido a cambios en cantidades, piezas o nidos, puedes eliminarla por completo aquí.
        **Esta acción borrará definitivamente la orden, sus nidos, catálogo de piezas, avances y scrap.**
        """
    )
    
    # Obtener todas las OFs
    conn = get_connection()
    df_ofs_del = pd.read_sql_query("SELECT of_number FROM ordenes ORDER BY of_number ASC", conn)
    conn.close()
    
    if df_ofs_del.empty:
        st.info("ℹ️ No hay Órdenes de Fabricación cargadas en el sistema.")
    else:
        col_del_of, col_del_btn = st.columns([2, 1])
        with col_del_of:
            of_to_delete = st.selectbox("Selecciona la OF a eliminar por completo:", df_ofs_del["of_number"].tolist(), key="selectbox_delete_of")
            confirm_del_of = st.checkbox(f"Confirmar que deseo eliminar de forma definitiva la **{of_to_delete}**", key="confirm_delete_of_chk")
        
        with col_del_btn:
            st.write("") # Espacio para alinear verticalmente
            st.write("")
            if st.button("🗑️ Eliminar OF Seleccionada", type="primary", disabled=not confirm_del_of, use_container_width=True):
                conn = get_connection()
                c = conn.cursor()
                try:
                    c.execute("DELETE FROM ordenes WHERE of_number = ?", (of_to_delete,))
                    c.execute("DELETE FROM nidos WHERE of_number = ?", (of_to_delete,))
                    c.execute("DELETE FROM piezas WHERE of_number = ?", (of_to_delete,))
                    c.execute("DELETE FROM avances WHERE of_number = ?", (of_to_delete,))
                    c.execute("DELETE FROM rechazos WHERE of_number = ?", (of_to_delete,))
                    conn.commit()
                    
                    # Si era la OF activa en sesión, limpiar de sesión
                    if st.session_state.get("of_number") == of_to_delete:
                        keys_to_clear = ['production_data', 'of_number', 'wip_data']
                        for k in keys_to_clear:
                            if k in st.session_state:
                                del st.session_state[k]
                                
                    st.success(f"✅ ¡La orden {of_to_delete} y todos sus registros asociados han sido eliminados con éxito!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error al eliminar la orden: {e}")
                finally:
                    conn.close()
                    
    st.markdown("---")
    st.header("📅 Redistribuir Fechas de Avances (Simulación Histórica)")
    st.markdown(
        """
        Si cargaste datos históricos pero todos los avances quedaron registrados con la fecha de hoy, puedes redistribuir 
        los avances y rechazos de forma uniforme a lo largo de un rango de fechas de producción.
        Esto corregirá los gráficos de tendencia de producción diaria.
        """
    )
    
    # Obtener todas las OFs
    conn = get_connection()
    df_ofs_dist = pd.read_sql_query("SELECT of_number FROM ordenes ORDER BY of_number ASC", conn)
    conn.close()
    
    if df_ofs_dist.empty:
        st.info("ℹ️ No hay Órdenes de Fabricación cargadas en el sistema.")
    else:
        col_dist_of, col_dist_dates = st.columns([1, 2])
        with col_dist_of:
            of_to_dist = st.selectbox("Selecciona OF a redistribuir:", ["Todas"] + df_ofs_dist["of_number"].tolist(), key="selectbox_dist_of")
            
        with col_dist_dates:
            default_dates = ["2026-06-30", "2026-07-01", "2026-07-02", "2026-07-03", "2026-07-06", "2026-07-07", "2026-07-08"]
            selected_dates = st.multiselect(
                "Selecciona las fechas de producción para distribuir:",
                default_dates,
                default=default_dates,
                key="multiselect_dist_dates"
            )
            
        if not selected_dates:
            st.warning("⚠️ Debes seleccionar al menos una fecha para la distribución.")
        else:
            if st.button("📅 Redistribuir Fechas de Producción", type="primary", use_container_width=True):
                conn = get_connection()
                c = conn.cursor()
                try:
                    # Determinar condición de filtrado
                    query_av = "SELECT id, timestamp FROM avances"
                    query_rec = "SELECT id, timestamp FROM rechazos"
                    params = []
                    if of_to_dist != "Todas":
                        query_av += " WHERE of_number = ?"
                        query_rec += " WHERE of_number = ?"
                        params = [of_to_dist]
                        
                    c.execute(query_av, params)
                    av_rows = c.fetchall()
                    
                    num_dates = len(selected_dates)
                    
                    # Actualizar avances
                    for idx, (av_id, old_ts) in enumerate(av_rows):
                        date_str = selected_dates[idx % num_dates]
                        try:
                            old_time = old_ts.split(" ")[1] if " " in old_ts else "12:00:00"
                        except Exception:
                            old_time = "12:00:00"
                        new_ts = f"{date_str} {old_time}"
                        c.execute("UPDATE avances SET timestamp = ? WHERE id = ?", (new_ts, av_id))
                        
                    # Actualizar rechazos
                    c.execute(query_rec, params)
                    rec_rows = c.fetchall()
                    for idx, (rec_id, old_ts) in enumerate(rec_rows):
                        date_str = selected_dates[idx % num_dates]
                        try:
                            old_time = old_ts.split(" ")[1] if " " in old_ts else "12:00:00"
                        except Exception:
                            old_time = "12:00:00"
                        new_ts = f"{date_str} {old_time}"
                        c.execute("UPDATE rechazos SET timestamp = ? WHERE id = ?", (new_ts, rec_id))
                        
                    conn.commit()
                    st.success(f"✅ ¡Fechas redistribuidas con éxito para {len(av_rows)} avances y {len(rec_rows)} rechazos!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error al redistribuir fechas: {e}")
                finally:
                    conn.close()
                    
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

    st.header("👥 Áreas Autorizadas por Colaborador")
    st.markdown(
        """
        Configura qué áreas de producción está autorizado a trabajar cada colaborador de la prenómina.
        Esto filtrará dinámicamente la lista de operadores disponibles al momento de registrar un avance de producción.
        """
    )
    
    # Cargar todos los colaboradores de prenomina
    df_pers = get_personal_prenomina()
    if df_pers.empty:
        st.warning("⚠️ No se pudo cargar el catálogo de personal de Prenómina.")
    else:
        # Limpieza de datos
        df_pers['nombre'] = df_pers['nombre'].astype(str).str.strip().str.upper()
        df_pers['area'] = df_pers['area'].astype(str).str.strip()
        
        # Eliminar duplicados o registros nulos
        df_pers = df_pers[df_pers['nombre'].notna() & (df_pers['nombre'] != 'NAN') & (df_pers['nombre'] != '')].drop_duplicates(subset=['nombre'])
        
        # Cargar asignaciones actuales en DB
        conn_pers = get_connection()
        try:
            df_saved = pd.read_sql_query("SELECT * FROM personal_areas", conn_pers)
        except Exception:
            # Si no existe la tabla aún, crearla
            c_temp = conn_pers.cursor()
            c_temp.execute("CREATE TABLE IF NOT EXISTS personal_areas (operador_nombre TEXT NOT NULL, area TEXT NOT NULL, PRIMARY KEY (operador_nombre, area))")
            conn_pers.commit()
            df_saved = pd.DataFrame(columns=["operador_nombre", "area"])
        conn_pers.close()
        
        # Construir matriz de checkboxes
        matrix_rows = []
        app_areas = ["Corte", "Rebabeo", "Doblez", "Barrenado", "Pintura", "Liberado", "Empaque", "Ingenieria"]
        
        for _, r_pers in df_pers.iterrows():
            nom = r_pers['nombre']
            dpto = r_pers['area']
            
            row_dict = {
                "Colaborador": nom,
                "Departamento": dpto
            }
            
            for a_name in app_areas:
                # Verificar si ya existe esta asignación en la base de datos
                is_assigned = not df_saved[(df_saved['operador_nombre'] == nom) & (df_saved['area'] == a_name)].empty
                row_dict[a_name] = is_assigned
                
            matrix_rows.append(row_dict)
            
        df_matrix = pd.DataFrame(matrix_rows)
        
        # Definir configuracion de columnas del data_editor
        col_configs = {
            "Colaborador": st.column_config.TextColumn("Colaborador", disabled=True),
            "Departamento": st.column_config.TextColumn("Dpto. Prenómina", disabled=True),
        }
        for a_name in app_areas:
            col_configs[a_name] = st.column_config.CheckboxColumn(a_name, default=False)
            
        edited_matrix = st.data_editor(
            df_matrix,
            column_config=col_configs,
            use_container_width=True,
            hide_index=True,
            key="editor_matriz_personal"
        )
        
        # Botón para guardar permisos
        if st.button("💾 Guardar Autorizaciones de Personal", type="primary", use_container_width=True):
            conn_save = get_connection()
            c_save = conn_save.cursor()
            try:
                c_save.execute("DELETE FROM personal_areas")
                for _, r_mat in edited_matrix.iterrows():
                    op_name = r_mat['Colaborador']
                    for a_name in app_areas:
                        if r_mat[a_name]:
                            c_save.execute(
                                "INSERT INTO personal_areas (operador_nombre, area) VALUES (?, ?)",
                                (op_name, a_name)
                            )
                conn_save.commit()
                st.success("✅ ¡Permisos y autorizaciones de personal guardados con éxito!")
                st.rerun()
            except Exception as err:
                st.error(f"Error al guardar permisos: {err}")
            finally:
                conn_save.close()
                
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

    st.markdown("---")
    st.header("💾 Respaldo y Restauración de la Base de Datos")
    st.markdown(
        """
        Dado que el servidor en la nube es temporal (stateless), si el servidor se reinicia, los datos nuevos podrían perderse. 
        Utiliza esta sección para descargar un respaldo completo de tu base de datos activa o restaurar la información desde un archivo guardado.
        """
    )
    
    col_db_dl, col_db_ul = st.columns(2)
    
    with col_db_dl:
        st.subheader("📥 Descargar Respaldo")
        st.markdown("Guarda una copia completa de toda la información actual (OFs, piezas, avances, scrap y permisos):")
        try:
            with open("sigrama.db", "rb") as f:
                db_bytes = f.read()
            st.download_button(
                label="📥 Descargar sigrama.db",
                data=db_bytes,
                file_name="sigrama.db",
                mime="application/octet-stream",
                use_container_width=True,
                type="primary"
            )
        except Exception as e:
            st.error(f"No se pudo leer el archivo de base de datos: {e}")
            
    with col_db_ul:
        st.subheader("📤 Restaurar Base de Datos")
        st.markdown("Sube tu archivo de respaldo `sigrama.db` para recuperar al 100% todos tus registros en caso de reinicio:")
        uploaded_db = st.file_uploader("Sube el archivo de respaldo (.db):", type=["db"], key="uploader_restore_db")
        if uploaded_db is not None:
            if st.button("🚨 Sobrescribir Base de Datos Activa", type="primary", use_container_width=True):
                try:
                    with open("sigrama.db", "wb") as f:
                        f.write(uploaded_db.getbuffer())
                    st.success("✅ ¡Base de datos restaurada con éxito! La aplicación se actualizará.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error al restaurar base de datos: {e}")
