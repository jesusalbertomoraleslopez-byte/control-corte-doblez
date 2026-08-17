import pandas as pd
import sqlite3
import datetime
import io
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from utils.database import get_connection, get_local_now, get_local_today

def format_date_spanish(dt_str):
    """Format date string YYYY-MM-DD to DD-mmm-YY (e.g. 15-jul-26)."""
    if not dt_str:
        return ""
    try:
        dt = datetime.datetime.strptime(str(dt_str)[:10], "%Y-%m-%d")
        months = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
        months_es = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
        m_idx = dt.month - 1
        return f"{dt.day:02d}-{months_es[m_idx]}-{str(dt.year)[2:]}"
    except Exception:
        return str(dt_str)

def fetch_reporte_consumo_laminas(fecha_inicio=None, fecha_fin=None, calibre_filter=None, of_filter=None):
    """
    Consulta la base de datos para obtener el consumo real de láminas (hojas cortadas en Corte).
    Retorna dataframes formateados y metadatos del reporte.
    """
    conn = get_connection()
    
    where_clauses = ["a.area = 'Corte'"]
    params = []
    
    if fecha_inicio:
        where_clauses.append("DATE(a.timestamp) >= DATE(?)")
        params.append(str(fecha_inicio))
    if fecha_fin:
        where_clauses.append("DATE(a.timestamp) <= DATE(?)")
        params.append(str(fecha_fin))
    if calibre_filter and calibre_filter != "Todos":
        where_clauses.append("COALESCE(NULLIF(n.calibre, ''), NULLIF(o.calibre, ''), 'Cal 16') = ?")
        params.append(calibre_filter)
    if of_filter and of_filter != "Todas":
        where_clauses.append("a.of_number = ?")
        params.append(of_filter)
        
    where_sql = " AND ".join(where_clauses)
    
    # 1. Resumen por OF (idéntico a la imagen del usuario)
    query_ofs = f"""
        SELECT 
            a.of_number as [of_number],
            COUNT(DISTINCT a.nido || '_' || a.hoja) as [hojas_totales],
            COALESCE(NULLIF(n.calibre, ''), NULLIF(o.calibre, ''), 'Cal 16') as [calibre],
            MIN(SUBSTR(a.timestamp, 1, 10)) as [fecha_corte_raw]
        FROM avances a
        LEFT JOIN ordenes o ON a.of_number = o.of_number
        LEFT JOIN nidos n ON a.of_number = n.of_number AND a.nido = n.nido
        WHERE {where_sql}
        GROUP BY a.of_number, COALESCE(NULLIF(n.calibre, ''), NULLIF(o.calibre, ''), 'Cal 16')
        ORDER BY a.of_number ASC
    """
    df_ofs_raw = pd.read_sql_query(query_ofs, conn, params=params)
    
    # 2. Resumen por Calibre / Material
    query_calibres = f"""
        SELECT 
            COALESCE(NULLIF(n.calibre, ''), NULLIF(o.calibre, ''), 'Cal 16') as [calibre],
            COUNT(DISTINCT a.nido || '_' || a.hoja) as [hojas_totales]
        FROM avances a
        LEFT JOIN ordenes o ON a.of_number = o.of_number
        LEFT JOIN nidos n ON a.of_number = n.of_number AND a.nido = n.nido
        WHERE {where_sql}
        GROUP BY COALESCE(NULLIF(n.calibre, ''), NULLIF(o.calibre, ''), 'Cal 16')
        ORDER BY [hojas_totales] DESC
    """
    df_calibres_raw = pd.read_sql_query(query_calibres, conn, params=params)
    
    # 3. Resumen por Fecha
    query_fechas = f"""
        SELECT 
            SUBSTR(a.timestamp, 1, 10) as [fecha_raw],
            COUNT(DISTINCT a.nido || '_' || a.hoja) as [hojas_totales],
            COUNT(DISTINCT a.of_number) as [total_ofs],
            GROUP_CONCAT(DISTINCT COALESCE(NULLIF(n.calibre, ''), NULLIF(o.calibre, ''), 'Cal 16')) as [calibres]
        FROM avances a
        LEFT JOIN ordenes o ON a.of_number = o.of_number
        LEFT JOIN nidos n ON a.of_number = n.of_number AND a.nido = n.nido
        WHERE {where_sql}
        GROUP BY [fecha_raw]
        ORDER BY [fecha_raw] ASC
    """
    df_fechas_raw = pd.read_sql_query(query_fechas, conn, params=params)
    
    # 4. Detalle de nidos y hojas cortadas
    query_detalle = f"""
        SELECT 
            a.of_number as [OF],
            a.nido as [Nido],
            a.hoja as [Hoja #],
            COALESCE(NULLIF(n.calibre, ''), NULLIF(o.calibre, ''), 'Cal 16') as [Calibre],
            a.operador as [Operador],
            a.maquina as [Máquina],
            a.timestamp as [Fecha/Hora Corte]
        FROM avances a
        LEFT JOIN ordenes o ON a.of_number = o.of_number
        LEFT JOIN nidos n ON a.of_number = n.of_number AND a.nido = n.nido
        WHERE {where_sql}
        GROUP BY a.of_number, a.nido, a.hoja
        ORDER BY a.timestamp DESC
    """
    df_detalle = pd.read_sql_query(query_detalle, conn, params=params)
    conn.close()
    
    # Formatear df_ofs para presentación y exportación
    df_ofs = df_ofs_raw.copy()
    if not df_ofs.empty:
        df_ofs["Fecha de Corte"] = df_ofs["fecha_corte_raw"].apply(format_date_spanish)
        df_ofs_display = pd.DataFrame({
            "RESUMEN DE ORDENES DE FABRICACION": df_ofs["of_number"],
            "Cantidad de Hojas Totales (Hojas)": df_ofs["hojas_totales"],
            "Material Calibre": df_ofs["calibre"],
            "Fecha de Corte": df_ofs["Fecha de Corte"]
        })
    else:
        df_ofs_display = pd.DataFrame(columns=[
            "RESUMEN DE ORDENES DE FABRICACION",
            "Cantidad de Hojas Totales (Hojas)",
            "Material Calibre",
            "Fecha de Corte"
        ])

    # Formatear df_calibres con porcentajes
    df_calibres = df_calibres_raw.copy()
    if not df_calibres.empty:
        total_h = df_calibres["hojas_totales"].sum()
        df_calibres["Porcentaje"] = (df_calibres["hojas_totales"] / (total_h if total_h > 0 else 1) * 100).round(1).astype(str) + " %"
        df_calibres_display = pd.DataFrame({
            "Material / Calibre": df_calibres["calibre"],
            "Cantidad de Hojas Cortadas": df_calibres["hojas_totales"],
            "Porcentaje del Consumo Total": df_calibres["Porcentaje"]
        })
    else:
        df_calibres_display = pd.DataFrame(columns=[
            "Material / Calibre",
            "Cantidad de Hojas Cortadas",
            "Porcentaje del Consumo Total"
        ])
        
    # Formatear df_fechas
    df_fechas = df_fechas_raw.copy()
    if not df_fechas.empty:
        df_fechas["Fecha de Corte"] = df_fechas["fecha_raw"].apply(format_date_spanish)
        df_fechas_display = pd.DataFrame({
            "Fecha de Corte": df_fechas["Fecha de Corte"],
            "Hojas Cortadas (Consumo)": df_fechas["hojas_totales"],
            "OFs Atendidas": df_fechas["total_ofs"],
            "Calibres Procesados": df_fechas["calibres"]
        })
    else:
        df_fechas_display = pd.DataFrame(columns=[
            "Fecha de Corte",
            "Hojas Cortadas (Consumo)",
            "OFs Atendidas",
            "Calibres Procesados"
        ])
        
    total_hojas = df_ofs_display["Cantidad de Hojas Totales (Hojas)"].sum() if not df_ofs_display.empty else 0
    total_calibres = df_calibres_display["Material / Calibre"].nunique() if not df_calibres_display.empty else 0
    total_ofs = df_ofs_display["RESUMEN DE ORDENES DE FABRICACION"].nunique() if not df_ofs_display.empty else 0
    
    metadata = {
        "total_hojas": int(total_hojas),
        "total_calibres": int(total_calibres),
        "total_ofs": int(total_ofs),
        "fecha_inicio": format_date_spanish(fecha_inicio) if fecha_inicio else "Histórico",
        "fecha_fin": format_date_spanish(fecha_fin) if fecha_fin else "Actualidad",
        "fecha_emision": get_local_now().strftime("%d-%b-%Y %H:%M"),
        "folio": f"VALE-{get_local_now().strftime('%Y%m%d-%H%M')}"
    }
    
    return {
        "df_ofs": df_ofs_display,
        "df_calibres": df_calibres_display,
        "df_fechas": df_fechas_display,
        "df_detalle": df_detalle,
        "metadata": metadata
    }

