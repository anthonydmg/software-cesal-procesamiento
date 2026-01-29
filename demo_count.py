import sys
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QLineEdit, QPushButton, QFrame, QComboBox, 
                             QScrollArea)
from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QFont, QPen, QBrush, QColor
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
    
        
class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Gestor de Bandas")
        self.setStyleSheet("background-color: white;")
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(30, 30, 30, 20)

        card = StatCard("Arboles Detectados",300, 0.5, self)
        main_layout.addWidget(card)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())