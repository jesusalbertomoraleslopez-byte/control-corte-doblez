import streamlit as st
import pandas as pd
from utils.database import get_active_of, get_todas_piezas, get_avances_nido, save_avances_mixto, get_total_rechazos, get_connection, get_movimientos_area, get_all_ofs
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, DataReturnMode, JsCode

# Constantes de diseño
RED = "#EC2024"
BLACK = "#111111"
GRAY = "#D2D3D5"
WHITE = "#FFFFFF"

PROCESSES = ["Ingenieria", "Corte", "Rebabeo", "Doblez", "Barrenado", "Pintura", "Liberado", "Empaque"]

def view_avances():
    st.markdown("## 🏭 Panel de Operador - Registro de Avances")
    
    st.markdown(
        f"""
        <div style="background-color: {GRAY}; padding: 15px; border-radius: 8px; margin-bottom: 20px;">
            <h4 style="margin: 0; color: {BLACK};">Filtros de Búsqueda y Estación de Trabajo</h4>
        </div>
        """, unsafe_allow_html=True
    )
    
    # 1. Obtener proyectos y calibres disponibles para los filtros
    conn = get_connection()
    df_proj = pd.read_sql_query("SELECT DISTINCT proyecto FROM ordenes WHERE proyecto IS NOT NULL AND proyecto != ''", conn)
    proyectos_list = ["Todos"] + df_proj["proyecto"].tolist()
    
    # Verificar si calibre existe en la base de datos
    c_info = conn.cursor()
    c_info.execute("PRAGMA table_info(nidos)")
    nidos_cols = [row[1] for row in c_info.fetchall()]
    if "calibre" in nidos_cols:
        df_cal = pd.read_sql_query("SELECT DISTINCT calibre FROM nidos WHERE calibre IS NOT NULL AND calibre != ''", conn)
        calibres_list = ["Todos"] + df_cal["calibre"].tolist()
    else:
        calibres_list = ["Todos"]
    conn.close()

    # Fila 1 de Filtros (3 columnas)
    col_f1, col_f2, col_f3 = st.columns(3)
    
    with col_f1:
        area_seleccionada = st.selectbox("1️⃣ Área / Proceso", PROCESSES, key="avance_area")
        
    with col_f2:
        proyecto_seleccionado = st.selectbox("📂 Proyecto", proyectos_list, key="avance_proyecto_selector")
        
    with col_f3:
        # Filtrar OFs disponibles por el proyecto seleccionado
        conn = get_connection()
        if proyecto_seleccionado == "Todos":
            df_ofs_f = pd.read_sql_query("SELECT DISTINCT of_number FROM ordenes", conn)
        else:
            df_ofs_f = pd.read_sql_query("SELECT DISTINCT of_number FROM ordenes WHERE proyecto = ?", conn, params=(proyecto_seleccionado,))
        conn.close()
        
        todas_ofs = df_ofs_f["of_number"].tolist()
        todas_ofs_opciones = ["Todas"] + todas_ofs
        of_seleccionada = st.selectbox("2️⃣ Orden de Fabricación (OF)", todas_ofs_opciones, key="avance_of_selector")
        of_number = of_seleccionada

    # Fila 2 de Filtros (3 columnas)
    col_f4, col_f5, col_f6 = st.columns(3)
    
    with col_f4:
        calibre_seleccionado = st.selectbox("📏 Calibre", calibres_list, key="avance_calibre_selector")
        
    with col_f5:
        lista_maquinas = [
            "N/A", 
            "Láser 1", "Láser 2", "Láser 3", "Láser 4", 
            "Dobladora 1", "Dobladora 2", "Dobladora 3", "Dobladora 4", 
            "Lijadora 1", "Lijadora 2", 
            "Línea de Pintura Batch", "Línea Continua", 
            "Manual"
        ]
        maquina = st.selectbox("3️⃣ Máquina", lista_maquinas, key="avance_maquina")
        
    with col_f6:
        operador = st.text_input("4️⃣ Operador (Nombre o Nómina)", key="avance_operador")
        
    # Obtener piezas desde la Base de Datos
    df_todas = get_todas_piezas(of_number)
    
    # Aplicar filtro de calibre en python
    if calibre_seleccionado != "Todos" and "calibre" in df_todas.columns:
        df_todas = df_todas[df_todas['calibre'] == calibre_seleccionado]
        
    if df_todas.empty:
        st.warning("⚠️ No se encontraron piezas que coincidan con los filtros seleccionados.")
        return
        
    nidos_list = df_todas['nido'].unique().tolist()
    
    is_ingenieria = (area_seleccionada == "Ingenieria")
    is_corte = (area_seleccionada == "Corte")
    is_post_corte = not is_ingenieria and not is_corte
    
    nido_seleccionado = "Seleccionar..."
    if is_corte:
        st.markdown("👇 **Selecciona un Nido de la tabla haciendo clic en la fila correspondiente:**")
        
        # Obtener el estado de los nidos para esta área
        conn = get_connection()
        c = conn.cursor()
        if of_number == "Todas":
            c.execute("SELECT DISTINCT of_number || '-' || nido FROM avances WHERE area = ?", (area_seleccionada,))
            terminados = [row[0] for row in c.fetchall()]
            nidos_list_unique = (df_todas['of_number'] + ' | ' + df_todas['nido']).unique().tolist()
            df_nidos_list = pd.DataFrame({"Nido": nidos_list_unique})
            # Adjust terminados to match format
            df_nidos_list["Estado"] = df_nidos_list["Nido"].apply(
                lambda x: "✅ Terminado" if x.replace(" | ", "-") in terminados else "⏳ Pendiente"
            )
        else:
            c.execute("SELECT DISTINCT nido FROM avances WHERE of_number = ? AND area = ?", (of_number, area_seleccionada))
            terminados = [row[0] for row in c.fetchall()]
            df_nidos_list = pd.DataFrame({"Nido": nidos_list})
            df_nidos_list["Estado"] = df_nidos_list["Nido"].apply(
                lambda x: "✅ Terminado" if x in terminados else "⏳ Pendiente"
            )
        conn.close()
        
        event = st.dataframe(
            df_nidos_list,
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            key="nido_selector",
            height=200
        )
        
        selected_rows = event.selection.rows
        if selected_rows:
            nido_seleccionado = df_nidos_list.iloc[selected_rows[0]]['Nido']

    if is_ingenieria:
        st.markdown(f"### 📋 Números de Parte de la OF: **{of_number}**")
        st.markdown("👇 **Para INGENIERÍA, marca las partes que ya has terminado de diseñar/programar.**")
        
        # Unique parts
        df_partes = df_todas.drop_duplicates(subset=['of_number', 'no_pieza']).copy()
        
        # Check which ones are already completed in Ingenieria
        conn = get_connection()
        c = conn.cursor()
        if of_number == "Todas":
            c.execute("SELECT DISTINCT of_number || '-' || no_pieza FROM avances WHERE area = 'Ingenieria'")
        else:
            c.execute("SELECT DISTINCT of_number || '-' || no_pieza FROM avances WHERE of_number = ? AND area = 'Ingenieria'", (of_number,))
            
        terminadas = [row[0] for row in c.fetchall()]
        conn.close()
        
        # Create a df for the editor
        df_edit = df_partes[['of_number', 'no_pieza', 'nombre_pieza']].copy()
        df_edit['Diseñada'] = df_edit.apply(lambda row: f"{row['of_number']}-{row['no_pieza']}" in terminadas, axis=1)
        
        edited_df = st.data_editor(
            df_edit,
            use_container_width=True,
            hide_index=True,
            column_config={
                "of_number": st.column_config.TextColumn("OF", disabled=True),
                "no_pieza": st.column_config.TextColumn("No. Parte", disabled=True),
                "nombre_pieza": st.column_config.TextColumn("Descripción", disabled=True),
                "Diseñada": st.column_config.CheckboxColumn("¿Terminada?")
            },
            height=250
        )
        
        if st.button("✅ Guardar Avances de Ingeniería", type="primary"):
            # Encontrar las que se acaban de marcar y no estaban antes
            nuevas_terminadas = edited_df[edited_df["Diseñada"] & (~edited_df["no_pieza"].isin(terminadas))].copy()
            
            if nuevas_terminadas.empty:
                st.info("No hay partes nuevas por registrar.")
            else:
                # save_avances_mixto already imported at top level
                # Guardamos cada parte con nido='N/A' y cantidad=1
                nuevas_terminadas["cantidad"] = 1
                nuevas_terminadas["Terminadas"] = 1
                # Llamamos save_avances_mixto pasando N/A
                save_avances_mixto(of_number, "N/A", area_seleccionada, False, nuevas_terminadas, None, operador, maquina, None)
                st.success(f"🎉 ¡{len(nuevas_terminadas)} partes marcadas como terminadas en Ingeniería!")
                st.rerun()
                
    elif is_corte and nido_seleccionado != "Seleccionar...":
        st.markdown(f"### 📋 Detalles del Nido: **{nido_seleccionado}**")
        
        actual_of = of_number
        actual_nido = nido_seleccionado
        if " | " in nido_seleccionado:
            actual_of, actual_nido = nido_seleccionado.split(" | ", 1)
            
        # Verificar si este nido ya se completó en esta área
        df_avances = get_avances_nido(actual_of, actual_nido)
        areas_terminadas = df_avances['area'].tolist() if not df_avances.empty else []
        
        if area_seleccionada in areas_terminadas:
            st.success(f"✅ Este nido ya fue marcado como TERMINADO en **{area_seleccionada}**.")
            st.stop() # No permitir registrar de nuevo
            
        # Obtener piezas del nido específico
        df_nido = df_todas[(df_todas['nido'] == actual_nido) & (df_todas['of_number'] == actual_of)].copy()
        total_hojas = int(df_nido['hojas'].iloc[0]) if 'hojas' in df_nido.columns and not df_nido.empty else 1
        
        # Consultar en DB qué hoja sigue
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT IFNULL(MAX(hoja), 0) FROM avances WHERE of_number=? AND nido=? AND area='Corte'", (actual_of, actual_nido))
        ultima_hoja = c.fetchone()[0]
        conn.close()
        
        hoja_actual = ultima_hoja + 1
        
        if hoja_actual > total_hojas:
            st.success(f"✅ Todas las hojas ({total_hojas}/{total_hojas}) de este Nesteo ya fueron cortadas.")
        else:
            st.markdown(f"👇 **CORTE: Registrando Hoja {hoja_actual} de {total_hojas}**")
            st.markdown(f"Las cantidades mostradas abajo corresponden **solamente a las piezas que salen de esta hoja**.")
            
            df_edit = df_nido[['no_pieza', 'nombre_pieza', 'cantidad']].copy()
            df_edit['Rechazos'] = 0
            df_edit['Motivo'] = ""
            
            edited_df = st.data_editor(
                df_edit,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "no_pieza": st.column_config.TextColumn("No. Pieza", disabled=True),
                    "nombre_pieza": st.column_config.TextColumn("Descripción", disabled=True),
                    "cantidad": st.column_config.NumberColumn("Cantidad (x Hoja)", disabled=True),
                    "Rechazos": st.column_config.NumberColumn("Cant. Rechazada", min_value=0, step=1),
                    "Motivo": st.column_config.TextColumn("Motivo de rechazo")
                },
                height=200
            )
            
            if st.button(f"✅ Registrar Hoja {hoja_actual} Terminada", type="primary"):
                if not operador.strip():
                    st.error("⚠️ Por favor ingresa el nombre del Operador antes de guardar.")
                    st.stop()
                    
                df_terminadas = edited_df.copy()
                df_terminadas["Terminadas"] = df_terminadas["cantidad"] # Avanza exactamente lo de 1 hoja
                df_terminadas["of_number"] = actual_of
                
                df_rechazos = edited_df[edited_df["Rechazos"] > 0].copy()
                if not df_rechazos.empty:
                    df_rechazos["of_number"] = actual_of
                    
                save_avances_mixto(actual_of, actual_nido, area_seleccionada, is_corte, df_terminadas, df_rechazos, operador, maquina, hoja_actual)
                st.success(f"🎉 ¡Hoja {hoja_actual} registrada en Corte!")
                st.rerun()

    elif is_post_corte:
        st.markdown(f"### 📋 Números de Parte de la OF: **{of_number}**")
        st.markdown(f"👇 **Para {area_seleccionada}, registra las piezas que vayas terminando.**")
        
        # 1. Filtrar piezas que SÍ pasan por esta área
        df_piezas = df_todas.copy()
        if 'hojas' not in df_piezas.columns:
            df_piezas['hojas'] = 1
        df_piezas['total_requeridas'] = df_piezas['cantidad'] * df_piezas['hojas']
        
        # Verificar si la pieza pasa por area_seleccionada y obtener su area anterior
        def get_area_anterior(ruta_str, current_area):
            procesos = str(ruta_str).split(', ')
            if current_area in procesos:
                idx = procesos.index(current_area)
                if idx > 0:
                    return procesos[idx - 1]
            return None
            
        df_piezas['pasa_por_aqui'] = df_piezas['ruta'].apply(lambda x: area_seleccionada in str(x).split(', '))
        df_piezas = df_piezas[df_piezas['pasa_por_aqui']]
        
        if df_piezas.empty:
            st.warning(f"⚠️ No hay piezas programadas para pasar por {area_seleccionada} en esta OF.")
            st.stop()
            
        df_piezas['area_anterior'] = df_piezas['ruta'].apply(lambda x: get_area_anterior(x, area_seleccionada))
        
        # Agrupar por pieza (sumando total requeridas)
        df_agrupado = df_piezas.groupby(['of_number', 'no_pieza']).agg({
            'nombre_pieza': 'first',
            'total_requeridas': 'sum',
            'area_anterior': 'first' # Asumimos misma ruta para misma pieza
        }).reset_index()
        
        # 2. Cargar todos los avances y rechazos de la OF de una sola vez
        conn = get_connection()
        if of_number == "Todas":
            df_avances_all = pd.read_sql_query("SELECT of_number, no_pieza, area, SUM(cantidad) as cantidad FROM avances GROUP BY of_number, no_pieza, area", conn)
            df_rechazos_all = pd.read_sql_query("SELECT of_number, no_pieza, area, SUM(cantidad) as cantidad FROM rechazos GROUP BY of_number, no_pieza, area", conn)
        else:
            df_avances_all = pd.read_sql_query("SELECT of_number, no_pieza, area, SUM(cantidad) as cantidad FROM avances WHERE of_number=? GROUP BY of_number, no_pieza, area", conn, params=(of_number,))
            df_rechazos_all = pd.read_sql_query("SELECT of_number, no_pieza, area, SUM(cantidad) as cantidad FROM rechazos WHERE of_number=? GROUP BY of_number, no_pieza, area", conn, params=(of_number,))
        conn.close()
        
        # 3. Calcular métricas por pieza
        def get_wip(row):
            area_ant = row['area_anterior']
            if pd.isna(area_ant) or not area_ant:
                return 0 # Ej: Si es el primer proceso y no es corte
            wip = df_avances_all[(df_avances_all['no_pieza'] == row['no_pieza']) & (df_avances_all['of_number'] == row['of_number']) & (df_avances_all['area'] == area_ant)]['cantidad'].sum()
            return int(wip)
            
        def get_terminadas_ant(row):
            term = df_avances_all[(df_avances_all['no_pieza'] == row['no_pieza']) & (df_avances_all['of_number'] == row['of_number']) & (df_avances_all['area'] == area_seleccionada)]['cantidad'].sum()
            return int(term)
            
        def get_rechazadas_ant(row):
            rech = df_rechazos_all[(df_rechazos_all['no_pieza'] == row['no_pieza']) & (df_rechazos_all['of_number'] == row['of_number']) & (df_rechazos_all['area'] == area_seleccionada)]['cantidad'].sum()
            return int(rech)
            
        df_agrupado['wip'] = df_agrupado.apply(get_wip, axis=1)
        df_agrupado['terminadas_ant'] = df_agrupado.apply(get_terminadas_ant, axis=1)
        df_agrupado['rechazadas_ant'] = df_agrupado.apply(get_rechazadas_ant, axis=1)
        
        df_edit = df_agrupado.copy()
        
        df_edit['Pendiente Disponible'] = df_edit['wip'] - df_edit['terminadas_ant'] - df_edit['rechazadas_ant']
        df_edit['Pendiente Total OF'] = df_edit['total_requeridas'] - df_edit['terminadas_ant'] - df_edit['rechazadas_ant']
        
        # Evitar negativos
        df_edit['Pendiente Disponible'] = df_edit['Pendiente Disponible'].apply(lambda x: max(0, x))
        df_edit['Pendiente Total OF'] = df_edit['Pendiente Total OF'].apply(lambda x: max(0, x))
        
        # Filtrar solo las que tienen Pendiente Total y además tienen WIP Disponible o avance en esta área
        mask_pendiente = df_edit['Pendiente Total OF'] > 0
        mask_wip = (df_edit['Pendiente Disponible'] > 0) | (df_edit['terminadas_ant'] > 0) | (df_edit['rechazadas_ant'] > 0)
        df_edit = df_edit[mask_pendiente & mask_wip].copy()
        
        if df_edit.empty:
            st.success(f"✅ ¡Todas las piezas de la OF ya fueron procesadas en {area_seleccionada}!")
        else:
            df_edit['Terminadas'] = 0
            df_edit['Rechazos'] = 0
            df_edit['Motivo'] = ""
            df_edit['✅ Todo a Buenas'] = False
            
            total_wip_actual = df_edit['Pendiente Disponible'].sum()
            
            st.markdown(
                f"""
                <div style="background-color: #f8f9fa; border-left: 8px solid #EC2024; padding: 25px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                    <h3 style="margin: 0; color: #555; font-size: 1.4rem; text-transform: uppercase;">Sumatoria WIP - {area_seleccionada}</h3>
                    <div style="display: flex; align-items: baseline; gap: 10px;">
                        <h1 style="margin: 0; color: #EC2024; font-size: 4.5rem; font-weight: 900; line-height: 1;">{int(total_wip_actual)}</h1>
                        <span style="font-size: 1.8rem; font-weight: bold; color: #666;">piezas disponibles para procesar</span>
                    </div>
                </div>
                """, unsafe_allow_html=True
            )
            
            # Reordenar columnas para cumplir con la solicitud
            col_order = [
                "✅ Todo a Buenas", "of_number", "no_pieza", "nombre_pieza", "total_requeridas", "Pendiente Disponible", 
                "terminadas_ant", "rechazadas_ant", 
                "Terminadas", "Rechazos", "Motivo", "Pendiente Total OF"
            ]
            df_edit = df_edit[col_order]
            
            gb = GridOptionsBuilder.from_dataframe(df_edit)
            
            # Configurar columnas no editables
            gb.configure_column("✅ Todo a Buenas", header_name="✅ Completar", editable=True, width=120)
            gb.configure_column("of_number", header_name="OF", width=100, pinned='left')
            gb.configure_column("no_pieza", header_name="No. Pieza", width=120)
            gb.configure_column("nombre_pieza", header_name="Descripción", width=250)
            gb.configure_column("total_requeridas", header_name="Totales (OF)", width=100, cellStyle={'backgroundColor': 'black', 'color': 'white'})
            gb.configure_column("Pendiente Disponible", header_name="WIP Disp.", width=100, cellStyle={'backgroundColor': '#d4edda', 'color': 'black'})
            gb.configure_column("terminadas_ant", header_name="Proc. Ant.", width=100, cellStyle={'color': 'blue'})
            gb.configure_column("rechazadas_ant", header_name="Rech. Ant.", width=100, cellStyle={'color': 'red'})
            gb.configure_column("Pendiente Total OF", header_name="Pend. Total", width=110, cellStyle={'color': 'red', 'fontWeight': 'bold', 'fontSize': '120%'})
            
            # Configurar columnas editables
            gb.configure_column("Terminadas", header_name="Proc. Buenas", editable=True, type=["numericColumn","numberColumnFilter"], cellStyle={'backgroundColor': '#d1ecf1', 'fontWeight': 'bold', 'fontSize': '120%', 'color': 'black'})
            gb.configure_column("Rechazos", header_name="Proc. Malas", editable=True, type=["numericColumn","numberColumnFilter"], cellStyle={'backgroundColor': '#f8d7da', 'fontWeight': 'bold', 'fontSize': '120%', 'color': 'black'})
            gb.configure_column("Motivo", header_name="Motivo de rechazo", editable=True, width=150)
            
            # Configurar Javascript para copiar automáticamente cuando se presiona el Checkbox
            on_cell_val_changed = JsCode("""
            function(event) {
                if (event.column.colId === '✅ Todo a Buenas') {
                    if (event.newValue === true) {
                        event.node.setDataValue('Terminadas', event.data['Pendiente Disponible']);
                    } else {
                        event.node.setDataValue('Terminadas', 0);
                    }
                }
            }
            """)
            gb.configure_grid_options(onCellValueChanged=on_cell_val_changed)
            
            grid_options = gb.build()
            
            grid_response = AgGrid(
                df_edit,
                gridOptions=grid_options,
                update_mode=GridUpdateMode.MODEL_CHANGED,
                data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
                fit_columns_on_grid_load=True,
                allow_unsafe_jscode=True,
                theme='streamlit',
                height=250
            )
            
            edited_df = pd.DataFrame(grid_response['data'])
            
            # Cast editables to numeric just in case AgGrid returns them as strings
            edited_df["Terminadas"] = pd.to_numeric(edited_df["Terminadas"], errors='coerce').fillna(0).astype(int)
            edited_df["Rechazos"] = pd.to_numeric(edited_df["Rechazos"], errors='coerce').fillna(0).astype(int)
            
            if st.button(f"✅ Registrar Avance en {area_seleccionada}", type="primary"):
                if not operador.strip():
                    st.error("⚠️ Por favor ingresa el nombre del Operador antes de guardar.")
                    st.stop()
                    
                df_terminadas = edited_df[edited_df["Terminadas"] > 0]
                df_rechazos = edited_df[edited_df["Rechazos"] > 0]
                
                # Validar que no registren más de las pendientes
                if not df_terminadas.empty:
                    sobrepasadas = df_terminadas[df_terminadas["Terminadas"] > df_terminadas["Pendiente Disponible"]]
                    if not sobrepasadas.empty:
                        st.error("❌ No puedes registrar más piezas terminadas de las que tienes 'Disponibles en WIP'.")
                        st.stop()
                
                if df_terminadas.empty and df_rechazos.empty:
                    st.warning("Debes capturar al menos 1 pieza terminada o rechazada.")
                else:
                    # Guardar con nido="N/A"
                    save_avances_mixto(of_number, "N/A", area_seleccionada, False, df_terminadas, df_rechazos, operador, maquina, None)
                    st.success(f"🎉 ¡Avance registrado exitosamente en {area_seleccionada}!")
                    st.rerun()

    # Mostrar historial de movimientos de esta área en la parte inferior (para todas las áreas)
    df_movimientos = get_movimientos_area(of_number, area_seleccionada)
    if not df_movimientos.empty:
        st.markdown("---")
        st.markdown(f"### 🕒 Historial de Movimientos ({area_seleccionada})")
        st.markdown("👇 *Hora y último registro primero. Si necesitas corregir/eliminar un movimiento, dirígete a la sección 3.4 (Correcciones).*")
        
        # Reordenar columnas para poner Fecha (timestamp) primero
        cols_order = ["Fecha", "Tipo", "No. Pieza", "Cantidad", "Operador", "Máquina", "OF", "Motivo"]
        df_movimientos = df_movimientos[[c for c in cols_order if c in df_movimientos.columns]]
        st.dataframe(df_movimientos, use_container_width=True, hide_index=True, height=250)
    else:
        # Mostrar historial de rechazos globales de la OF si no hay movimientos en esta área
        df_rechazos_hist = get_total_rechazos(of_number)
        if not df_rechazos_hist.empty:
            st.markdown("---")
            st.markdown(f"### ⚠️ Historial de Rechazos Globales (OF {of_number})")
            st.dataframe(df_rechazos_hist, use_container_width=True, hide_index=True, height=200)
