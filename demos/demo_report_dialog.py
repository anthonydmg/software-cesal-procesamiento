import sys
from PySide6.QtWidgets import (QApplication, QDialog, QVBoxLayout, QHBoxLayout, 
                               QLabel, QLineEdit, QComboBox, QCheckBox, 
                               QRadioButton, QTextEdit, QPushButton, QFrame, 
                               QWidget, QSpacerItem, QSizePolicy, QButtonGroup)
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QFont

class ReportDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Generar Reporte")
        self.setFixedSize(600, 750)
        
        # Configuración principal de la ventana (Fondo gris claro para simular el modal)
        self.setStyleSheet("background-color: #F3F4F6;") 

        # Layout principal de la ventana
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setAlignment(Qt.AlignCenter)

        # --- TARJETA BLANCA (Contenedor principal) ---
        self.card = QFrame()
        self.card.setObjectName("Card")
        self.card_layout = QVBoxLayout(self.card)
        self.card_layout.setContentsMargins(30, 30, 30, 30)
        self.card_layout.setSpacing(15)
        
        # Aplicamos estilos específicos a la tarjeta y sus componentes
        self.apply_styles()

        # 1. HEADER (Título y Botón Cerrar)
        header_layout = QHBoxLayout()
        title = QLabel("Generar Reporte")
        title.setObjectName("Title")
        
        close_btn = QPushButton("×")
        close_btn.setObjectName("CloseButton")
        close_btn.setFixedSize(30, 30)
        close_btn.clicked.connect(self.reject)
        
        header_layout.addWidget(title)
        header_layout.addStretch()
        header_layout.addWidget(close_btn)
        self.card_layout.addLayout(header_layout)

        # 2. NOMBRE DE ANÁLISIS
        self.create_label("Nombre de Análisis")
        self.input_analisis = QLineEdit("Análisis Predeterminado 2024-07-26")
        self.card_layout.addWidget(self.input_analisis)

        # 3. FILA: SOLICITANTE Y DEPARTAMENTO
        row1_layout = QHBoxLayout()
        
        col1 = QVBoxLayout()
        col1.addWidget(QLabel("Nombre del Solicitante"))
        self.input_solicitante = QLineEdit()
        col1.addWidget(self.input_solicitante)
        
        col2 = QVBoxLayout()
        col2.addWidget(QLabel("Departamento"))
        self.input_departamento = QLineEdit()
        col2.addWidget(self.input_departamento)
        
        row1_layout.addLayout(col1)
        row1_layout.addSpacing(15)
        row1_layout.addLayout(col2)
        self.card_layout.addLayout(row1_layout)

        # 4. FILA: PROVINCIA Y DISTRITO
        row2_layout = QHBoxLayout()
        
        col3 = QVBoxLayout()
        col3.addWidget(QLabel("Provincia"))
        self.combo_provincia = QComboBox()
        self.combo_provincia.addItems(["Seleccionar Provincia", "Lima", "Arequipa"])
        col3.addWidget(self.combo_provincia)
        
        col4 = QVBoxLayout()
        col4.addWidget(QLabel("Distrito"))
        self.combo_distrito = QComboBox()
        self.combo_distrito.addItems(["Seleccionar Distrito", "Miraflores", "Surco"])
        col4.addWidget(self.combo_distrito)
        
        row2_layout.addLayout(col3)
        row2_layout.addSpacing(15)
        row2_layout.addLayout(col4)
        self.card_layout.addLayout(row2_layout)

        # Separador pequeño
        self.card_layout.addSpacing(10)

        # 5. CHECKBOXES
        self.chk_area = QCheckBox("Incluir área aproximada del terreno")
        self.card_layout.addWidget(self.chk_area)

        self.chk_detalles = QCheckBox("Incluir detalles de la adquisición de imágenes")
        self.chk_detalles.setChecked(True) # Marcado como en la imagen
        self.card_layout.addWidget(self.chk_detalles)

        self.chk_fecha = QCheckBox("Incluir fecha de adquisición")
        self.card_layout.addWidget(self.chk_fecha)

        self.chk_mapa = QCheckBox("Incluir mapa para imprimir")
        self.card_layout.addWidget(self.chk_mapa)

        # 6. RADIO BUTTONS (Formato A4/A3) - Indentados
        format_layout = QHBoxLayout()
        format_layout.setContentsMargins(30, 0, 0, 0) # Indentación a la izquierda
        lbl_formato = QLabel("Formato:")
        lbl_formato.setStyleSheet("color: #6B7280; font-weight: normal;")
        
        self.rb_a4 = QRadioButton("A4")
        self.rb_a3 = QRadioButton("A3")
        self.rb_a3.setChecked(True) # Marcado y verde en la imagen
        
        # Grupo para que sean excluyentes
        self.format_group = QButtonGroup(self)
        self.format_group.addButton(self.rb_a4)
        self.format_group.addButton(self.rb_a3)

        format_layout.addWidget(lbl_formato)
        format_layout.addWidget(self.rb_a4)
        format_layout.addWidget(self.rb_a3)
        format_layout.addStretch()
        self.card_layout.addLayout(format_layout)

        # 7. COMENTARIOS
        self.card_layout.addSpacing(10)
        self.create_label("Incluir Comentarios o Sugerencias")
        self.txt_comentarios = QTextEdit()
        self.txt_comentarios.setPlaceholderText("Añade tus comentarios aquí...")
        self.txt_comentarios.setFixedHeight(80)
        self.card_layout.addWidget(self.txt_comentarios)

        # 8. FOOTER BUTTONS
        self.card_layout.addSpacing(10)
        footer_layout = QHBoxLayout()
        footer_layout.addStretch()
        
        self.btn_cancelar = QPushButton("Cancelar")
        self.btn_cancelar.setObjectName("BtnCancel")
        self.btn_cancelar.setCursor(Qt.PointingHandCursor)
        self.btn_cancelar.clicked.connect(self.reject)
        
        self.btn_generar = QPushButton("Generar PDF") # Podrías añadir un icono aquí
        self.btn_generar.setObjectName("BtnSuccess")
        self.btn_generar.setCursor(Qt.PointingHandCursor)
        self.btn_generar.clicked.connect(self.accept)
        
        footer_layout.addWidget(self.btn_cancelar)
        footer_layout.addWidget(self.btn_generar)
        self.card_layout.addLayout(footer_layout)

        # Agregar la tarjeta al layout principal
        main_layout.addWidget(self.card)

    def create_label(self, text):
        lbl = QLabel(text)
        # El estilo ya se aplica globalmente, pero esto ayuda a organizar
        self.card_layout.addWidget(lbl)
        return lbl

    def apply_styles(self):
        # Definimos la hoja de estilos CSS (QSS)
        styles = """
            /* Fuente General */
            QWidget {
                font-family: 'Segoe UI', sans-serif;
                font-size: 13px;
                color: #374151;
            }

            /* Tarjeta Blanca */
            QFrame#Card {
                background-color: white;
                border-radius: 8px;
                border: 1px solid #E5E7EB;
            }

            /* Título */
            QLabel#Title {
                font-size: 18px;
                font-weight: bold;
                color: #111827;
            }

            /* Botón Cerrar (X) */
            QPushButton#CloseButton {
                background-color: transparent;
                border: none;
                font-size: 20px;
                color: #9CA3AF;
            }
            QPushButton#CloseButton:hover {
                color: #374151;
            }

            /* Inputs y Combos */
            QLineEdit, QComboBox, QTextEdit {
                border: 1px solid #D1D5DB;
                border-radius: 6px;
                padding: 8px;
                background-color: #FFFFFF;
                color: #1F2937;
            }
            QLineEdit:focus, QComboBox:focus, QTextEdit:focus {
                border: 1px solid #10B981; /* Verde al enfocar */
            }

            /* Labels de campos */
            QLabel {
                font-weight: 600;
                margin-bottom: 2px;
                color: #4B5563;
            }

            /* Checkboxes y Radio Buttons */
            QCheckBox, QRadioButton {
                spacing: 8px;
                font-weight: 500;
            }
            
            /* Personalización del indicador (cuadradito) del checkbox */
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border: 1px solid #D1D5DB;
                border-radius: 3px;
                background: white;
            }
            QCheckBox::indicator:checked {
                background-color: #00C853; /* El verde vibrante de la imagen */
                border: 1px solid #00C853;
                image: url(data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0ibm9uZSIgc3Ryb2tlPSJ3aGl0ZSIgc3Ryb2tlLXdpZHRoPSIzIiBzdHJva2UtbGluZWNhcD0icm91bmQiIHN0cm9rZS1saW5lam9pbj0icm91bmQiPjxwb2x5bGluZSBwb2ludHM9IjIwIDYgOSAxNyA0IDEyIi8+PC9zdmc+);
            }

            /* Personalización del indicador del Radio Button */
            QRadioButton::indicator {
                width: 16px;
                height: 16px;
                border: 1px solid #D1D5DB;
                border-radius: 8px;
                background: white;
            }
            QRadioButton::indicator:checked {
                background-color: white;
                border: 5px solid #00C853; /* Borde grueso verde para simular el punto */
            }

            /* Botones del Footer */
            QPushButton {
                padding: 8px 16px;
                border-radius: 6px;
                font-weight: 600;
            }
            
            QPushButton#BtnCancel {
                background-color: #E5E7EB;
                color: #374151;
                border: none;
            }
            QPushButton#BtnCancel:hover {
                background-color: #D1D5DB;
            }

            QPushButton#BtnSuccess {
                background-color: #00C853; /* Verde vibrante */
                color: white;
                border: none;
            }
            QPushButton#BtnSuccess:hover {
                background-color: #00A844;
            }
        """
        self.setStyleSheet(self.styleSheet() + styles)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Fuente global opcional para asegurar que se vea bien en cualquier OS
    font = QFont("Segoe UI", 10)
    app.setFont(font)
    
    window = ReportDialog()
    window.show()
    sys.exit(app.exec())