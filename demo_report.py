from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, A3, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, PageBreak, Frame, PageTemplate
from reportlab.graphics.shapes import Drawing, Circle, String, Rect
from reportlab.lib.utils import ImageReader
# --- CONFIGURACIÓN DE COLORES ---
COLOR_AZUL_OSCURO = colors.HexColor("#003366")
COLOR_AZUL_CLARO = colors.HexColor("#e6f2ff")
COLOR_NARANJA = colors.HexColor("#ffcc80") 
COLOR_GRIS_CLARO = colors.HexColor("#f2f2f2")
COLOR_VERDE = colors.HexColor("#008000")

# --- DATOS DE EJEMPLO ---
info_general = [
    ("Nombre del Análisis:", "Análisis de ejemplo 1"),
    ("Cantidad de Imágenes:", "331"),
    ("Modelo de Cámara:", "M3M"),
    ("GSD Promedio:", "0.5 cm/px"),
    ("Altura Promedio:", "14.92 m"),
    ("Fecha de Captura:", "2024-08-12"),
]

# Datos simulados
datos_arboles = []
for i in range(1, 21):
    estado = "SALUDABLE"
    ndvi = 0.80 + (i * 0.01)
    if i in [2, 11, 15, 19]: 
        estado = "POSIBLE DEFICIENCIA"
        ndvi = 0.65
    
    datos_arboles.append({
        "id": i,
        "diagnostico": estado,
        "ndvi": f"{ndvi:.2f}"
    })


def dibujar_pagina_final(canvas, doc):
    canvas.saveState()
    
    # Ruta de tu imagen para la página final
    ruta_imagen_full = "mapa_arboles.jpg" 
    
    # Definimos el tamaño de la hoja A3 en Horizontal (Landscape)
    # A3 standard: (841.89, 1190.55). Landscape invierte esto.
    ancho_hoja = landscape(A3)[0]
    alto_hoja = landscape(A3)[1]
    
    # Dibujamos la imagen desde la esquina (0,0) con el ancho y alto total
    try:
        canvas.drawImage(ruta_imagen_full, 0, 0, width=ancho_hoja, height=alto_hoja)
    except:
        # Si falla, fondo negro de error
        canvas.setFillColor(colors.black)
        canvas.rect(0, 0, ancho_hoja, alto_hoja, fill=1)
        
    canvas.restoreState()

def personalizar_pagina(canvas, doc):
    canvas.saveState()
    
    # --- 1. PIE DE PÁGINA (Tu nota existente) ---
    styles = getSampleStyleSheet()
    note_style = ParagraphStyle('Note', parent=styles['Normal'], fontSize=8, alignment=1)
    text = "* Nota: Valores de NDVI < 0.70 podrían indicar posibles problemas de salud en el palto."
    p = Paragraph(text, note_style)
    w, h = p.wrap(doc.width, doc.bottomMargin)
    p.drawOn(canvas, doc.leftMargin, 15) # 15 pts desde el borde inferior

    # --- 2. ENCABEZADO (Los Logos) ---
    # Rutas de tus logos
    logo_izq = "./assets/CITE_logo.jpg"
    logo_der = "./assets/INICTEL-LOGO.jpg"
    
    # Dimensiones deseadas para los logos (ajústalas a tu gusto)
    logo_height = 40 # Altura en puntos
    logo_width = 100 # Ancho máximo estimado (puedes ajustar)
    
    # Posición Y (altura): Calculamos basándonos en la altura de la página
    # page_height - margen_superior + un ajuste hacia arriba
    # doc.pagesize[1] es la altura total de la hoja (A4 = ~842 pts)
    y_pos = doc.pagesize[1] - 45 # 45 pts desde el borde superior
    
    # Dibujar Logo Izquierdo
    try:
        # preserveAspectRatio=True mantiene la forma original sin estirar
        canvas.drawImage(logo_izq, doc.leftMargin, y_pos, height=logo_height, preserveAspectRatio=True, mask='auto')
    except Exception:
        # Si falla (no encuentra imagen), dibuja un cuadro gris para avisar
        canvas.setFillColor(colors.lightgrey)
        canvas.rect(doc.leftMargin, y_pos, 50, logo_height, fill=1)

    # Dibujar Logo Derecho
    # Para el derecho, necesitamos saber el ancho real para alinearlo a la derecha. 
    # Como drawImage con preserveAspectRatio no nos dice el ancho final fácilmente antes de dibujar,
    # una técnica simple es anclarlo a la derecha asumiendo un ancho fijo o usando ImageReader.
    # Aquí usaré una posición fija restando un ancho estimado para simplificar.
    
    try:
        # Truco: Si quieres alinearlo perfecto a la derecha, necesitaríamos calcular el ratio.
        # Por ahora, lo pondremos en la posición: AnchoPagina - MargenDerecho - AnchoImagen
        x_pos_der = doc.pagesize[1] - doc.rightMargin - 100 # Ajusta este valor si queda muy al centro
        
        # Opción más precisa: anclar usando el ancho de la página
        page_width = doc.pagesize[0]
        x_pos = page_width - doc.rightMargin - logo_width
        
        canvas.drawImage(logo_der, x_pos, y_pos, width=logo_width, height=logo_height, preserveAspectRatio=True, anchor='ne', mask='auto')
    except Exception:
        canvas.setFillColor(colors.lightgrey)
        canvas.rect(doc.pagesize[0] - doc.rightMargin - 50, y_pos, 50, logo_height, fill=1)

    canvas.restoreState()

