from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, A3, landscape
from reportlab.graphics.shapes import Drawing, Circle
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, 
    Spacer, Image, PageBreak, Frame, PageTemplate, NextPageTemplate
)
import os
from svglib.svglib import svg2rlg

from core.utils import resource_path

# --- CONFIGURACIÓN DE COLORES ---
COLOR_AZUL_OSCURO = colors.HexColor("#003366")
COLOR_AZUL_CLARO = colors.HexColor("#e6f2ff")
COLOR_NARANJA = colors.HexColor("#ffcc80") 
COLOR_GRIS_CLARO = colors.HexColor("#f2f2f2")
COLOR_VERDE = colors.HexColor("#008000")


EXAMPLE_GENERAL_INFO = [("Nombre del Análisis:", "Análisis de ejemplo 1"),
                    ("Nombre del Solicitante:", "Carlos Quispe"),
                    ("Localidad:", "Apurimac/ Abancay/ Pichirhua"),
                    ("Area Apox. Terreno:", "0.5 ha"),
                    ("Cantidad de Imágenes:", "331"), 
                    ("Modelo de Cámara:", "M3M"), 
                    ("GSD Promedio:", "0.5 cm/px"), 
                    ("Altura Promedio:", "14.92 m"), 
                    ("Fecha de Captura:", "2024-08-12")]

EXAMPLE_DATOS_ARBOLES = [{"id": i, "N_diagnostico": "POSIBLE DEFICIENCIA" if i in [2,11,15,19] else "SALUDABLE", "ndvi": f"{0.65 if i in [2,11,15,19] else 0.80 + i*0.01:.2f}"} for i in range(1, 51)]

EXAMPLE_COMENTARIOS = "Se sugiere revisión en campo."
EXAMPLE_MAP_IMAGE = "20250819_184004.tif"

def create_dot(color_hex):
    d = Drawing(4*mm, 4*mm)
    c = Circle(2*mm, 2*mm, 1.5*mm)
    c.fillColor = colors.HexColor(color_hex)
    c.strokeColor = None
    d.add(c)
    return d
# --- 1. FUNCIÓN PARA PÁGINAS A4 (Logos + Pie de página) ---
def dibujar_pagina_a4(
        canvas, 
        doc, 
        logo_cite = resource_path(os.path.join("assets", "CITE_logo.jpg")), 
        logo_cesal = resource_path(os.path.join("assets", "cesal-logo.png")),
        logo_inictel = resource_path(os.path.join("assets", "INICTEL-LOGO.jpg"))):
    
    """ Dibuja logos y pie de página solo en hojas A4 """
    canvas.saveState()
    
    # --- Pie de página ---
    styles = getSampleStyleSheet()
    note_style = ParagraphStyle('Note', parent=styles['Normal'], fontSize=8, alignment=1)
    text = "* Nota: Valores de NDVI < 0.70 podrían indicar posibles problemas de salud en el palto."
    p = Paragraph(text, note_style)
    w, h = p.wrap(doc.width, doc.bottomMargin)
    p.drawOn(canvas, doc.leftMargin, 15)

    # --- Encabezado (Logos) ---
    
    logo_height = 40
    logo_width = 100 # Ancho máximo estimado (puedes ajustar)
    y_pos = doc.pagesize[1] - 50 
    
    # # Logo Izquierdo
    # try:
    #     x_pos =  doc.leftMargin - 175
    #     canvas.drawImage(logo_cite, x_pos, y_pos, height=logo_height, preserveAspectRatio=True, mask='auto')
    # except:
    #      canvas.setFillColor(colors.lightgrey)
    #      canvas.rect(doc.leftMargin, y_pos, 50, logo_height, fill=1)

    # # Logo Derecho
    # try:
    #     page_width = doc.pagesize[0]
    #     x_pos = page_width - doc.rightMargin - 100 
    #     canvas.drawImage(logo_inictel, x_pos, y_pos, width=logo_width, height=logo_height, preserveAspectRatio=True, anchor='ne', mask='auto')
    # except Exception as e:
    #     print(f"Ocurrió un error: {e}")
    #     canvas.setFillColor(colors.lightgrey)
    #     canvas.rect(doc.pagesize[0] - doc.rightMargin - 50, y_pos, 50, logo_height, fill=1)
    

    # try:
    #     page_width = doc.pagesize[0]
    #     x_pos = page_width - doc.rightMargin - 170 
    #     canvas.drawImage(logo_cesal, x_pos, y_pos, width=logo_width, height=logo_height, preserveAspectRatio=True, anchor='ne', mask='auto')
    # except Exception as e:
    #     print(f"Ocurrió un error: {e}")
    #     canvas.setFillColor(colors.lightgrey)
    #     canvas.rect(doc.pagesize[0] - doc.rightMargin - 50, y_pos, 50, logo_height, fill=1)

    canvas.restoreState()


