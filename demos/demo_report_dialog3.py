from PySide6.QtCore import Qt, QSize, QPoint
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QPushButton, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QComboBox, QRadioButton, QButtonGroup, QTextEdit,
    QDialog, QFrame, QGroupBox, QSpacerItem, QSizePolicy
)
import sys

class ReportDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.setWindowTitle("Generar Reporte")
        # Hacer el dialog con aspecto "card" flotante
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint | Qt.WindowSystemMenuHint)
        
        # Modal para que esté por encima de la ventana principal
        self.setWindowModality(Qt.ApplicationModal)
        self.setMinimumWidth(700)
        self.setStyleSheet(self.dialog_stylesheet())
        self.init_ui()
        # Centrar encima del padre (si existe)
        if parent:
            self.center_over_parent()

    def center_over_parent(self):
        # Calcula para centrar el dialog sobre la ventana padre
        parent_geo = self.parent.geometry()
        x = parent_geo.x() + (parent_geo.width() - self.width()) // 2
        y = parent_geo.y() + (parent_geo.height() - self.height()) // 2
        self.move(max(0, x), max(0, y))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            diff = event.globalPosition().toPoint() - self.drag_pos
            self.move(self.pos() + diff)
            self.drag_pos = event.globalPosition().toPoint()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 24, 24, 24)

        # Header con título y botón cerrar (estético)
        header = QHBoxLayout()
        title = QLabel("Generar Reporte")
        title.setObjectName("title")
        header.addWidget(title)
        header.addStretch()
        btn_close = QPushButton("✕")
        btn_close.setObjectName("closeButton")
        btn_close.setFixedSize(28, 28)
        btn_close.clicked.connect(self.reject)
        header.addWidget(btn_close)
        main_layout.addLayout(header)
        main_layout.addSpacing(8)

        # Grid-like area con campos
        form_area = QVBoxLayout()
        # Nombre de Análisis
        form_area.addWidget(self.labeled_lineedit("Nombre de Análisis", "Análisis Predeterminado 2024-07-26"))
        # Row: Nombre del Solicitante | Departamento
        row1 = QHBoxLayout()
        row1.addWidget(self.labeled_lineedit("Nombre del Solicitante"))
        row1.addSpacing(12)
        row1.addWidget(self.labeled_lineedit("Departamento"))
        form_area.addLayout(row1)
        form_area.addSpacing(8)

        # Row: Provincia | Distrito (combos)
        row2 = QHBoxLayout()
        province = self.labeled_combobox("Provincia", ["Seleccionar Provincia"])
        district = self.labeled_combobox("Distrito", ["Seleccionar Distrito"])
        row2.addWidget(province)
        row2.addSpacing(12)
        row2.addWidget(district)
        form_area.addLayout(row2)
        form_area.addSpacing(12)

        # Opciones con radio / check-like (usaremos radio + group for look)
        options_box = QGroupBox()
        options_layout = QVBoxLayout()
        rb1 = QRadioButton("Incluir área aproximada del terreno")
        rb2 = QRadioButton("Incluir detalles de la adquisición de imágenes")
        rb2.setChecked(True)
        rb3 = QRadioButton("Incluir fecha de adquisición")
        rb4 = QRadioButton("Incluir mapa para imprimir")
        # Agrupar para ejemplo (puedes usar checkboxes si quieres multi-selección)
        # Si quieres multi-selección, cambiar a QCheckBox.
        options_layout.addWidget(rb1)
        options_layout.addWidget(rb2)
        options_layout.addWidget(rb3)
        options_layout.addWidget(rb4)
        options_box.setLayout(options_layout)
        form_area.addWidget(options_box)
        form_area.addSpacing(8)

        # Formato con radios A4 / A3
        format_row = QHBoxLayout()
        format_row.addWidget(QLabel("Formato:"))
        rb_a4 = QRadioButton("A4")
        rb_a3 = QRadioButton("A3")
        rb_a3.setChecked(True)
        format_group = QButtonGroup(self)
        format_group.addButton(rb_a4)
        format_group.addButton(rb_a3)
        format_row.addWidget(rb_a4)
        format_row.addWidget(rb_a3)
        format_row.addStretch()
        form_area.addLayout(format_row)
        form_area.addSpacing(12)

        # Comentarios (TextEdit)
        form_area.addWidget(self.labeled_textedit("Incluir Comentarios o Sugerencias", "Añade tus comentarios aquí..."))

        main_layout.addLayout(form_area)
        main_layout.addSpacing(12)

        # Footer botones Cancelar / Generar PDF
        footer = QHBoxLayout()
        footer.addStretch()
        btn_cancel = QPushButton("Cancelar")
        btn_cancel.setObjectName("btnCancel")
        btn_cancel.setFixedHeight(36)
        btn_cancel.clicked.connect(self.reject)

        btn_generate = QPushButton("Generar PDF")
        btn_generate.setObjectName("btnGenerate")
        btn_generate.setFixedHeight(36)
        btn_generate.clicked.connect(self.on_generate)

        footer.addWidget(btn_cancel)
        footer.addSpacing(8)
        footer.addWidget(btn_generate)

        main_layout.addLayout(footer)

    def labeled_lineedit(self, label_text, placeholder_text=""):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        lbl = QLabel(label_text)
        le = QLineEdit()
        le.setPlaceholderText(placeholder_text)
        le.setFixedHeight(30)
        layout.addWidget(lbl)
        layout.addWidget(le)
        return container

    def labeled_combobox(self, label_text, items):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        lbl = QLabel(label_text)
        cb = QComboBox()
        cb.addItems(items)
        cb.setFixedHeight(30)
        layout.addWidget(lbl)
        layout.addWidget(cb)
        return container

    def labeled_textedit(self, label_text, placeholder):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        lbl = QLabel(label_text)
        te = QTextEdit()
        te.setPlaceholderText(placeholder)
        te.setFixedHeight(120)
        layout.addWidget(lbl)
        layout.addWidget(te)
        return container

    def on_generate(self):
        # Aquí puedes leer los campos y generar el PDF.
        # Por ahora solo aceptamos el diálogo.
        # Ejemplo:
        print("Generar PDF (aquí procesarías los datos)...")
        self.accept()

    
    def dialog_stylesheet(self):
        # Stylesheet para darle un aspecto similar: fondo blanco, sombras sutiles, botones verdes, etc.
        return """
        QDialog {
            background: #ffffff;
            border-radius: 8px;
        }
        #title {
            font-size: 18px;
            font-weight: 700;
        }
        QLabel {
            color: #222;
            font-size: 12px;
        }
        QLineEdit, QComboBox, QTextEdit {
            border: 1px solid #e5e5e5;
            border-radius: 6px;
            padding: 6px;
            background: #fff;
        }
        QGroupBox {
            border: none;
        }
        QPushButton#btnCancel {
            background: #efefef;
            border: 1px solid #dfdfdf;
            border-radius: 8px;
            padding-left: 12px;
            padding-right: 12px;
        }
        QPushButton#btnCancel:hover { background: #e6e6e6; }
        QPushButton#btnGenerate {
            background: #00c853; /* verde */
            color: white;
            border-radius: 8px;
            padding-left: 16px;
            padding-right: 16px;
        }
        QPushButton#btnGenerate:hover { background: #00b24a; }
        QPushButton#closeButton {
            background: transparent;
            border: none;
            font-size: 14px;
        }
        """

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Ejemplo App - Ventana Principal")
        self.resize(1024, 720)
        self.init_ui()

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        info = QLabel("Ventana Principal\nPresiona el botón para abrir el diálogo 'Generar Reporte'.")
        info.setWordWrap(True)
        layout.addWidget(info)

        btn_open = QPushButton("Abrir Generar Reporte")
        btn_open.setFixedSize(QSize(220, 40))
        btn_open.clicked.connect(self.open_report_dialog)
        layout.addWidget(btn_open)

        layout.addStretch()

    def open_report_dialog(self):
        dialog = ReportDialog(self)
        # Dos formas de mostrar encima:
        # 1) modal con exec() -> bloquea hasta se cierre
        result = dialog.exec()  # exec() muestra modal y se queda encima de la ventana principal
        # 2) Si quisieras no bloquear, podrías usar dialog.show() y setModal(True)
        if result == QDialog.Accepted:
            print("Usuario generó el PDF (o presionó Generar).")
        else:
            print("Dialog cancelado.")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())
