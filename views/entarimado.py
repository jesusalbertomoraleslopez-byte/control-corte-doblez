import streamlit as st
import pandas as pd
import datetime
from utils.database import get_connection, save_db_to_excel, sync_and_push_db

def get_inventario_pt():
    conn = get_connection()
    # 1. Obtener avances acumulados en Empaque
    df_avances = pd.read_sql_query("""
        SELECT a.of_number, a.no_pieza, p.descripcion, SUM(a.cantidad) as total_avances
        FROM avances a
        LEFT JOIN (
            SELECT of_number, no_pieza, MIN(nombre_pieza) as descripcion
            FROM piezas
            GROUP BY of_number, no_pieza
        ) p ON a.of_number = p.of_number AND a.no_pieza = p.no_pieza
        WHERE a.area = 'Empaque'
        GROUP BY a.of_number, a.no_pieza
    """, conn)
    
    # 2. Obtener lo ya entarimado
    df_tarimas = pd.read_sql_query("""
        SELECT of_number, no_pieza, SUM(cantidad) as total_empaquetado
        FROM tarimas
        GROUP BY of_number, no_pieza
    """, conn)
    
    # 3. Obtener metadata de ordenes (PO, Proyecto, etc.)
    df_meta = pd.read_sql_query("""
        SELECT of_number, po, proyecto, proyecto_cliente, descripcion_pronest
        FROM ordenes
    """, conn)
    conn.close()
    
    if df_avances.empty:
        return pd.DataFrame(columns=[
            "OF", "Producto/SKU", "Descripción", "PO", "Proyecto", 
            "Proyecto Cliente", "Total Avanzado en PT", "Total Entarimado", "Disponible en PT"
        ])
        
    df_inv = df_avances.merge(df_tarimas, on=["of_number", "no_pieza"], how="left")
    df_inv["total_empaquetado"] = df_inv["total_empaquetado"].fillna(0).astype(int)
    df_inv["disponible"] = df_inv["total_avances"] - df_inv["total_empaquetado"]
    
    df_inv = df_inv.merge(df_meta, on="of_number", how="left")
    
    df_inv.rename(columns={
        "of_number": "OF",
        "no_pieza": "Producto/SKU",
        "descripcion": "Descripción",
        "po": "PO",
        "proyecto": "Proyecto",
        "proyecto_cliente": "Proyecto Cliente",
        "total_avances": "Total Avanzado en PT",
        "total_empaquetado": "Total Entarimado",
        "disponible": "Disponible en PT"
    }, inplace=True)
    
    df_inv = df_inv[[
        "OF", "Producto/SKU", "Descripción", "PO", "Proyecto", "Proyecto Cliente", 
        "Total Avanzado en PT", "Total Entarimado", "Disponible en PT"
    ]]
    return df_inv

def get_next_bulto_name():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT DISTINCT tarima_id FROM tarimas")
    rows = c.fetchall()
    conn.close()
    
    max_num = 0
    for r in rows:
        name = r[0]
        if name.startswith("Bulto_"):
            try:
                num = int(name.split("_")[1])
                if num > max_num:
                    max_num = num
            except ValueError:
                pass
    return f"Bulto_{max_num + 1}"

def generate_plantilla_tarimas_excel(selected_tarima_ids):
    import openpyxl
    import io
    import os
    
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    template_path = os.path.join(base_dir, "plantilla_carga_tarimas_sigrama.xlsx")
    wb = openpyxl.load_workbook(template_path)
    ws = wb['Plantilla_Tarimas']
    
    # Limpiar datos anteriores (desde fila 2 hasta la última con datos)
    if ws.max_row > 1:
        for r in range(2, ws.max_row + 1):
            for c in range(1, 8):
                ws.cell(row=r, column=c).value = None
                
    conn = get_connection()
    placeholders = ",".join(["?"] * len(selected_tarima_ids))
    cursor = conn.cursor()
    cursor.execute(f"""
        SELECT t.tarima_id, t.no_pieza, o.po, 
               COALESCE(o.proyecto_cliente, o.proyecto) as proyecto, 
               o.prioridad, 
               o.descripcion_pronest, 
               t.cantidad
        FROM tarimas t
        LEFT JOIN ordenes o ON t.of_number = o.of_number
        WHERE t.tarima_id IN ({placeholders})
    """, selected_tarima_ids)
    rows = cursor.fetchall()
    conn.close()
    
    for i, row in enumerate(rows):
        row_num = i + 2
        ws.cell(row=row_num, column=1, value=row[0]) # Tarima
        ws.cell(row=row_num, column=2, value=row[1]) # Producto/SKU
        ws.cell(row=row_num, column=3, value=row[2] if row[2] else "") # PO
        ws.cell(row=row_num, column=4, value=row[3] if row[3] else "") # Proyecto
        ws.cell(row=row_num, column=5, value=row[4] if row[4] else "") # Parcialidad
        ws.cell(row=row_num, column=6, value=row[5] if row[5] else "") # Descripcion
        ws.cell(row=row_num, column=7, value=row[6]) # Cantidad
        
    output = io.BytesIO()
    wb.save(output)
    return output.getvalue()

