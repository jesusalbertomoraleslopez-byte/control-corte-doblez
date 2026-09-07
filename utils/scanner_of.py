import os
import re
import sqlite3
import pandas as pd

try:
    import streamlit as st
    cache_decorator = st.cache_data(ttl=60)
except Exception:
    cache_decorator = lambda f: f

@cache_decorator
def cargar_catalogo_pos_app():
    """
    Carga el catálogo de Órdenes de Compra (POs) registradas en la App de POs
    (desde po_tracker.db o BD_POs_Cabecera.xlsx).
    """
    possible_paths = [
        r"C:\Users\albertol\.gemini\antigravity\scratch\sigrama_po_tracker\data\po_tracker.db",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sigrama_po_tracker", "data", "po_tracker.db"),
        r"C:\Users\albertol\.gemini\antigravity\scratch\sigrama_po_tracker\data\BD_POs_Cabecera.xlsx"
    ]
    for p in possible_paths:
        if os.path.exists(p):
            try:
                if p.endswith('.db'):
                    conn = sqlite3.connect(p, timeout=10)
                    df = pd.read_sql('''
                        SELECT po, id_interno, proyecto, solicitante, destino, cliente_facturar_a, estatus_general 
                        FROM po_cabecera 
                        ORDER BY 
                            CASE WHEN id_interno IS NOT NULL AND id_interno != '' THEN 0 ELSE 1 END ASC,
                            id_interno DESC, 
                            po DESC
                    ''', conn)
                    conn.close()
                    if not df.empty:
                        return df
                elif p.endswith('.xlsx'):
                    df = pd.read_excel(p)
                    if not df.empty:
                        col_map = {c: str(c).lower().strip() for c in df.columns}
                        df = df.rename(columns=col_map)
                        return df
            except Exception:
                pass
    return pd.DataFrame()

def obtener_opciones_po():
    """
    Retorna (lista_labels, diccionario_lookup, df_pos) para usar en st.selectbox
    """
    df_pos = cargar_catalogo_pos_app()
    labels = ["-- Seleccionar de App de PO's --"]
    lookup = {}
    if not df_pos.empty:
        for _, r in df_pos.iterrows():
            po_val = str(r.get("po", "")).strip()
            if not po_val or po_val.lower() == "nan":
                continue
            proy_val = str(r.get("proyecto", "")).strip() if pd.notnull(r.get("proyecto")) else ""
            id_int = str(r.get("id_interno", "")).strip() if pd.notnull(r.get("id_interno")) else ""
            solic = str(r.get("solicitante", "")).strip() if pd.notnull(r.get("solicitante")) else ""
            
            lbl = f"PO {po_val}"
            if proy_val:
                lbl += f" | {proy_val}"
            if id_int:
                lbl += f" [{id_int}]"
            if solic:
                lbl += f" ({solic})"
                
            labels.append(lbl)
            lookup[lbl] = {
                "po": po_val,
                "proyecto": proy_val,
                "id_interno": id_int,
                "solicitante": solic
            }
    return labels, lookup, df_pos

def buscar_po_sugerida(of_title, labels_po=None, lookup_dict=None):
    """
    Busca si el título de la OF coincide con alguna PO o Proyecto del catálogo.
    Retorna una tupla (po_sug, idx_sug).
    """
    if labels_po is None and lookup_dict is None:
        labels_po, lookup_dict, _ = obtener_opciones_po()
    elif isinstance(labels_po, dict):
        lookup_dict = labels_po
        labels_po, _, _ = obtener_opciones_po()
    elif lookup_dict is None:
        _, lookup_dict, _ = obtener_opciones_po()

    # Detección por regex en el nombre de la OF
    po_detectada = ""
    m_po = re.search(r'(PO\s*(\d+)|(\d{4}[-\s]\d{4})|(\d{7,10}))', of_title, re.IGNORECASE)
    if m_po:
        po_detectada = m_po.group(0).strip()

    if not of_title or not lookup_dict:
        return po_detectada, 0

    of_lower = of_title.lower()
    of_digits = re.sub(r'\D', '', of_title)

    # 1. Búsqueda exacta por PO en el catálogo
    for idx, lbl in enumerate(labels_po):
        data = lookup_dict.get(lbl, {})
        p_num = str(data.get("po", "")).strip()
        p_digits = re.sub(r'\D', '', p_num)
        if p_digits and len(p_digits) >= 5 and p_digits in of_digits:
            return p_num, idx
        if p_num and len(p_num) >= 4 and p_num.lower() in of_lower:
            return p_num, idx

    # 2. Búsqueda por Nombre de Proyecto
    for idx, lbl in enumerate(labels_po):
        data = lookup_dict.get(lbl, {})
        proy = str(data.get("proyecto", "")).strip()
        if proy and len(proy) >= 4 and proy.lower() in of_lower:
            p_num = str(data.get("po", "")).strip()
            return (p_num if p_num else po_detectada), idx

    return po_detectada, 0

