import sys
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QLineEdit, QPushButton, QFrame, QComboBox, 
                             QScrollArea)
from PySide6.QtCore import Qt, Slot

# --- NUEVA CONFIGURACIÓN DE ANCHOS ---
# [Index, RGB, Roja, Verde, NIR, Red Edge, Eliminar]
COL_WIDTHS = [50, 170, 170, 170, 170, 170, 60]

class BandSelector(QComboBox):
    def __init__(self):
        super().__init__()
        # Los hacemos un poco más anchos ahora que hay más espacio
        self.setFixedWidth(160)
        self.addItem("Seleccion...")
        self.setStyleSheet("""
            QComboBox {
                border: 1px solid #D1D5DB;
                border-radius: 6px;
                padding: 6px;
                background-color: white;
            }
            QComboBox::drop-down { border: none; }
        """)

class CaptureRow(QFrame):
    def __init__(self, index, is_new=False):
        super().__init__()
        self.setFixedHeight(70)
        self.setObjectName("FilaCaptura")
        
        self.setStyleSheet("""
            #FilaCaptura {
                border-bottom: 1px solid #F3F4F6;
                background-color: white;
            }
            #FilaCaptura:hover {
                background-color: #F9FAFB;
            }
        """)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 0, 20, 0)
        layout.setSpacing(10)

        # 1. Índice
        #lbl_idx = QLabel("New" if is_new else str(index))
        #lbl_idx.setFixedWidth(COL_WIDTHS[0])
        #lbl_idx.setStyleSheet("color: #3B82F6; font-weight: bold; border: none;" if is_new else "color: #9CA3AF; border: none;")
        #layout.addWidget(lbl_idx)

        # 2. Columnas de Bandas (Empezando por RGB)
        # Creamos 5 selectores para: RGB, Roja, Verde, NIR, Red Edge
        for _ in range(5):
            cb = BandSelector()
            layout.addWidget(cb)

        # 3. Icono de Eliminar (Tacho)
        self.btn_delete = QPushButton("🗑️")
        self.btn_delete.setFixedWidth(COL_WIDTHS[6])
        self.btn_delete.setCursor(Qt.PointingHandCursor)
        self.btn_delete.setStyleSheet("""
            QPushButton {
                color: #EF4444;
                border: none;
                background: transparent;
                font-size: 18px;
            }
            QPushButton:hover { color: #B91C1C; }
        """)
        self.btn_delete.clicked.connect(self.deleteLater)
        layout.addWidget(self.btn_delete)

class ManageMultiSpecBanbScreen(QFrame):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Gestor de Bandas")
        self.resize(1100, 700)
        self.setStyleSheet("background-color: white;")
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(30, 30, 30, 20)

        # --- HEADER (TÍTULO, SUBTÍTULO Y BOTÓN) ---
        header_layout = QHBoxLayout()
        title_vbox = QVBoxLayout()
        title = QLabel("Gestor de Capturas y Bandas")
        title.setStyleSheet("font-size: 22px; font-weight: bold; color: #111827; border: none;")
        subtitle = QLabel("*No fue posible identificar las bandas espectrales en las siguientes capturas. Por favor, realiza la asignación manual de las bandas para cada captura.")
        subtitle.setStyleSheet("color: #FF0000; font-size: 14px; border: none;")
        title_vbox.addWidget(title)
        title_vbox.addWidget(subtitle)
        
        btn_new = QPushButton("+ Nueva Captura")
        btn_new.setCursor(Qt.PointingHandCursor)
        btn_new.setStyleSheet("""
            QPushButton {
                background-color: #3B82F6; color: white; border-radius: 8px;
                padding: 10px 20px; font-weight: bold; border: none;
            }
            QPushButton:hover { background-color: #2563EB; }
        """)
        btn_new.clicked.connect(self.add_empty_row)

        header_layout.addLayout(title_vbox)
        header_layout.addStretch()
        header_layout.addWidget(btn_new)
        main_layout.addLayout(header_layout)

        # --- TABLA ---
        self.table_box = QFrame()
        self.table_box.setObjectName("ContenedorPrincipal")
        self.table_box.setStyleSheet("""
            #ContenedorPrincipal {
                border: 1px solid #E5E7EB;
                border-radius: 12px;
                background-color: white;
            }
        """)
        
        table_vbox = QVBoxLayout(self.table_box)
        table_vbox.setContentsMargins(0, 0, 0, 0)
        table_vbox.setSpacing(0)

        # Encabezado
        header_row = QFrame()
        header_row.setFixedHeight(50)
        header_row.setStyleSheet("""
            background-color: #F9FAFB; 
            border-bottom: 1px solid #E5E7EB; 
            border-top-left-radius: 12px; 
            border-top-right-radius: 12px;
        """)
        hr_layout = QHBoxLayout(header_row)
        hr_layout.setContentsMargins(20, 0, 20, 0)
        hr_layout.setSpacing(10)

        # Etiquetas de columna (Sin el identificador)
        cols = [
            #("#", COL_WIDTHS[0]), 
            ("<font color='#A855F7'>●</font> RGB", COL_WIDTHS[1]), 
            ("<font color='#EF4444'>●</font> Roja", COL_WIDTHS[2]), 
            ("<font color='#22C55E'>●</font> Verde", COL_WIDTHS[3]), 
            ("<font color='#6B7280'>●</font> NIR", COL_WIDTHS[4]), 
            ("<font color='#F97316'>●</font> Red Edge", COL_WIDTHS[5]), 
            ("", COL_WIDTHS[6])
        ]
        
        for text, w in cols:
            lbl = QLabel(text)
            lbl.setFixedWidth(w)
            lbl.setStyleSheet("font-weight: bold; color: #4B5563; font-size: 12px; border: none;")
            hr_layout.addWidget(lbl)
        
        table_vbox.addWidget(header_row)

        # Scroll
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("QScrollArea { border: none; background: white; border-bottom-left-radius: 12px; border-bottom-right-radius: 12px; }")
        
        self.scroll_content = QWidget()
        self.rows_layout = QVBoxLayout(self.scroll_content)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(0)
        self.rows_layout.setAlignment(Qt.AlignTop)
        self.scroll.setWidget(self.scroll_content)
        
        table_vbox.addWidget(self.scroll)
        main_layout.addWidget(self.table_box)

        # Filas iniciales
        for i in range(1, 4):
            self.rows_layout.addWidget(CaptureRow(i))

    @Slot()
    def add_empty_row(self):
        # Añade la fila nueva al principio
        self.rows_layout.insertWidget(0, CaptureRow(0, is_new=True))

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ManageMultiSpecBanbScreen()
    window.show()
    sys.exit(app.exec())