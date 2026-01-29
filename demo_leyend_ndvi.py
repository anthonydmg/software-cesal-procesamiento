import sys
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QLineEdit, QPushButton, QFrame, QComboBox, 
                             QScrollArea, QGridLayout, QSpacerItem, QSizePolicy)
from PySide6.QtCore import Qt, Slot, QRect, QSize
from PySide6.QtGui import QFont, QPen, QBrush, QColor, QPainter, QLinearGradient
from PySide6.QtWidgets import QGraphicsDropShadowEffect


class StatCard(QFrame):
    def __init__(self, title: str, value: int, area:int, parent=None):
        super().__init__(parent)
        # Sombra suave alrededor de la tarjeta
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(10)          # Suavidad de la sombra
        shadow.setXOffset(0)              # Desplazamiento horizontal
        shadow.setYOffset(1)              # Desplazamiento vertical
        shadow.setColor(QColor(0, 0, 0, 40))  # Negro con transparencia

        self.setGraphicsEffect(shadow)
        # Configurar borde, fondo y esquinas redondeadas
        #self.setFrameShape(QFrame.StyledPanel)
        self.setObjectName("StatCardFrame")   # ← ID único
        
        self.setStyleSheet("""
            #StatCardFrame {
                background-color: #FFFFFF;
                border: 2px solid #F4F5F7;
                border-radius: 18px;
                padding-top: 5px;
            }
        """)

        # Num Arboles Layout
        layout_count = QVBoxLayout()
        ## Título
        lbl_title = QLabel(title)
        lbl_title.setAlignment(Qt.AlignCenter)
        lbl_title.setFont(QFont("Segoe UI", 13))
        lbl_title.setStyleSheet("color: #0A281A;")

        layout_count.addWidget(lbl_title)

        ## Arboles
        self.lbl_value = QLabel(str(value))
        self.lbl_value.setAlignment(Qt.AlignCenter)
        self.lbl_value.setFont(QFont("Segoe UI", 34, QFont.Bold))
        self.lbl_value.setStyleSheet("color: #0A281A;")

        layout_count.addWidget(self.lbl_value)

        # Line verticarl

        linea = QFrame()
        linea.setFrameShape(QFrame.VLine)
        linea.setFrameShadow(QFrame.Raised)
        #linea.setStyleSheet("color: #d1d1d1;") # Color de la línea
        linea.setFixedWidth(2)
        linea.setStyleSheet("background-color: #F4F5F7; border-radius: 1px")


        # Area Estimadas
        layout_area = QVBoxLayout()
        ## Título
        lbl_title_area = QLabel("Area Estimada")
        lbl_title_area.setAlignment(Qt.AlignCenter)
        lbl_title_area.setFont(QFont("Segoe UI", 13))
        lbl_title_area.setStyleSheet("color: #0A281A;")

        layout_area.addWidget(lbl_title_area)
        ## Area valor
        self.val_area = QLabel(f'{area}<span style="font-size:20px; color:#D3D3D3;"> Ha</span>')
        self.val_area.setFont(QFont("Segoe UI", 34, QFont.Bold))
        self.val_area.setAlignment(Qt.AlignCenter)
        layout_area.addWidget(self.val_area)
        
        # Layout
        layout = QHBoxLayout(self)
        
        layout.addLayout(layout_count)
        layout.addWidget(linea)
        layout.addLayout(layout_area)

        #layout.addWidget(self.lbl_value)
        layout.setContentsMargins(20, 15, 20, 15)
    
    def update_count(self, num_trees = 0):
        self.lbl_value.setText(str(num_trees))

    def update_area(self, area = 0):
        self.val_area.setText(f'{area}<span style="font-size:20px; color:#D3D3D3;"> Ha</span>')
    

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


# --- Constantes de Color Leyenda NDVI---
COLOR_GREEN = "#1b833d"    # Saludable
COLOR_YELLOW = "#eab308"   # Precaución
COLOR_ORANGE = "#f97316"   # Problema Probable
COLOR_RED = "#dc2626"      # Problema Crítico
COLOR_BG_CARD = "#eeeeee"  # Fondo de la tarjeta
COLOR_TEXT_TITLE = "#495057"
COLOR_TEXT_SUBTITLE = "#868e96"

class LegendItemVI(QWidget):
    def __init__(self, color, title, count, range_text, parent=None):
        super().__init__(parent)
        # Layout principal vertical para que el subtítulo quede debajo
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 10, 0, 10)
        layout.setSpacing(2)

        # --- Fila superior: [PUNTO] [TÍTULO] [CUENTA] ---
        top_row_layout = QHBoxLayout()
        top_row_layout.setSpacing(12) # Espacio entre el punto y el texto
        top_row_layout.setContentsMargins(0, 0, 0, 0)
        
        # 1. El punto de color
        dot = QFrame()
        dot.setFixedSize(10, 10)
        dot.setStyleSheet(f"background-color: {color}; border-radius: 5px;")
        
        # 2. Título
        title_label = QLabel(title)
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(10)
        title_label.setFont(title_font)
        title_label.setStyleSheet(f"color: {COLOR_TEXT_TITLE};")
        
        # 3. Cuenta (el número)
        self.count_label = QLabel(str(count))
        count_font = QFont()
        count_font.setBold(True)
        count_font.setPointSize(11)
        self.count_label.setFont(count_font)
        self. count_label.setStyleSheet(f"color: {color};")

        # Añadimos todo a la fila superior con alineación centrada verticalmente
        top_row_layout.addWidget(dot, alignment=Qt.AlignVCenter)
        top_row_layout.addWidget(title_label, alignment=Qt.AlignVCenter)
        top_row_layout.addWidget(self.count_label, alignment=Qt.AlignVCenter)
        top_row_layout.addStretch() 

        # --- Fila inferior: Subtítulo (alineado con el inicio del texto del título) ---
        # Usamos un margen izquierdo para que el subtítulo no quede debajo del punto
        subtitle_label = QLabel(f"({range_text}): {count} árboles")
        subtitle_label.setStyleSheet(f"""
            color: {COLOR_TEXT_SUBTITLE}; 
            font-size: 11px;
            margin-left: 22px; 
        """) # 22px = 10px (dot) + 12px (spacing) aprox.

        layout.addLayout(top_row_layout)
        layout.addWidget(subtitle_label)
    
    def update_value_count(self, value):
        self.count_label.setText(value)