def dibujar_pie_pagina(canvas, doc):
    canvas.saveState()
    styles = getSampleStyleSheet()
    
    # Tu estilo original
    note_style = ParagraphStyle('Note', parent=styles['Normal'], fontSize=8, alignment=1)
    
    # El texto del pie de página
    text = "* Nota: Valores de NDVI < 0.70 podrían indicar posibles problemas de salud en el palto."
    p = Paragraph(text, note_style)
    
    # Calcular el tamaño y posición
    # ancho = ancho de la página (dentro de los márgenes)
    # alto = altura disponible (usamos el margen inferior)
    w, h = p.wrap(doc.width, doc.bottomMargin)
    
    # Dibujar el párrafo:
    # x = margen izquierdo
    # y = 15 puntos desde el borde inferior de la hoja (puedes ajustar este 15)
    p.drawOn(canvas, doc.leftMargin, 15)
    
    canvas.restoreState()

def crear_reporte(filename):
    doc = SimpleDocTemplate(filename, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=60, bottomMargin=30)

    ancho_a3, alto_a3 = landscape(A3)
    frame_a3 = Frame(0, 0, ancho_a3, alto_a3, id='FrameA3')
    
    # Creamos la plantilla vinculándola a la función de dibujo que hicimos arriba
    template_a3 = PageTemplate(id='PlantillaMapaGigante', frames=[frame_a3], onPage=dibujar_pagina_final, pagesize=landscape(A3))
    
    # Añadimos esta plantilla a la lista de plantillas del documento
    doc.addPageTemplates([template_a3])

    elements = []
    styles = getSampleStyleSheet()

    # --- 1. ENCABEZADO ---
    title_style = ParagraphStyle(
        'MainTitle', 
        parent=styles['Heading1'], 
        textColor=COLOR_AZUL_OSCURO, 
        alignment=1, # Centrado
        fontSize=14,
        spaceAfter=20
    )
    elements.append(Paragraph("INFORME DE ANÁLISIS BASADO EN IMÁGENES", title_style))
    
    # CORRECCIÓN: Usamos Spacer en lugar del hack incorrecto
    elements.append(Spacer(1, 12))
    
    # --- 2. SECCIÓN I: INFORMACIÓN GENERAL ---
    header_section_style = ParagraphStyle(
        'SectionTitle', 
        parent=styles['Heading2'], 
        textColor=COLOR_AZUL_OSCURO, 
        fontSize=12,
        spaceAfter=5
    )
    elements.append(Paragraph("I. INFORMACIÓN GENERAL", header_section_style))
    
    # Línea azul debajo del título
    t_line = Table([[""]], colWidths=[530], rowHeights=[2])
    t_line.setStyle(TableStyle([('LINEBELOW', (0,0), (-1,-1), 1, COLOR_AZUL_OSCURO)]))
    elements.append(t_line)
    elements.append(Spacer(1, 15))

    # Tabla de Información General
    table_data = []
    for row in info_general:
        table_data.append(row)

    t_info = Table(table_data, colWidths=[150, 380])
    
    estilo_info = [
        ('FONTNAME', (0,0), (-1,-1), 'Helvetica'),
        ('FONTSIZE', (0,0), (-1,-1), 9),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TEXTCOLOR', (0,0), (-1,-1), colors.black),
    ]
    
    for i in range(len(info_general)):
        bg_color = COLOR_GRIS_CLARO if i % 2 == 0 else colors.white
        estilo_info.append(('BACKGROUND', (0, i), (-1, i), bg_color))

    t_info.setStyle(TableStyle(estilo_info))
    elements.append(t_info)

    # --- 3. SECCIÓN II: RESULTADOS ---
    elements.append(Spacer(1, 30))
    elements.append(Paragraph("II. RESULTADOS DEL ANÁLISIS", header_section_style))
    elements.append(t_line) 
    elements.append(Spacer(1, 15))

    columnas_por_fila = 5
    chunks = [datos_arboles[i:i + columnas_por_fila] for i in range(0, len(datos_arboles), columnas_por_fila)]

    for chunk in chunks:
        row_ids = []
        row_diag = []
        row_ndvi = []
        orange_cols = [] 

        for idx, item in enumerate(chunk):
            row_ids.append(str(item['id']))
            row_diag.append(item['diagnostico'])
            row_ndvi.append(item['ndvi'])
            
            # Detectar columnas naranjas
            if item['diagnostico'] == "POSIBLE DEFICIENCIA":
                orange_cols.append(idx)

        # Rellenar celdas vacías si falta para completar 6 columnas
        while len(row_ids) < columnas_por_fila:
            row_ids.append("")
            row_diag.append("")
            row_ndvi.append("")
        
        # --- AQUÍ ESTÁ EL CAMBIO DE DATOS ---
        data_bloque = [
            ["Árbol"] + row_ids,           # Antes era [""] ahora es ["Árbol"]
            ["DIAGNÓSTICO"] + row_diag,
            ["NDVI Promedio"] + row_ndvi
        ]
        
        t_res = Table(data_bloque, colWidths=[80] + [80]*5)
        
        # --- AQUÍ ESTÁ EL CAMBIO DE ESTILOS ---
        style_res = [
            # Grilla general
            ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
            ('FONTNAME', (0,0), (-1,-1), 'Helvetica'),
            ('FONTSIZE', (0,0), (-1,-1), 7),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            
            # 1. CABECERA AZUL (Fila 0): Ahora aplica desde la columna 0 (Árbol) hasta el final
            ('BACKGROUND', (0,0), (-1,0), COLOR_AZUL_OSCURO),
            ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'), # Opcional: negrita para el encabezado
            
            # 2. ETIQUETAS LATERALES (Columna 0): Ahora aplica desde la Fila 1 hacia abajo (para respetar el azul de arriba)
            ('BACKGROUND', (0,1), (0,-1), COLOR_GRIS_CLARO),
            ('ALIGN', (0,1), (0,-1), 'CENTER'), # Alineación derecha solo para las etiquetas de abajo
            ('FONTSIZE', (0,1), (0,-1), 6),
        ]

        # Pintar celdas naranjas (Lógica condicional)
        for col_idx in orange_cols:
            actual_col = col_idx + 1
            style_res.append(('BACKGROUND', (actual_col, 1), (actual_col, 2), COLOR_NARANJA))

        t_res.setStyle(TableStyle(style_res))
        elements.append(t_res)
        elements.append(Spacer(1, 10))

    # --- 4. SECCIÓN III: MAPA DE ÁRBOLES ---
    elements.append(Spacer(1, 20))
    elements.append(PageBreak())
    elements.append(Paragraph("III. MAPA DE ÁRBOLES", header_section_style))
    elements.append(t_line)
    elements.append(Spacer(1, 20))

    ruta_imagen = "./20250819_184004.tif" 
    # 1. Definir el espacio máximo disponible
    max_width = 650
    max_height = 450
    # 2. Leer dimensiones originales de la imagen
    utils_img = ImageReader(ruta_imagen)
    img_orig_w, img_orig_h = utils_img.getSize()
    
    # 3. Calcular la relación de aspecto (aspect ratio)
    aspect = img_orig_h / float(img_orig_w)
    
    # 4. Determinar nuevas dimensiones ajustadas
    # Opción A: Intentar ajustar al ancho máximo
    new_width = max_width
    new_height = max_width * aspect
    
    # Si la altura calculada se pasa del máximo permitido, ajustamos por altura
    if new_height > max_height:
        new_height = max_height
        new_width = max_height / aspect

    # 5. Crear la imagen con las dimensiones calculadas
    imagen_mapa = Image(ruta_imagen, width=new_width, height=new_height)
    imagen_mapa.hAlign = 'CENTER'

    # --- AQUÍ INSERTAMOS LA IMAGEN ---
    # Asegúrate de que 'mapa_arboles.jpg' esté en la misma carpeta o pon la ruta completa
    #
    
    # width=500 es un buen ancho para que ocupe casi toda la página (A4)
    # height=300 es la altura; ajústala según la forma de tu imagen para que no se deforme
    #imagen_mapa = Image(ruta_imagen, width=500, height=300)
    #imagen_mapa.hAlign = 'CENTER' # Centrar la imagen en la página
    
    elements.append(imagen_mapa)

    elements.append(Spacer(1, 20))
    
    # --- 5. SECCIÓN IV: COMENTARIOS Y/O SUGERENCIAS ---
    elements.append(Spacer(1, 30)) # Espacio para separar de la sección anterior
    elements.append(Paragraph("IV. COMENTARIOS Y/O SUGERENCIAS", header_section_style))
    elements.append(t_line) # La misma línea azul que usamos antes
    elements.append(Spacer(1, 15))

    # Texto del comentario
    # Aquí puedes poner una variable si los comentarios vienen de tu base de datos
    texto_comentarios = ("Se recomienda realizar una visita de campo para verificar los árboles "
                         "marcados con 'Posible Deficiencia'. Sugerimos revisar el sistema de riego "
                         "en las zonas donde el NDVI es inferior a 0.70.")
    
    # Estilo de párrafo normal pero justificado
    estilo_comentarios = ParagraphStyle(
        'TextoComentarios', 
        parent=styles['Normal'], 
        fontSize=10, 
        leading=14, 
        alignment=4 # 4 = Justificado (Justify)
    )
    
    elements.append(Paragraph(texto_comentarios, estilo_comentarios))
    

    doc.build(elements, onFirstPage=personalizar_pagina, onLaterPages=personalizar_pagina)
    print(f"Reporte generado exitosamente: {filename}")

if __name__ == "__main__":
    crear_reporte("reporte_analisis.pdf")