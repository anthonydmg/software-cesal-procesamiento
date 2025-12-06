from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, A3, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, 
    Spacer, Image, PageBreak, Frame, PageTemplate, NextPageTemplate
)
from PIL import Image as PILImage

# --- CONFIGURACIÓN DE COLORES ---
COLOR_AZUL_OSCURO = colors.HexColor("#003366")
COLOR_AZUL_CLARO = colors.HexColor("#e6f2ff")
COLOR_NARANJA = colors.HexColor("#ffcc80") 
COLOR_GRIS_CLARO = colors.HexColor("#f2f2f2")
COLOR_VERDE = colors.HexColor("#008000")

# --- 1. FUNCIÓN PARA PÁGINAS A4 (Logos + Pie de página) ---
def dibujar_pagina_a4(canvas, doc):
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
    logo_izq = "./assets/CITE_logo.jpg"
    
    logo_cesal = "./assets/cesal-logo.png"
    logo_der = "./assets/INICTEL-LOGO.jpg"

    logo_height = 40
    logo_width = 100 # Ancho máximo estimado (puedes ajustar)
    y_pos = doc.pagesize[1] - 50 
    
    # Logo Izquierdo
    try:
        x_pos =  doc.leftMargin - 175
        canvas.drawImage(logo_izq, x_pos, y_pos, height=logo_height, preserveAspectRatio=True, mask='auto')
    except:
         canvas.setFillColor(colors.lightgrey)
         canvas.rect(doc.leftMargin, y_pos, 50, logo_height, fill=1)

    # Logo Derecho
    try:
        page_width = doc.pagesize[0]
        x_pos = page_width - doc.rightMargin - 100 
        canvas.drawImage(logo_der, x_pos, y_pos, width=logo_width, height=logo_height, preserveAspectRatio=True, anchor='ne', mask='auto')
    except Exception as e:
        print(f"Ocurrió un error: {e}")
        canvas.setFillColor(colors.lightgrey)
        canvas.rect(doc.pagesize[0] - doc.rightMargin - 50, y_pos, 50, logo_height, fill=1)
    

    try:
        page_width = doc.pagesize[0]
        x_pos = page_width - doc.rightMargin - 170 
        canvas.drawImage(logo_cesal, x_pos, y_pos, width=logo_width, height=logo_height, preserveAspectRatio=True, anchor='ne', mask='auto')
    except Exception as e:
        print(f"Ocurrió un error: {e}")
        canvas.setFillColor(colors.lightgrey)
        canvas.rect(doc.pagesize[0] - doc.rightMargin - 50, y_pos, 50, logo_height, fill=1)

    canvas.restoreState()

# --- 2. FUNCIÓN PARA PÁGINA A3 (Imagen Full) ---
def dibujar_pagina_final_a3(canvas, doc):
    """ Dibuja la imagen gigante en A3 """
    canvas.saveState()
    ruta_imagen_full = "20250819_184004.tif" 
    ancho_hoja = landscape(A3)[0]
    alto_hoja = landscape(A3)[1]
    
    try:
        # 1. Abrimos la imagen usando Pillow primero
        pil_img = PILImage.open(ruta_imagen_full)
        
        # 2. Convertimos explícitamente a "RGBA". 
        # La 'A' es el canal Alfa. Esto suele arreglar el problema del fondo negro en TIFs.
        pil_img_rgba = pil_img.convert("RGBA")

        canvas.drawImage(ruta_imagen_full, 0, 0, width=ancho_hoja, height=alto_hoja, preserveAspectRatio=True, mask='auto')
    except:
        canvas.setFillColor(colors.white)
        canvas.rect(0, 0, ancho_hoja, alto_hoja, fill=1)
        canvas.setFillColor(colors.white)
        canvas.drawString(100, alto_hoja/2, "Error: No se encontró mapa_arboles.jpg")
        
    canvas.restoreState()

