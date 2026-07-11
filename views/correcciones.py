import streamlit as st
import pandas as pd
from utils.database import get_connection, get_personal_prenomina, get_operadores_por_area, git_sync_db

def get_registros(tabla, of_number, area, nido="Todos", no_pieza="Todas"):
    conn = get_connection()
    motivo_select = ", motivo" if tabla == "rechazos" else ""
    query = f"SELECT id, of_number, nido, hoja, no_pieza, area, cantidad{motivo_select}, operador, maquina, timestamp FROM {tabla} WHERE of_number = ? AND area = ?"
    params = [of_number, area]
    
    if area == "Corte" and nido != "Todos":
        query += " AND nido = ?"
        params.append(nido)
    elif area != "Corte" and no_pieza != "Todas":
        query += " AND no_pieza = ?"
        params.append(no_pieza)
        
    query += " ORDER BY timestamp DESC"
    
    df = pd.read_sql_query(query, conn, params=tuple(params))
    conn.close()
    return df

def delete_registros(tabla, ids_to_delete):
    if not ids_to_delete: return
    conn = get_connection()
    c = conn.cursor()
    
    if tabla == "avances":
        # Para cada ID, ver si es de Corte. Si es de Corte, obtener su of_number, nido y hoja para borrar todo el lote
        for rid in ids_to_delete:
            c.execute("SELECT of_number, nido, area, hoja FROM avances WHERE id = ?", (rid,))
            row = c.fetchone()
            if row:
                of_num, nido, area, hoja = row
                if area == "Corte" and hoja is not None:
                    # Borrar todas las piezas asociadas a esta hoja de este nido en esta OF
                    c.execute("DELETE FROM avances WHERE of_number = ? AND nido = ? AND area = 'Corte' AND hoja = ?", 
                              (of_num, nido, hoja))
                else:
                    # Borrar normal por ID
                    c.execute("DELETE FROM avances WHERE id = ?", (rid,))
    else:
        placeholders = ",".join("?" * len(ids_to_delete))
        c.execute(f"DELETE FROM {tabla} WHERE id IN ({placeholders})", ids_to_delete)
        
    conn.commit()
    conn.close()
    git_sync_db()

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
        git_sync_db()
    conn.close()
    return updates

