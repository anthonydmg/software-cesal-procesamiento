from PySide6.QtWidgets import (
    QApplication, QDialog, QLabel, QLineEdit, QComboBox, QPushButton,
    QVBoxLayout, QHBoxLayout, QGridLayout, QTextEdit, QCheckBox, QRadioButton,
    QWidget, QButtonGroup
)

from PySide6.QtWidgets import QApplication, QMainWindow, QPushButton, QVBoxLayout, QWidget
from PySide6.QtCore import Qt
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
import sys

class ReportDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Generar Reporte")
        self.setMinimumWidth(650)
        self.setStyleSheet("""
            QLabel {
                font-size: 14px;
            }
            QLineEdit, QComboBox, QTextEdit {
                padding: 8px;
                font-size: 14px;
                border: 1px solid #c9c9c9;
                border-radius: 6px;
            }
            QCheckBox, QRadioButton {
                font-size: 14px;
            }
            QPushButton {
                padding: 10px 18px;
                font-size: 14px;
                border-radius: 6px;
            }
            QPushButton#cancelBtn {
                background-color: #E9E9E9;
            }
            QPushButton#generateBtn {
                background-color: #00AF4F;
                color: white;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 30, 40, 30)
        layout.setSpacing(18)

        # -----------------------------------------------------------
        # Título
        # -----------------------------------------------------------
        title = QLabel("Generar Reporte")
        title.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        layout.addWidget(title)

        # -----------------------------------------------------------
        # GRID DE CAMPOS SUPERIORES
        # -----------------------------------------------------------
        grid = QGridLayout()
        grid.setSpacing(18)

        # Nombre del análisis
        grid.addWidget(QLabel("Nombre de Análisis"), 0, 0)
        self.analysis_name = QLineEdit("Análisis Predeterminado 2024-07-26")
        grid.addWidget(self.analysis_name, 1, 0, 1, 2)

        # Nombre Solicitante
        grid.addWidget(QLabel("Nombre del Solicitante"), 2, 0)
        self.requester_name = QLineEdit()
        grid.addWidget(self.requester_name, 3, 0)

        # Departamento
        grid.addWidget(QLabel("Departamento"), 2, 1)
        self.department = QLineEdit()
        grid.addWidget(self.department, 3, 1)

        # Provincia
        grid.addWidget(QLabel("Provincia"), 4, 0)
        self.province = QComboBox()
        self.province.addItems(["Seleccionar Provincia", "Lima", "Cusco", "Piura"])
        grid.addWidget(self.province, 5, 0)

        # Distrito
        grid.addWidget(QLabel("Distrito"), 4, 1)
        self.district = QComboBox()
        self.district.addItems(["Seleccionar Distrito", "Miraflores", "San Isidro", "Barranco"])
        grid.addWidget(self.district, 5, 1)

        layout.addLayout(grid)

        # -----------------------------------------------------------
        # OPCIONES (CHECKBOXES)
        # -----------------------------------------------------------
        self.cb_area = QCheckBox("Incluir área aproximada del terreno")
        self.cb_detalles = QCheckBox("Incluir detalles de la adquisición de imágenes")
        self.cb_detalles.setChecked(True)

        self.cb_fecha = QCheckBox("Incluir fecha de adquisición")
        self.cb_mapa = QCheckBox("Incluir mapa para imprimir")

        layout.addWidget(self.cb_area)
        layout.addWidget(self.cb_detalles)
        layout.addWidget(self.cb_fecha)
        layout.addWidget(self.cb_mapa)

        # -----------------------------------------------------------
        # FORMATO (RADIO BUTTONS)
        # -----------------------------------------------------------
        format_layout = QHBoxLayout()
        format_layout.addWidget(QLabel("Formato:"))

        self.format_group = QButtonGroup()
        self.rb_a4 = QRadioButton("A4")
        self.rb_a3 = QRadioButton("A3")
        self.rb_a3.setChecked(True)

        self.format_group.addButton(self.rb_a4)
        self.format_group.addButton(self.rb_a3)

        format_layout.addWidget(self.rb_a4)
        format_layout.addWidget(self.rb_a3)
        format_layout.addStretch()

        layout.addLayout(format_layout)

        # -----------------------------------------------------------
        # COMENTARIOS
        # -----------------------------------------------------------
        layout.addWidget(QLabel("Incluir Comentarios o Sugerencias"))
        self.comments = QTextEdit()
        self.comments.setPlaceholderText("Añade tus comentarios aquí...")
        layout.addWidget(self.comments)

        # -----------------------------------------------------------
        # BOTONES FINALES
        # -----------------------------------------------------------
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self.btn_cancel = QPushButton("Cancelar")
        self.btn_cancel.setObjectName("cancelBtn")
        self.btn_cancel.clicked.connect(self.close)

        self.btn_generate = QPushButton("Generar PDF")
        self.btn_generate.setObjectName("generateBtn")

        btn_row.addWidget(self.btn_cancel)
        btn_row.addWidget(self.btn_generate)

        layout.addLayout(btn_row)

#############################################################

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Mi Aplicación")

        btn = QPushButton("Abrir diálogo")
        btn.clicked.connect(self.abrir_dialogo)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.addWidget(btn)
        self.setCentralWidget(container)

    def abrir_dialogo(self):
        dlg = ReportDialog(self)  # <-- Muy importante el parent
        dlg.exec()      

if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())