# --- 2. FUNCIÓN PARA PÁGINA A3 (Imagen Full) ---
def dibujar_pagina_final_a3(canvas, doc, mapa_image, page_size):
    page_format = A3 if page_size == "A3" else A4
    """ Dibuja la imagen gigante en A3 """
    canvas.saveState()
    ancho_hoja = landscape(page_format)[0]
    alto_hoja = landscape(page_format)[1]
    
    try:
        canvas.drawImage(mapa_image, 0, 0, width=ancho_hoja, height=alto_hoja, preserveAspectRatio=True, mask='auto')
    except:
        canvas.setFillColor(colors.white)
        canvas.rect(0, 0, ancho_hoja, alto_hoja, fill=1)
        canvas.setFillColor(colors.white)
        canvas.drawString(100, alto_hoja/2, "Error: No se encontró mapa_arboles.jpg")
        
    canvas.restoreState()

def add_information_section(general_info, elements, header_section_style, t_line):
    elements.append(Paragraph("I. INFORMACIÓN GENERAL", header_section_style))
    # t_line = Table([[""]], colWidths=[530], rowHeights=[2])
    # t_line.setStyle(TableStyle([('LINEBELOW', (0,0), (-1,-1), 1, COLOR_AZUL_OSCURO)]))
    elements.append(t_line)
    elements.append(Spacer(1, 15))

    # Tabla Info
    t_info = Table(general_info, colWidths=[150, 380])
    estilo_info = [('FONTNAME', (0,0), (-1,-1), 'Helvetica'), ('FONTSIZE', (0,0), (-1,-1), 9), ('ALIGN', (0,0), (-1,-1), 'LEFT'), ('VALIGN', (0,0), (-1,-1), 'MIDDLE')]
    for i in range(len(general_info)): estilo_info.append(('BACKGROUND', (0, i), (-1, i), COLOR_GRIS_CLARO if i % 2 == 0 else colors.white))
    t_info.setStyle(TableStyle(estilo_info))
    elements.append(t_info)

    elements.append(Spacer(1, 30))

def add_results_table_section(trees_data, elements, header_section_style, t_line):
    elements.append(Paragraph("II. RESULTADOS DEL ANÁLISIS", header_section_style))
    elements.append(t_line) 
    elements.append(Spacer(1, 15))

    #sal_trees = [ r for r in trees_result if r['N_class'] == "saludable"]
    #        prec_trees = [r for r in trees_result if r['N_class'] == "precaución"]
    #        def_trees = [ r for r in trees_result if r['N_class'] == "deficiencia"]
    
    # Tablas de Árboles
    columnas_por_fila = 5
    chunks = [trees_data[i:i + columnas_por_fila] for i in range(0, len(trees_data), columnas_por_fila)]
    for chunk in chunks:
        row_ids, row_diag, row_ndvi, orange_cols = [], [], [], []
        for idx, item in enumerate(chunk):
            row_ids.append(str(item['id']))
            row_diag.append(item['N_diagnostico'])
            row_ndvi.append(str(item['ndvi']))
            if item['N_diagnostico'] != "SALUDABLE": orange_cols.append([idx, 1])
            if float(item["ndvi"]) < 0.75: orange_cols.append([idx, 2])
        while len(row_ids) < columnas_por_fila:
            row_ids.append(""); row_diag.append(""); row_ndvi.append("")
        
        t_res = Table([["Árbol"] + row_ids, ["DIAGNÓSTICO N."] + row_diag, ["NDVI Promedio"] + row_ndvi], colWidths=[80] + [80]*6)
        style_res = [('GRID', (0,0), (-1,-1), 0.5, colors.grey), ('FONTSIZE', (0,0), (-1,-1), 7), ('ALIGN', (0,0), (-1,-1), 'CENTER'), ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                     ('BACKGROUND', (0,0), (-1,0), COLOR_AZUL_OSCURO), ('TEXTCOLOR', (0,0), (-1,0), colors.white), ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                     ('BACKGROUND', (0,1), (0,-1), COLOR_GRIS_CLARO), ('FONTSIZE', (0,1), (0,-1), 6), ('LEFTPADDING', (0,1), (0,-1), 0), ('RIGHTPADDING', (0,1), (0,-1), 0)]
        for col_idx, row_idx in orange_cols: style_res.append(('BACKGROUND', (col_idx + 1, row_idx), (col_idx + 1, row_idx), COLOR_NARANJA))
        t_res.setStyle(TableStyle(style_res))
        elements.append(t_res)
        elements.append(Spacer(1, 10))

    elements.append(PageBreak())