# --- FUNCIÓN PRINCIPAL ---
def crear_reporte(filename):
    # Márgenes ajustados (topMargin alto para logos)
    doc = SimpleDocTemplate(filename, pagesize=A4, 
                            rightMargin=30, leftMargin=30, 
                            topMargin=70, bottomMargin=30)
    
    # --- DEFINICIÓN EXPLÍCITA DE PLANTILLAS ---
    
    # 1. Plantilla NORMAL (A4): La definimos explícitamente primero.
    # Usamos un Frame que respete los márgenes del doc
    frame_a4 = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id='normal')
    template_a4 = PageTemplate(id='Normal', frames=[frame_a4], onPage=dibujar_pagina_a4, pagesize=A4)
    
    # 2. Plantilla GIGANTE (A3): Para la última página
    ancho_a3, alto_a3 = landscape(A3)
    frame_a3 = Frame(0, 0, ancho_a3, alto_a3, id='FrameA3', showBoundary=0)
    template_a3 = PageTemplate(id='PlantillaMapaGigante', frames=[frame_a3], onPage=dibujar_pagina_final_a3, pagesize=landscape(A3))
    
    # Agregamos AMBAS plantillas. Al poner 'template_a4' primero, será la default.
    doc.addPageTemplates([template_a4, template_a3])

    elements = []
    styles = getSampleStyleSheet()

    # --- CONTENIDO DEL REPORTE (A4) ---
    
    # ... Datos ...
    info_general = [("Nombre del Análisis:", "Análisis de ejemplo 1"),
                    ("Nombre del Solicitante:", "Carlos Quispe"),
                    ("Localidad:", "Apurimac/ Abancay/ Pichirhua"),
                    ("Area Apox. Terreno:", "0.5 ha"),
                    ("Cantidad de Imágenes:", "331"), 
                    ("Modelo de Cámara:", "M3M"), 
                    ("GSD Promedio:", "0.5 cm/px"), 
                    ("Altura Promedio:", "14.92 m"), 
                    ("Fecha de Captura:", "2024-08-12")]
    datos_arboles = [{"id": i, "diagnostico": "POSIBLE DEFICIENCIA" if i in [2,11,15,19] else "SALUDABLE", "ndvi": f"{0.65 if i in [2,11,15,19] else 0.80 + i*0.01:.2f}"} for i in range(1, 51)]

    # ... Títulos y Tablas ...
    title_style = ParagraphStyle('MainTitle', parent=styles['Heading1'], textColor=COLOR_AZUL_OSCURO, alignment=1, fontSize=14, spaceAfter=20)
    elements.append(Paragraph("INFORME DE ANÁLISIS BASADO EN IMÁGENES", title_style))
    elements.append(Spacer(1, 12))
    
    header_section_style = ParagraphStyle('SectionTitle', parent=styles['Heading2'], textColor=COLOR_AZUL_OSCURO, fontSize=12, spaceAfter=5)
    elements.append(Paragraph("I. INFORMACIÓN GENERAL", header_section_style))
    t_line = Table([[""]], colWidths=[530], rowHeights=[2])
    t_line.setStyle(TableStyle([('LINEBELOW', (0,0), (-1,-1), 1, COLOR_AZUL_OSCURO)]))
    elements.append(t_line)
    elements.append(Spacer(1, 15))

    # Tabla Info
    t_info = Table(info_general, colWidths=[150, 380])
    estilo_info = [('FONTNAME', (0,0), (-1,-1), 'Helvetica'), ('FONTSIZE', (0,0), (-1,-1), 9), ('ALIGN', (0,0), (-1,-1), 'LEFT'), ('VALIGN', (0,0), (-1,-1), 'MIDDLE')]
    for i in range(len(info_general)): estilo_info.append(('BACKGROUND', (0, i), (-1, i), COLOR_GRIS_CLARO if i % 2 == 0 else colors.white))
    t_info.setStyle(TableStyle(estilo_info))
    elements.append(t_info)

    elements.append(Spacer(1, 30))
    elements.append(Paragraph("II. RESULTADOS DEL ANÁLISIS", header_section_style))
    elements.append(t_line) 
    elements.append(Spacer(1, 15))

    # Tablas de Árboles
    columnas_por_fila = 5
    chunks = [datos_arboles[i:i + columnas_por_fila] for i in range(0, len(datos_arboles), columnas_por_fila)]
    for chunk in chunks:
        row_ids, row_diag, row_ndvi, orange_cols = [], [], [], []
        for idx, item in enumerate(chunk):
            row_ids.append(str(item['id']))
            row_diag.append(item['diagnostico'])
            row_ndvi.append(item['ndvi'])
            if item['diagnostico'] == "POSIBLE DEFICIENCIA": orange_cols.append(idx)
        while len(row_ids) < columnas_por_fila:
            row_ids.append(""); row_diag.append(""); row_ndvi.append("")
        
        t_res = Table([["Árbol"] + row_ids, ["DIAGNÓSTICO"] + row_diag, ["NDVI Promedio"] + row_ndvi], colWidths=[80] + [80]*6)
        style_res = [('GRID', (0,0), (-1,-1), 0.5, colors.grey), ('FONTSIZE', (0,0), (-1,-1), 7), ('ALIGN', (0,0), (-1,-1), 'CENTER'), ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                     ('BACKGROUND', (0,0), (-1,0), COLOR_AZUL_OSCURO), ('TEXTCOLOR', (0,0), (-1,0), colors.white), ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                     ('BACKGROUND', (0,1), (0,-1), COLOR_GRIS_CLARO), ('FONTSIZE', (0,1), (0,-1), 6), ('LEFTPADDING', (0,1), (0,-1), 0), ('RIGHTPADDING', (0,1), (0,-1), 0)]
        for col_idx in orange_cols: style_res.append(('BACKGROUND', (col_idx + 1, 1), (col_idx + 1, 2), COLOR_NARANJA))
        t_res.setStyle(TableStyle(style_res))
        elements.append(t_res)
        elements.append(Spacer(1, 10))

    elements.append(PageBreak())
    elements.append(Paragraph("III. MAPA DE ÁRBOLES", header_section_style))
    elements.append(t_line)
    elements.append(Spacer(1, 15))
    elements.append(Paragraph("Distribución Espacial del Lote", styles['Normal']))
    
    try:
        utils_img = ImageReader("20250819_184004.tif")
        aspect = utils_img.getSize()[1] / float(utils_img.getSize()[0])
        imagen_mapa = Image("20250819_184004.tif", width=500, height=500 * aspect)
        imagen_mapa.hAlign = 'CENTER'
        elements.append(imagen_mapa)
    except: pass

    elements.append(Spacer(1, 30))
    elements.append(Paragraph("IV. COMENTARIOS", header_section_style))
    elements.append(t_line)
    elements.append(Paragraph("Se sugiere revisión en campo.", ParagraphStyle('C', parent=styles['Normal'], alignment=4)))

    # --- TRANSICIÓN A PÁGINA A3 ---
    elements.append(NextPageTemplate('PlantillaMapaGigante'))
    elements.append(PageBreak())
    elements.append(Paragraph(" ", styles['Normal'])) # Párrafo vacío necesario

    # --- BUILD ---
    # Nota: Ya NO pasamos onFirstPage aquí, porque lo definimos arriba en las plantillas
    doc.build(elements, onFirstPage=dibujar_pagina_a4, onLaterPages=dibujar_pagina_a4)
    print(f"Reporte generado exitosamente: {filename}")

if __name__ == "__main__":
    crear_reporte("reporte_final_corregido.pdf")