def analizar_carpeta_of(folder_path):
    """
    Analiza una carpeta para determinar si contiene los 3 PDFs de ProNest
    y si ya cuenta con el Excel generado.
    """
    res = {
        "resumen": None,
        "nido": None,
        "pieza": None,
        "excel_existente": None
    }
    if not os.path.exists(folder_path):
        return res
    try:
        files = os.listdir(folder_path)
    except Exception:
        return res
        
    for f in files:
        fl = f.lower()
        if fl.endswith(".pdf"):
            if "resumen de trabajo" in fl or "resumen del trabajo" in fl:
                res["resumen"] = f
            elif "detalle del nido de cabezal" in fl or "detalle de nido" in fl:
                res["nido"] = f
            elif "detalle de la pieza" in fl or "detalle de pieza" in fl:
                res["pieza"] = f
        elif fl.endswith(".xlsx") and not f.startswith("~$"):
            res["excel_existente"] = f
    return res

@cache_decorator
def escanear_directorio_ofs(base_dir=r"Z:\14 - ORDENES DE FABRICACION"):
    """
    Escanea recursivamente el directorio de Órdenes de Fabricación
    detectando carpetas principales y subcarpetas de revisión (REVISION 1, REVISION 2, etc.).
    Retorna una lista de diccionarios con el diagnóstico de cada una.
    """
    if not os.path.exists(base_dir):
        return []
        
    resultados = []
    try:
        items = os.listdir(base_dir)
    except Exception:
        return []

    for item in sorted(items):
        full_p = os.path.join(base_dir, item)
        if not os.path.isdir(full_p):
            continue
            
        try:
            subdirs = [d for d in os.listdir(full_p) if os.path.isdir(os.path.join(full_p, d)) and d.lower() != 'nesteos']
        except Exception:
            subdirs = []
            
        subdirs_con_reportes = []
        for d in subdirs:
            diag_sub = analizar_carpeta_of(os.path.join(full_p, d))
            if diag_sub["resumen"] or diag_sub["nido"] or diag_sub["pieza"] or diag_sub["excel_existente"]:
                subdirs_con_reportes.append((d, diag_sub))

        if subdirs_con_reportes:
            for rd, diag in sorted(subdirs_con_reportes, key=lambda x: x[0]):
                target_path = os.path.join(full_p, rd)
                tiene_3_pdfs = bool(diag["resumen"] and diag["nido"] and diag["pieza"])
                tiene_excel = bool(diag["excel_existente"])
                resultados.append({
                    "of_nombre": item,
                    "subcarpeta": rd,
                    "etiqueta": f"{item} / {rd}",
                    "ruta": target_path,
                    "resumen_pdf": diag["resumen"],
                    "nido_pdf": diag["nido"],
                    "pieza_pdf": diag["pieza"],
                    "excel_existente": diag["excel_existente"],
                    "completo": tiene_3_pdfs,
                    "tiene_excel": tiene_excel
                })
        else:
            diag = analizar_carpeta_of(full_p)
            tiene_3_pdfs = bool(diag["resumen"] and diag["nido"] and diag["pieza"])
            tiene_excel = bool(diag["excel_existente"])
            resultados.append({
                "of_nombre": item,
                "subcarpeta": "",
                "etiqueta": item,
                "ruta": full_p,
                "resumen_pdf": diag["resumen"],
                "nido_pdf": diag["nido"],
                "pieza_pdf": diag["pieza"],
                "excel_existente": diag["excel_existente"],
                "completo": tiene_3_pdfs,
                "tiene_excel": tiene_excel
            })
            
    return resultados
