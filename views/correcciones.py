import streamlit as st
import pandas as pd
from utils.database import get_connection

def get_registros(tabla, operador="Todos", area="Todas"):
    conn = get_connection()
    query = f"SELECT id, of_number, nido, no_pieza, area, cantidad, operador, maquina, timestamp FROM {tabla} WHERE 1=1"
    params = []
    
    if operador != "Todos":
        query += " AND operador = ?"
        params.append(operador)
        
    if area != "Todas":
        query += " AND area = ?"
        params.append(area)
        
    query += " ORDER BY timestamp DESC LIMIT 500"
    
    df = pd.read_sql_query(query, conn, params=tuple(params) if params else None)
    conn.close()
    return df

def delete_registros(tabla, ids_to_delete):
    if not ids_to_delete: return
    conn = get_connection()
    c = conn.cursor()
    placeholders = ",".join("?" * len(ids_to_delete))
    c.execute(f"DELETE FROM {tabla} WHERE id IN ({placeholders})", ids_to_delete)
    conn.commit()
    conn.close()

def update_registros(tabla, original_df, edited_df):
    conn = get_connection()
    c = conn.cursor()
    updates = 0
    for i in range(len(original_df)):
        orig = original_df.iloc[i]
        edit = edited_df.iloc[i]
        if orig['cantidad'] != edit['cantidad'] or orig['operador'] != edit['operador'] or orig['maquina'] != edit['maquina']:
            c.execute(f"UPDATE {tabla} SET cantidad=?, operador=?, maquina=? WHERE id=?", 
                      (edit['cantidad'], edit['operador'], edit['maquina'], orig['id']))
            updates += 1
    if updates > 0:
        conn.commit()
    conn.close()
    return updates

def view_correcciones():
    st.markdown("## ✏️ Corrección de Avances y Rechazos")
    st.markdown("Selecciona los registros ingresados por error y elimínalos, o edita su Cantidad, Operador y Máquina.")
    
    conn = get_connection()
    operadores_df = pd.read_sql_query("SELECT DISTINCT operador FROM avances UNION SELECT DISTINCT operador FROM rechazos", conn)
    areas_df = pd.read_sql_query("SELECT DISTINCT area FROM avances UNION SELECT DISTINCT area FROM rechazos", conn)
    conn.close()
    
    lista_operadores = ["Todos"] + [op for op in operadores_df['operador'].dropna().unique() if str(op).strip()]
    lista_areas = ["Todas"] + [ar for ar in areas_df['area'].dropna().unique() if str(ar).strip()]
    
    col1, col2 = st.columns(2)
    with col1:
        sel_operador = st.selectbox("👤 Filtrar por Operador:", lista_operadores, key="corr_op")
    with col2:
        sel_area = st.selectbox("🏭 Filtrar por Área:", lista_areas, key="corr_area")
    
    st.markdown("### 🟢 Avances Registrados (Últimos 500)")
    df_av = get_registros("avances", sel_operador, sel_area)
    
    if df_av.empty:
        st.info("No hay avances registrados para estos filtros.")
    else:
        df_av.insert(0, "🗑️ Eliminar", False)
        
        column_config = {
            "id": None,
            "🗑️ Eliminar": st.column_config.CheckboxColumn("Seleccionar", help="Marca esta casilla para eliminar el registro", default=False),
            "of_number": st.column_config.TextColumn("OF", disabled=True),
            "nido": st.column_config.TextColumn("Nido", disabled=True),
            "no_pieza": st.column_config.TextColumn("No. Pieza", disabled=True),
            "area": st.column_config.TextColumn("Área", disabled=True),
            "cantidad": st.column_config.NumberColumn("Cantidad", disabled=False),
            "operador": st.column_config.TextColumn("Operador", disabled=False),
            "maquina": st.column_config.TextColumn("Máquina", disabled=False),
            "timestamp": st.column_config.DatetimeColumn("Fecha/Hora", disabled=True, format="YYYY-MM-DD HH:mm:ss")
        }
        
        edited_av = st.data_editor(
            df_av,
            column_config=column_config,
            hide_index=True,
            use_container_width=True,
            key="editor_avances"
        )
        
        ids_av = edited_av[edited_av["🗑️ Eliminar"]]["id"].tolist() if "🗑️ Eliminar" in edited_av else []
        
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("🚨 Eliminar Avances Seleccionados", type="primary"):
                if ids_av:
                    delete_registros("avances", ids_av)
                    st.success(f"✅ Se eliminaron {len(ids_av)} avance(s) correctamente.")
                    st.rerun()
                else:
                    st.warning("Selecciona al menos un avance para eliminar.")
        with col_btn2:
            if st.button("💾 Guardar Cambios Editados", key="save_av"):
                upd = update_registros("avances", df_av, edited_av)
                if upd > 0:
                    st.success(f"✅ Se actualizaron {upd} avance(s) correctamente.")
                    st.rerun()
                else:
                    st.info("No detecté ningún cambio.")

    st.markdown("### 🔴 Rechazos Registrados (Últimos 500)")
    # Obtener columna motivo para rechazos
    conn = get_connection()
    query_r = "SELECT id, of_number, nido, no_pieza, area, cantidad, motivo, operador, maquina, timestamp FROM rechazos WHERE 1=1"
    params_r = []
    
    if sel_operador != "Todos":
        query_r += " AND operador = ?"
        params_r.append(sel_operador)
        
    if sel_area != "Todas":
        query_r += " AND area = ?"
        params_r.append(sel_area)
        
    query_r += " ORDER BY timestamp DESC LIMIT 500"
    df_rech_full = pd.read_sql_query(query_r, conn, params=tuple(params_r) if params_r else None)
    conn.close()
    
    if df_rech_full.empty:
        st.info("No hay rechazos registrados para estos filtros.")
    else:
        df_rech_full.insert(0, "🗑️ Eliminar", False)
        
        column_config_r = column_config.copy()
        column_config_r["motivo"] = st.column_config.TextColumn("Motivo", disabled=True)
        
        edited_rech = st.data_editor(
            df_rech_full,
            column_config=column_config_r,
            hide_index=True,
            use_container_width=True,
            key="editor_rechazos"
        )
        
        ids_rech = edited_rech[edited_rech["🗑️ Eliminar"]]["id"].tolist() if "🗑️ Eliminar" in edited_rech else []
        
        col_r1, col_r2 = st.columns(2)
        with col_r1:
            if st.button("🚨 Eliminar Rechazos Seleccionados", type="primary"):
                if ids_rech:
                    delete_registros("rechazos", ids_rech)
                    st.success(f"✅ Se eliminaron {len(ids_rech)} rechazo(s) correctamente.")
                    st.rerun()
                else:
                    st.warning("Selecciona al menos un rechazo para eliminar.")
        with col_r2:
            if st.button("💾 Guardar Cambios Editados", key="save_re"):
                upd = update_registros("rechazos", df_rech_full, edited_rech)
                if upd > 0:
                    st.success(f"✅ Se actualizaron {upd} rechazo(s) correctamente.")
                    st.rerun()
                else:
                    st.info("No detecté ningún cambio.")