def view_correcciones():
    st.markdown("## ✏️ Corrección de Avances y Rechazos")
    st.markdown("Filtra los registros paso a paso, selecciona los ingresados por error y elimínalos, o edita sus campos directamente en la tabla.")
    
    # ── FILTROS EN CASCADA ────────────────────────────────────────────
    from views.avances import PROCESSES
    
    friendly_names = {
        "Ingenieria": "Ingeniería",
        "Corte": "Corte (Nidos)",
        "Rebabeo": "Rebabeo",
        "Doblez": "Doblez",
        "Barrenado": "Barrenado",
        "Pintura": "Pintura",
        "Liberado": "Liberado",
        "Empaque": "Empaque"
    }
    inv_friendly_names = {v: k for k, v in friendly_names.items()}
    
    col_f1, col_f2, col_f3 = st.columns(3)
    
    with col_f1:
        sel_area_friendly = st.selectbox(
            "1️⃣ Seleccionar Área / Proceso:", 
            [friendly_names[p] for p in PROCESSES if p in friendly_names],
            key="corr_area"
        )
        sel_area = inv_friendly_names[sel_area_friendly]
        
    # Paso 2: Cargar OFs que tengan movimientos en el área seleccionada
    conn = get_connection()
    df_ofs = pd.read_sql_query(
        "SELECT DISTINCT of_number FROM avances WHERE area = ? UNION SELECT DISTINCT of_number FROM rechazos WHERE area = ?",
        conn, params=(sel_area, sel_area)
    )
    conn.close()
    
    ofs_list = ["Selecciona una OF..."] + df_ofs["of_number"].dropna().tolist()
    
    with col_f2:
        sel_of = st.selectbox(
            "2️⃣ Seleccionar Orden de Fabricación (OF):", 
            ofs_list,
            key="corr_of"
        )
        
    if sel_of == "Selecciona una OF...":
        st.info("ℹ️ Por favor, selecciona una Orden de Fabricación (OF) para continuar.")
        return
        
    # Paso 3: Seleccionar Nido (para Corte) o Pieza (para las demás áreas)
    is_corte = (sel_area == "Corte")
    conn = get_connection()
    
    if is_corte:
        df_nidos = pd.read_sql_query(
            "SELECT DISTINCT nido FROM avances WHERE area = 'Corte' AND of_number = ? UNION SELECT DISTINCT nido FROM rechazos WHERE area = 'Corte' AND of_number = ?",
            conn, params=(sel_of, sel_of)
        )
        nidos_list = ["Todos"] + df_nidos["nido"].dropna().tolist()
        with col_f3:
            sel_nido = st.selectbox("3️⃣ Seleccionar Nido:", nidos_list, key="corr_nido")
            sel_pieza = "Todas"
    else:
        df_piezas = pd.read_sql_query(
            "SELECT DISTINCT no_pieza FROM avances WHERE area = ? AND of_number = ? UNION SELECT DISTINCT no_pieza FROM rechazos WHERE area = ? AND of_number = ?",
            conn, params=(sel_area, sel_of, sel_area, sel_of)
        )
        piezas_list = ["Todas"] + df_piezas["no_pieza"].dropna().tolist()
        with col_f3:
            sel_pieza = st.selectbox("3️⃣ Seleccionar Número de Pieza:", piezas_list, key="corr_pieza")
            sel_nido = "Todos"
            
    conn.close()
    
    # ── TABLA DE AVANCES ──────────────────────────────────────────────
    st.markdown("### 🟢 Avances Registrados")
    df_av = get_registros("avances", sel_of, sel_area, sel_nido, sel_pieza)
    
    # Cargar operadores de la prenomina filtrados por el área seleccionada
    ops_all = get_operadores_por_area(sel_area)
        
    column_config = {
        "id": None,
        "🗑️ Eliminar": st.column_config.CheckboxColumn("Seleccionar", help="Marca esta casilla para eliminar el registro", default=False),
        "of_number": st.column_config.TextColumn("OF", disabled=True),
        "nido": st.column_config.TextColumn("Nido", disabled=True),
        "hoja": st.column_config.NumberColumn("Hoja", disabled=True),
        "no_pieza": st.column_config.TextColumn("No. Pieza", disabled=True),
        "area": st.column_config.TextColumn("Área", disabled=True),
        "cantidad": st.column_config.NumberColumn("Cantidad", disabled=False),
        "operador": st.column_config.SelectboxColumn("Operador", options=ops_all, disabled=False) if ops_all else st.column_config.TextColumn("Operador", disabled=False),
        "maquina": st.column_config.TextColumn("Máquina", disabled=False),
        "timestamp": st.column_config.DatetimeColumn("Fecha/Hora", disabled=True, format="YYYY-MM-DD HH:mm:ss")
    }
    
    if df_av.empty:
        st.info("No se encontraron avances registrados para esta selección.")
    else:
        df_av.insert(0, "🗑️ Eliminar", False)
        
        edited_av = st.data_editor(
            df_av,
            column_config=column_config,
            hide_index=True,
            use_container_width=True,
            key="editor_avances"
        )
        
        ids_av = edited_av[edited_av["🗑️ Eliminar"]]["id"].tolist() if "🗑️ Eliminar" in edited_av else []
        
        # --- Resumen de impacto antes de eliminar ---
        if ids_av:
            filas_sel = df_av[df_av["id"].isin(ids_av)]
            # Detectar el área anterior para cada pieza seleccionada
            conn_imp = get_connection()
            area_anterior_map = {}
            for _, row_imp in filas_sel.iterrows():
                cur = conn_imp.cursor()
                cur.execute(
                    "SELECT ruta FROM piezas WHERE of_number=? AND no_pieza=? LIMIT 1",
                    (row_imp["of_number"], row_imp["no_pieza"])
                )
                res = cur.fetchone()
                if res and res[0]:
                    procesos = [p.strip() for p in res[0].split(",")]
                    if sel_area in procesos:
                        idx_a = procesos.index(sel_area)
                        area_ant = procesos[idx_a - 1] if idx_a > 0 else "Planeación"
                    else:
                        area_ant = "Planeación"
                else:
                    area_ant = "Planeación"
                area_anterior_map[row_imp["no_pieza"]] = area_ant
            conn_imp.close()

            resumen_html = "<div style='background:#fff8e1;border-left:6px solid #FFC107;padding:14px;border-radius:8px;margin-bottom:12px'>"
            resumen_html += "<b>⚠️ Impacto de la eliminación:</b> Las siguientes piezas <b>regresarán al WIP</b> del área indicada:<br><br>"
            resumen_html += "<table style='width:100%;font-size:.9rem'><tr><th>No. Parte</th><th>Cantidad</th><th>Regresa a</th></tr>"
            for _, row_imp in filas_sel.iterrows():
                area_ret = area_anterior_map.get(row_imp["no_pieza"], "Planeación")
                resumen_html += f"<tr><td>{row_imp['no_pieza']}</td><td>{row_imp['cantidad']}</td><td><b>{area_ret}</b></td></tr>"
            resumen_html += "</table></div>"
            st.markdown(resumen_html, unsafe_allow_html=True)

        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("🚨 Eliminar Avances Seleccionados", type="primary"):
                if ids_av:
                    delete_registros("avances", ids_av)
                    st.success(f"✅ Se eliminaron {len(ids_av)} avance(s). El material regresó al WIP del área anterior.")
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
                    
    # ── TABLA DE RECHAZOS ─────────────────────────────────────────────
    st.markdown("### 🔴 Rechazos Registrados")
    df_rech = get_registros("rechazos", sel_of, sel_area, sel_nido, sel_pieza)
    
    if df_rech.empty:
        st.info("No se encontraron rechazos registrados para esta selección.")
    else:
        df_rech.insert(0, "🗑️ Eliminar", False)
        
        column_config_r = column_config.copy()
        column_config_r["motivo"] = st.column_config.TextColumn("Motivo", disabled=True)
        
        edited_rech = st.data_editor(
            df_rech,
            column_config=column_config_r,
            hide_index=True,
            use_container_width=True,
            key="editor_rechazos"
        )
        
        ids_rech = edited_rech[edited_rech["🗑️ Eliminar"]]["id"].tolist() if "🗑️ Eliminar" in edited_rech else []
        
        # --- Resumen de impacto rechazos ---
        if ids_rech:
            filas_rech_sel = df_rech[df_rech["id"].isin(ids_rech)]
            resumen_r_html = "<div style='background:#e8f5e9;border-left:6px solid #28a745;padding:14px;border-radius:8px;margin-bottom:12px'>"
            resumen_r_html += "<b>✅ Impacto de la eliminación de rechazos:</b> Las piezas dejarán de contabilizarse como Scrap y el sistema las contará nuevamente como WIP disponible:<br><br>"
            resumen_r_html += "<table style='width:100%;font-size:.9rem'><tr><th>No. Parte</th><th>Cantidad</th><th>Motivo cancelado</th></tr>"
            for _, rr in filas_rech_sel.iterrows():
                resumen_r_html += f"<tr><td>{rr['no_pieza']}</td><td>{rr['cantidad']}</td><td>{rr.get('motivo','')}</td></tr>"
            resumen_r_html += "</table></div>"
            st.markdown(resumen_r_html, unsafe_allow_html=True)

        col_r1, col_r2 = st.columns(2)
        with col_r1:
            if st.button("🚨 Eliminar Rechazos Seleccionados", type="primary"):
                if ids_rech:
                    delete_registros("rechazos", ids_rech)
                    st.success(f"✅ Se eliminaron {len(ids_rech)} rechazo(s). Las piezas vuelven a estar disponibles en WIP.")
                    st.rerun()
                else:
                    st.warning("Selecciona al menos un rechazo para eliminar.")
        with col_r2:
            if st.button("💾 Guardar Cambios Editados", key="save_re"):
                upd = update_registros("rechazos", df_rech, edited_rech)
                if upd > 0:
                    st.success(f"✅ Se actualizaron {upd} rechazo(s) correctamente.")
                    st.rerun()
                else:
                    st.info("No detecté ningún cambio.")
