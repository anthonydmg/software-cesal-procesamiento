import sys
from PySide6.QtWidgets import (QApplication, QDialog, QVBoxLayout, QHBoxLayout, 
                             QLabel, QPushButton, QFrame, QGraphicsBlurEffect)
from PySide6.QtGui import QFont, QColor
from PySide6.QtCore import Qt, QSize

class VIInfoDialog(QDialog):
    def __init__(self, title, definition, average_desc, equation_str, variable_legend, parent=None):
        super().__init__(parent)
        
        # Configuración de la ventana del diálogo
        self.setWindowTitle(title)
        self.setWindowFlags(Qt.WindowFlags.FramelessWindowHint | Qt.WindowFlags.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(460, 520) # Tamaño proporcional al de la captura
        
        # Guardar datos dinámicos
        self.title_text = title
        self.definition_text = definition
        self.average_desc_text = average_desc
        self.equation_text = equation_str
        self.legend_text = variable_legend
        
        self.init_ui()

    def init_ui(self):
        # Layout principal del QDialog que contendrá la tarjeta blanca
        dialog_layout = QVBoxLayout(self)
        dialog_layout.setContentsMargins(10, 10, 10, 10) # Margen para la sombra/borde si fuera necesario
        
        # --- Fondo del Diálogo (Tarjeta Blanca Redondeada) ---
        container = QFrame()
        container.setObjectName("ContainerCard")
        container.setStyleSheet("""
            QFrame#ContainerCard {
                background-color: #ffffff;
                border-radius: 12px;
                border: 1px solid #e5e7eb;
            }
        """)
        
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(25, 20, 25, 25)
        container_layout.setSpacing(18)
        
        # =========================================================================
        # 1. CABECERA (Título + Botón Cerrar)
        # =========================================================================
        header_layout = QHBoxLayout()
        
        title_label = QLabel(self.title_text)
        title_label.setStyleSheet("color: #111827; font-size: 16px; font-weight: bold; font-family: 'Segoe UI', Arial;")
        
        close_btn = QPushButton("✕")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setFixedSize(24, 24)
        close_btn.setStyleSheet("""
            QPushButton {
                border: none;
                background-color: transparent;
                color: #6b7280;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                color: #111827;
                background-color: #f3f4f6;
                border-radius: 12px;
            }
        """)
        close_btn.clicked.connect(self.reject)
        
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        header_layout.addWidget(close_btn)
        container_layout.addLayout(header_layout)
        
        # Línea divisoria sutil bajo la cabecera
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("background-color: #f3f4f6; max-height: 1px; border: none;")
        container_layout.addWidget(line)
        
        # =========================================================================
        # 2. SECCIÓN: DEFINICIÓN
        # =========================================================================
        def_layout = QVBoxLayout()
        def_layout.setSpacing(4)
        
        def_title = QLabel("DEFINICIÓN")
        def_title.setStyleSheet("color: #065f46; font-size: 11px; font-weight: bold; letter-spacing: 0.5px;")
        
        def_body = QLabel(self.definition_text)
        def_body.setWordWrap(True)
        def_body.setStyleSheet("color: #4b5563; font-size: 12px; line-height: 18px; font-family: 'Segoe UI';")
        
        def_layout.addWidget(def_title)
        def_layout.addWidget(def_body)
        container_layout.addLayout(def_layout)
        
        # =========================================================================
        # 3. SECCIÓN: PROMEDIO POR ÁRBOL
        # =========================================================================
        avg_layout = QVBoxLayout()
        avg_layout.setSpacing(4)
        
        avg_title = QLabel("PROMEDIO POR ÁRBOL")
        avg_title.setStyleSheet("color: #065f46; font-size: 11px; font-weight: bold; letter-spacing: 0.5px;")
        
        avg_body = QLabel(self.average_desc_text)
        avg_body.setWordWrap(True)
        avg_body.setStyleSheet("color: #4b5563; font-size: 12px; line-height: 18px; font-family: 'Segoe UI';")
        
        avg_layout.addWidget(avg_title)
        avg_layout.addWidget(avg_body)
        container_layout.addLayout(avg_layout)
        
        # =========================================================================
        # 4. SECCIÓN: ECUACIÓN
        # =========================================================================
        eq_layout = QVBoxLayout()
        eq_layout.setSpacing(6)
        
        eq_title = QLabel("ECUACIÓN")
        eq_title.setStyleSheet("color: #065f46; font-size: 11px; font-weight: bold; letter-spacing: 0.5px;")
        
        # Caja contenedora gris para la fórmula matemática
        eq_box = QFrame()
        eq_box.setStyleSheet("""
            QFrame {
                background-color: #f9fafb;
                border: 1px solid #e5e7eb;
                border-radius: 8px;
            }
        """)
        eq_box_layout = QVBoxLayout(eq_box)
        eq_box_layout.setContentsMargins(15, 18, 15, 18)
        
        # Texto de la ecuación centralizado
        eq_display = QLabel(self.equation_text)
        eq_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        eq_display.setStyleSheet("color: #111827; font-size: 15px; font-weight: bold; font-family: 'Courier New', monospace;")
        eq_box_layout.addWidget(eq_display)
        
        # Leyenda de variables debajo de la caja
        eq_legend = QLabel(self.legend_text)
        eq_legend.setAlignment(Qt.AlignmentFlag.AlignCenter)
        eq_legend.setStyleSheet("color: #6b7280; font-size: 10px; font-style: italic;")
        
        eq_layout.addWidget(eq_title)
        eq_layout.addWidget(eq_box)
        eq_layout.addWidget(eq_legend)
        container_layout.addLayout(eq_layout)
        
        container_layout.addStretch()
        
        # =========================================================================
        # 5. BOTÓN DE ACCIÓN (Entendido)
        # =========================================================================
        btn_action_layout = QHBoxLayout()
        btn_action_layout.addStretch()
        
        accept_btn = QPushButton("Entendido")
        accept_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        accept_btn.setFixedSize(110, 32)
        # Estilo idéntico verde esmeralda de AgroHass
        accept_btn.setStyleSheet("""
            QPushButton {
                background-color: #006643;
                color: #ffffff;
                font-size: 12px;
                font-weight: bold;
                border-radius: 6px;
                border: none;
            }
            QPushButton:hover {
                background-color: #004d32;
            }
            QPushButton:pressed {
                background-color: #003321;
            }
        """)
        accept_btn.clicked.connect(self.accept)
        btn_action_layout.addWidget(accept_btn)
        
        container_layout.addLayout(btn_action_layout)
        dialog_layout.addWidget(container)


# =========================================================================
# EJEMPLO DE USO E INTEGRACIÓN DINÁMICA
# =========================================================================
if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # -------------------------------------------------------------
    # Configuración de datos para el caso NDVI (como el de tu imagen)
    # -------------------------------------------------------------
    ndvi_data = {
        "title": "¿Qué es el NDVI?",
        "definition": "El <b>NDVI (Índice de Vegetación de Diferencia Normalizada)</b> es una métrica utilizada para cuantificar la salud y densidad de la vegetación mediante datos de sensores multiespectrales a bordo de drones. Se calcula a partir de bandas específicas: roja e infrarroja cercana.",
        "average_desc": "Nuestro software calcula el valor promedio de NDVI para cada árbol individualmente. Esto permite identificar variaciones de salud específicas planta por planta, facilitando intervenciones precisas y un monitoreo detallado del vigor de cada cultivo.",
        "equation_str": "NDVI = (NIR - RED) / (NIR + RED)",
        "variable_legend": "*NIR: Infrarrojo Cercano | RED: Banda Roja Visible"
    }

    # -------------------------------------------------------------
    # Ejemplo de cómo podrías reusarlo con otro índice (e.g. NDRE)
    # -------------------------------------------------------------
    ndre_data = {
        "title": "¿Qué es el NDRE?",
        "definition": "El <b>NDRE (Índice de Vegetación de Borde Rojo de Diferencia Normalizada)</b> es una métrica similar al NDVI pero utiliza la banda de transición del Borde Rojo (RedEdge). Es especialmente útil en etapas avanzadas del cultivo donde el NDVI suele saturarse.",
        "average_desc": "El análisis por árbol analiza la penetración foliar profunda para detectar clorosis temprana en las capas internas de la copa del aguacate.",
        "equation_str": "NDRE = (NIR - REG) / (NIR + REG)",
        "variable_legend": "*NIR: Infrarrojo Cercano | REG: Borde Rojo (RedEdge)"
    }
    
    # Instanciamos cargando los datos de NDVI de forma dinámica
    dialog = CustomIndexInfoDialog(
        title=ndvi_data["title"],
        definition=ndvi_data["definition"],
        average_desc=ndvi_data["average_desc"],
        equation_str=ndvi_data["equation_str"],
        variable_legend=ndvi_data["variable_legend"]
    )
    
    dialog.exec()
    sys.exit(app.exec())