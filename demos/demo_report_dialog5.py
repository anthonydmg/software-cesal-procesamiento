import sys, time, tempfile, os, shutil
from PySide6.QtCore import (
    Qt, QSize, QPoint, QThread, Signal, Slot
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QPushButton, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QComboBox, QRadioButton, QButtonGroup, QTextEdit,
    QDialog, QFrame, QGroupBox, QFileDialog, QMessageBox
)


# ============================================================
# WORKER: Generación del PDF (simulada con espera)
# ============================================================
class PdfGeneratorWorker(QThread):
    finished = Signal(str)     # envía ruta del PDF temporal
    failed = Signal(str)       # envía mensaje de error

    def __init__(self, data: dict, parent=None):
        super().__init__(parent)
        self.data = data

    def run(self):
        try:
            # Simulación de un proceso pesado
            time.sleep(3)

            # Crear PDF vacío en carpeta temporal
            temp_dir = tempfile.gettempdir()
            temp_pdf = os.path.join(temp_dir, "reporte_temp.pdf")

            with open(temp_pdf, "wb") as f:
                f.write(b"%PDF-1.4\n%EOF\n")  # PDF mínimo válido

            self.finished.emit(temp_pdf)

        except Exception as e:
            self.failed.emit(str(e))



# ============================================================
# DIALOG PARA GENERAR REPORTE
# ============================================================
class ReportDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.setWindowTitle("Generar Reporte")
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setWindowModality(Qt.ApplicationModal)
        self.setMinimumWidth(700)

        # Estado: Diccionario donde se guarda todo
        self.data = self.default_data()

        self.init_ui()

        if parent:
            self.center_over_parent()

    # -------------------------------
    # Valores por defecto
    # -------------------------------
    def default_data(self):
        return {
            "nombre_analisis": "Análisis Predeterminado 2024-07-26",
            "solicitante": "",
            "departamento": "",
            "provincia": "Seleccionar Provincia",
            "distrito": "Seleccionar Distrito",
            "include_area": False,
            "include_adquisicion": True,
            "include_fecha": False,
            "include_mapa": False,
            "formato": "A3",
            "comentarios": "",
        }

    # -------------------------------
    # Centrado sobre ventana padre
    # -------------------------------
    def center_over_parent(self):
        pg = self.parent.geometry()
        x = pg.x() + (pg.width() - self.width()) // 2
        y = pg.y() + (pg.height() - self.height()) // 2
        self.move(max(0, x), max(0, y))

    # -------------------------------
    # Arrastre del diálogo
    # -------------------------------
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.drag_pos = e.globalPosition().toPoint()

    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.LeftButton:
            diff = e.globalPosition().toPoint() - self.drag_pos
            self.move(self.pos() + diff)
            self.drag_pos = e.globalPosition().toPoint()

    # -------------------------------
    # UI completa
    # -------------------------------
    def init_ui(self):
        self.setStyleSheet(self.dialog_stylesheet())

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 24, 24, 24)

        # HEADER ----------------------
        header = QHBoxLayout()
        title = QLabel("Generar Reporte")
        title.setObjectName("title")
        header.addWidget(title)
        header.addStretch()
        btn_close = QPushButton("✕")
        btn_close.setObjectName("closeButton")
        btn_close.clicked.connect(self.reject)
        header.addWidget(btn_close)
        main_layout.addLayout(header)
        main_layout.addSpacing(8)

        # CAMPOS ----------------------
        self.fields = {}

        # Nombre del análisis
        self.fields["nombre_analisis"] = self.add_lineedit(
            main_layout, "Nombre de Análisis",
            self.data["nombre_analisis"]
        )

        # Solicitante + departamento
        row1 = QHBoxLayout()
        self.fields["solicitante"] = self.add_lineedit(row1, "Nombre del Solicitante")
        row1.addSpacing(12)
        self.fields["departamento"] = self.add_lineedit(row1, "Departamento")
        main_layout.addLayout(row1)

        # Provincia + Distrito
        row2 = QHBoxLayout()
        self.fields["provincia"] = self.add_combobox(
            row2, "Provincia", ["Seleccionar Provincia"]
        )
        row2.addSpacing(12)
        self.fields["distrito"] = self.add_combobox(
            row2, "Distrito", ["Seleccionar Distrito"]
        )
        main_layout.addLayout(row2)

        main_layout.addSpacing(12)

        # OPCIONES ----------------------
        options_box = QGroupBox()
        vopt = QVBoxLayout(options_box)

        self.rb_area = QRadioButton("Incluir área aproximada del terreno")
        self.rb_adq = QRadioButton("Incluir detalles de la adquisición de imágenes")
        self.rb_fecha = QRadioButton("Incluir fecha de adquisición")
        self.rb_mapa = QRadioButton("Incluir mapa para imprimir")

        self.rb_adq.setChecked(True)

        vopt.addWidget(self.rb_area)
        vopt.addWidget(self.rb_adq)
        vopt.addWidget(self.rb_fecha)
        vopt.addWidget(self.rb_mapa)

        main_layout.addWidget(options_box)

        # FORMATO ----------------------
        fr = QHBoxLayout()
        fr.addWidget(QLabel("Formato:"))

        self.rb_a4 = QRadioButton("A4")
        self.rb_a3 = QRadioButton("A3")
        self.rb_a3.setChecked(True)

        self.format_group = QButtonGroup(self)
        self.format_group.addButton(self.rb_a4)
        self.format_group.addButton(self.rb_a3)

        fr.addWidget(self.rb_a4)
        fr.addWidget(self.rb_a3)
        fr.addStretch()
        main_layout.addLayout(fr)

        # COMENTARIOS ----------------------
        self.fields["comentarios"] = self.add_textedit(
            main_layout,
            "Incluir Comentarios o Sugerencias",
            "Añade tus comentarios aquí..."
        )

        # FOOTER ----------------------
        main_layout.addSpacing(12)
        footer = QHBoxLayout()
        footer.addStretch()

        self.btn_cancel = QPushButton("Cancelar")
        self.btn_cancel.setObjectName("btnCancel")
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_generate = QPushButton("Generar PDF")
        self.btn_generate.setObjectName("btnGenerate")
        self.btn_generate.clicked.connect(self.on_generate_clicked)

        footer.addWidget(self.btn_cancel)
        footer.addSpacing(8)
        footer.addWidget(self.btn_generate)
        main_layout.addLayout(footer)

    # -------------------------------
    # Helpers UI
    # -------------------------------
    def add_lineedit(self, parent_layout, label, placeholder=""):
        c = QVBoxLayout()
        lbl = QLabel(label)
        le = QLineEdit()
        le.setPlaceholderText(placeholder)
        le.setFixedHeight(30)
        c.addWidget(lbl)
        c.addWidget(le)

        w = QWidget()
        w.setLayout(c)
        parent_layout.addWidget(w)
        return le

    def add_combobox(self, parent_layout, label, items):
        c = QVBoxLayout()
        lbl = QLabel(label)
        cb = QComboBox()
        cb.addItems(items)
        cb.setFixedHeight(30)
        c.addWidget(lbl)
        c.addWidget(cb)

        w = QWidget()
        w.setLayout(c)
        parent_layout.addWidget(w)
        return cb

    def add_textedit(self, parent_layout, label, placeholder):
        c = QVBoxLayout()
        lbl = QLabel(label)
        te = QTextEdit()
        te.setPlaceholderText(placeholder)
        te.setFixedHeight(120)
        c.addWidget(lbl)
        c.addWidget(te)

        w = QWidget()
        w.setLayout(c)
        parent_layout.addWidget(w)
        return te

    # -------------------------------
    # CLICK EN GENERAR PDF
    # -------------------------------
    def on_generate_clicked(self):
        # 1) Recolectar datos del UI → dict
        self.collect_data()

        # 2) Desactivar botones
        self.btn_generate.setEnabled(False)
        self.btn_cancel.setEnabled(False)

        # 3) Mostrar spinner (texto simple)
        self.btn_generate.setText("Procesando...")

        # 4) Lanzar worker
        self.worker = PdfGeneratorWorker(self.data)
        self.worker.finished.connect(self.on_pdf_ready)
        self.worker.failed.connect(self.on_pdf_error)
        self.worker.start()

    # -------------------------------
    # Recolectar datos desde el UI
    # -------------------------------
    def collect_data(self):
        self.data["nombre_analisis"] = self.fields["nombre_analisis"].text()
        self.data["solicitante"] = self.fields["solicitante"].text()
        self.data["departamento"] = self.fields["departamento"].text()
        self.data["provincia"] = self.fields["provincia"].currentText()
        self.data["distrito"] = self.fields["distrito"].currentText()
        self.data["include_area"] = self.rb_area.isChecked()
        self.data["include_adquisicion"] = self.rb_adq.isChecked()
        self.data["include_fecha"] = self.rb_fecha.isChecked()
        self.data["include_mapa"] = self.rb_mapa.isChecked()
        self.data["formato"] = "A3" if self.rb_a3.isChecked() else "A4"
        self.data["comentarios"] = self.fields["comentarios"].toPlainText()

    # -------------------------------
    # Worker terminado OK
    # -------------------------------
    @Slot(str)
    def on_pdf_ready(self, temp_pdf_path):
        # Restaurar botón
        self.btn_generate.setEnabled(True)
        self.btn_cancel.setEnabled(True)
        self.btn_generate.setText("Generar PDF")

        # Abrir dialog de Guardar
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Guardar Reporte",
            "Reporte.pdf",
            "PDF (*.pdf)"
        )

        if not file_path:
            os.remove(temp_pdf_path)
            return

        shutil.move(temp_pdf_path, file_path)

        QMessageBox.information(self, "Éxito", "Reporte guardado correctamente.")

        self.accept()

    # -------------------------------
    # Worker error
    # -------------------------------
    @Slot(str)
    def on_pdf_error(self, msg):
        QMessageBox.critical(self, "Error", f"No se pudo generar el reporte:\n{msg}")
        self.btn_generate.setEnabled(True)
        self.btn_cancel.setEnabled(True)
        self.btn_generate.setText("Generar PDF")


    # -------------------------------
    # Stylesheet
    # -------------------------------
    def dialog_stylesheet(self):
        return """
        QDialog {
            background: #ffffff;
            border-radius: 8px;
        }
        #title { font-size: 18px; font-weight: 700; }
        QLabel { color: #222; font-size: 12px; }
        QLineEdit, QComboBox, QTextEdit {
            border: 1px solid #e5e5e5;
            border-radius: 6px;
            padding: 6px;
        }
        QPushButton#btnCancel {
            background: #efefef;
            border: 1px solid #dfdfdf;
            border-radius: 8px;
        }
        QPushButton#btnGenerate {
            background: #00c853;
            color: white;
            border-radius: 8px;
        }
        QPushButton#closeButton {
            background: transparent;
            border: none;
        }
        """



# ============================================================
# MAIN WINDOW (para probar)
# ============================================================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Ejemplo App")
        self.resize(900, 600)

        central = QWidget()
        layout = QVBoxLayout(central)

        lbl = QLabel("Ventana principal.\nPresiona el botón para generar reporte.")
        layout.addWidget(lbl)

        btn = QPushButton("Abrir Generar Reporte")
        btn.clicked.connect(self.open_report)
        layout.addWidget(btn)

        layout.addStretch()
        self.setCentralWidget(central)

    def open_report(self):
        dialog = ReportDialog(self)
        dialog.exec()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())
