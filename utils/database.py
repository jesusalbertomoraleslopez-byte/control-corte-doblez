import sqlite3
import pandas as pd
import datetime
import subprocess
import threading
import os

EXCEL_DB_PATH = "sigrama_database.xlsx"
TEMP_DB_PATH = "sigrama_temp.db"

_last_excel_mtime = 0

def git_sync_db():
    """Hace commit y push de sigrama_database.xlsx a GitHub en un hilo separado para no bloquear la UI."""
    def _sync():
        try:
            if os.path.exists(EXCEL_DB_PATH):
                import streamlit as st
                try:
                    token = st.secrets.get("GITHUB_TOKEN")
                    if token:
                        url = f"https://{token}@github.com/jesusalbertomoraleslopez-byte/control-corte-doblez.git"
                        subprocess.run(["git", "remote", "set-url", "origin", url], capture_output=True)
                except Exception:
                    pass
                
                subprocess.run(["git", "add", EXCEL_DB_PATH], capture_output=True, timeout=15)
                result = subprocess.run(
                    ["git", "commit", "-m", f"Auto-sync DB Excel {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"],
                    capture_output=True, timeout=15
                )
                subprocess.run(
                    ["git", "-c", "core.sshCommand=ssh -o StrictHostKeyChecking=no", "push", "origin", "main"],
                    capture_output=True, timeout=30
                )
        except Exception:
            pass  # Silencioso: no romper la app si git falla
    threading.Thread(target=_sync, daemon=True).start()

def save_db_to_excel(conn=None):
    """Exporta todas las tablas SQLite al archivo Excel sigrama_database.xlsx."""
    close_at_end = False
    if conn is None:
        conn = sqlite3.connect(TEMP_DB_PATH)
        close_at_end = True
        
    tables = ["ordenes", "nidos", "piezas", "avances", "rechazos", "personal_areas"]
    temp_excel = "sigrama_database_temp.xlsx"
    try:
        with pd.ExcelWriter(temp_excel, engine='openpyxl') as writer:
            for t in tables:
                try:
                    df = pd.read_sql_query(f"SELECT * FROM {t}", conn)
                except Exception:
                    df = pd.DataFrame()
                df.to_excel(writer, sheet_name=t, index=False)
        
        if os.path.exists(EXCEL_DB_PATH):
            os.remove(EXCEL_DB_PATH)
        os.rename(temp_excel, EXCEL_DB_PATH)
        
        # Actualizar mtime para evitar re-sincronizaciones locales innecesarias
        global _last_excel_mtime
        _last_excel_mtime = os.path.getmtime(EXCEL_DB_PATH)
    except Exception as e:
        print(f"Error al guardar base de datos a Excel: {e}")
        if os.path.exists(temp_excel):
            try:
                os.remove(temp_excel)
            except:
                pass
    finally:
        if close_at_end:
            conn.close()

def sync_excel_to_sqlite():
    """Carga los datos del archivo Excel sigrama_database.xlsx a la base SQLite temporal."""
    init_db_schema()
    
    if not os.path.exists(EXCEL_DB_PATH):
        # Si el Excel no existe, pero existe la base de datos vieja sigrama.db, migramos
        if os.path.exists("sigrama.db"):
            try:
                old_conn = sqlite3.connect("sigrama.db")
                save_db_to_excel(old_conn)
                old_conn.close()
                # Renombramos para evitar migraciones repetidas
                os.rename("sigrama.db", "sigrama_migrated.db")
            except Exception as em:
                print(f"Error al migrar DB vieja: {em}")
                save_db_to_excel()
        else:
            # Si no hay ninguna BD, crear un Excel vacío inicial a partir del esquema
            save_db_to_excel()
            return
        
    conn = sqlite3.connect(TEMP_DB_PATH)
    c = conn.cursor()
    
    try:
        excel_file = pd.ExcelFile(EXCEL_DB_PATH)
        sheets = excel_file.sheet_names
        
        tables = ["ordenes", "nidos", "piezas", "avances", "rechazos", "personal_areas"]
        for t in tables:
            best_match = next((s for s in sheets if s.lower() == t.lower()), None)
            if best_match:
                df = pd.read_excel(excel_file, sheet_name=best_match)
                c.execute(f"DELETE FROM {t}")
                if not df.empty:
                    # Reemplazar valores nulos por None para evitar errores en SQLite
                    df = df.astype(object).where(pd.notnull(df), None)
                    df.to_sql(t, conn, if_exists='append', index=False)
        conn.commit()
    except Exception as e:
        print(f"Error al sincronizar Excel a SQLite: {e}")
    finally:
        conn.close()

