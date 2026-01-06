from PySide6.QtCore import (
    Qt, QSize, QPoint, QThread, Signal, Slot
)

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QPushButton, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QComboBox, QRadioButton, QButtonGroup, QTextEdit, QCheckBox,
    QDialog, QFrame, QGroupBox, QFileDialog, QMessageBox, QSpacerItem, QSizePolicy
)

import sys, time, tempfile, os, shutil, json


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


class ReportDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent

        # =====================================================
        #  DICT DE VALORES (CON VALORES POR DEFECTO)
        # =====================================================
        self.data = {
            "nombre_analisis": "Análisis Predeterminado 2024-07-26",
            "solicitante": "",
            "departamento": "",
            "provincia": "Seleccionar Provincia",
            "distrito": "Seleccionar Distrito",

            # Opciones
            "incl_area": False,
            "incl_detalles": True,
            "incl_fecha": False,
            "incl_mapa": False,

            # Formato
            "formato": "A3",

            # Comentarios
            "comentarios": ""
        }

        self.setWindowTitle("Generar Reporte")
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint | Qt.WindowSystemMenuHint)
        self.setWindowModality(Qt.ApplicationModal)
        self.setMinimumWidth(700)
        self.setStyleSheet(self.dialog_stylesheet())

        # Referencias a widgets
        self.widgets = {}
        
        self.init_ui()

        if parent:
            self.center_over_parent()

    # ============================================================
    # CENTRAR
    # ============================================================
    def center_over_parent(self):
        parent_geo = self.parent.geometry()
        x = parent_geo.x() + (parent_geo.width() - self.width()) // 2
        y = parent_geo.y() + (parent_geo.height() - self.height()) // 2
        self.move(max(0, x), max(0, y))

    # ============================================================
    # DRAG DEL DIALOGO
    # ============================================================
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            diff = event.globalPosition().toPoint() - self.drag_pos
            self.move(self.pos() + diff)
            self.drag_pos = event.globalPosition().toPoint()

    # ============================================================
    # UI
    # ============================================================
    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 24, 24, 24)
        self.department = None
        # Header
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

        # Form area
        form_area = QVBoxLayout()

        # ---------------------------
        # NOMBRE DEL ANALISIS
        # ---------------------------
        form_area.addWidget(
            self.labeled_lineedit("nombre_analisis", "Nombre de Análisis",
                                  self.data["nombre_analisis"])
        )

        
        # Row: Nombre solicitante | Departamento
        row1 = QHBoxLayout()
        row1.addWidget(self.labeled_lineedit("solicitante", "Nombre del Solicitante"))
        row1.addSpacing(12)
        departamentos = self.load_departementos()

        row1.addWidget(self.depertamentos_combobox("departamento", "Departamento", ["Seleccionar Departamento"] + departamentos))#self.labeled_lineedit("departamento", "Departamento"))
        form_area.addLayout(row1)
        form_area.addSpacing(8)

        # Row: Provincia | Distrito
        row2 = QHBoxLayout()
        row2.addWidget(self.provincias_combobox("provincia", "Provincia", ["Seleccionar Provincia"]))
        row2.addSpacing(12)
        row2.addWidget(self.distritos_combobox("distrito", "Distrito", ["Seleccionar Distrito"]))
        form_area.addLayout(row2)
        form_area.addSpacing(12)

        # ---------------------------
        # OPCIONES
        # ---------------------------
        options_box = QGroupBox()
        options_layout = QVBoxLayout()

        self.widgets["incl_area"] = QCheckBox("Incluir área aproximada del terreno")
        self.widgets["incl_detalles"] = QCheckBox("Incluir detalles de la adquisición de imágenes")
        self.widgets["incl_fecha"] = QCheckBox("Incluir fecha de adquisición")
        self.widgets["incl_mapa"] = QCheckBox("Incluir mapa para imprimir")

        # Valores por defecto del dict
        self.widgets["incl_detalles"].setChecked(True)

        # Conectar señales
        self.widgets["incl_area"].toggled.connect(lambda v: self.update_dict("incl_area", v))
        self.widgets["incl_detalles"].toggled.connect(lambda v: self.update_dict("incl_detalles", v))
        self.widgets["incl_fecha"].toggled.connect(lambda v: self.update_dict("incl_fecha", v))
        self.widgets["incl_mapa"].toggled.connect(lambda v: self.update_dict("incl_mapa", v))

        options_layout.addWidget(self.widgets["incl_area"])
        options_layout.addWidget(self.widgets["incl_detalles"])
        options_layout.addWidget(self.widgets["incl_fecha"])
        options_layout.addWidget(self.widgets["incl_mapa"])
        options_box.setLayout(options_layout)
        form_area.addWidget(options_box)
        form_area.addSpacing(8)

        # ---------------------------
        # FORMATO
        # ---------------------------
        format_row = QHBoxLayout()
        format_row.addWidget(QLabel("Formato:"))
        rb_a4 = QRadioButton("A4")
        rb_a3 = QRadioButton("A3")
        rb_a3.setChecked(True)

        format_group = QButtonGroup(self)
        format_group.addButton(rb_a4)
        format_group.addButton(rb_a3)

        rb_a4.toggled.connect(lambda v: self.update_dict("formato", "A4" if v else self.data["formato"]))
        rb_a3.toggled.connect(lambda v: self.update_dict("formato", "A3" if v else self.data["formato"]))

        format_row.addWidget(rb_a4)
        format_row.addWidget(rb_a3)
        format_row.addStretch()
        form_area.addLayout(format_row)
        form_area.addSpacing(12)
        
        # ---------------------------
        # COMENTARIOS
        # ---------------------------
        form_area.addWidget(
            self.labeled_textedit("comentarios", "Incluir Comentarios o Sugerencias")
        )

        main_layout.addLayout(form_area)
        main_layout.addSpacing(12)

        # ---------------------------
        # FOOTER
        # ---------------------------
        footer = QHBoxLayout()
        footer.addStretch()
        self.btn_cancel = QPushButton("Cancelar")
        self.btn_cancel.setObjectName("btnCancel")
        self.btn_cancel.setFixedHeight(36)
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_generate = QPushButton("Generar PDF")
        self.btn_generate.setObjectName("btnGenerate")
        self.btn_generate.setFixedHeight(36)
        self.btn_generate.clicked.connect(self.on_generate_clicked)

        footer.addWidget(self.btn_cancel)
        footer.addSpacing(8)
        footer.addWidget(self.btn_generate)
        main_layout.addLayout(footer)


    def load_departementos(self):
        departamentos = []
        with open("./assets/departamentos.json", "r", encoding="utf-8") as f:
            departamentos = json.load(f)
            departamentos = departamentos['departamentos']
        return departamentos
    
    def load_provincias(self):
        provincias = []
        with open("./assets/provincias.json", "r", encoding="utf-8") as f:
            provincias = json.load(f)
        return provincias
    
    def load_distritos(self, departamento):
        distritos = None
        if departamento is None:
            return distritos
        path = f"./assets/distritos_{departamento.lower()}.json"
        if os.path.exists(path):
            with open(f"./assets/distritos_{departamento.lower()}.json", "r", encoding="utf-8") as f:
                distritos = json.load(f)
        return distritos
    
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

    # ============================================================
    # FACTORÍAS DE WIDGETS
    # ============================================================
    def labeled_lineedit(self, key, label_text, placeholder=""):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        lbl = QLabel(label_text)
        le = QLineEdit()
        le.setText(placeholder)
        le.textChanged.connect(lambda v: self.update_dict(key, v))
        le.setFixedHeight(30)

        self.widgets[key] = le
        layout.addWidget(lbl)
        layout.addWidget(le)
        return container

    def depertamentos_combobox(self, key, label_text, items):
        def update_provincias(key, v):
                provincias = self.load_provincias()
                self.department = v
                nuevos_items = provincias[v]
                self.pv_cb.clear()
                self.pv_cb.addItems(["Seleccionar Provincia"] + nuevos_items)
                self.update_dict(key, v)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        lbl = QLabel(label_text)
        
        self.dp_cb = QComboBox()
        self.dp_cb.addItems(items)
        self.dp_cb.currentTextChanged.connect(lambda v: update_provincias(key, v))
        self.dp_cb.setFixedHeight(30)

        self.widgets[key] = self.dp_cb
        layout.addWidget(lbl)
        layout.addWidget(self.dp_cb)
        return container

    def provincias_combobox(self, key, label_text, items):
        def update_distritos(key, v):
            distritos = self.load_distritos(self.department)
            if distritos is not None:
                nuevos_items = distritos[v]
                self.dt_cb.clear()
                self.dt_cb.addItems(["Seleccionar Distrito"] + nuevos_items)
            self.update_dict(key, v)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        lbl = QLabel(label_text)
        
        self.pv_cb = QComboBox()
        self.pv_cb.addItems(items)
        self.pv_cb.currentTextChanged.connect(lambda v: update_distritos(key, v))
        self.pv_cb.setFixedHeight(30)

        self.widgets[key] = self.pv_cb
        layout.addWidget(lbl)
        layout.addWidget(self.pv_cb)
        return container
    
    def distritos_combobox(self, key, label_text, items):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        lbl = QLabel(label_text)
        
        self.dt_cb = QComboBox()
        self.dt_cb.addItems(items)
        self.dt_cb.currentTextChanged.connect(lambda v: self.update_dict(key, v))
        self.dt_cb.setFixedHeight(30)

        self.widgets[key] = self.dt_cb
        layout.addWidget(lbl)
        layout.addWidget(self.dt_cb)
        return container

    def labeled_combobox(self, key, label_text, items):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        lbl = QLabel(label_text)
        cb = QComboBox()
        cb.addItems(items)
            
        cb.currentTextChanged.connect(lambda v: self.update_dict(key, v))
        cb.setFixedHeight(30)

        self.widgets[key] = cb
        layout.addWidget(lbl)
        layout.addWidget(cb)
        return container

    def labeled_textedit(self, key, label_text):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        lbl = QLabel(label_text)
        te = QTextEdit()
        te.textChanged.connect(lambda: self.update_dict(key, te.toPlainText()))
        te.setFixedHeight(120)

        self.widgets[key] = te
        layout.addWidget(lbl)
        layout.addWidget(te)
        return container

    def on_generate_clicked(self):
        # 1) Recolectar datos del UI → dict
        #self.collect_data()

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


    @Slot(str)
    def on_pdf_error(self, msg):
        QMessageBox.critical(self, "Error", f"No se pudo generar el reporte:\n{msg}")
        self.btn_generate.setEnabled(True)
        self.btn_cancel.setEnabled(True)
        self.btn_generate.setText("Generar PDF")

    # ============================================================
    # ACTUALIZAR DICCIONARIO
    # ============================================================
    def update_dict(self, key, value):
        self.data[key] = value
        # print(self.data)  # Debug opcional

    # ============================================================
    # BOTÓN GENERAR
    # ============================================================
    def on_generate(self):
        print("=== VALORES DEL DIALOGO ===")
        print(self.data)
        print("===========================")
        self.accept()

    # ============================================================
    # STYLE
    # ============================================================
    def dialog_stylesheet(self):
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
            background: #00c853;
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

# ============================================================
# MAIN WINDOW
# ============================================================
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
        result = dialog.exec()
        if result == QDialog.Accepted:
            print("Datos recibidos del reporte:")
            print(dialog.data)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())