def generate_excel_consumo_laminas(df_ofs, df_calibres, df_fechas, df_detalle, metadata):
    """Genera archivo Excel multi-hoja formateado con XlsxWriter."""
    output = io.BytesIO()
    
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        workbook = writer.book
        
        # Estilos corporativos
        header_fmt = workbook.add_format({
            'bold': True,
            'bg_color': '#1F497D',
            'font_color': '#FFFFFF',
            'border': 1,
            'align': 'center',
            'valign': 'vcenter',
            'text_wrap': True
        })
        title_fmt = workbook.add_format({
            'bold': True,
            'font_size': 14,
            'font_color': '#EC2024',
            'align': 'left'
        })
        subtitle_fmt = workbook.add_format({
            'italic': True,
            'font_size': 10,
            'font_color': '#555555'
        })
        data_fmt = workbook.add_format({
            'border': 1,
            'align': 'center',
            'valign': 'vcenter'
        })
        data_left_fmt = workbook.add_format({
            'border': 1,
            'align': 'left',
            'valign': 'vcenter'
        })
        num_fmt = workbook.add_format({
            'border': 1,
            'align': 'center',
            'valign': 'vcenter',
            'num_format': '#,##0'
        })
        total_fmt = workbook.add_format({
            'bold': True,
            'bg_color': '#EFEFEF',
            'border': 1,
            'align': 'center',
            'num_format': '#,##0'
        })

        # --- HOJA 1: RESUMEN POR OF (Diseño exacto al usuario) ---
        df_ofs.to_excel(writer, sheet_name='Resumen por OF', index=False, startrow=3)
        ws_ofs = writer.sheets['Resumen por OF']
        ws_ofs.write(0, 0, "SIGRAMA - VALE Y REPORTE DE CONSUMO DE LÁMINAS (ALMACÉN)", title_fmt)
        ws_ofs.write(1, 0, f"Folio: {metadata['folio']} | Emisión: {metadata['fecha_emision']} | Rango: {metadata['fecha_inicio']} a {metadata['fecha_fin']}", subtitle_fmt)
        
        # Formatear encabezados Hoja 1
        for col_num, value in enumerate(df_ofs.columns.values):
            ws_ofs.write(3, col_num, value, header_fmt)
            
        ws_ofs.set_column('A:A', 45, data_left_fmt)
        ws_ofs.set_column('B:B', 32, num_fmt)
        ws_ofs.set_column('C:C', 20, data_fmt)
        ws_ofs.set_column('D:D', 20, data_fmt)
        
        # Fila de Total acumulado en Hoja 1
        len_ofs = len(df_ofs)
        ws_ofs.write(4 + len_ofs, 0, "TOTAL DE CONSUMO", total_fmt)
        ws_ofs.write_formula(4 + len_ofs, 1, f"=SUM(B5:B{4 + len_ofs})", total_fmt)
        ws_ofs.write(4 + len_ofs, 2, "-", total_fmt)
        ws_ofs.write(4 + len_ofs, 3, "-", total_fmt)

        # --- HOJA 2: RESUMEN POR CALIBRE ---
        df_calibres.to_excel(writer, sheet_name='Resumen por Calibre', index=False, startrow=3)
        ws_cal = writer.sheets['Resumen por Calibre']
        ws_cal.write(0, 0, "RESUMEN DE CONSUMO POR MATERIAL / CALIBRE", title_fmt)
        ws_cal.write(1, 0, f"Folio: {metadata['folio']} | Hojas Totales: {metadata['total_hojas']}", subtitle_fmt)
        for col_num, value in enumerate(df_calibres.columns.values):
            ws_cal.write(3, col_num, value, header_fmt)
        ws_cal.set_column('A:A', 25, data_left_fmt)
        ws_cal.set_column('B:B', 30, num_fmt)
        ws_cal.set_column('C:C', 30, data_fmt)

        # --- HOJA 3: RESUMEN POR FECHA ---
        df_fechas.to_excel(writer, sheet_name='Resumen por Fecha', index=False, startrow=3)
        ws_fec = writer.sheets['Resumen por Fecha']
        ws_fec.write(0, 0, "RESUMEN DIARIO DE CONSUMO DE LÁMINAS", title_fmt)
        for col_num, value in enumerate(df_fechas.columns.values):
            ws_fec.write(3, col_num, value, header_fmt)
        ws_fec.set_column('A:A', 20, data_fmt)
        ws_fec.set_column('B:B', 25, num_fmt)
        ws_fec.set_column('C:C', 20, num_fmt)
        ws_fec.set_column('D:D', 40, data_left_fmt)

        # --- HOJA 4: DETALLE DE HOJAS CORTADAS ---
        df_detalle.to_excel(writer, sheet_name='Detalle Hojas Cortadas', index=False, startrow=3)
        ws_det = writer.sheets['Detalle Hojas Cortadas']
        ws_det.write(0, 0, "DETALLE INDIVIDUAL DE NIDOS Y HOJAS CORTADAS EN PISO", title_fmt)
        for col_num, value in enumerate(df_detalle.columns.values):
            ws_det.write(3, col_num, value, header_fmt)
        ws_det.set_column('A:G', 20, data_fmt)

        # --- HOJA 5: METADATOS ---
        df_meta = pd.DataFrame(list(metadata.items()), columns=["Parámetro", "Valor"])
        df_meta.to_excel(writer, sheet_name='Metadatos y Filtros', index=False)

    return output.getvalue()