def load_svg_icon(filepath, target_size=12):
    """
    Carga un archivo SVG y lo escala al tamaño especificado para ReportLab.
    """
    drawing = svg2rlg(filepath)
    
    if drawing is None:
        return ""  # Retorna vacío si no encuentra el archivo
    
    # Calcular el factor de escala
    scale_x = target_size / drawing.width
    scale_y = target_size / drawing.height
    
    # Aplicar la escala al dibujo
    drawing.width = target_size
    drawing.height = target_size
    drawing.scale(scale_x, scale_y)
    
    return drawing

def add_map_trees_def_n_section(trees_data, map_image, elements, styles, header_section_style, t_line):
    elements.append(Paragraph("III. MAPA DE ÁRBOLES CON POSIBLES DEFICIENCIAS DE NITRÓGENO", header_section_style))
    elements.append(t_line)
    elements.append(Spacer(1, 15))
    
    try:
        utils_img = ImageReader(map_image)
        aspect = utils_img.getSize()[1] / float(utils_img.getSize()[0])
        imagen_mapa = Image(map_image, width=500, height=500 * aspect)
        imagen_mapa.hAlign = 'CENTER'
        elements.append(imagen_mapa)
    except: pass
    elements.append(Spacer(1, 20))
    # =========================================================================
    # NUEVO: TARJETA DE "ANALYSIS BREAKDOWN" (Dinámica)
    # =========================================================================

    # 1. Calcular Estadísticas basándonos en trees_data
    total_trees = len(trees_data)
    deficient_count = 0
    warning_count = 0
    
    ndvi_warn_count = 0
    ndvi_alert_count = 0

    for item in trees_data:
        diag = item.get('N_diagnostico', '')
        if diag == "POSIBLE DEFICIENCIA":
            deficient_count += 1
        elif diag == "POSIBLE NIVEL BAJO":
            warning_count += 1
        ndvi_state = item.get('ndvi_state', '')
        
        if ndvi_state == "precaución":
            ndvi_warn_count += 1
        elif ndvi_state == "posible-problema":
            ndvi_alert_count +=1

    healthy_count = total_trees - deficient_count - warning_count
    
    # Calcular porcentajes (evitando división por cero)
    healthy_pct = f"{round((healthy_count/total_trees)*100, 2)}%" if total_trees > 0 else "0%"
    warning_pct = f"{round((warning_count/total_trees)*100, 2)}%" if total_trees > 0 else "0%"
    deficient_pct = f"{round((deficient_count/total_trees)*100, 2)}%" if total_trees > 0 else "0%"

    # 2. Definir Estilos Locales para la tarjeta
    # Título de la tarjeta
    style_card_header = ParagraphStyle('CardHead', parent=styles['Normal'], fontSize=11, fontName='Helvetica-Bold', spaceAfter=6)
    # Texto de etiquetas
    style_card_label = ParagraphStyle('CardLbl', parent=styles['Normal'], fontSize=10, textColor=colors.black)
    # Texto de valores (alineado a derecha)
    style_card_value = ParagraphStyle('CardVal', parent=styles['Normal'], fontSize=10, textColor=colors.black, alignment=2)

    # 3. Crear los elementos visuales
    # ---------------------------------------------------------
    # 1. Tu Tabla Original (Distribución de Nitrógeno)
    # ---------------------------------------------------------
    dot_green = create_dot("#28a745")   # Verde
    dot_yellow = create_dot("#eab308")  # Amarillo/Naranja
    dot_orange = create_dot("#F97316")  # Naranja oscuro

    # Textos de tu tabla original
    p_header = Paragraph("<b>DISTRIBUCIÓN DE POSIBLES DEFICIENCIAS DE NITROGENO</b>", style_card_header)

    p_lbl_healthy = Paragraph("Saludable", style_card_label)
    p_val_healthy = Paragraph(f"<b>{healthy_count} Árboles ({healthy_pct})</b>", style_card_value)

    p_lbl_warn = Paragraph("Posible Nivel Bajo", style_card_label)
    p_val_warn = Paragraph(f"<b>{warning_count} Árboles ({warning_pct})</b>", style_card_value)

    p_lbl_def = Paragraph("Posible Deficiencia", style_card_label)
    p_val_def = Paragraph(f"<b>{deficient_count} Árboles ({deficient_pct})</b>", style_card_value)

    card_data = [
        [p_header, '', ''], 
        [dot_green, p_lbl_healthy, p_val_healthy],
        [dot_yellow, p_lbl_warn, p_val_warn],
        [dot_orange, p_lbl_def, p_val_def]
    ]

    t_breakdown = Table(card_data, colWidths=[8*mm, 25*mm, 40*mm], hAlign='LEFT')
    t_breakdown.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BACKGROUND', (0,0), (-1,-1), colors.white),
        ('SPAN', (0,0), (-1,0)), 
        ('BOTTOMPADDING', (0,0), (-1,0), 8),
        ('LINEBELOW', (0,0), (-1,0), 1, colors.HexColor("#dcdcdc")),
        ('TOPPADDING', (0,1), (-1,-1), 8),
        ('BOTTOMPADDING', (0,1), (-1,-1), 8),
        ('LINEBELOW', (0,1), (-1,2), 1, colors.HexColor("#f0f0f0")), # Separadores suaves
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#A8D5BA")),
    ]))

    # ---------------------------------------------------------
    # 2. La Nueva Tabla NDVI (Basada en la imagen)
    # ---------------------------------------------------------
    # Variables de ejemplo (Reemplázalas con tus variables reales)
    ndvi_norm_cnt = total_trees - ndvi_alert_count - ndvi_warn_count
    ndvi_norm_pct = round(ndvi_norm_cnt / total_trees, 2)
    ndvi_bajo_pct = round(ndvi_warn_count / total_trees, 2)
    ndvi_muyb_pct = round(ndvi_alert_count / total_trees, 2)

    
    #ndvi_bajo_pct, ndvi_bajo_cnt = "0.94%", 1
    #ndvi_muyb_pct, ndvi_muyb_cnt = "0.01%", 1

    # Usamos etiquetas <font> de ReportLab para darle color exacto a porcentajes y texto gris
    p_ndvi_header = Paragraph("<b>DISTRIBUCION DE NDVI </b>", style_card_header)
    f"<b>{warning_count} Árboles ({warning_pct})</b>"
    p_lbl_norm = Paragraph("Normal", style_card_label)
    p_pct_norm = Paragraph(f"<b>{ndvi_norm_cnt} Árboles ({ndvi_norm_pct})</b>", style_card_value)
    #p_cnt_norm = Paragraph(f"<font color='#6b7280'>({ndvi_norm_cnt} Árboles)</font>", style_card_value)

    p_lbl_bajo = Paragraph("Bajo (Alerta)", style_card_label)
    p_pct_bajo = Paragraph(f"<b>{ndvi_warn_count} Árboles ({ndvi_bajo_pct})</b>", style_card_value)
    #p_cnt_bajo = Paragraph(f"<font color='#6b7280'>({ndvi_bajo_cnt} Árboles)</font>", style_card_value)

    p_lbl_muyb = Paragraph("Muy Bajo (Pos. Problema)", style_card_label)
    p_pct_muyb = Paragraph(f"<b>{ndvi_alert_count} Árboles ({ndvi_muyb_pct})</b>", style_card_value)
    #p_cnt_muyb = Paragraph(f"<font color='#6b7280'>({ndvi_muyb_cnt} Árboles)</font>", style_card_value)
    
    icon_yellow = load_svg_icon(resource_path("assets/warn_icon.svg"), target_size=12)
    icon_orange = load_svg_icon(resource_path("assets/alert_orange_icon.svg"), target_size=12)

    # La primera fila ("Normal") no tiene icono en la imagen, pasamos un string vacío ''
    card_data_ndvi = [
        [p_ndvi_header, '', ''],
        ['', p_lbl_norm, p_pct_norm],
        [icon_yellow, p_lbl_bajo, p_pct_bajo],
        [icon_orange, p_lbl_muyb, p_pct_muyb]
    ]

    # 4 columnas: [Icono, Etiqueta, Porcentaje, Conteo]
    t_ndvi = Table(card_data_ndvi, colWidths=[8*mm, 25*mm, 40*mm], hAlign='LEFT')
    t_ndvi.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BACKGROUND', (0,0), (-1,-1), colors.white),
        ('SPAN', (0,0), (-1,0)), 
        ('BOTTOMPADDING', (0,0), (-1,0), 8),
        ('LINEBELOW', (0,0), (-1,0), 1, colors.HexColor("#dcdcdc")),
        ('TOPPADDING', (0,1), (-1,-1), 8),
        ('BOTTOMPADDING', (0,1), (-1,-1), 8),
        ('LINEBELOW', (0,1), (-1,2), 1, colors.HexColor("#f0f0f0")), # Separadores suaves
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#dcdcdc")), # Borde gris claro
    ]))

    # ---------------------------------------------------------
    # 3. Posicionar ambas tablas LADO a LADO
    # ---------------------------------------------------------
    # Creamos una tabla "contenedor" que sostiene a las dos tablas en una sola fila
    # El espacio en medio (Spacer(5*mm, 0)) actúa como un margen entre las dos tablas
    container_data = [
        [t_breakdown, Spacer(5*mm, 0), t_ndvi]
    ]

    t_container = Table(container_data, colWidths=[73*mm, 5*mm, 73*mm], hAlign='CENTER')
    t_container.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'), # Alinea ambas tablas arriba
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
        ('BOTTOMPADDING', (0,0), (-1,-1), 0),
        ('TOPPADDING', (0,0), (-1,-1), 0),
    ]))

    # Agregamos la tabla contenedora a los elementos del PDF
    elements.append(t_container)

    elements.append(Spacer(1, 30))
    elements.append(PageBreak())


