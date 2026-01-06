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
import os

# --- CONFIGURACIÓN DE COLORES ---
COLOR_AZUL_OSCURO = colors.HexColor("#003366")
COLOR_AZUL_CLARO = colors.HexColor("#e6f2ff")
COLOR_NARANJA = colors.HexColor("#ffcc80") 
COLOR_GRIS_CLARO = colors.HexColor("#f2f2f2")
COLOR_VERDE = colors.HexColor("#008000")

# --- 1. FUNCIÓN PARA PÁGINAS A4 (Logos + Pie de página) ---
def dibujar_pagina_a4(canvas, doc):
    """ Dibuja logos y pie de página en TODAS las hojas A4 """
    # --- FILTRO DE SEGURIDAD ---
    # Si la página actual usa la plantilla del Mapa Gigante, NO dibujamos logos.
    if hasattr(doc, 'pageTemplate') and doc.pageTemplate.id == 'PlantillaMapaGigante':
        return

    canvas.saveState()
    
    # --- A. Pie de página (Nota) ---
    styles = getSampleStyleSheet()
    note_style = ParagraphStyle('Note', parent=styles['Normal'], fontSize=8, alignment=1)
    text = "* Nota: Valores de NDVI < 0.70 podrían indicar posibles problemas de salud en el palto."
    p = Paragraph(text, note_style)
    w, h = p.wrap(doc.width, doc.bottomMargin)
    p.drawOn(canvas, doc.leftMargin, 15) # 15 pts desde abajo

    # --- B. Encabezado (Logos) ---
    logo_izq = "./assets/CITE_logo.jpg"
    logo_cesal = "./assets/cesal-logo.png"
    logo_der = "./assets/INICTEL-LOGO.jpg"

    logo_height = 40
    y_pos = doc.pagesize[1] - 55 
    
    # 1. Logo Izquierdo (CITE)
    try:
        x_pos = doc.leftMargin 
        canvas.drawImage(logo_izq, x_pos, y_pos, height=logo_height, preserveAspectRatio=True, mask='auto')
    except:
        canvas.setFillColor(colors.lightgrey)
        canvas.rect(doc.leftMargin, y_pos, 40, logo_height, fill=1)

    # 2. Logo Derecho (INICTEL)
    try:
        page_width = doc.pagesize[0]
        x_pos = page_width - doc.rightMargin - 80 
        canvas.drawImage(logo_der, x_pos, y_pos, height=logo_height, preserveAspectRatio=True, anchor='ne', mask='auto')
    except:
        canvas.setFillColor(colors.lightgrey)
        canvas.rect(doc.pagesize[0] - doc.rightMargin - 40, y_pos, 40, logo_height, fill=1)

    # 3. Logo Central/Derecho (CESAL)
    try:
        page_width = doc.pagesize[0]
        x_pos = page_width - doc.rightMargin - 180 
        canvas.drawImage(logo_cesal, x_pos, y_pos, height=logo_height, preserveAspectRatio=True, anchor='ne', mask='auto')
    except:
        canvas.setFillColor(colors.lightgrey)
        canvas.rect(doc.pagesize[0] - doc.rightMargin - 100, y_pos, 40, logo_height, fill=1)

    canvas.restoreState()

# --- 2. FUNCIÓN PARA PÁGINA A3 (Imagen Full) ---
def dibujar_pagina_final_a3(canvas, doc):
    """ Dibuja la imagen gigante en A3 corrigiendo TIF """
    canvas.saveState()
    ruta_imagen_full = "20250819_184004.tif" 
    
    ancho_hoja = landscape(A3)[0]
    alto_hoja = landscape(A3)[1]
    
    try:
        pil_img = PILImage.open(ruta_imagen_full)
        pil_img_rgba = pil_img.convert("RGBA") 
        canvas.drawImage(pil_img_rgba, 0, 0, width=ancho_hoja, height=alto_hoja, preserveAspectRatio=True, mask='auto')
    except Exception as e:
        canvas.setFillColor(colors.white)
        canvas.rect(0, 0, ancho_hoja, alto_hoja, fill=1)
        canvas.setFillColor(colors.red)
        canvas.setFont("Helvetica-Bold", 12)
        canvas.drawString(50, alto_hoja/2, f"Error imagen: {str(e)} (Verificar ruta)")
        
    canvas.restoreState()

