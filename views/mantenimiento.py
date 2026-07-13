import streamlit as st
import pandas as pd
import sqlite3
import subprocess
from utils.database import get_connection, clear_avances_rechazos, clear_plans_keep_catalog, clear_db, get_personal_prenomina
from views.correcciones import view_correcciones

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

def view_mantenimiento_admin():
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
                    from utils.database import git_sync_db
                    git_sync_db()
                    
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
                    
        # --- RESETEAR AVANCES DE OF ESPECIFICA ---
        st.markdown("---")
        st.header("🔄 Resetear Avances y Rechazos de una OF")
        st.markdown("Si necesitas reiniciar los contadores de producción de una OF, puedes borrar todos sus avances y rechazos aquí. **Esto conservará el plan de producción (nidos y piezas)**.")
        
        col_res_of, col_res_btn = st.columns([2, 1])
        with col_res_of:
            of_to_reset = st.selectbox("Selecciona la OF a resetear:", df_ofs_del["of_number"].tolist(), key="selectbox_reset_of")
            confirm_res_of = st.checkbox(f"Confirmar que deseo resetear avances/rechazos de la **{of_to_reset}**", key="confirm_reset_of_chk")
            
        with col_res_btn:
            st.write("")
            st.write("")
            if st.button("🔄 Resetear Avances de la OF", type="primary", disabled=not confirm_res_of, use_container_width=True):
                conn = get_connection()
                c = conn.cursor()
                try:
                    c.execute("DELETE FROM avances WHERE of_number = ?", (of_to_reset,))
                    c.execute("DELETE FROM rechazos WHERE of_number = ?", (of_to_reset,))
                    conn.commit()
                    from utils.database import git_sync_db
                    git_sync_db()
                    st.success(f"✅ ¡Se han borrado los avances y rechazos de la orden {of_to_reset} con éxito! El plan de producción se conservó.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error al resetear avances de la orden: {e}")
                finally:
                    conn.close()

        # --- REINICIO Y LIMPIEZA COMPLETA DEL SISTEMA ---
        st.markdown("---")
        st.header("🧹 Reinicio y Limpieza Completa del Sistema")
        st.markdown("Si deseas reiniciar la aplicación desde cero para iniciar una nueva temporada o recargar múltiples órdenes:")
        
        col_clean1, col_clean2 = st.columns(2)
        
        with col_clean1:
            st.subheader("📋 Limpiar Planes (Mantener Catálogo)")
            st.write("Borra todas las OFs, nidos, avances y rechazos, pero **conserva las rutas y procesos** configurados en el catálogo de piezas.")
            confirm_keep_cat = st.checkbox("Confirmar: deseo limpiar planes pero conservar el catálogo de piezas", key="chk_keep_cat")
            if st.button("🗑️ Limpiar Planes (Mantener Catálogo)", type="secondary", disabled=not confirm_keep_cat, use_container_width=True):
                try:
                    clear_plans_keep_catalog()
                    keys_to_clear = ['production_data', 'of_number', 'wip_data',
                                     'input_proyecto', 'input_programador', 'uploaded_excel']
                    for k in keys_to_clear:
                        if k in st.session_state:
                            del st.session_state[k]
                    from utils.database import git_sync_db
                    git_sync_db()
                    st.success("✅ ¡Planes de producción y avances eliminados! El catálogo de rutas se conservó.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")
                    
        with col_clean2:
            st.subheader("🚨 Vaciar Base de Datos (Limpiar Todo)")
            st.write("Borra **completamente** la base de datos: elimina todas las OFs, nidos, piezas, avances, rechazos e historial.")
            confirm_clear_all = st.checkbox("Confirmar: deseo borrar TODO y reiniciar la app vacía", key="chk_clear_all_db")
            if st.button("🚨 Borrar Todo el Sistema", type="primary", disabled=not confirm_clear_all, use_container_width=True):
                try:
                    clear_db()
                    keys_to_clear = ['production_data', 'of_number', 'wip_data',
                                     'input_proyecto', 'input_programador', 'uploaded_excel']
                    for k in keys_to_clear:
                        if k in st.session_state:
                            del st.session_state[k]
                    from utils.database import git_sync_db
                    git_sync_db()
                    st.success("🚨 ¡Base de datos vaciada por completo! El sistema está limpio.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")

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
                    from utils.database import git_sync_db
                    git_sync_db()
                    st.success(f"✅ ¡Fechas redistribuidas con éxito para {len(av_rows)} avances y {len(rec_rows)} rechazos!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error al redistribuir fechas: {e}")
                finally:
                    conn.close()
                    



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
        app_areas = ["Corte", "Rebabeo", "Doblez", "Barrenado", "Liberado", "Empaque", "Ingenieria"]
        
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
                from utils.database import git_sync_db
                git_sync_db()
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
    st.header("🔧 Cierre Masivo de Nidos — Corte")
    st.markdown(
        """
        Esta sección permite **cerrar masivamente los nidos** que ya fueron cortados físicamente pero que 
        aparecen como pendientes porque la nueva lógica (hojas completas) detectó que no todas las hojas 
        fueron registradas hoja por hoja. También verifica que el WIP coincida con lo planeado.
        """
    )

    from utils.database import git_sync_db
    import datetime as _dt

    conn_mant = get_connection()

    # Obtener nidos incompletos
    df_nidos_incompletos = pd.read_sql_query("""
        SELECT n.of_number, n.nido, n.hojas as hojas_req,
               COUNT(DISTINCT a.hoja) as hojas_cortadas,
               n.hojas - COUNT(DISTINCT a.hoja) as hojas_faltantes
        FROM nidos n
        LEFT JOIN avances a ON n.of_number=a.of_number AND n.nido=a.nido AND a.area='Corte'
        GROUP BY n.of_number, n.nido, n.hojas
        HAVING hojas_cortadas < n.hojas
        ORDER BY n.of_number, n.nido
    """, conn_mant)

    # Obtener resumen de piezas: planeadas vs registradas en avances Corte
    # IMPORTANTE: usar subqueries separadas para evitar producto cartesiano al unir piezas+nidos con avances
    df_verif = pd.read_sql_query("""
        SELECT 
            plan.of_number,
            plan.no_pieza,
            plan.nombre_pieza,
            plan.planeadas,
            COALESCE(reg.registradas, 0) as registradas,
            plan.planeadas - COALESCE(reg.registradas, 0) as diferencia
        FROM (
            SELECT p.of_number, p.no_pieza, MAX(p.nombre_pieza) as nombre_pieza,
                   SUM(p.cantidad * n.hojas) as planeadas
            FROM piezas p
            JOIN nidos n ON p.of_number=n.of_number AND p.nido=n.nido
            GROUP BY p.of_number, p.no_pieza
        ) plan
        LEFT JOIN (
            SELECT of_number, no_pieza, SUM(cantidad) as registradas
            FROM avances
            WHERE area='Corte'
            GROUP BY of_number, no_pieza
        ) reg ON plan.of_number=reg.of_number AND plan.no_pieza=reg.no_pieza
        ORDER BY plan.of_number, plan.no_pieza
    """, conn_mant)
    conn_mant.close()

    # --- Tabla de verificación planeado vs real ---
    st.markdown("#### 📊 Verificación: Piezas Planeadas vs. Registradas en Corte")
    if df_verif.empty:
        st.info("No hay datos de piezas cargadas.")
    else:
        # Contar reposiciones por separado (nido=REPOSICION)
        conn_rep = get_connection()
        df_repos = pd.read_sql_query("""
            SELECT of_number, no_pieza, SUM(cantidad) as reposiciones
            FROM avances WHERE area='Corte' AND nido='REPOSICION'
            GROUP BY of_number, no_pieza
        """, conn_rep)
        conn_rep.close()

        total_plan = int(df_verif['planeadas'].sum())
        total_reg  = int(df_verif['registradas'].sum())
        total_repos = int(df_repos['reposiciones'].sum()) if not df_repos.empty else 0
        total_reg_sin_repos = total_reg - total_repos
        total_diff = total_plan - total_reg_sin_repos

        col_v1, col_v2, col_v3, col_v4 = st.columns(4)
        col_v1.metric("📦 Total Planeado", f"{total_plan:,} pzs")
        col_v2.metric("✅ Registrado (nidos)", f"{total_reg_sin_repos:,} pzs")
        col_v3.metric("🔁 Reposiciones Corte", f"{total_repos:,} pzs",
                      help="Piezas registradas como re-corte por scrap (nido=REPOSICION). Son adicionales al plan y no afectan el conteo.")
        if total_diff == 0:
            col_v4.metric("🎯 Diferencia", "0 pzs ✅")
        elif total_diff > 0:
            col_v4.metric("⚠️ Diferencia (Faltantes)", f"{total_diff:,} pzs")
        else:
            col_v4.metric("❗ Diferencia (Exceso)", f"{total_diff:,} pzs",
                          help="Hay más piezas registradas que planeadas. Puede deberse a registros duplicados en algún nido.")

        if total_diff < 0:
            st.warning(
                f"❗ **Atención:** Se registraron **{abs(total_diff)} piezas extra** más de las planeadas en Corte. "
                f"Esto generalmente se debe a **registros duplicados** (misma hoja registrada más de una vez). "
                f"Revisa el detalle por pieza para identificar el nido con exceso y corrígelo en la sección **5. Correcciones**."
            )

        with st.expander("🔍 Ver detalle por No. Pieza"):
            df_show = df_verif.copy()
            df_show.columns = ['OF', 'No. Pieza', 'Descripción', 'Planeadas', 'Registradas', 'Diferencia']
            def _estado(x):
                if x == 0: return '✅ OK'
                if x > 0:  return f'⚠️ Faltan {int(x)}'
                return f'❗ Exceso {abs(int(x))} (posible duplicado)'
            df_show['Estado'] = df_show['Diferencia'].apply(_estado)
            st.dataframe(df_show, use_container_width=True, hide_index=True, height=300)

    st.markdown("---")

    # --- Cierre masivo ---
    st.markdown("#### 🔒 Nidos con Hojas Incompletas (Físicamente Ya Cortados)")
    if df_nidos_incompletos.empty:
        st.success("✅ ¡Todos los nidos tienen sus hojas completas registradas! No hay pendientes.")
    else:
        st.warning(f"⚠️ Se detectaron **{len(df_nidos_incompletos)}** nidos con hojas faltantes en el sistema.")

        df_show_inc = df_nidos_incompletos.copy()
        df_show_inc.columns = ['OF', 'Nido', 'Hojas Req', 'Hojas Cortadas', 'Faltantes']
        df_show_inc['Seleccionar'] = True
        edited_inc = st.data_editor(
            df_show_inc,
            use_container_width=True,
            hide_index=True,
            column_config={
                "OF": st.column_config.TextColumn("OF", disabled=True),
                "Nido": st.column_config.TextColumn("Nido", disabled=True),
                "Hojas Req": st.column_config.NumberColumn("Hojas Req", disabled=True),
                "Hojas Cortadas": st.column_config.NumberColumn("Ya Registradas", disabled=True),
                "Faltantes": st.column_config.NumberColumn("Hojas Faltantes", disabled=True),
                "Seleccionar": st.column_config.CheckboxColumn("¿Cerrar?", help="Marca para completar las hojas faltantes de este nido")
            },
            key="editor_cierre_masivo"
        )

        nidos_a_cerrar = edited_inc[edited_inc['Seleccionar'] == True]
        total_hojas_a_reg = int(nidos_a_cerrar['Faltantes'].sum())

        if not nidos_a_cerrar.empty:
            st.info(f"👉 Se registrarán **{total_hojas_a_reg} hojas** para cerrar **{len(nidos_a_cerrar)} nidos** seleccionados.")

            col_op, col_maq = st.columns(2)
            with col_op:
                operador_cierre = st.text_input("Operador (para el registro)", value="ADMINISTRADOR", key="cierre_operador")
            with col_maq:
                maquina_cierre = st.text_input("Máquina", value="Láser 1", key="cierre_maquina")

            if st.button("🔒 Completar Hojas Faltantes de los Nidos Seleccionados", type="primary", use_container_width=True):
                conn_cierre = get_connection()
                c_cierre = conn_cierre.cursor()
                now_cierre = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                total_insertados = 0

                for _, row_nido in nidos_a_cerrar.iterrows():
                    of_n = row_nido['OF']
                    nido_n = row_nido['Nido']
                    hojas_ya = int(row_nido['Hojas Cortadas'])
                    hojas_req = int(row_nido['Hojas Req'])

                    # Obtener piezas del nido
                    c_cierre.execute(
                        "SELECT no_pieza, cantidad FROM piezas WHERE of_number=? AND nido=?",
                        (of_n, nido_n)
                    )
                    piezas_nido = c_cierre.fetchall()

                    # Registrar las hojas faltantes
                    for h in range(hojas_ya + 1, hojas_req + 1):
                        for no_pieza, cant in piezas_nido:
                            c_cierre.execute(
                                "INSERT INTO avances (of_number, nido, no_pieza, area, cantidad, operador, maquina, hoja, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                (of_n, nido_n, no_pieza, "Corte", int(cant), operador_cierre, maquina_cierre, h, now_cierre)
                            )
                            total_insertados += 1

                conn_cierre.commit()
                conn_cierre.close()
                git_sync_db()
                st.success(f"🎉 ¡Cierre completado! Se registraron {total_insertados} entradas para cerrar {len(nidos_a_cerrar)} nidos.")
                st.rerun()

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
            from utils.database import save_db_to_excel, EXCEL_DB_PATH
            save_db_to_excel()
            with open(EXCEL_DB_PATH, "rb") as f:
                db_bytes = f.read()
            st.download_button(
                label="📥 Descargar sigrama_database.xlsx",
                data=db_bytes,
                file_name="sigrama_database.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                type="primary"
            )
        except Exception as e:
            st.error(f"No se pudo leer el archivo de base de datos Excel: {e}")
            
    with col_db_ul:
        st.subheader("📤 Restaurar Base de Datos (Excel)")
        st.markdown("Sube tu archivo de respaldo `sigrama_database.xlsx` para recuperar al 100% todos tus registros:")
        uploaded_db = st.file_uploader("Sube el archivo de respaldo (.xlsx):", type=["xlsx"], key="uploader_restore_db")
        if uploaded_db is not None:
            if st.button("🚨 Sobrescribir Base de Datos Activa", type="primary", use_container_width=True):
                try:
                    from utils.database import EXCEL_DB_PATH, sync_excel_to_sqlite, git_sync_db
                    with open(EXCEL_DB_PATH, "wb") as f:
                        f.write(uploaded_db.getbuffer())
                    # Forzar la recarga desde el nuevo Excel
                    sync_excel_to_sqlite()
                    git_sync_db()
                    st.success("✅ ¡Base de datos restaurada con éxito! La aplicación se actualizará.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error al restaurar base de datos: {e}")

    st.markdown("---")
    st.header("📊 Historial de Respaldos y Cambios (GitHub)")
    st.markdown(
        """
        Esta sección muestra los últimos registros de sincronización y cambios guardados en el repositorio de GitHub. 
        Cada registro representa una versión respaldada de tu base de datos o actualizaciones del sistema.
        """
    )
    
    col_git_title, col_git_btn1, col_git_btn2 = st.columns([2, 1, 1])
    with col_git_btn1:
        if st.button("🔄 Sincronizar con GitHub", key="sync_git_manually", use_container_width=True, type="primary"):
            import datetime
            try:
                from utils.database import EXCEL_DB_PATH, save_db_to_excel
                save_db_to_excel()
                subprocess.run(["git", "add", EXCEL_DB_PATH], capture_output=True, timeout=15)
                res_commit = subprocess.run(
                    ["git", "commit", "-m", f"Manual-sync DB Excel {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"],
                    capture_output=True, timeout=15
                )
                res_push = subprocess.run(["git", "push", "origin", "main"], capture_output=True, timeout=30)
                if res_push.returncode == 0:
                    st.success("✅ ¡Sincronizado con éxito en GitHub!")
                    st.balloons()
                    st.rerun()
                else:
                    st.error(f"❌ Error al subir a GitHub: {res_push.stderr.decode('utf-8', errors='ignore')}")
            except Exception as e:
                st.error(f"Error de sistema al sincronizar: {e}")
                
    with col_git_btn2:
        if st.button("🔄 Actualizar Historial", key="refresh_git_commits", use_container_width=True):
            st.rerun()
    try:
        # Ejecutar comando git log para obtener los últimos 8 commits
        result = subprocess.run(
            ["git", "log", "-n", "8", "--date=format:%d/%m/%Y %H:%M:%S", "--pretty=format:%h|%ad|%an|%s"],
            capture_output=True, text=True, check=True
        )
        lines = result.stdout.strip().split("\n")
        commit_data = []
        for line in lines:
            if "|" in line:
                h, dt, author, msg = line.split("|", 3)
                commit_data.append({
                    "Hash": h,
                    "Fecha / Hora": dt,
                    "Autor / Sistema": author,
                    "Detalle / Mensaje": msg
                })
        
        if commit_data:
            df_commits = pd.DataFrame(commit_data)
            st.dataframe(
                df_commits,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Hash": st.column_config.TextColumn("ID Commit", width=100),
                    "Fecha / Hora": st.column_config.TextColumn("Fecha / Hora", width=180),
                    "Autor / Sistema": st.column_config.TextColumn("Autor / Emisor", width=150),
                    "Detalle / Mensaje": st.column_config.TextColumn("Detalle / Respaldos", width=400),
                }
            )
            st.info("💡 Los commits con el mensaje 'Auto-sync DB' son respaldos automáticos en tiempo real de tu base de datos.")
        else:
            st.info("No se encontró historial de cambios de Git.")
    except Exception as err:
        st.warning(f"No se pudo consultar el historial de GitHub: {err}")

def view_mantenimiento():
    st.title("🛠️ 6. MANTENIMIENTO DEL SISTEMA")
    
    tab_admin, tab_correc = st.tabs([
        "🛠️ MANTENIMIENTO Y RESPALDOS",
        "✏️ CORRECCIÓN DE AVANCES/RECHAZOS"
    ])
    
    with tab_admin:
        view_mantenimiento_admin()
        
    with tab_correc:
        view_correcciones()