def view_entarimado():
    st.markdown("## 📦 CONTROL DE ENTARIMADO (PRODUCTO TERMINADO)")
    
    # Inicializar lista activa en session state
    if 'active_tarima_items' not in st.session_state:
        st.session_state.active_tarima_items = []
        
    tab_crear, tab_historial = st.tabs(["📦 Crear Tarima / Bulto", "🗃️ Registro de Tarimas"])
    
    # Obtener inventario disponible
    df_inv = get_inventario_pt()
    
    # Descontar lo que ya está en la lista activa de la UI en esta sesión
    for item in st.session_state.active_tarima_items:
        idx = df_inv[(df_inv["OF"] == item["OF"]) & (df_inv["Producto/SKU"] == item["Producto/SKU"])].index
        if not idx.empty:
            df_inv.loc[idx, "Disponible en PT"] -= item["Cantidad"]
            
    # Filtrar solo disponibles > 0
    df_inv_disponibles = df_inv[df_inv["Disponible en PT"] > 0].copy()
    
    with tab_crear:
        st.markdown("### 1. Inventario Disponible en Almacén PT")
        if df_inv.empty or len(df_inv[df_inv["Disponible en PT"] > 0]) == 0:
            st.info("⚠️ No hay piezas disponibles en Almacén PT para empaquetar en tarimas. Primero registra avances en la estación 'Empaque' en el Control de Producción.")
        else:
            st.dataframe(df_inv[df_inv["Disponible en PT"] > 0], use_container_width=True, height=250, hide_index=True)
            
            st.markdown("---")
            st.markdown("### 2. Armar Nueva Tarima")
            
            # Nombre de la tarima (Bulto_X)
            next_bulto = get_next_bulto_name()
            bulto_name = st.text_input("🏷️ Nombre de la Tarima / Bulto:", value=next_bulto, key="entarimado_bulto_name")
            
            st.markdown("##### 🔍 Filtrar y Seleccionar Pieza/SKU")
            
            # Filtros para simplificar la búsqueda
            col_f1, col_f2 = st.columns([1, 2])
            with col_f1:
                unique_ofs = sorted(df_inv_disponibles["OF"].unique())
                of_filter = st.selectbox("📂 Filtrar por OF:", ["Todas"] + unique_ofs, key="filter_of_select")
            
            # Filtrar según la OF elegida
            df_sel_filtered = df_inv_disponibles
            if of_filter != "Todas":
                df_sel_filtered = df_sel_filtered[df_sel_filtered["OF"] == of_filter]
                
            with col_f2:
                # Selector de SKU/OF mejorado (comienza con el SKU para permitir búsqueda rápida escribiendo)
                options = []
                opt_map = {}
                for idx, row in df_sel_filtered.iterrows():
                    opt_str = f"SKU: {row['Producto/SKU']} | {row['Descripción']} (OF: {row['OF']} | Disp: {row['Disponible en PT']})"
                    options.append(opt_str)
                    opt_map[opt_str] = row
                    
                if not options:
                    selected_opt = st.selectbox("🔍 Seleccionar Pieza / SKU a agregar:", ["No hay piezas disponibles"], disabled=True, key="select_sku_opt_disabled")
                else:
                    selected_opt = st.selectbox("🔍 Seleccionar Pieza / SKU (escribe para buscar):", options, key="select_sku_opt")
            
            if selected_opt and selected_opt in opt_map:
                selected_row = opt_map[selected_opt]
                max_cant = int(selected_row["Disponible en PT"])
                
                col_c1, col_c2 = st.columns(2)
                with col_c1:
                    cant = st.number_input("🔢 Cantidad a empacar:", min_value=1, max_value=max_cant, value=1, step=1)
                with col_c2:
                    st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
                    if st.button("➕ Agregar a la lista", use_container_width=True, type="secondary"):
                        # Verificar si ya existe en la lista activa
                        found = False
                        for item in st.session_state.active_tarima_items:
                            if item["OF"] == selected_row["OF"] and item["Producto/SKU"] == selected_row["Producto/SKU"]:
                                if item["Cantidad"] + cant <= int(selected_row["Disponible en PT"]) + item["Cantidad"]: # max original
                                    item["Cantidad"] += cant
                                    found = True
                                else:
                                    st.error("No puedes exceder la cantidad disponible.")
                                    found = True
                                break
                        if not found:
                            st.session_state.active_tarima_items.append({
                                "OF": selected_row["OF"],
                                "Producto/SKU": selected_row["Producto/SKU"],
                                "Descripción": selected_row["Descripción"],
                                "PO": selected_row["PO"],
                                "Proyecto": selected_row["Proyecto"],
                                "Cantidad": cant
                            })
                        st.rerun()
                        
            # Mostrar lista activa de la tarima
            if st.session_state.active_tarima_items:
                st.markdown(f"#### 📝 Piezas en la Tarima Activa: `{bulto_name}`")
                df_active = pd.DataFrame(st.session_state.active_tarima_items)
                st.dataframe(df_active, use_container_width=True, hide_index=True)
                
                col_b1, col_b2 = st.columns(2)
                with col_b1:
                    if st.button("🗑️ Limpiar Lista", use_container_width=True):
                        st.session_state.active_tarima_items = []
                        st.rerun()
                with col_b2:
                    if st.button("💾 Guardar y Confirmar Bulto", use_container_width=True, type="primary"):
                        if not bulto_name.strip():
                            st.error("El nombre de la tarima no puede estar vacío.")
                        else:
                            conn = get_connection()
                            cursor = conn.cursor()
                            now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            
                            # Insertar cada registro
                            for item in st.session_state.active_tarima_items:
                                cursor.execute("""
                                    INSERT INTO tarimas (tarima_id, no_pieza, of_number, cantidad, timestamp)
                                    VALUES (?, ?, ?, ?, ?)
                                """, (bulto_name, item["Producto/SKU"], item["OF"], item["Cantidad"], now_str))
                                
                            conn.commit()
                            conn.close()
                            
                            # Sincronizar Excel y GitHub
                            save_db_to_excel()
                            sync_and_push_db()
                            
                            st.success(f"✅ ¡{bulto_name} registrado y sincronizado exitosamente!")
                            st.session_state.active_tarima_items = []
                            st.rerun()
                            
    with tab_historial:
        st.markdown("### Historial de Tarimas Registradas")
        
        conn = get_connection()
        df_tarimas_list = pd.read_sql_query("""
            SELECT tarima_id as [ID Tarima], 
                   COUNT(DISTINCT no_pieza) as [SKUs Únicos], 
                   SUM(cantidad) as [Total Piezas], 
                   MIN(timestamp) as [Fecha Creación]
            FROM tarimas
            GROUP BY tarima_id
            ORDER BY timestamp DESC
        """, conn)
        conn.close()
        
        if df_tarimas_list.empty:
            st.info("No se han registrado tarimas aún.")
        else:
            st.dataframe(df_tarimas_list, use_container_width=True, hide_index=True)
            
            st.markdown("---")
            st.markdown("### Acciones de Tarimas")
            
            # Selector de tarimas para descarga / borrado
            all_tarima_ids = df_tarimas_list["ID Tarima"].tolist()
            selected_ids = st.multiselect("📦 Selecciona las Tarimas para operar:", all_tarima_ids)
            
            if selected_ids:
                col_a1, col_a2 = st.columns(2)
                with col_a1:
                    # Botón para descargar Excel
                    try:
                        excel_data = generate_plantilla_tarimas_excel(selected_ids)
                        st.download_button(
                            label="📥 Descargar plantilla_carga_tarimas_sigrama.xlsx",
                            data=excel_data,
                            file_name="plantilla_carga_tarimas_sigrama.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=True,
                            type="primary"
                        )
                    except Exception as ex_excel:
                        st.error(f"Error al generar archivo Excel: {ex_excel}")
                        
                with col_a2:
                    # Botón para eliminar
                    if st.button("❌ Eliminar Bulto(s) Seleccionado(s)", use_container_width=True):
                        conn = get_connection()
                        cursor = conn.cursor()
                        placeholders = ",".join(["?"] * len(selected_ids))
                        cursor.execute(f"DELETE FROM tarimas WHERE tarima_id IN ({placeholders})", selected_ids)
                        conn.commit()
                        conn.close()
                        
                        # Sincronizar Excel y GitHub
                        save_db_to_excel()
                        sync_and_push_db()
                        
                        st.success("✅ Bultos eliminados. El inventario disponible ha sido restaurado.")
                        st.rerun()