def add_map_trees_def_zn_section(trees_data, map_image, elements, styles, header_section_style, t_line):
    elements.append(Paragraph("IV. MAPA DE ÁRBOLES CON POSIBLES PROBLEMAS ASOCIADOS  ZINC", header_section_style))
    elements.append(t_line)
    elements.append(Spacer(1, 15))
    
    try:
        utils_img = ImageReader(map_image)
        aspect = utils_img.getSize()[1] / float(utils_img.getSize()[0])
        imagen_mapa = Image(map_image, width=500, height=500 * aspect)
        imagen_mapa.hAlign = 'CENTER'
        elements.append(imagen_mapa)
    except: pass
    elements.append(Spacer(1, 20))
    # =========================================================================
    # NUEVO: TARJETA DE "ANALYSIS BREAKDOWN" (Dinámica)
    # =========================================================================

    # 1. Calcular Estadísticas basándonos en trees_data
    total_trees = len(trees_data)
    #deficient_count = 0
    mcari_warn_count = 0
    mcari_alert_count = 0
    # Usamos la misma lógica que usaste para las filas naranjas
    for item in trees_data:
        mcari_state = item.get('mcari_state', '')
        
        if mcari_state == "precaución":
            mcari_warn_count += 1
        elif mcari_state == "posible-problema":
            mcari_alert_count +=1

    print("mcari_warn_count:", mcari_warn_count)
            
    healthy_count = total_trees - mcari_warn_count - mcari_alert_count
    
    # Calcular porcentajes (evitando división por cero)
    healthy_pct = f"{round((healthy_count/total_trees)*100, 2)}%" if total_trees > 0 else "0%"
    mcari_warn_pct = f"{round((mcari_warn_count/total_trees)*100, 2)}%" if total_trees > 0 else "0%"
    mcari_alert_pct = f"{round((mcari_alert_count/total_trees)*100, 2)}%" if total_trees > 0 else "0%"

    # 2. Definir Estilos Locales para la tarjeta
    # Título de la tarjeta
    style_card_header = ParagraphStyle('CardHead', parent=styles['Normal'], fontSize=11, fontName='Helvetica-Bold', spaceAfter=6)
    # Texto de etiquetas
    style_card_label = ParagraphStyle('CardLbl', parent=styles['Normal'], fontSize=10, textColor=colors.black)
    # Texto de valores (alineado a derecha)
    style_card_value = ParagraphStyle('CardVal', parent=styles['Normal'], fontSize=10, textColor=colors.black, alignment=2)

    # 3. Crear los elementos visuales
    dot_green = create_dot("#28a745")   # Verde
    dot_yellow = create_dot("#eab308")  # Amarillo/Naranja
    icon_yellow = load_svg_icon(resource_path("assets/warn_icon.svg"), target_size=12)
    icon_orange = load_svg_icon(resource_path("assets/alert_orange_icon.svg"), target_size=12)
    # Textos
    p_header = Paragraph("<b>Distribución de Árboles con Posibles Problemas de Zinc</b>", style_card_header)
    
    p_lbl_healthy = Paragraph("Saludable", style_card_label)
    p_val_healthy = Paragraph(f"<b>{healthy_count} Árboles ({healthy_pct})</b>", style_card_value)
    
    p_lbl_def = Paragraph("Precaucion (MCARI bajo)", style_card_label)
    p_val_def = Paragraph(f"<b>{mcari_warn_count} Árboles ({mcari_warn_pct})</b>", style_card_value)

    p_lbl_prob = Paragraph("Posible Problema (MCARI my bajo)", style_card_label)
    p_val_prob = Paragraph(f"<b>{mcari_alert_count} Árboles ({mcari_alert_pct})</b>", style_card_value)


    # 4. Armar la data de la Tabla
    # Estructura: [Header], [Green, Label, Val], [Yellow, Label, Val]
    card_data = [
        [p_header, '', ''], 
        [dot_green, p_lbl_healthy, p_val_healthy],
        [icon_yellow, p_lbl_def, p_val_def],
        [icon_orange, p_lbl_prob, p_val_prob]
    ]

    # 5. Crear Tabla y Estilos
    # Anchos: Columna pequeña para el punto, espacio para texto, columna para valor
    t_breakdown = Table(card_data, colWidths=[8*mm, 60*mm, 50*mm], hAlign='LEFT')

    t_breakdown.setStyle(TableStyle([
        # General
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BACKGROUND', (0,0), (-1,-1), colors.white),
        
        # Header (Fila 0)
        ('SPAN', (0,0), (-1,0)), # Fusionar columnas
        ('BOTTOMPADDING', (0,0), (-1,0), 8),
        ('LINEBELOW', (0,0), (-1,0), 1, colors.HexColor("#dcdcdc")), # Línea gris fina
        
        # Filas de datos
        ('TOPPADDING', (0,1), (-1,-1), 8),
        ('BOTTOMPADDING', (0,1), (-1,-1), 8),
        
        # Línea divisoria entre Healthy y Deficient
        ('LINEBELOW', (0,1), (-1,1), 1, colors.HexColor("#dcdcdc")),

        # Borde exterior (Caja verde suave)
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#A8D5BA")),
    ]))

    elements.append(t_breakdown)

    elements.append(Spacer(1, 30))

