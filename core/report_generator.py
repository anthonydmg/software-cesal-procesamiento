from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from datetime import datetime
import os

class ReportGenerator():
    def __init__(self, target_dir = ".", prefix_name = "RESULTADOS"):
        self.prefix_name = prefix_name
        self.target_dir = target_dir

    def create_report(self, save_path = None):
        if save_path is None:
            date_str = datetime.now().strftime("%Y%m%d_%H%M%S")

            pdf_file = f"{self.target_dir}/{self.prefix_name}_{date_str}.pdf"
        else:
            pdf_file = save_path
        
        os.makedirs(os.path.dirname(save_path), exist_ok= True)

        c = canvas.Canvas(pdf_file, pagesize=A4)

        self._add_firt_page(c, A4)
        self._add_second_page(c, A4)

        c.save()

        print(f"PDF generado: {pdf_file}")
    
    def _add_header(self, canva, size = A4):
        # Logo Izquierdo
        width, height = size
        logo_izquierda = "./assets/CITE_logo.jpg"
        logo_derecho = "./assets/INICTEL-LOGO.jpg"
        logo_size = 80

        canva.drawImage(logo_izquierda,
                40,
                height - logo_size - 30,
                width=logo_size + 30,
                height=logo_size + 30,
                preserveAspectRatio=True)

        # Logo Derecho
        canva.drawImage(logo_derecho,
                    width - logo_size - 40,
                    height - logo_size - 10,
                    width=logo_size,
                    height=logo_size,
                    preserveAspectRatio=True)
        
       


    def _add_firt_page(self, c, size = A4):
        # ==============================
        # PAGINA 1 (PORTADA)
        # ==============================
        # Titulo
        width, height = size
        titulo = "INFORME DE ANALISIS BASADO EN IMAGENES"
        c.setFont("Helvetica-Bold", 18)
        c.drawCentredString(width / 2, height - 100, titulo)

        # Logos

        self._add_header(c)

        # Campos descriptivos
        campos = [
            ("Nombre del Análisis:", "Análisis de ejemplo 1"),
            ("Cantidad de Imágenes:", "331"),
            ("Modelo de Cámara:", "M3M"),
            ("GSD Promedio:", "0.5 cm/px"),
            ("Altura Promedio:", "14.92 m"),
            ("Fecha de Captura de Imagenes:", "2024-08-12"),
        ]

        text_x = 80
        text_y = height - 180  # posición inicial del texto

        for campo, valor in campos:
            c.setFont("Helvetica-Bold", 12)
            c.drawString(text_x, text_y, campo)

            c.setFont("Helvetica", 12)
            c.drawString(text_x + 240, text_y, valor)

            text_y -= 25

        c.showPage()  # pasa a la página 2
    
    def _add_second_page(self, c, size = A4):
        # ==============================
        # PAGINA 2 (IMAGEN Y TABLA)
        # ==============================
        self._add_header(c)
        width, height = size
        # Imagen
        image = "./mosaic/20250828_123902.tif"
        img_width = width / 2
        img_height = height / 2
        x = (width - img_width) / 2
        y = height - img_height - 100
        c.drawImage(image, x, y, width=img_width, height=img_height, preserveAspectRatio=True)

        # Datos de tabla
        categorias = [
            "SALUDABLE",
            "DEFICIENCIA NITROGENO",
            "DEFICIENCIA ZINC",
            "DEFICIENCIA MAGNESIO",
            "DEF. NITROGENO Y ZINC",
            "DEF. NITROGENO Y MAGNESIO",
            "DEF. ZINC Y MAGNESIO",
            "DEF. NITROGENO ZINC Y MAGNESIO"
        ]
        porcentajes = [45, 12, 6, 6, 8, 10, 8, 5]
        total = 150
        cantidades = [round((p/100)*total) for p in porcentajes]

        data = [["Condición", "Cantidad", "Porcentaje"]]
        for cat, porc, cant in zip(categorias, cantidades, porcentajes):
            data.append([cat, str(cant), f"{porc}%"])

        # Config tabla
        colWidths = [200, 100, 100]
        rowHeight = 20
        x0, y0 = 100, 250  # posición inicial de la tabla (abajo de la imagen)

        # Dibujar filas y columnas
        for rowIndex, row in enumerate(data):
            y_row = y0 - rowIndex * rowHeight

            # Fondo de encabezado
            if rowIndex == 0:
                c.setFillColor(colors.grey)
                c.rect(x0, y_row - rowHeight, sum(colWidths), rowHeight, fill=1, stroke=1)
                c.setFillColor(colors.whitesmoke)
            else:
                c.setFillColor(colors.beige)
                c.rect(x0, y_row - rowHeight, sum(colWidths), rowHeight, fill=1, stroke=1)
                c.setFillColor(colors.black)

            # Dibujar columnas
            x_col = x0
            for colIndex, value in enumerate(row):
                # Bordes de celda
                c.setStrokeColor(colors.black)
                c.rect(x_col, y_row - rowHeight, colWidths[colIndex], rowHeight, fill=0, stroke=1)

                # Texto centrado
                text_x = x_col + colWidths[colIndex] / 2
                text_y = y_row - rowHeight / 2 - 4
                if rowIndex == 0:
                    c.setFont("Helvetica-Bold", 10)
                else:
                    c.setFont("Helvetica", 9)
                c.drawCentredString(text_x, text_y, value)

                x_col += colWidths[colIndex]

        c.showPage()


if __name__ == "__main__":
    report_generator = ReportGenerator()
    report_generator.create_report()






