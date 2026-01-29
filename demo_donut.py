import sys
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QLineEdit, QPushButton, QFrame, QComboBox, 
                             QScrollArea)
from PySide6.QtCore import Qt 
from PySide6.QtGui import QFont, QPen, QBrush, QColor, QPainter
from PySide6.QtWidgets import QGraphicsDropShadowEffect
from PySide6.QtCore import Qt, QRectF, Signal, QPoint, QEvent, QThread, Slot, QSize, QRect




class StatCountWidget(QWidget):
    def __init__(self, color, title, percentage, count, parent=None):
        super().__init__(parent)
        
        # Layout principal vertical
        layout = QVBoxLayout(self)
        layout.setSpacing(2) # Espacio pequeño entre líneas
        
        # --- Fila superior (Punto de color + Título) ---
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)
        
        # El "punto" de color hecho con un QFrame
        dot = QFrame()
        dot.setFixedSize(12, 12)
        dot.setStyleSheet(f"background-color: {color}; border-radius: 6px;")
        
        title_label = QLabel(title.upper())
        title_label.setStyleSheet("color: #8E97A4; font-weight: bold; font-size: 11px;")
        
        header_layout.addWidget(dot)
        header_layout.addWidget(title_label)
        header_layout.addStretch() # Empuja todo a la izquierda
        
        # --- Fila media (Porcentaje) ---
        self.percent_label = QLabel(percentage)
        self.percent_label.setStyleSheet("color: #2D3748; font-size: 22px; font-weight: 800;")
        
        # --- Fila inferior (Subtexto de ejemplares) ---
        self.count_label = QLabel(f"{count} Árboles")
        self.count_label.setStyleSheet("color: #718096; font-size: 12px;")
        
        # Agregar todo al layout principal
        layout.addLayout(header_layout)
        layout.addWidget(self.percent_label)
        layout.addWidget(self.count_label)
    
    def update_stat(self, count, percentage):
        self.percent_label.setText(f"{percentage}%")
        self.count_label.setText(f"{count} Árboles")
        


class StatsDeficiency(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Dashboard Stats")
        self.setStyleSheet("background-color: white;") # Fondo blanco como en la imagen
        
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(40) # Espacio entre los dos bloques

        # Bloque Saludable (Verde)
        self.saludable = StatCountWidget("#108548", "Saludable", "0.0%", 0)
        
        # Bloque Deficiencia (Amarillo/Naranja)
        self.deficiencia = StatCountWidget("#F97316", "Deficiencia", "0.0%", 0)

        main_layout.addWidget(self.saludable)
        main_layout.addWidget(self.deficiencia)
        main_layout.addStretch()
    
    def update_stats(self, num_healty, num_deficency):
        percentage_healthy = round(num_healty * 100 / (num_healty + num_deficency), 2) 
        percentage_deficient = round(num_deficency * 100 / (num_healty + num_deficency),2) 
        
        self.saludable.update_stat(num_healty, percentage_healthy)
        self.deficiencia.update_stat(num_deficency, percentage_deficient)
        
class DonutChartWidget(QWidget):
    def __init__(self, healthy=65, deficient=35, parent=None):
        super().__init__(parent)

        self.healthy = healthy
        self.deficient = deficient
        total = max((healthy + deficient),1)
        self.percentage_healthy = round(healthy * 100 / total, 1) 
        self.percentage_deficient = round(deficient * 100 / total, 1) 

        # Para una mejor calidad en pantallas HiDPI
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMinimumSize(200, 200)

    # =================================================
    #                  DIBUJAR DONUT
    # =================================================
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        size = min(w, h)

        cx = w / 2
        cy = h / 2
        radius = size * 0.40
        thickness = radius * 0.30

        rect = QRectF(
            cx - radius,
            cy - radius,
            radius * 2,
            radius * 2
        )

        # ========================
        # Arcos (Healthy / Deficient)
        # ========================
        start_angle = 0#90 * 48

        healthy_angle = int(360 * (self.percentage_healthy / 100) * 16)
        deficient_angle = int(360 * (self.percentage_deficient / 100) * 16)

        # HEALTHY (verde)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#22A529"))
        p.drawPie(rect, start_angle, healthy_angle)

        # DEFICIENT (amarillo)
        p.setBrush(QColor("#F97316"))
        p.drawPie(rect, start_angle + healthy_angle, deficient_angle)

        # ========================
        # agujero interior (donut)
        # ========================
        inner_radius = radius - thickness
        hole = QRectF(
            cx - inner_radius,
            cy - inner_radius,
            inner_radius * 2,
            inner_radius * 2
        )

        p.setBrush(QColor(self.palette().window().color()))
        p.drawEllipse(hole)

        # ==================================================
        #                   TEXTOS
        # ==================================================
        def draw_text(center_x, center_y, text, size_ratio, bold=False, color=QColor("black")):
            font = QFont("Segoe UI", int(size * size_ratio))
            font.setBold(bold)
            p.setFont(font)
            p.setPen(color)

            p.drawText(
                QRectF(center_x - radius, center_y - radius, radius*2, radius*2),
                Qt.AlignCenter,
                text
            )
        # TEXTOS IZQUIERDA (Healthy)
        left_x = cx #- radius * 0.10
        top_left_y = cy - radius * 0.10

        print("left_x:", left_x)
        print("top_left_y:", top_left_y)
        draw_text(left_x, top_left_y + radius * 0.24, "Saludable", 0.05, True, QColor("#22A529"))
        draw_text(left_x, top_left_y , f"{self.percentage_healthy}%", 0.09, True, QColor("black"))
        #draw_text(left_x, top_left_y + radius * 0.30, f"({self.healthy} Árboles)", 0.03, False, QColor("gray"))

        # TEXTOS DERECHA (Deficient)
        right_x = cx #+ radius * 0.90
        top_right_y = cy + radius * 0.10

        #draw_text(right_x, top_right_y, "Con Deficiencia",  0.03, True, QColor("#FFC000"))
        #draw_text(right_x, top_right_y + radius * 0.15, f"{self.percentage_deficient}%", 0.04, True, QColor("black"))
        #draw_text(right_x, top_right_y + radius * 0.30, f"({self.deficient} Árboles)", 0.03  , False, QColor("gray"))

    # =================================================
    #       ACTUALIZAR VALORES EXTERNAMENTE
    # =================================================
    def update_values(self, healthy, deficient):
        self.healthy = healthy
        self.deficient = deficient
        
        self.percentage_healthy = round(healthy * 100 / (healthy + deficient), 2) 
        self.percentage_deficient = round(deficient * 100 / (healthy + deficient),2) 
        self.update()

class CantanierStats(QFrame):
    def __init__(self, parent = None):
        super().__init__(parent)
        self.setObjectName("CantanierStats")   # ← ID único
        self.setStyleSheet("""
            #CantanierStats {
                background-color: #FFFFFF;
                border: 2px solid #F4F5F7;
                border-radius: 18px;
                padding-top: 5px;
            }
        """)
        layout = QVBoxLayout(self)
        layout.setSpacing(2) # Espacio pequeño entre líneas

        card = DonutChartWidget(65,35, self)
        stat = StatsDeficiency()

        layout.addWidget(card)
        layout.addWidget(stat)

        self.setLayout(layout)

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Gestor de Bandas")
        self.setStyleSheet("background-color: white;")
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(30, 30, 30, 20)

        container_layout = CantanierStats(self)
        main_layout.addWidget(container_layout)
        #card = DonutChartWidget(65,35, self)
        #stat = StatsDeficiency()
        #main_layout.addWidget(card)
        #main_layout.addWidget(stat)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())