class NDVIScaleCard(QFrame):
    """
    El widget principal tipo tarjeta que contiene todo.
    """
    def __init__(self, num_health = 0, num_warning = 0, num_potential_issue = 0, num_critical_problem = 0, parent=None):
        super().__init__(parent)
        # Estilo principal de la tarjeta (fondo, bordes redondeados)
        self.setStyleSheet(f"""
            NDVIScaleCard {{
                background-color: {COLOR_BG_CARD};
                border-radius: 15px;
                border: 1px solid #e9ecef;
            }}
        """)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(30, 25, 30, 30)
        main_layout.setSpacing(20)

        # --- Título Principal ---
        title_label = QLabel("ESCALA DE SALUD NDVI")
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(10)
        title_font.setLetterSpacing(QFont.AbsoluteSpacing, 1.2) # Espaciado entre letras
        title_label.setFont(title_font)
        title_label.setStyleSheet(f"color: {COLOR_TEXT_TITLE};")
        main_layout.addWidget(title_label)

        # --- Contenido (Barra izquierda + Leyenda derecha) ---
        content_layout = QHBoxLayout()
        content_layout.setSpacing(25)

        # 1. Sección Izquierda: Barra de Degradado y Etiquetas
        scale_layout = QGridLayout()
        scale_layout.setSpacing(0)
        
        # Etiquetas numéricas
        labels_vals = ["1.0", "0.70", "0.55", "0.40", "0.0"]
        for i, val in enumerate(labels_vals):
            lbl = QLabel(val)
            lbl.setStyleSheet(f"color: #adb5bd; font-weight: bold; font-size: 11px; margin-right: 8px;")
            # Alinear verticalmente: el primero arriba, el último abajo, los del medio centrados
            align = Qt.AlignVCenter
            if i == 0: align = Qt.AlignTop
            if i == len(labels_vals) -1: align = Qt.AlignBottom
            
            # Añadir a la columna 0
            scale_layout.addWidget(lbl, i*2, 0, alignment=align)
            # Truco: añadir espaciadores entre etiquetas para distribuir la altura
            if i < len(labels_vals) - 1:
                 scale_layout.addItem(QSpacerItem(1, 1, QSizePolicy.Minimum, QSizePolicy.Expanding), (i*2)+1, 0)


        # La barra de color en sí (un QFrame delgado)
        gradient_bar = QFrame()
        gradient_bar.setFixedWidth(8)
        # CSS crucial para el degradado vertical y bordes redondeados
        gradient_bar.setStyleSheet(f"""
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop: 0 {COLOR_GREEN},
                stop: 0.35 {COLOR_YELLOW},
                stop: 0.65 {COLOR_ORANGE},
                stop: 1.0 {COLOR_RED});
            border-radius: 4px;
        """)
        # La barra ocupa la columna 1 y se expande verticalmente
        scale_layout.addWidget(gradient_bar, 0, 1, 9, 1) # Ocupa 9 filas del grid

        content_layout.addLayout(scale_layout)

        # 2. Sección Derecha: Leyenda (Lista de items)
        legend_layout = QVBoxLayout()
        legend_layout.setSpacing(0)
        legend_layout.setContentsMargins(0,0,0,0)

        # Crear los items usando nuestra clase reutilizable
        self.item1 = LegendItemVI(COLOR_GREEN, "SALUDABLE", num_health, "> 0.70")
        self.item2 = LegendItemVI(COLOR_YELLOW, "PRECAUCIÓN", num_warning, "0.55 - 0.70")
        self.item3 = LegendItemVI(COLOR_ORANGE, "POSIBLE PROBLEMA", num_potential_issue, "0.40 - 0.55")
        self.item4 = LegendItemVI(COLOR_RED, "CONDICIÓN CRÍTICA", num_critical_problem, "< 0.40")
        
        legend_layout.addWidget(self.item1)
        legend_layout.addWidget(self.item2)
        legend_layout.addWidget(self.item3)
        legend_layout.addWidget(self.item4)
        # Empujar los items hacia arriba
        #legend_layout.addStretch()

        content_layout.addLayout(legend_layout)
        
        # Añadir el contenido al layout principal de la tarjeta
        main_layout.addLayout(content_layout)
    
    def update_counts(self, num_health = 0, num_warning = 0, num_potential_issue = 0, num_critical_problem = 0):
        self.item1.update_value_count(num_health)
        self.item2.update_value_count(num_warning)
        self.item3.update_value_count(num_potential_issue)
        self.item4.update_value_count(num_critical_problem)

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Gestor de Bandas")
        #self.setStyleSheet("background-color: white;")
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(30, 30, 30, 20)

        card = NDVIScaleCard(parent=self)
        main_layout.addWidget(card)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())