def get_connection():
    """Obtiene la conexión a la base de datos temporal SQLite, sincronizándola si el Excel cambió."""
    global _last_excel_mtime
    
    if os.path.exists(EXCEL_DB_PATH):
        mtime = os.path.getmtime(EXCEL_DB_PATH)
        if mtime > _last_excel_mtime or not os.path.exists(TEMP_DB_PATH):
            sync_excel_to_sqlite()
            _last_excel_mtime = mtime
    else:
        if not os.path.exists(TEMP_DB_PATH):
            sync_excel_to_sqlite()
            
    conn = sqlite3.connect(TEMP_DB_PATH)
    return conn

def init_db_schema(conn=None):
    """Inicializa la estructura de tablas de la base de datos SQLite."""
    close_at_end = False
    if conn is None:
        conn = sqlite3.connect(TEMP_DB_PATH)
        close_at_end = True
        
    cursor = conn.cursor()
    
    # 1. Tabla de Órdenes
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ordenes (
            of_number TEXT PRIMARY KEY,
            proyecto TEXT,
            programador TEXT,
            fecha TEXT,
            fecha_carga TEXT,
            po TEXT,
            descripcion_pronest TEXT,
            calibre TEXT,
            prioridad TEXT,
            proyecto_cliente TEXT
        )
    ''')
    
    # 2. Tabla de Nidos
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS nidos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            of_number TEXT,
            nido TEXT,
            hojas INTEGER,
            calibre TEXT,
            FOREIGN KEY (of_number) REFERENCES ordenes (of_number)
        )
    ''')
    
    # 3. Tabla de Piezas
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS piezas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            of_number TEXT,
            nido TEXT,
            no_pieza TEXT,
            nombre_pieza TEXT,
            cantidad INTEGER,
            ruta TEXT,
            FOREIGN KEY (of_number) REFERENCES ordenes (of_number)
        )
    ''')
    
    # 4. Tabla de Avances
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS avances (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            of_number TEXT,
            nido TEXT,
            no_pieza TEXT,
            area TEXT,
            cantidad INTEGER,
            operador TEXT,
            maquina TEXT,
            hoja INTEGER,
            timestamp TEXT,
            FOREIGN KEY (of_number) REFERENCES ordenes (of_number)
        )
    ''')
    
    # 5. Tabla de Rechazos
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS rechazos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            of_number TEXT,
            nido TEXT,
            no_pieza TEXT,
            area TEXT,
            cantidad INTEGER,
            motivo TEXT,
            operador TEXT,
            maquina TEXT,
            hoja INTEGER,
            timestamp TEXT,
            FOREIGN KEY (of_number) REFERENCES ordenes (of_number)
        )
    ''')
    
    # 6. Tabla de Áreas de Personal
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS personal_areas (
            operador_nombre TEXT NOT NULL,
            area TEXT NOT NULL,
            PRIMARY KEY (operador_nombre, area)
        )
    ''')
    
    try:
        check_and_seed_personal_areas(cursor)
    except Exception:
        pass
        
    conn.commit()
    if close_at_end:
        conn.close()

def init_db():
    sync_excel_to_sqlite()

def clear_db():
    """Limpia todas las tablas."""
    conn = get_connection()
    c = conn.cursor()
    for t in ["rechazos", "avances", "piezas", "nidos", "ordenes"]:
        c.execute(f"DELETE FROM {t}")
    conn.commit()
    save_db_to_excel(conn)
    conn.close()
    git_sync_db()

def clear_avances_rechazos():
    """Limpia solo los registros de producción (avances y rechazos)."""
    conn = get_connection()
    c = conn.cursor()
    for t in ["rechazos", "avances"]:
        c.execute(f"DELETE FROM {t}")
    conn.commit()
    save_db_to_excel(conn)
    conn.close()
    git_sync_db()

