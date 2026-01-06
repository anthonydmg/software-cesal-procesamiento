from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.graphics.shapes import Drawing, Circle
from reportlab.lib.units import mm

# 1. Función para crear el círculo de color (el "Dot")
def create_dot(color_hex):
    # Creamos un dibujo pequeño de 4mm x 4mm
    d = Drawing(4*mm, 4*mm)
    # Dibujamos un círculo: x, y, radio, color
    c = Circle(2*mm, 2*mm, 1.5*mm) 
    c.fillColor = colors.HexColor(color_hex)
    c.strokeColor = None # Sin borde negro
    d.add(c)
    return d

def generate_pdf():
    doc = SimpleDocTemplate("reporte_arboles.pdf", pagesize=A4)
    elements = []
    
    styles = getSampleStyleSheet()

    # --- DATOS DE ENTRADA ---
    # Simulamos los datos de tu imagen
    healthy_count = 130
    healthy_pct = "65%"
    deficient_count = 70
    deficient_pct = "35%"

    # --- COLORES ---
    # Colores aproximados de la imagen
    col_green = "#28a745"  # Verde
    col_yellow = "#ffc107" # Amarillo/Naranja
    col_border = "#dcdcdc" # Gris claro para bordes

    # --- ESTILOS DE TEXTO ---
    # Estilo para el título de la tarjeta
    style_header = ParagraphStyle(
        'CardHeader',
        parent=styles['Heading3'],
        fontSize=12,
        textColor=colors.black,
        spaceAfter=0,
    )

    # Estilo para el texto normal (Healthy/Deficient)
    style_label = ParagraphStyle(
        'Label',
        parent=styles['BodyText'],
        fontSize=10,
        textColor=colors.black,
        alignment=0 # Izquierda
    )

    # Estilo para los números (alineados a la derecha)
    style_value = ParagraphStyle(
        'Value',
        parent=styles['BodyText'],
        fontSize=10,
        textColor=colors.black,
        alignment=2 # Derecha
    )

    # --- CONSTRUCCIÓN DE LA TABLA ---
    
    # Fila 1: Título (ocupa toda la fila)
    header_text = Paragraph("<b>Distribución de Arboles</b>", style_header)
    
    # Fila 2: Datos Healthy
    # Usamos HTML tags <b> para negritas dentro del Paragraph
    dot_green = create_dot(col_green)
    label_healthy = Paragraph("Saludables", style_label)
    value_healthy = Paragraph(f"<b>{healthy_count} Trees ({healthy_pct})</b>", style_value)

    # Fila 3: Separador (Lo haremos con estilo de tabla, o una fila vacía fina)
    
    # Fila 4: Datos Deficient
    dot_yellow = create_dot(col_yellow)
    label_deficient = Paragraph("Con Deficiencia", style_label)
    value_deficient = Paragraph(f"<b>{deficient_count} Trees ({deficient_pct})</b>", style_value)

    # Estructura de la data para la Tabla
    # Columna 1: Punto | Columna 2: Etiqueta | Columna 3: Valor
    data = [
        [header_text, '', ''],           # Fila 0: Título (hará span)
        [dot_green, label_healthy, value_healthy], # Fila 1
        [dot_yellow, label_deficient, value_deficient] # Fila 2
    ]

    # Crear la Tabla
    # Definimos anchos de columna: Punto(10mm), Texto(80mm), Valor(40mm)
    table = Table(data, colWidths=[10*mm, 80*mm, 40*mm])

    # --- ESTILO VISUAL DE LA TABLA (CSS de ReportLab) ---
    style = TableStyle([
        # 1. Configuración General
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'), # Centrar verticalmente todo
        ('background', (0,0), (-1,-1), colors.white),
        
        # 2. El Título (Fila 0)
        ('SPAN', (0,0), (-1,0)),        # Fusionar las 3 columnas de la primera fila
        ('BOTTOMPADDING', (0,0), (-1,0), 10), # Espacio debajo del título
        ('LINEBELOW', (0,0), (-1,0), 1, colors.HexColor(col_border)), # Línea verde/gris debajo del título
        
        # 3. Filas de Datos
        ('TOPPADDING', (0,1), (-1,-1), 10),    # Padding superior para filas de datos
        ('BOTTOMPADDING', (0,1), (-1,-1), 10), # Padding inferior
        
        # 4. Línea separadora entre Healthy y Deficient
        # Dibujamos una línea debajo de la fila "Healthy" (Fila 1)
        ('LINEBELOW', (0,1), (-1,1), 1, colors.HexColor(col_border)),

        # 5. Borde Exterior (La caja)
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#A8D5BA")), # Borde verde suave tipo la imagen
        ('ROUNDEDCORNERS', [10, 10, 10, 10]), # Nota: ReportLab nativo no redondea tablas facilmente,
                                              # pero el borde cuadrado se ve profesional.
    ])

    table.setStyle(style)

    # Añadir a la lista de elementos y construir PDF
    elements.append(table)
    doc.build(elements)
    print("PDF generado con éxito: reporte_arboles.pdf")

if __name__ == "__main__":
    generate_pdf()