def generate_eml_consumo_laminas(df_ofs, df_calibres, metadata):
    """Genera archivo de correo (.eml) en memoria listo para enviar desde cliente de correo."""
    msg = MIMEMultipart('alternative')
    msg['Subject'] = f"[SIGRAMA] Reporte Oficial de Consumo de Láminas - Almacén ({metadata['fecha_inicio']} a {metadata['fecha_fin']})"
    msg['From'] = "sistema_sigrama@planta.com"
    msg['To'] = "almacen@sigrama.com, produccion@sigrama.com"
    
    # Construir HTML de las tablas
    rows_ofs_html = ""
    for _, r in df_ofs.iterrows():
        rows_ofs_html += f"""
        <tr>
            <td style="padding:8px;border:1px solid #ddd;font-family:sans-serif;font-size:12px;">{r['RESUMEN DE ORDENES DE FABRICACION']}</td>
            <td style="padding:8px;border:1px solid #ddd;font-family:sans-serif;font-size:12px;text-align:center;font-weight:bold;color:#EC2024;">{r['Cantidad de Hojas Totales (Hojas)']}</td>
            <td style="padding:8px;border:1px solid #ddd;font-family:sans-serif;font-size:12px;text-align:center;">{r['Material Calibre']}</td>
            <td style="padding:8px;border:1px solid #ddd;font-family:sans-serif;font-size:12px;text-align:center;">{r['Fecha de Corte']}</td>
        </tr>
        """
        
    rows_cal_html = ""
    for _, r in df_calibres.iterrows():
        rows_cal_html += f"""
        <tr>
            <td style="padding:8px;border:1px solid #ddd;font-family:sans-serif;font-size:12px;font-weight:bold;">{r['Material / Calibre']}</td>
            <td style="padding:8px;border:1px solid #ddd;font-family:sans-serif;font-size:12px;text-align:center;color:#1F497D;font-weight:bold;">{r['Cantidad de Hojas Cortadas']}</td>
            <td style="padding:8px;border:1px solid #ddd;font-family:sans-serif;font-size:12px;text-align:center;">{r['Porcentaje del Consumo Total']}</td>
        </tr>
        """
        
    html_content = f"""
    <html>
    <body style="font-family:'Segoe UI',Arial,sans-serif;color:#333;background-color:#f8f9fa;padding:20px;">
        <div style="max-width:750px;margin:0 auto;background:#ffffff;border-radius:8px;border:1px solid #e2e8f0;padding:25px;box-shadow:0 4px 6px rgba(0,0,0,0.05);">
            <div style="border-bottom:3px solid #EC2024;padding-bottom:12px;margin-bottom:20px;">
                <h2 style="color:#1e1e1e;margin:0;font-size:20px;">SIGRAMA — Vale y Reporte Oficial de Consumo de Láminas</h2>
                <p style="color:#718096;margin:4px 0 0 0;font-size:13px;">Notificación automática para descarga de inventario en Almacén</p>
            </div>
            
            <div style="background-color:#edf2f7;border-radius:6px;padding:12px 16px;margin-bottom:20px;font-size:13px;">
                <strong>Folio de Control:</strong> {metadata['folio']}<br>
                <strong>Fecha de Emisión:</strong> {metadata['fecha_emision']}<br>
                <strong>Período de Consumo:</strong> {metadata['fecha_inicio']} a {metadata['fecha_fin']}<br>
                <strong>Total de Hojas Cortadas:</strong> <span style="color:#EC2024;font-weight:bold;font-size:16px;">{metadata['total_hojas']} Hojas</span>
            </div>
            
            <h3 style="color:#1F497D;font-size:15px;margin-bottom:10px;">1. RESUMEN POR ORDEN DE FABRICACIÓN (OF)</h3>
            <table style="width:100%;border-collapse:collapse;margin-bottom:25px;">
                <thead>
                    <tr style="background-color:#1F497D;color:#ffffff;font-size:12px;text-align:center;">
                        <th style="padding:10px;border:1px solid #1F497D;text-align:left;">RESUMEN DE ORDENES DE FABRICACION</th>
                        <th style="padding:10px;border:1px solid #1F497D;">Cantidad de Hojas Totales (Hojas)</th>
                        <th style="padding:10px;border:1px solid #1F497D;">Material Calibre</th>
                        <th style="padding:10px;border:1px solid #1F497D;">Fecha de Corte</th>
                    </tr>
                </thead>
                <tbody>
                    {rows_ofs_html}
                </tbody>
            </table>
            
            <h3 style="color:#1F497D;font-size:15px;margin-bottom:10px;">2. CONSOLIDADO POR TIPO DE MATERIAL / CALIBRE</h3>
            <table style="width:100%;border-collapse:collapse;margin-bottom:25px;">
                <thead>
                    <tr style="background-color:#4A5568;color:#ffffff;font-size:12px;text-align:center;">
                        <th style="padding:10px;border:1px solid #4A5568;text-align:left;">Material / Calibre</th>
                        <th style="padding:10px;border:1px solid #4A5568;">Cantidad de Hojas Cortadas</th>
                        <th style="padding:10px;border:1px solid #4A5568;">Porcentaje del Consumo Total</th>
                    </tr>
                </thead>
                <tbody>
                    {rows_cal_html}
                </tbody>
            </table>
            
            <div style="border-top:1px solid #e2e8f0;padding-top:15px;margin-top:20px;font-size:11px;color:#a0aec0;text-align:center;">
                Este reporte fue generado automáticamente por la plataforma <strong>SIGRAMA - Control de Corte y Doblez</strong>. Favor de procesar la baja correspondiente en el sistema de inventarios de Almacén.
            </div>
        </div>
    </body>
    </html>
    """
    
    msg.attach(MIMEText(html_content, 'html'))
    return msg.as_bytes()