def clear_plans_keep_catalog():
    """Borra ordenes, nidos, avances y rechazos, pero conserva las piezas para mantener el catálogo de rutas."""
    conn = get_connection()
    c = conn.cursor()
    for t in ["rechazos", "avances", "nidos", "ordenes"]:
        c.execute(f"DELETE FROM {t}")
    conn.commit()
    save_db_to_excel(conn)
    conn.close()
    git_sync_db()

def get_active_of():
    """Devuelve la OF más reciente."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("PRAGMA table_info(ordenes)")
    columns = [row[1] for row in c.fetchall()]
    
    cols_to_select = ["of_number", "proyecto", "programador", "fecha"]
    extra_cols = ["po", "descripcion_pronest", "calibre", "prioridad", "proyecto_cliente"]
    for ec in extra_cols:
        if ec in columns:
            cols_to_select.append(ec)
            
    cols_str = ", ".join(cols_to_select)
    
    import streamlit as st
    session_of = st.session_state.get("of_number")
    if session_of:
        c.execute(f"SELECT {cols_str} FROM ordenes WHERE of_number = ?", (session_of,))
    else:
        c.execute(f"SELECT {cols_str} FROM ordenes ORDER BY fecha_carga DESC LIMIT 1")
    row = c.fetchone()
    conn.close()
    
    if row:
        res = {}
        for idx, col_name in enumerate(cols_to_select):
            res[col_name] = row[idx]
        return res
    return None

def get_all_ofs():
    """Devuelve una lista de todos los números de OF disponibles."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT of_number FROM ordenes ORDER BY fecha_carga DESC")
    rows = c.fetchall()
    conn.close()
    return [row[0] for row in rows]

