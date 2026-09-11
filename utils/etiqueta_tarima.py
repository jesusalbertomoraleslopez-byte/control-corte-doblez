"""
utils/etiqueta_tarima.py
Generador de Etiqueta PDF por PIEZA en Tarima WIP -- SIGRAMA
Cada etiqueta es para UNA PIEZA específica dentro de una tarima.
Una tarima física puede tener múltiples etiquetas (una por tipo de pieza).
ID de Tarima: T-WIP-XXXXX
"""
import io
from fpdf import FPDF
from utils.database import get_connection, get_local_now


# ─────────────────────────────────────────────────────────────────────────────
# DATA HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def get_next_twip_id() -> str:
    """Genera el siguiente ID de Tarima WIP con formato T-WIP-XXXXX."""
    from utils.database import get_connection
    conn = get_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tarimas_wip (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                twip_id     TEXT UNIQUE NOT NULL,
                of_number   TEXT,
                nido        TEXT,
                no_pieza    TEXT,
                int_id      INTEGER,
                cantidad    INTEGER,
                auditor     TEXT,
                timestamp   TEXT
            )
        """)
        conn.commit()
        row = conn.execute("SELECT MAX(id) FROM tarimas_wip").fetchone()
        next_num = (row[0] or 0) + 1
    finally:
        conn.close()
    return f"T-WIP-{next_num:05d}"


def get_pieza_data(of_number: str, nido: str, no_pieza: str) -> dict:
    """Obtiene todos los datos necesarios para generar la etiqueta de UNA pieza en tarima."""
    conn = get_connection()
    import pandas as pd

    # Datos de la orden
    df_orden = pd.read_sql_query(
        "SELECT of_number, po, proyecto, proyecto_cliente, calibre, descripcion_pronest FROM ordenes WHERE of_number = ?",
        conn, params=(of_number,)
    )
    # Datos del nido
    df_nido = pd.read_sql_query(
        "SELECT hojas, calibre FROM nidos WHERE of_number = ? AND nido = ?",
        conn, params=(of_number, nido)
    )
    # Datos de la pieza específica (INT = id en tabla piezas)
    df_pieza = pd.read_sql_query(
        "SELECT id, no_pieza, nombre_pieza, cantidad FROM piezas WHERE of_number = ? AND nido = ? AND no_pieza = ?",
        conn, params=(of_number, nido, no_pieza)
    )
    # Avances actuales para determinar proceso actual
    df_avances = pd.read_sql_query(
        """SELECT area, SUM(cantidad) as total FROM avances
           WHERE of_number = ? AND nido = ? AND no_pieza = ? GROUP BY area""",
        conn, params=(of_number, nido, no_pieza)
    )
    conn.close()

    orden_procesos = ["Ingenieria", "Corte", "Rebabeo", "Doblez", "Barrenado", "Pintura", "Liberado", "Empaque"]
    proceso_actual = "Ingenieria"
    if not df_avances.empty:
        areas_con_avance = df_avances[df_avances['total'] > 0]['area'].tolist()
        for proc in reversed(orden_procesos):
            if proc in areas_con_avance:
                proceso_actual = proc
                break

    proceso_siguiente = {
        "Ingenieria": "Corte",
        "Corte": "Rebabeo",
        "Rebabeo": "Doblez",
        "Doblez": "Barrenado",
        "Barrenado": "Pintura",
        "Pintura": "Liberado",
        "Liberado": "Empaque",
        "Empaque": "PT"
    }.get(proceso_actual, "PT")

    nido_info = df_nido.iloc[0] if not df_nido.empty else None
    orden_info = df_orden.iloc[0] if not df_orden.empty else None
    pieza_info = df_pieza.iloc[0] if not df_pieza.empty else None

    hojas = int(nido_info['hojas']) if nido_info is not None else 1
    calibre = str(nido_info.get('calibre', '') or '') if nido_info is not None else ''
    if not calibre and orden_info is not None:
        calibre = str(orden_info.get('calibre', '') or '')

    po = str(orden_info.get('po', '') or '--') if orden_info is not None else '--'
    proyecto = str(orden_info.get('proyecto_cliente') or orden_info.get('proyecto', '') or '--') if orden_info is not None else '--'

    cant_por_hoja = int(pieza_info['cantidad']) if pieza_info is not None else 0
    cant_total = cant_por_hoja * hojas
    int_id = int(pieza_info['id']) if pieza_info is not None else 0
    nombre_pieza = str(pieza_info.get('nombre_pieza', '') or '') if pieza_info is not None else ''

    return {
        "of": of_number,
        "nido": nido,
        "no_pieza": no_pieza,
        "nombre_pieza": nombre_pieza,
        "int_id": int_id,
        "hojas": hojas,
        "calibre": calibre,
        "po": po,
        "proyecto": proyecto[:35],
        "cantidad_sistema": cant_total,
        "cant_por_hoja": cant_por_hoja,
        "proceso_actual": proceso_actual,
        "proceso_siguiente": proceso_siguiente,
        "fecha_emision": get_local_now().strftime("%d/%m/%Y  %H:%M"),
    }


# ─────────────────────────────────────────────────────────────────────────────
# PDF GENERATOR
# ─────────────────────────────────────────────────────────────────────────────

class EtiquetaPDF(FPDF):
    ROJO = (236, 32, 36)
    NEGRO = (17, 17, 17)
    GRIS_OSCURO = (60, 60, 60)
    GRIS_MEDIO = (130, 130, 130)
    GRIS_CLARO = (230, 230, 230)
    BLANCO = (255, 255, 255)

    def footer(self):
        self.set_y(-10)
        self.set_font("Helvetica", "I", 6)
        self.set_text_color(*self.GRIS_MEDIO)
        self.cell(0, 4,
            f"SIGRAMA - Sistema de Control de Produccion  |  {get_local_now().strftime('%d/%m/%Y %H:%M')}",
            align="C")


def _draw_label_page(pdf: EtiquetaPDF, data: dict, twip_id: str):
    """Dibuja una página de etiqueta para una pieza."""
    pdf.add_page()

    # ── BARRA NEGRA SUPERIOR ──────────────────────────────────────────────────
    pdf.set_fill_color(*EtiquetaPDF.NEGRO)
    pdf.rect(0, 0, 216, 20, "F")

    pdf.set_xy(12, 3)
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(*EtiquetaPDF.ROJO)
    pdf.cell(60, 8, "SIGRAMA", ln=0)

    pdf.set_xy(80, 3)
    pdf.set_font("Helvetica", "B", 13)
    pdf.set_text_color(*EtiquetaPDF.BLANCO)
    pdf.cell(125, 8, "ETIQUETA TARIMA WIP", align="R", ln=0)

    pdf.set_xy(12, 12)
    pdf.set_font("Helvetica", "", 7)
    pdf.set_text_color(*EtiquetaPDF.GRIS_CLARO)
    pdf.cell(80, 5, "industria  |  Control de Producción", ln=0)

    # ── FRANJA ROJA DE PROCESO ────────────────────────────────────────────────
    pdf.set_fill_color(*EtiquetaPDF.ROJO)
    pdf.rect(0, 20, 216, 9, "F")
    pdf.set_xy(0, 21.5)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(*EtiquetaPDF.BLANCO)
    pdf.cell(216, 6,
        f"PROCESO ACTUAL: {data['proceso_actual'].upper()}   >>   SIGUIENTE: {data['proceso_siguiente'].upper()}",
        align="C")

    # ── ID TARIMA (prominente) ────────────────────────────────────────────────
    pdf.set_fill_color(245, 245, 245)
    pdf.rect(12, 33, 192, 18, "F")
    pdf.set_xy(12, 34)
    pdf.set_font("Helvetica", "", 7)
    pdf.set_text_color(*EtiquetaPDF.GRIS_MEDIO)
    pdf.cell(96, 4, "ID TARIMA WIP", ln=0)
    pdf.set_xy(110, 34)
    pdf.cell(92, 4, "No. INTERNO (INT)", ln=0)

    pdf.set_xy(12, 38)
    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(*EtiquetaPDF.ROJO)
    pdf.cell(96, 10, twip_id, ln=0)

    pdf.set_xy(110, 38)
    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(*EtiquetaPDF.NEGRO)
    pdf.cell(92, 10, f"INT {data['int_id']:03d}", ln=0)

    # ── BLOQUE PRINCIPAL DE DATOS ─────────────────────────────────────────────
    # Rejilla 2 columnas
    def field(x, y, label, value, bold_value=True, val_color=None, label_size=7, val_size=11):
        pdf.set_xy(x, y)
        pdf.set_font("Helvetica", "", label_size)
        pdf.set_text_color(*EtiquetaPDF.GRIS_MEDIO)
        pdf.cell(93, 4, label.upper(), ln=0)
        pdf.set_xy(x, y + 4)
        pdf.set_font("Helvetica", "B" if bold_value else "", val_size)
        pdf.set_text_color(*(val_color or EtiquetaPDF.NEGRO))
        pdf.cell(93, 6, str(value), ln=0)

    # Fondo datos
    pdf.set_fill_color(252, 252, 252)
    pdf.set_draw_color(*EtiquetaPDF.GRIS_CLARO)
    pdf.rect(12, 55, 192, 60, "FD")

    field(15, 57, "Orden de Fabricación (OF)", data['of'], val_color=EtiquetaPDF.ROJO)
    field(110, 57, "Orden de Compra (OC / PO)", data['po'])

    field(15, 70, "Nido", data['nido'])
    field(110, 70, "Calibre", data['calibre'])

    field(15, 83, "Proyecto / Cliente", data['proyecto'])
    field(110, 83, "Hojas de Lámina en Nido", str(data['hojas']))

    # ── PIEZA DESTACADA ───────────────────────────────────────────────────────
    pdf.set_fill_color(*EtiquetaPDF.NEGRO)
    pdf.rect(12, 120, 192, 8, "F")
    pdf.set_xy(12, 121)
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_text_color(*EtiquetaPDF.BLANCO)
    pdf.cell(192, 6, "  PIEZA EN ESTA TARIMA", ln=0)

    # Fila de la pieza
    pdf.set_fill_color(255, 255, 255)
    pdf.set_draw_color(*EtiquetaPDF.GRIS_CLARO)
    pdf.rect(12, 128, 192, 30, "FD")

    pdf.set_xy(15, 130)
    pdf.set_font("Helvetica", "", 6.5)
    pdf.set_text_color(*EtiquetaPDF.GRIS_MEDIO)
    pdf.cell(80, 3.5, "No. DE PIEZA", ln=0)
    pdf.set_xy(100, 130)
    pdf.cell(60, 3.5, "DESCRIPCIÓN / NOMBRE", ln=0)
    pdf.set_xy(163, 130)
    pdf.cell(38, 3.5, "CANTIDAD SISTEMA", align="C", ln=0)

    pdf.set_xy(15, 134)
    pdf.set_font("Helvetica", "B", 13)
    pdf.set_text_color(*EtiquetaPDF.NEGRO)
    pdf.cell(82, 8, data['no_pieza'], ln=0)

    pdf.set_xy(100, 134)
    pdf.set_font("Helvetica", "", 8)
    nombre_corto = data['nombre_pieza'][:38] if data['nombre_pieza'] else '--'
    pdf.cell(60, 8, nombre_corto, ln=0)

    pdf.set_xy(163, 133)
    pdf.set_font("Helvetica", "B", 22)
    pdf.set_text_color(*EtiquetaPDF.ROJO)
    pdf.cell(38, 12, str(data['cantidad_sistema']), align="C", ln=0)

    pdf.set_xy(163, 146)
    pdf.set_font("Helvetica", "", 6)
    pdf.set_text_color(*EtiquetaPDF.GRIS_MEDIO)
    pdf.cell(38, 4, f"({data['cant_por_hoja']} x {data['hojas']} hojas)", align="C", ln=0)

    # ── SECCIÓN AUDITORÍA FÍSICA ──────────────────────────────────────────────
    pdf.set_fill_color(*EtiquetaPDF.GRIS_CLARO)
    pdf.rect(12, 163, 192, 7, "F")
    pdf.set_xy(12, 164)
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_text_color(*EtiquetaPDF.NEGRO)
    pdf.cell(192, 5, "  REGISTRO DE INVENTARIO FÍSICO", ln=0)

    y_a = 173
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(*EtiquetaPDF.GRIS_OSCURO)

    # Línea 1: fecha, auditor
    pdf.set_xy(12, y_a)
    pdf.cell(32, 5, "Fecha de Inventario:", ln=0)
    pdf.set_draw_color(*EtiquetaPDF.GRIS_MEDIO)
    pdf.line(46, y_a + 4.5, 98, y_a + 4.5)

    pdf.set_xy(102, y_a)
    pdf.cell(24, 5, "Realizado por:", ln=0)
    pdf.line(128, y_a + 4.5, 204, y_a + 4.5)

    y_a += 12
    # Línea 2: conteo físico y desviación
    pdf.set_xy(12, y_a)
    pdf.cell(28, 5, "Conteo Físico:", ln=0)
    # Cuadro grande para escribir el número contado
    pdf.set_fill_color(255, 255, 255)
    pdf.set_draw_color(*EtiquetaPDF.NEGRO)
    pdf.rect(42, y_a - 1, 22, 10, "FD")

    pdf.set_xy(68, y_a)
    pdf.set_text_color(*EtiquetaPDF.GRIS_OSCURO)
    pdf.cell(18, 5, "Desviación:", ln=0)
    pdf.rect(88, y_a - 1, 18, 10, "FD")

    pdf.set_xy(110, y_a)
    pdf.cell(8, 5, "¿OK?", ln=0)
    pdf.set_draw_color(*EtiquetaPDF.GRIS_MEDIO)
    pdf.rect(120, y_a, 6, 5, "D")   # checkbox SI
    pdf.set_xy(127, y_a)
    pdf.cell(8, 5, "SI", ln=0)
    pdf.rect(137, y_a, 6, 5, "D")   # checkbox NO
    pdf.set_xy(144, y_a)
    pdf.cell(8, 5, "NO", ln=0)

    y_a += 14
    # Línea 3: observaciones
    pdf.set_xy(12, y_a)
    pdf.set_text_color(*EtiquetaPDF.GRIS_OSCURO)
    pdf.cell(28, 5, "Observaciones:", ln=0)
    pdf.set_draw_color(*EtiquetaPDF.GRIS_MEDIO)
    pdf.line(42, y_a + 4.5, 204, y_a + 4.5)

    # ── PIE NEGRO ─────────────────────────────────────────────────────────────
    pdf.set_fill_color(*EtiquetaPDF.NEGRO)
    pdf.rect(0, 225, 216, 8, "F")
    pdf.set_xy(12, 226)
    pdf.set_font("Helvetica", "", 6.5)
    pdf.set_text_color(*EtiquetaPDF.GRIS_CLARO)
    pdf.cell(100, 5,
        f"{twip_id}  |  INT {data['int_id']:03d}  |  {data['of']}  |  {data['nido']}  |  Emitida: {data['fecha_emision']}",
        ln=0)
    pdf.set_text_color(*EtiquetaPDF.ROJO)
    pdf.cell(92, 5, "industria SIGRAMA", align="R", ln=0)


def generar_etiqueta_pieza_pdf(of_number: str, nido: str, no_pieza: str,
                                twip_id: str = None) -> bytes:
    """
    Genera el PDF de etiqueta para UNA PIEZA en una tarima WIP.
    Si twip_id es None, genera uno nuevo con get_next_twip_id().
    Retorna bytes del PDF.
    """
    if twip_id is None:
        twip_id = get_next_twip_id()

    data = get_pieza_data(of_number, nido, no_pieza)
    pdf = EtiquetaPDF(orientation="P", unit="mm", format="Letter")
    pdf.set_auto_page_break(auto=False)
    pdf.set_margins(0, 0, 0)
    _draw_label_page(pdf, data, twip_id)
    return bytes(pdf.output())


def generar_etiqueta_pieza_stream(of_number: str, nido: str, no_pieza: str,
                                   twip_id: str = None) -> io.BytesIO:
    """Retorna BytesIO del PDF listo para st.download_button."""
    raw = generar_etiqueta_pieza_pdf(of_number, nido, no_pieza, twip_id)
    buf = io.BytesIO(raw)
    buf.seek(0)
    return buf


def generar_multiples_etiquetas_pdf(piezas: list, twip_id: str = None) -> bytes:
    """
    Genera un PDF con UNA PÁGINA POR PIEZA.
    piezas = [{'of_number': ..., 'nido': ..., 'no_pieza': ...}, ...]
    Si twip_id es None, se asigna uno compartido para todas.
    """
    if twip_id is None:
        twip_id = get_next_twip_id()

    pdf = EtiquetaPDF(orientation="P", unit="mm", format="Letter")
    pdf.set_auto_page_break(auto=False)
    pdf.set_margins(0, 0, 0)

    for p in piezas:
        data = get_pieza_data(p['of_number'], p['nido'], p['no_pieza'])
        _draw_label_page(pdf, data, twip_id)

    return bytes(pdf.output())


def generar_multiples_etiquetas_stream(piezas: list, twip_id: str = None) -> io.BytesIO:
    """Retorna BytesIO con todas las etiquetas en un solo PDF."""
    raw = generar_multiples_etiquetas_pdf(piezas, twip_id)
    buf = io.BytesIO(raw)
    buf.seek(0)
    return buf