def add_comment_section(comments, elements, styles, header_section_style, t_line):
    elements.append(Paragraph("V. COMENTARIOS", header_section_style))
    elements.append(t_line)
    elements.append(Paragraph(comments, ParagraphStyle('C', parent=styles['Normal'], alignment=4)))

def crear_reporte(filename,
                  general_info,
                  trees_data,
                  comments,
                  map_image,
                  zinc_map_image,
                  final_page_size = None):
    # Márgenes ajustados (topMargin alto para logos)
    doc = SimpleDocTemplate(filename, pagesize=A4, 
                            rightMargin=30, leftMargin=30, 
                            topMargin=70, bottomMargin=30)
    
    # --- DEFINICIÓN EXPLÍCITA DE PLANTILLAS ---
    
    # 1. Plantilla NORMAL (A4): La definimos explícitamente primero.
    # Usamos un Frame que respete los márgenes del doc
    frame_a4 = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id='normal')
    template_a4 = PageTemplate(id='Normal', frames=[frame_a4], onPage=dibujar_pagina_a4, pagesize = A4)
    
    # 2. Plantilla GIGANTE (A3): Para la última página
    ancho_a3, alto_a3 = landscape(A3)
    
    frame_a3 = Frame(0, 0, ancho_a3, alto_a3, id='FrameA3', showBoundary=0)
    
    if final_page_size:
        on_page_A3_map = lambda canvas, doc: dibujar_pagina_final_a3(canvas, doc, map_image, final_page_size)

        template_a3 = PageTemplate(id='PlantillaMapaGigante', frames=[frame_a3], onPage=on_page_A3_map, pagesize=landscape(A3))
        
        on_page_A3_map_zinc = lambda canvas, doc: dibujar_pagina_final_a3(canvas, doc, zinc_map_image, final_page_size)

        template_a3_zinc = PageTemplate(id='PlantillaMapaGiganteZinc', frames=[frame_a3], onPage=on_page_A3_map_zinc, pagesize=landscape(A3))

        # Agregamos AMBAS plantillas. Al poner 'template_a4' primero, será la default.
        doc.addPageTemplates([template_a4, template_a3, template_a3_zinc])
    else:
        doc.addPageTemplates([template_a4])

    elements = []
    styles = getSampleStyleSheet()

    # --- CONTENIDO DEL REPORTE (A4) ---
    
    # ... Títulos y Tablas ...
    title_style = ParagraphStyle('MainTitle', parent=styles['Heading1'], textColor=COLOR_AZUL_OSCURO, alignment=1, fontSize=14, spaceAfter=20)
    elements.append(Paragraph("INFORME DE ANÁLISIS BASADO EN IMÁGENES", title_style))
    elements.append(Spacer(1, 12))
    
    header_section_style = ParagraphStyle('SectionTitle', parent=styles['Heading2'], textColor=COLOR_AZUL_OSCURO, fontSize=12, spaceAfter=5)
    t_line = Table([[""]], colWidths=[530], rowHeights=[2])
    t_line.setStyle(TableStyle([('LINEBELOW', (0,0), (-1,-1), 1, COLOR_AZUL_OSCURO)]))
    
    # I. INFORMACIÓN GENERAL
    add_information_section(general_info, elements, header_section_style, t_line)

    # II. RESULTADOS DEL ANÁLISIS
    add_results_table_section(trees_data, elements, header_section_style, t_line)

    # III. MAPA DE ÁRBOLES CON POSIBLES DEFICIENCIAS DE NITRÓGENO
    add_map_trees_def_n_section(trees_data, map_image, elements, styles, header_section_style, t_line)

    # IV. MAPA DE ÁRBOLES CON POSIBLES DEFICIENCIAS DE ZINC

    add_map_trees_def_zn_section(trees_data, zinc_map_image, elements, styles, header_section_style, t_line)

    # V. COMENTARIOS
    add_comment_section(comments, elements, styles, header_section_style, t_line)

    # --- TRANSICIÓN A PÁGINA A3 ---
    if final_page_size:
        elements.append(NextPageTemplate('PlantillaMapaGigante'))
        elements.append(PageBreak())
        elements.append(Paragraph(" ", styles['Normal'])) # Párrafo vacío necesario

        elements.append(NextPageTemplate('PlantillaMapaGiganteZinc'))
        elements.append(PageBreak())
        elements.append(Paragraph(" ", styles['Normal'])) # Párrafo vacío necesario

    # --- BUILD ---
    # Nota: Ya NO pasamos onFirstPage aquí, porque lo definimos arriba en las plantillas
    doc.build(elements, onFirstPage=dibujar_pagina_a4, onLaterPages=dibujar_pagina_a4)
    print(f"Reporte generado exitosamente: {filename}")


if __name__ == "__main__":
    crear_reporte("reporte_final_corregido2.pdf",
                  general_info=EXAMPLE_GENERAL_INFO,
                  trees_data=EXAMPLE_DATOS_ARBOLES,
                  comments= EXAMPLE_COMENTARIOS,
                  map_image=EXAMPLE_MAP_IMAGE,
                  final_page_size = "A3")
    