# --- FUNCIÓN PRINCIPAL ---
def crear_reporte(filename):
    doc = SimpleDocTemplate(filename, pagesize=A4, 
                            rightMargin=30, leftMargin=30, 
                            topMargin=75, bottomMargin=30)
    
    # --- DEFINICIÓN DE PLANTILLAS ---
    
    # A. Plantilla A4 ("Normal")
    frame_a4 = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id='normal')
    # CAMBIO: Quitamos 'onPage=dibujar_pagina_a4' de aquí para usarlo globalmente en el build
    template_a4 = PageTemplate(id='Normal', frames=[frame_a4], pagesize=A4, onPage=dibujar_pagina_a4)
    
    # B. Plantilla A3 ("Gigante")
    ancho_a3, alto_a3 = landscape(A3)
    frame_a3 = Frame(0, 0, ancho_a3, alto_a3, id='FrameA3', showBoundary=0)
    template_a3 = PageTemplate(id='PlantillaMapaGigante', frames=[frame_a3], onPage=dibujar_pagina_final_a3, pagesize=landscape(A3))
    
    # C. ASIGNACIÓN FORZADA
    doc.pageTemplates = [template_a4, template_a3]

    elements = []
    styles = getSampleStyleSheet()

    # --- DATOS DE EJEMPLO ---
    info_general = [("Nombre del Análisis:", "Análisis de ejemplo 1"), ("Cantidad de Imágenes:", "331"), ("Modelo de Cámara:", "M3M"), ("GSD Promedio:", "0.5 cm/px"), ("Altura Promedio:", "14.92 m"), ("Fecha de Captura:", "2024-08-12")]
    
    # Generamos suficientes datos para que haya multiples paginas
    datos_arboles = [{"id": i, "diagnostico": "POSIBLE DEFICIENCIA" if i % 5 == 0 else "SALUDABLE", "ndvi": "0.65" if i % 5 == 0 else "0.85"} for i in range(1, 61)]

    # --- SECCIÓN 1: INFO GENERAL ---
    title_style = ParagraphStyle('MainTitle', parent=styles['Heading1'], textColor=COLOR_AZUL_OSCURO, alignment=1, fontSize=14, spaceAfter=20)
    elements.append(Paragraph("INFORME DE ANÁLISIS BASADO EN IMÁGENES", title_style))
    
    header_section_style = ParagraphStyle('SectionTitle', parent=styles['Heading2'], textColor=COLOR_AZUL_OSCURO, fontSize=12, spaceAfter=5)
    elements.append(Paragraph("I. INFORMACIÓN GENERAL", header_section_style))
    
    t_line = Table([[""]], colWidths=[530], rowHeights=[2])
    t_line.setStyle(TableStyle([('LINEBELOW', (0,0), (-1,-1), 1, COLOR_AZUL_OSCURO)]))
    elements.append(t_line)
    elements.append(Spacer(1, 15))

    t_info = Table(info_general, colWidths=[150, 380])
    estilo_info = [('FONTNAME', (0,0), (-1,-1), 'Helvetica'), ('FONTSIZE', (0,0), (-1,-1), 9), ('VALIGN', (0,0), (-1,-1), 'MIDDLE')]
    for i in range(len(info_general)): estilo_info.append(('BACKGROUND', (0, i), (-1, i), COLOR_GRIS_CLARO if i % 2 == 0 else colors.white))
    t_info.setStyle(TableStyle(estilo_info))
    elements.append(t_info)

    # --- SECCIÓN 2: RESULTADOS ---
    elements.append(Spacer(1, 30))
    elements.append(Paragraph("II. RESULTADOS DEL ANÁLISIS", header_section_style))
    elements.append(t_line) 
    elements.append(Spacer(1, 15))

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
        
        data_res = [["Árbol"] + row_ids, ["DIAGNÓSTICO"] + row_diag, ["NDVI Promedio"] + row_ndvi]
        t_res = Table(data_res, colWidths=[80] + [80]*columnas_por_fila)
        
        style_res = [
            ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
            ('FONTSIZE', (0,0), (-1,-1), 7), ('ALIGN', (0,0), (-1,-1), 'CENTER'), ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('BACKGROUND', (0,0), (-1,0), COLOR_AZUL_OSCURO), ('TEXTCOLOR', (0,0), (-1,0), colors.white), ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('BACKGROUND', (0,1), (0,-1), COLOR_GRIS_CLARO), ('FONTSIZE', (0,1), (0,-1), 6),
            ('LEFTPADDING', (0,1), (0,-1), 0), ('RIGHTPADDING', (0,1), (0,-1), 0)
        ]
        for c in orange_cols: style_res.append(('BACKGROUND', (c+1, 1), (c+1, 2), COLOR_NARANJA))
        
        t_res.setStyle(TableStyle(style_res))
        t_res.keepWithNext = True 
        elements.append(t_res)
        elements.append(Spacer(1, 10))

    # --- SECCIÓN 3: MAPA (A4) ---
    elements.append(PageBreak()) 
    elements.append(Paragraph("III. MAPA DE ÁRBOLES (VISTA PREVIA)", header_section_style))
    elements.append(t_line)
    elements.append(Spacer(1, 15))
    
    try:
        # Intenta cargar vista previa pequeña
        pil_img = PILImage.open("20250819_184004.tif")
        pil_img_rgba = pil_img.convert("RGBA")
        w_orig, h_orig = pil_img.size
        aspect = h_orig / float(w_orig)
        img_mapa = Image("20250819_184004.tif", width=450, height=450*aspect)
        img_mapa.hAlign = 'CENTER'
        elements.append(img_mapa)
    except:
        elements.append(Paragraph("[Imagen TIF no disponible para vista previa]", styles['Normal']))

    # --- SECCIÓN 4: COMENTARIOS ---
    elements.append(Spacer(1, 20))
    elements.append(Paragraph("IV. COMENTARIOS", header_section_style))
    elements.append(t_line)
    elements.append(Paragraph("Se sugiere revisión en campo detallada.", ParagraphStyle('C', parent=styles['Normal'], alignment=4)))

    # --- 5. CAMBIO A A3 GIGANTE ---
    elements.append(NextPageTemplate('PlantillaMapaGigante'))
    elements.append(PageBreak())
    elements.append(Paragraph(" ", styles['Normal']))

    # --- GENERACIÓN FINAL (LA SOLUCIÓN) ---
    # Usamos onFirstPage y onLaterPages explícitamente.
    # Esto fuerza a ReportLab a ejecutar dibujar_pagina_a4 en CADA página.
    # El filtro que añadimos al inicio de esa función evitará que pinte en la A3.
    doc.build(elements, onFirstPage=dibujar_pagina_a4, onLaterPages=dibujar_pagina_a4)
    print(f"Reporte generado: {filename}")

if __name__ == "__main__":
    crear_reporte("reporte_final_v6.pdf")