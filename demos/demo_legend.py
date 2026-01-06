import sys
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel, QFrame
from PySide6.QtGui import QPainter, QLinearGradient, QColor, QBrush, QPen, QFont
from PySide6.QtCore import Qt, QRect, QSize

class LeyendaSaludWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Layout principal (Vertical)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5) # Espacio entre título y caja

        # 1. Título "Leyenda" (Afuera de la caja, como tu foto)
        lbl_titulo = QLabel("Leyenda")
        lbl_titulo.setStyleSheet("font-weight: bold; font-size: 14px; color: #333333;")
        layout.addWidget(lbl_titulo)

        # 2. El contenedor (Caja con borde)
        self.caja_contenedor = QFrame()
        self.caja_contenedor.setStyleSheet("""
            QFrame {
                background-color: white;
                border: 1px solid #CCCCCC;
                border-radius: 5px;
            }
        """)
        caja_layout = QVBoxLayout(self.caja_contenedor)
        caja_layout.setContentsMargins(15, 15, 15, 15) # Margen interno para que no pegue al borde
        
        # 3. El Widget que dibuja la barra y textos
        self.contenido_grafico = ContenidoLeyenda()
        caja_layout.addWidget(self.contenido_grafico)

        layout.addWidget(self.caja_contenedor)

class ContenidoLeyenda(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        # Definir tamaño mínimo obligatorio para que no se descuadre
        self.setMinimumHeight(220) 
        self.setMinimumWidth(200)

        # Colores
        self.c_green       = QColor(20, 80, 0)     # Verde Oscuro
        self.c_medium_green = QColor(70, 140, 0)
        self.c_lime        = QColor(120, 200, 0)   # Lima
        self.c_yellow      = QColor(220, 240, 0)   # Amarillo
        self.c_soft_orange = QColor(220, 170, 0)   # Naranja Suave
        self.c_dark_orange = QColor(220, 100, 0)   # Naranja Oscuro

        # Marcadores: (Valor, Color, Texto Principal)
        self.markers = [
            (1.00, self.c_green,       "MUY SALUDABLE (1.0)"),
            (0.90, self.c_medium_green,      "SALUDABLE (0.9)"),
            (0.80, self.c_lime, "ACEPTABLE (0.8)"),
            (0.70, self.c_soft_orange, "DEFICIENTE (0.7)"),
            (0.60, self.c_dark_orange, "BAJO (< 0.6)")
        ]
        
        # Gradiente visual (Stops para QGradient)
        self.gradient_stops = [
            (0.00, self.c_green),
            (0.20, self.c_medium_green),
            (0.40, self.c_lime),
            (0.60, self.c_yellow),
            (0.70, self.c_soft_orange),
            (1.00, self.c_dark_orange)
        ]

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Geometría disponible
        rect = self.rect()
        w = rect.width()
        h = rect.height()
        
        # Configuración de diseño
        bar_width = 20        # Ancho de la barra de color
        bar_x = 0             # Pegado a la izquierda del contenido
        text_offset_x = 35    # Donde empieza el texto
        
        # 1. DIBUJAR LA BARRA DE COLOR VERTICAL
        grad = QLinearGradient(bar_x, 0, bar_x, h) # De arriba a abajo
        for stop, color in self.gradient_stops:
            grad.setColorAt(stop, color)
            
        painter.setBrush(QBrush(grad))
        painter.setPen(Qt.NoPen)
        # Dibujamos un rectángulo redondeado para la barra
        painter.drawRoundedRect(bar_x, 0, bar_width, h, 5, 5)

        # 2. DIBUJAR LOS TEXTOS ALINEADOS
        # Fuentes
        font_main = QFont("Segoe UI", 9)
        painter.setFont(font_main)
        
        # Rango matemático para calcular posiciones
        max_val = 1.00
        min_val = 0.60
        span = max_val - min_val

        for val, color, label in self.markers:
            # Cálculo de posición Y (Invertido: 1.0 arriba, 0.6 abajo)
            ratio = (max_val - val) / span
            y_center = ratio * h
            
            # Corrección de bordes para que el texto no se corte arriba/abajo
            # Mantenemos el texto dentro del área visible
            y_center = max(10, min(h - 10, y_center))

            # Dibujar línea conectora pequeña (opcional, ayuda a leer)
            painter.setPen(QPen(QColor(200, 200, 200), 1))
            painter.drawLine(bar_x + bar_width + 2, int(y_center), bar_x + bar_width + 8, int(y_center))

            # Dibujar Texto
            painter.setPen(QColor(50, 50, 50)) # Gris oscuro (más elegante que negro)
            text_rect = QRect(text_offset_x, int(y_center) - 10, w - text_offset_x, 20)
            painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, label)

    # Esto es CRUCIAL: Le dice al layout cuánto espacio necesita como mínimo
    def sizeHint(self):
        return QSize(200, 250)

# --- PRUEBA ---
if __name__ == "__main__":
    app = QApplication(sys.argv)
    ventana = QWidget()
    ventana.setWindowTitle("Prueba de Leyenda")
    ventana.resize(300, 400)
    ventana.setStyleSheet("background-color: #F5F5F5;") # Fondo gris para ver el contraste

    layout_principal = QVBoxLayout(ventana)
    layout_principal.setAlignment(Qt.AlignCenter) # Centrar en la ventana
    
    # Instanciar nuestra leyenda arreglada
    mi_leyenda = LeyendaSaludWidget()
    
    layout_principal.addWidget(mi_leyenda)
    ventana.show()
    sys.exit(app.exec())