def save_production_plan(of_number, proyecto, programador, fecha, df_nidos, df_piezas,
                         po="", descripcion_pronest="", calibre="", prioridad="", proyecto_cliente=""):
    conn = get_connection()
    c = conn.cursor()
    
    # 1. Borrar si ya existe (para sobrescribir)
    for t in ["rechazos", "avances", "piezas", "nidos", "ordenes"]:
        c.execute(f"DELETE FROM {t} WHERE of_number = ?", (of_number,))
        
    # 2. Insertar Orden
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("""
        INSERT INTO ordenes (of_number, proyecto, programador, fecha, fecha_carga, po, descripcion_pronest, calibre, prioridad, proyecto_cliente)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (of_number, proyecto, programador, fecha, now, po, descripcion_pronest, calibre, prioridad, proyecto_cliente))
    
    # 3. Insertar Nidos
    nido_col_n = next((col for col in df_nidos.columns if 'NIDO' in str(col).upper()), None)
    hojas_col = next((col for col in df_nidos.columns if 'HOJAS' in str(col).upper()), None)
    calibre_col = next((col for col in df_nidos.columns if 'CALIBRE' in str(col).upper()), None)
    
    if nido_col_n and hojas_col:
        for _, row in df_nidos.iterrows():
            # Handle potential NaNs in Nidos
            nido_val = str(row[nido_col_n]).strip()
            if not nido_val or nido_val.lower() == 'nan':
                continue
            hojas_val = pd.to_numeric(row[hojas_col], errors='coerce')
            hojas_val = int(hojas_val) if pd.notna(hojas_val) else 1
            
            calibre_val = str(row[calibre_col]).strip() if calibre_col else ""
            if calibre_val.lower() == 'nan':
                calibre_val = ""
            
            c.execute("INSERT INTO nidos (of_number, nido, hojas, calibre) VALUES (?, ?, ?, ?)", 
                      (of_number, nido_val, hojas_val, calibre_val))
            
    # 4. Insertar Piezas
    nido_col_p = next((col for col in df_piezas.columns if 'NIDO' in str(col).upper()), None)
    pieza_col = next((col for col in df_piezas.columns if 'PIEZA' in str(col).upper() and 'NOMBRE' not in str(col).upper()), None)
    nombre_col = next((col for col in df_piezas.columns if 'NOMBRE' in str(col).upper()), None)
    cant_col = next((col for col in df_piezas.columns if 'CANTIDAD' in str(col).upper()), None)
    ruta_col = next((col for col in df_piezas.columns if 'RUTA' in str(col).upper()), None)
    
    default_ruta = "Ingenieria, Corte, Rebabeo, Doblez, Liberado, Empaque"
    
    if nido_col_p and pieza_col and cant_col:
        for _, row in df_piezas.iterrows():
            # Handle potential NaNs in Piezas
            nido_val = str(row[nido_col_p]).strip()
            if not nido_val or nido_val.lower() == 'nan':
                continue
            pieza_val = str(row[pieza_col]).strip()
            nombre_val = str(row[nombre_col]).strip() if nombre_col else ""
            cant_val = pd.to_numeric(row[cant_col], errors='coerce')
            cant_val = int(cant_val) if pd.notna(cant_val) else 0
            
            ruta_val = None
            if ruta_col:
                ruta_excel = str(row[ruta_col]).strip()
                if ruta_excel and ruta_excel.lower() != 'nan':
                    ruta_val = ruta_excel
            
            if not ruta_val:
                # Intentar buscar la ruta previamente guardada para esta pieza en la BD
                c_prev = conn.cursor()
                c_prev.execute("SELECT ruta FROM piezas WHERE no_pieza = ? AND ruta IS NOT NULL AND ruta != '' ORDER BY id DESC LIMIT 1", (pieza_val,))
                row_prev = c_prev.fetchone()
                if row_prev:
                    ruta_val = row_prev[0]
                else:
                    ruta_val = default_ruta
            
            c.execute("INSERT INTO piezas (of_number, nido, no_pieza, nombre_pieza, cantidad, ruta) VALUES (?, ?, ?, ?, ?, ?)",
                      (of_number, nido_val, pieza_val, nombre_val, cant_val, ruta_val))
            
    conn.commit()
    save_db_to_excel(conn)
    conn.close()
    git_sync_db()

def get_nidos(of_number):
    conn = get_connection()
    df = pd.read_sql_query("SELECT nido, hojas FROM nidos WHERE of_number = ?", conn, params=(of_number,))
    conn.close()
    return df

def get_piezas_nido(of_number, nido):
    conn = get_connection()
    df = pd.read_sql_query("SELECT no_pieza, nombre_pieza, cantidad FROM piezas WHERE of_number = ? AND nido = ?", 
                           conn, params=(of_number, nido))
    conn.close()
    return df

def get_todas_piezas(of_number=None):
    conn = get_connection()
    # Check if calibre column exists in nidos to prevent errors on legacy DBs
    c = conn.cursor()
    c.execute("PRAGMA table_info(nidos)")
    columns = [row[1] for row in c.fetchall()]
    has_calibre = "calibre" in columns
    
    calibre_select = ", n.calibre" if has_calibre else ", '' as calibre"
    
    if of_number == "Todas" or of_number is None:
        df = pd.read_sql_query(f"""
            SELECT p.of_number, p.nido, p.no_pieza, p.nombre_pieza, p.cantidad, p.ruta, n.hojas {calibre_select}
            FROM piezas p
            JOIN nidos n ON p.of_number = n.of_number AND p.nido = n.nido
        """, conn)
    else:
        df = pd.read_sql_query(f"""
            SELECT p.of_number, p.nido, p.no_pieza, p.nombre_pieza, p.cantidad, p.ruta, n.hojas {calibre_select}
            FROM piezas p
            JOIN nidos n ON p.of_number = n.of_number AND p.nido = n.nido
            WHERE p.of_number = ?
        """, conn, params=(of_number,))
    conn.close()
    return df

def update_ruta_piezas(of_number, actualizaciones):
    """
    Actualiza la columna ruta para varias piezas (todas las instancias de esa pieza en la OF).
    actualizaciones es una lista de diccionarios: [{'no_pieza': 'P1', 'ruta': 'Corte, Doblez'}]
    """
    conn = get_connection()
    c = conn.cursor()
    c.executemany("UPDATE piezas SET ruta = :ruta WHERE of_number = :of_number AND no_pieza = :no_pieza", 
                  [{'of_number': of_number, **d} for d in actualizaciones])
    conn.commit()
    save_db_to_excel(conn)
    conn.close()
    git_sync_db()

def get_avances_nido(of_number, nido):
    """Devuelve las áreas en las que este nido ya está terminado."""
    conn = get_connection()
    df = pd.read_sql_query("SELECT area, hoja, timestamp FROM avances WHERE of_number = ? AND nido = ?", conn, params=(of_number, nido))
    
    # Verificar cuántas hojas tiene el nido
    nido_info = pd.read_sql_query("SELECT hojas FROM nidos WHERE of_number = ? AND nido = ?", conn, params=(of_number, nido))
    conn.close()
    
    total_hojas = int(nido_info['hojas'].iloc[0]) if not nido_info.empty else 1
    
    areas_terminadas = []
    if not df.empty:
        # Para Corte, debe tener todas las hojas registradas
        df_corte = df[df['area'] == 'Corte']
        if df_corte['hoja'].nunique() >= total_hojas:
            areas_terminadas.append('Corte')
            
        # Para otras áreas, si hay registro, lo contamos
        otras_areas = df[df['area'] != 'Corte']['area'].unique()
        areas_terminadas.extend(otras_areas)
        
    return pd.DataFrame({"area": areas_terminadas})

def get_avances_area(of_number, area):
    """Devuelve los nidos terminados en un área para calcular progreso global."""
    conn = get_connection()
    df = pd.read_sql_query("SELECT nido FROM avances WHERE of_number = ? AND area = ?", conn, params=(of_number, area))
    conn.close()
    return [row['nido'] for _, row in df.iterrows()]

def save_avances_mixto(of_number, nido, area, is_corte, df_terminadas, df_rechazos, operador="", maquina="", hoja=None):
    """Guarda avances y rechazos. 
    Para Corte, df_terminadas trae todo el nido. Para otras, trae piezas individuales."""
    conn = get_connection()
    c = conn.cursor()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # 1. Registrar el avance
    if not df_terminadas.empty:
        for _, row in df_terminadas.iterrows():
            no_pieza = str(row["no_pieza"]) if "no_pieza" in row else ""
            cant = int(pd.to_numeric(row.get("Terminadas", row.get("cantidad", 0)), errors='coerce'))
            row_of = str(row.get("of_number", of_number))
            
            if cant > 0:
                c.execute("INSERT INTO avances (of_number, nido, no_pieza, area, cantidad, operador, maquina, hoja, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                          (row_of, nido, no_pieza, area, cant, operador, maquina, hoja, now))
    
    # 2. Registrar rechazos
    if df_rechazos is not None and not df_rechazos.empty:
        for _, row in df_rechazos.iterrows():
            cant = int(pd.to_numeric(row.get("Rechazos", 0), errors='coerce'))
            motivo = str(row.get("Motivo", ""))
            no_pieza = str(row["no_pieza"])
            row_of = str(row.get("of_number", of_number))
            
            if cant > 0:
                c.execute("INSERT INTO rechazos (of_number, nido, no_pieza, area, cantidad, motivo, operador, maquina, hoja, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                          (row_of, nido, no_pieza, area, cant, motivo, operador, maquina, hoja, now))
                
    conn.commit()
    conn.close()
    git_sync_db()

def get_total_rechazos(of_number=None):
    conn = get_connection()
    if of_number == "Todas" or of_number is None:
        df = pd.read_sql_query("SELECT of_number as OF, nido, no_pieza, area, cantidad, motivo, timestamp FROM rechazos", conn)
    else:
        df = pd.read_sql_query("SELECT of_number as OF, nido, no_pieza, area, cantidad, motivo, timestamp FROM rechazos WHERE of_number = ?", conn, params=(of_number,))
    conn.close()
    return df

def get_movimientos_area(of_number, area):
    conn = get_connection()
    if of_number == "Todas":
        query = """
            SELECT of_number as OF, timestamp as Fecha, operador as Operador, maquina as Máquina, no_pieza as 'No. Pieza', cantidad as Cantidad, 'Avance' as Tipo, '' as Motivo
            FROM avances WHERE area = ?
            UNION ALL
            SELECT of_number as OF, timestamp as Fecha, operador as Operador, maquina as Máquina, no_pieza as 'No. Pieza', cantidad as Cantidad, 'Rechazo' as Tipo, motivo as Motivo
            FROM rechazos WHERE area = ?
            ORDER BY Fecha DESC
        """
        df = pd.read_sql_query(query, conn, params=(area, area))
    else:
        query = """
            SELECT of_number as OF, timestamp as Fecha, operador as Operador, maquina as Máquina, no_pieza as 'No. Pieza', cantidad as Cantidad, 'Avance' as Tipo, '' as Motivo
            FROM avances WHERE of_number = ? AND area = ?
            UNION ALL
            SELECT of_number as OF, timestamp as Fecha, operador as Operador, maquina as Máquina, no_pieza as 'No. Pieza', cantidad as Cantidad, 'Rechazo' as Tipo, motivo as Motivo
            FROM rechazos WHERE of_number = ? AND area = ?
            ORDER BY Fecha DESC
        """
        df = pd.read_sql_query(query, conn, params=(of_number, area, of_number, area))
    conn.close()
    return df

def get_dashboard_stats(of_list=None):
    conn = get_connection()
    c = conn.cursor()
    
    if not of_list:
        return {
            "total_nidos": 0, "total_hojas": 0, "total_piezas": 0, "total_partes": 0,
            "avances_pzs": {}, "avances_pct": {}
        }
    
    if "Todas" in of_list:
        where_clause = ""
        where_p = ""
        where_a = ""
        params = []
    else:
        placeholders = ','.join(['?'] * len(of_list))
        where_clause = f"WHERE of_number IN ({placeholders})"
        where_p = f"WHERE p.of_number IN ({placeholders})"
        where_a = f"WHERE a.of_number IN ({placeholders})"
        params = list(of_list)
    
    # Totales
    c.execute(f"SELECT COUNT(nido), SUM(hojas) FROM nidos {where_clause}", params)
    nidos_row = c.fetchone()
    total_nidos = nidos_row[0] or 0
    total_hojas = nidos_row[1] or 0
    
    c.execute(f"""
        SELECT SUM(p.cantidad * n.hojas)
        FROM piezas p
        JOIN nidos n ON p.of_number = n.of_number AND p.nido = n.nido
        {where_p}
    """, params)
    piezas_row = c.fetchone()
    total_piezas = piezas_row[0] or 0
    
    c.execute(f"""
        SELECT COUNT(DISTINCT p.no_pieza)
        FROM piezas p
        {where_p}
    """, params)
    partes_row = c.fetchone()
    total_partes = partes_row[0] or 0
    
    stats = {
        "total_nidos": total_nidos,
        "total_hojas": total_hojas,
        "total_piezas": total_piezas,
        "total_partes": total_partes,
        "avances_pzs": {},
        "avances_pct": {}
    }
    
    # Progreso por area
    areas = ["Ingenieria", "Corte", "Rebabeo", "Doblez", "Liberado", "Empaque"]
    for area in areas:
        if area == "Ingenieria":
            # Para Ingeniería medimos Partes (no_pieza únicos) que pasen por Ing
            q_partes = f"SELECT COUNT(DISTINCT no_pieza) FROM piezas {where_clause} {'AND' if where_clause else 'WHERE'} ruta LIKE ?"
            c.execute(q_partes, (*params, f"%{area}%"))
            total_partes_area = c.fetchone()[0] or 0
            
            q_av = f"SELECT COUNT(DISTINCT no_pieza) FROM avances {where_clause} {'AND' if where_clause else 'WHERE'} area = ?"
            c.execute(q_av, (*params, area))
            row_ing = c.fetchone()
            partes_avanzadas = row_ing[0] or 0
            stats["avances_pzs"][area] = partes_avanzadas
            pct = (partes_avanzadas / total_partes_area * 100) if total_partes_area > 0 else 100.0 if total_partes_area == 0 else 0
            stats["avances_pct"][area] = min(100.0, round(pct, 1))
        elif area == "Corte":
            # Para Corte medimos Nesteos (Nidos completos)
            q_corte = f"SELECT COUNT(DISTINCT nido) FROM avances {where_clause} {'AND' if where_clause else 'WHERE'} area = ?"
            c.execute(q_corte, (*params, area))
            row_corte = c.fetchone()
            nidos_avanzados = row_corte[0] or 0
            stats["avances_pzs"][area] = nidos_avanzados
            pct = (nidos_avanzados / total_nidos * 100) if total_nidos > 0 else 100.0 if total_nidos == 0 else 0
            stats["avances_pct"][area] = min(100.0, round(pct, 1))
        else:
            # Calcular cuántas piezas realmente pasan por esta área
            q_tot_pzs = f"""
                SELECT SUM(p.cantidad * n.hojas)
                FROM piezas p
                JOIN nidos n ON p.of_number = n.of_number AND p.nido = n.nido
                {where_p} {'AND' if where_p else 'WHERE'} p.ruta LIKE ?
            """
            c.execute(q_tot_pzs, (*params, f"%{area}%"))
            tot_row = c.fetchone()
            total_piezas_area = tot_row[0] or 0
            
            # Para las demas areas, sumamos las piezas
            q_av_pzs = f"""
                SELECT SUM(a.cantidad)
                FROM avances a
                {where_a} {'AND' if where_a else 'WHERE'} a.area = ?
            """
            c.execute(q_av_pzs, (*params, area))
            av_row = c.fetchone()
            pzs_avanzadas = av_row[0] or 0
            
            # Restar rechazos de esta area
            q_rech = f"SELECT SUM(cantidad) FROM rechazos {where_clause} {'AND' if where_clause else 'WHERE'} area = ?"
            c.execute(q_rech, (*params, area))
            rech_row = c.fetchone()
            pzs_rechazadas = rech_row[0] or 0
            
            pzs_reales = max(0, pzs_avanzadas - pzs_rechazadas)
            stats["avances_pzs"][area] = pzs_reales
            
            pct = (pzs_reales / total_piezas_area * 100) if total_piezas_area > 0 else 100.0 if total_piezas_area == 0 else 0
            stats["avances_pct"][area] = min(100.0, round(pct, 1))
            
    conn.close()
    return stats

def get_personal_prenomina():
    """Carga la lista de personal de la prenomina desde local o GitHub raw url."""
    import os
    import pandas as pd
    import streamlit as st
    url_github = "https://raw.githubusercontent.com/jesusalbertomoraleslopez-byte/sigrama-prenomina-app/main/personal.xlsx"
    local_path = "../sigrama-prenomina-app/personal.xlsx"
    try:
        if os.path.exists(local_path):
            df = pd.read_excel(local_path)
        else:
            df = pd.read_excel(url_github)
        return df
    except Exception as e:
        return pd.DataFrame(columns=["id_empleado", "nombre", "area"])

def check_and_seed_personal_areas(cursor):
    """Sincroniza el catálogo de prenomina con personal_areas en la base de datos local."""
    df_pers = get_personal_prenomina()
    if df_pers.empty:
        return
        
    # Obtener qué operadores ya tienen registros de áreas configurados
    cursor.execute("SELECT DISTINCT operador_nombre FROM personal_areas")
    existing_ops = {row[0] for row in cursor.fetchall()}
    
    # Mapeo predeterminado de áreas de Prenómina a las de nuestra App
    default_mapping = {
        "✂️ Corte Laser": ["Corte", "Rebabeo", "Barrenado"],
        "📐 Doblez": ["Doblez", "Rebabeo", "Barrenado"],
        "🎨 Pintura": ["Pintura"],
        "⚙️ Ingeniería": ["Ingenieria"],
        "📦 Embarque": ["Empaque", "Liberado"],
        "👑 Dirección": ["Liberado"]
    }
    
    for _, row in df_pers.iterrows():
        nombre = str(row['nombre']).strip().upper()
        area_prenomina = str(row['area']).strip()
        
        if nombre and nombre not in existing_ops and nombre != 'NAN':
            # Seeding de áreas por defecto
            areas_to_assign = default_mapping.get(area_prenomina, [])
            for area in areas_to_assign:
                try:
                    cursor.execute(
                        "INSERT OR IGNORE INTO personal_areas (operador_nombre, area) VALUES (?, ?)",
                        (nombre, area)
                    )
                except Exception:
                    pass

def get_operadores_por_area(area):
    """Devuelve la lista de nombres de operadores autorizados para un área."""
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("CREATE TABLE IF NOT EXISTS personal_areas (operador_nombre TEXT NOT NULL, area TEXT NOT NULL, PRIMARY KEY (operador_nombre, area))")
        c.execute("SELECT DISTINCT operador_nombre FROM personal_areas WHERE area=?", (area,))
        ops = [row[0] for row in c.fetchall()]
    except Exception:
        ops = []
    conn.close()
    ops.sort()
    
    # Si está vacía, hacer fallback a todos los de prenomina
    if not ops:
        df_pers = get_personal_prenomina()
        if not df_pers.empty:
            ops = df_pers['nombre'].astype(str).str.strip().str.upper().dropna().unique().tolist()
            ops.sort()
    return ops