def generate_pdf_consumo_laminas(df_ofs, df_calibres, metadata):
    """Genera documento PDF imprimible oficial con ReportLab 5.0 conteniendo tablas y bloques de firma."""
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, KeepTogether

    pdf_buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        pdf_buffer,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()

    # Estilos de párrafos
    title_style = ParagraphStyle(
        'TitleStyle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=14,
        leading=16,
        textColor=colors.HexColor('#EC2024')
    )
    subtitle_style = ParagraphStyle(
        'SubTitleStyle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=12,
        textColor=colors.HexColor('#1F497D')
    )
    meta_style = ParagraphStyle(
        'MetaStyle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=11,
        textColor=colors.HexColor('#333333')
    )
    cell_header = ParagraphStyle(
        'CellHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=10,
        alignment=1,
        textColor=colors.white
    )
    cell_body_left = ParagraphStyle(
        'CellBodyLeft',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=10,
        alignment=0
    )
    cell_body_center = ParagraphStyle(
        'CellBodyCenter',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=10,
        alignment=1
    )
    cell_body_bold_center = ParagraphStyle(
        'CellBodyBoldCenter',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=10,
        alignment=1,
        textColor=colors.HexColor('#EC2024')
    )

    elements = []

    # 1. Encabezado Corporativo SIGRAMA
    header_data = [
        [
            Paragraph("<b>SIGRAMA</b><br/><font size=8 color='#666'>Ingeniería que da resultados!!</font>", title_style),
            Paragraph(f"<b>VALE Y REPORTE DE CONSUMO DE LÁMINAS</b><br/><font size=8 color='#555'>Folio: {metadata['folio']}</font>", title_style)
        ]
    ]
    header_table = Table(header_data, colWidths=[200, 340])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('ALIGN', (1,0), (1,0), 'RIGHT')
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 8))
    elements.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor('#EC2024'), spaceAfter=10))

    # 2. Resumen Metadatos
    meta_text = f"<b>Período de Consumo:</b> {metadata['fecha_inicio']} al {metadata['fecha_fin']} &nbsp;&nbsp;|&nbsp;&nbsp; <b>Fecha Emisión:</b> {metadata['fecha_emision']} &nbsp;&nbsp;|&nbsp;&nbsp; <b>Total Hojas Cortadas:</b> <font color='#EC2024'><b>{metadata['total_hojas']} Hojas</b></font>"
    elements.append(Paragraph(meta_text, meta_style))
    elements.append(Spacer(1, 10))

    # 3. Tabla Resumen por OF (Idéntica a la imagen del usuario)
    elements.append(Paragraph("1. RESUMEN POR ORDEN DE FABRICACIÓN (OF)", subtitle_style))
    elements.append(Spacer(1, 4))

    table_ofs_data = [
        [
            Paragraph("RESUMEN DE ORDENES DE FABRICACION", cell_header),
            Paragraph("Cantidad de Hojas Totales (Hojas)", cell_header),
            Paragraph("Material Calibre", cell_header),
            Paragraph("Fecha de Corte", cell_header)
        ]
    ]

    for _, r in df_ofs.iterrows():
        table_ofs_data.append([
            Paragraph(str(r['RESUMEN DE ORDENES DE FABRICACION']), cell_body_left),
            Paragraph(str(r['Cantidad de Hojas Totales (Hojas)']), cell_body_bold_center),
            Paragraph(str(r['Material Calibre']), cell_body_center),
            Paragraph(str(r['Fecha de Corte']), cell_body_center)
        ])

    table_ofs = Table(table_ofs_data, colWidths=[240, 110, 95, 95])
    table_ofs.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1F497D')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E0')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F7FAFC')]),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(table_ofs)
    elements.append(Spacer(1, 12))

    # 4. Tabla Resumen por Calibre
    elements.append(Paragraph("2. CONSOLIDADO POR TIPO DE MATERIAL / CALIBRE (PARA DESCARGA EN ALMACÉN)", subtitle_style))
    elements.append(Spacer(1, 4))

    table_cal_data = [
        [
            Paragraph("Material / Calibre", cell_header),
            Paragraph("Cantidad de Hojas Cortadas", cell_header),
            Paragraph("Porcentaje del Consumo Total", cell_header)
        ]
    ]

    for _, r in df_calibres.iterrows():
        table_cal_data.append([
            Paragraph(str(r['Material / Calibre']), cell_body_left),
            Paragraph(str(r['Cantidad de Hojas Cortadas']), cell_body_bold_center),
            Paragraph(str(r['Porcentaje del Consumo Total']), cell_body_center)
        ])

    table_cal = Table(table_cal_data, colWidths=[200, 170, 170])
    table_cal.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4A5568')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E0')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F7FAFC')]),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(table_cal)
    elements.append(Spacer(1, 20))

    # 5. Sección de Firmas Oficiales de Entrega y Recepción
    firmas_heading = Paragraph("<b>AUTORIZACIONES Y VALIDACIÓN DE ENTREGA / RECEPCIÓN EN ALMACÉN</b>", subtitle_style)
    
    firmas_data = [
        [
            Paragraph("<b>ENTREGA: OPERACIÓN / CORTE</b><br/><br/><br/>_____________________________________<br/>Nombre y Firma Jefe de Corte", cell_body_center),
            Paragraph("<b>RECIBE Y DESCARGA: ALMACÉN</b><br/><br/><br/>_____________________________________<br/>Nombre y Firma Encargado Almacén", cell_body_center),
            Paragraph("<b>VO.BO.: SUPERVISIÓN</b><br/><br/><br/>_____________________________________<br/>Nombre y Firma Supervisión Producción", cell_body_center)
        ]
    ]
    firmas_table = Table(firmas_data, colWidths=[180, 180, 180])
    firmas_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#A0AEC0')),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8FAFC'))
    ]))

    elements.append(KeepTogether([firmas_heading, Spacer(1, 6), firmas_table]))

    doc.build(elements)
    return pdf_buffer.getvalue()
