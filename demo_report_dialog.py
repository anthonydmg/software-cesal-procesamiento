import sys
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QLineEdit, QPushButton, QFrame, QComboBox, 
                             QScrollArea, QDialog, QCheckBox, QTextEdit, QRadioButton, QButtonGroup, QMessageBox, QFileDialog, QDoubleSpinBox)

from PySide6.QtCore import Qt, Slot, QRectF, Signal, QSize
from PySide6.QtGui import QFont, QPen, QBrush, QColor, QPainter, QDoubleValidator
from PySide6.QtWidgets import QGraphicsDropShadowEffect
from PySide6.QtWebEngineWidgets import QWebEngineView
import json
import shutil
import os
from core.utils import resource_path

class CustomCheckButton(QWidget):
    toggled = Signal(bool)

    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self._checked = False
        self.text = text

        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(24)
        self.setAttribute(Qt.WA_StyledBackground, True)

    # -----------------------------
    # API pública
    # -----------------------------
    def isChecked(self):
        return self._checked

    def setChecked(self, value: bool):
        if self._checked != value:
            self._checked = value
            self.toggled.emit(self._checked)
            self.update()

    def toggle(self):
        self.setChecked(not self._checked)

    # -----------------------------
    # Eventos
    # -----------------------------
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.toggle()

    def enterEvent(self, event):
        self.update()

    def leaveEvent(self, event):
        self.update()

    # -----------------------------
    # Renderizado
    # -----------------------------
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHints(QPainter.Antialiasing)

        rect = self.rect()
        box_size = 20
        x = 4
        y = (rect.height() - box_size) // 2

        # Hover
        if self.underMouse():
            painter.fillRect(rect, QColor(0, 0, 0, 8))

        # Caja exterior
        pen = QPen(QColor(80, 80, 80), 1.8)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)

        r = QRectF(x, y, box_size, box_size)
        painter.drawRoundedRect(r, 4, 4)

        # Check interno
        if self._checked:
            painter.setBrush(QBrush(QColor(0, 50, 150))) #QColor(40, 160, 90)
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(QRectF(x + 4, y + 4, box_size - 8, box_size - 8), 3, 3)

        # Texto
        painter.setPen(QColor(30, 30, 30))
        painter.setFont(QFont("Segoe UI", 10))

        painter.drawText(
            box_size + 12,
            0,
            rect.width() - box_size - 12,
            rect.height(),
            Qt.AlignVCenter | Qt.AlignLeft,
            self.text
        )

    def sizeHint(self):
        return QSize(150, 28)
    
class ReportDialog(QDialog):
    def __init__(self, parent=None, base_dir = None, name_analysis = "Análisis Predeterminado 2024-07-26"):
        super().__init__(parent)
        self.parent = parent
        self.base_dir = base_dir
        #self.setStyleSheet("background: yellow;")
        # =====================================================
        #  DICT DE VALORES (CON VALORES POR DEFECTO)
        # =====================================================

        
        #processing_sumary = self.load_sumary_processing(base_dir)
        
        self.data = {
            "nombre_analisis": name_analysis,
            "solicitante": "",
            "departamento": "",
            "provincia": "Seleccionar Provincia",
            "distrito": "Seleccionar Distrito",
            "zona:": "Seleccionar Zona",
            "riego": "Seleccionar",
            "suelo": "Seleccionar",
            "fenologia": "Seleccionar",
            # Opciones
            "incl_area": False,
            "incl_detalles": True,
            "incl_fecha": False,
            "incl_mapa": False,

            # Formato
            "formato": "A3",
            # Comentarios
            "comentarios": "",
            #"mapa": processing_sumary['map_trees'],
            "base_dir": base_dir
        }

        self.setWindowTitle("Generar Reporte")
        
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint | Qt.WindowSystemMenuHint)
        #self.setWindowModality(Qt.ApplicationModal)
        self.setMinimumWidth(700)
        self.setStyleSheet(self.dialog_stylesheet())

        # Referencias a widgets
        self.widgets = {}
        
        self.init_ui()

        if parent:
            self.center_over_parent()


    def load_sumary_processing(self, base_dir):
        with open(f"{base_dir}/processing_sumary.json", "r") as f:
            processing_sumary = json.load(f)
            return processing_sumary
        
        return None
    # ============================================================
    # CENTRAR
    # ============================================================
    def center_over_parent(self):
        parent_geo = self.parent.geometry()
        x = parent_geo.x() + (parent_geo.width() - self.width()) // 2 
        y = parent_geo.y() + (parent_geo.height() - self.height()) // 2 - 600 // 2
        self.move(max(0, x), max(0, y))


    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return super().mousePressEvent(event)

        # posición local (coord de widget)
        local_pos = event.position().toPoint()

        # widget bajo el cursor
        w = self.childAt(local_pos)

        # recorrer hacia arriba para ver si clic fue dentro de un control interactivo
        interactive_types = (QCheckBox, QLineEdit, QComboBox, QTextEdit, QPushButton, CustomCheckButton)
        while w is not None and w is not self:
            if isinstance(w, interactive_types):
                # dejar que el control procese el evento
                return super().mousePressEvent(event)
            w = w.parentWidget()

        # Si llegamos aquí: no fue sobre un control interactivo → iniciar drag
        self._dragging = True
        self._drag_pos = event.globalPosition().toPoint()
        event.accept()

    def mouseMoveEvent(self, event):
        if getattr(self, "_dragging", False):
            new_pos = self.pos() + (event.globalPosition().toPoint() - self._drag_pos)
            self.move(new_pos)
            self._drag_pos = event.globalPosition().toPoint()
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        # terminar arrastre
        self._dragging = False
        super().mouseReleaseEvent(event)
        
    # ============================================================
    # DRAG DEL DIALOGO
    # ============================================================
    # def mousePressEvent(self, event):
    #     if event.button() == Qt.LeftButton:
    #         self.drag_pos = event.globalPosition().toPoint()

    # def mouseMoveEvent(self, event):
    #     if event.buttons() & Qt.LeftButton:
    #         diff = event.globalPosition().toPoint() - self.drag_pos
    #         self.move(self.pos() + diff)
    #         self.drag_pos = event.globalPosition().toPoint()

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
            self.labeled_lineedit("nombre_analisis", "Nombre de Parcela",
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
        row2.addSpacing(12)
        row2.addWidget(self.sector_combobox("zona", "Zona/Sector", ["Seleccionar"]))
        form_area.addLayout(row2)
        form_area.addSpacing(12)

        details_field = QLabel("DETALLES DEL CAMPO DE CULTIVO")
        details_field.setStyleSheet("font-weight: bold; font-size: 11px; margin-bottom: 4px;")

        form_area.addWidget(details_field)
        
        row3 = QHBoxLayout()

        row3.addWidget(self.irrigation_combobox(
            "riego", "Tipo de Riego",
            ["Seleccionar", "Gravedad", "Tecnificado"]
        ))
        row3.addSpacing(12)
        row3.addWidget(self.soil_combobox(
            "suelo", "Tipo de Suelo",
            ["Seleccionar", "Arenoso", "Franco", "Arcilla", "Limoso"]
        ))
        row3.addSpacing(12)
        row3.addWidget(self.phenology_combobox(
            "fenologia", "Fenologia del Cultivo",
            ["Seleccionar", "Yema Hinchada", "Estado de Colifor",
            "Desarrollo de Brotes", "Apertura de flor", "Cuajado",
            "Crecimiento de fruto", "Madures"]
        ))
        row3.addSpacing(12)
        row3.addWidget(self.edad_cultivo_input(
            "crop_age", "Edad aproximada de cultivo (años)"
        ))

        # ✅ Repartir espacio igual entre todos
        row3.setStretch(0, 1)
        row3.setStretch(1, 1)
        row3.setStretch(2, 1)
        row3.setStretch(3, 1)
        form_area.addLayout(row3)
        form_area.addSpacing(12)

        options_layout = QVBoxLayout()

        label_opciones = QLabel("Opciones")
        label_opciones.setStyleSheet("font-weight: bold; font-size: 14px; margin-bottom: 4px;")
        options_layout.addWidget(label_opciones)

        self.widgets["incl_area"] = CustomCheckButton("Incluir área aproximada del terreno")
        self.widgets["incl_detalles"] = CustomCheckButton("Incluir detalles de la adquisición de imágenes")
        self.widgets["incl_fecha"] = CustomCheckButton("Incluir fecha de adquisición")
        self.widgets["incl_mapa"] = CustomCheckButton("Incluir mapa para imprimir")

        # Valor por defecto
        self.widgets["incl_detalles"].setChecked(True)

        # Conectar señales
        self.widgets["incl_area"].toggled.connect(lambda v: self.update_dict("incl_area", v))
        self.widgets["incl_detalles"].toggled.connect(lambda v: self.update_dict("incl_detalles", v))
        self.widgets["incl_fecha"].toggled.connect(lambda v: self.update_dict("incl_fecha", v))
        self.widgets["incl_mapa"].toggled.connect(lambda v: self.change_incl_last_mapa("incl_mapa", v))

        # Agregar los QCheckBox directamente
        options_layout.addWidget(self.widgets["incl_area"])
        options_layout.addWidget(self.widgets["incl_detalles"])
        options_layout.addWidget(self.widgets["incl_fecha"])
        options_layout.addWidget(self.widgets["incl_mapa"])

        # Añadir al form_area
        form_area.addLayout(options_layout)
        form_area.addSpacing(8)

        # ---------------------------
        # FORMATO
        # ---------------------------
        format_row = QHBoxLayout()
        format_row.addWidget(QLabel("Formato:"))
        self.rb_a4 = QRadioButton("A4")
        self.rb_a3 = QRadioButton("A3")
        
        self.rb_a3.setChecked(True)

        format_group = QButtonGroup(self)
        format_group.addButton(self.rb_a4)
        format_group.addButton(self.rb_a3)

        self.rb_a4.toggled.connect(lambda v: self.update_dict("formato", "A4" if v else self.data["formato"]))
        self.rb_a3.toggled.connect(lambda v: self.update_dict("formato", "A3" if v else self.data["formato"]))
        
        self.rb_a3.setEnabled(False)
        self.rb_a4.setEnabled(False)

        format_row.addWidget(self.rb_a4)
        format_row.addWidget(self.rb_a3)
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

    def change_incl_last_mapa(self, key, v):
        print("change_incl_last_mapa v:", v)
        if v:
            self.rb_a3.setEnabled(True)
            self.rb_a4.setEnabled(True)
        else:
            self.rb_a3.setEnabled(False)
            self.rb_a4.setEnabled(False)
        
        self.update_dict(key, v)


    def load_departementos(self):
        departamentos = []
        with open(resource_path(os.path.join("assets", "departamentos.json")), "r", encoding="utf-8") as f:
            departamentos = json.load(f)
            departamentos = departamentos['departamentos']
        return departamentos
    
    def load_provincias(self):
        provincias = []
        with open(resource_path(os.path.join("assets", "provincias.json")), "r", encoding="utf-8") as f:
            provincias = json.load(f)
        return provincias
    
    def load_distritos(self, departamento):
        distritos = None
        if departamento is None:
            return distritos
        path = resource_path(os.path.join("assets", f"distritos_{departamento.lower()}.json")) 
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                distritos = json.load(f)
        return distritos
    
    @Slot(str)
    def on_pdf_ready(self, temp_pdf_path, name_analisys):
        # Restaurar botón
        self.btn_generate.setEnabled(True)
        self.btn_cancel.setEnabled(True)
        self.btn_generate.setText("Generar PDF")

        # Abrir dialog de Guardar
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Guardar Reporte",
            f"{name_analisys}.pdf",
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

        le.setStyleSheet("""
        QLineEdit {
            border: 1px solid #dcdcdc;
            border-radius: 8px;
            padding: 8px;
            font-size: 12px;
            background: white;
        }

        QLineEdit:focus {
            border: 1px solid #4a90e2;
        }
        """)


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
                if v!= '' and v != 'Seleccionar Provincia':
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
    

    def irrigation_combobox(self, key, label_text, items):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        lbl = QLabel(label_text)
        
        self.irrig_cb = QComboBox()
        self.irrig_cb.addItems(items)
        self.irrig_cb.currentTextChanged.connect(lambda v: self.update_dict(key, v))
        self.irrig_cb.setFixedHeight(30)

        self.widgets[key] = self.irrig_cb
        layout.addWidget(lbl)
        layout.addWidget(self.irrig_cb)
        return container


    def soil_combobox(self, key, label_text, items):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        lbl = QLabel(label_text)
        
        self.soil_cb = QComboBox()
        self.soil_cb.addItems(items)
        self.soil_cb.currentTextChanged.connect(lambda v: self.update_dict(key, v))
        self.soil_cb.setFixedHeight(30)

        self.widgets[key] = self.soil_cb
        layout.addWidget(lbl)
        layout.addWidget(self.soil_cb)
        return container
    
    def phenology_combobox(self, key, label_text, items):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        lbl = QLabel(label_text)
        
        self.pheno_cb = QComboBox()
        self.pheno_cb.addItems(items)
        self.pheno_cb.currentTextChanged.connect(lambda v: self.update_dict(key, v))
        self.pheno_cb.setFixedHeight(30)

        self.widgets[key] = self.pheno_cb
        layout.addWidget(lbl)
        layout.addWidget(self.pheno_cb)
        return container
    
    def add_if_new(self):
        text = self.zone_cb.currentText()
        if text and self.zone_cb.findText(text) == -1:
            self.zone_cb.addItem(text)
        
    def sector_combobox(self, key, label_text, items): 
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        lbl = QLabel(label_text)

        self.zone_cb = QComboBox()
        self.zone_cb.addItems(items)

        # ✅ Permitir escribir nuevas opciones
        self.zone_cb.setEditable(True)

        # Guardar el texto escrito o seleccionado
        self.zone_cb.currentTextChanged.connect(
            lambda v: self.update_dict(key, v)
        )

        self.zone_cb.setFixedHeight(30)
        self.zone_cb.lineEdit().editingFinished.connect(self.add_if_new)

        self.widgets[key] = self.zone_cb
        layout.addWidget(lbl)
        layout.addWidget(self.zone_cb)

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

    def edad_cultivo_input(self, key, label_text):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Label arriba
        lbl = QLabel(label_text)
        lbl.setStyleSheet("""
            QLabel {
                font-size: 12px;
                color: #444;
                font-weight: 500;
            }
        """)

        # Input tipo web
        line = QLineEdit()
        line.setPlaceholderText("Ej: 2.5")
        line.setFixedWidth(140)
        #line.setFixedHeight(35)

        # ✅ Solo números decimales permitidos
        validator = QDoubleValidator(0.0, 100.0, 2)  # min, max, decimales
        validator.setNotation(QDoubleValidator.StandardNotation)
        line.setValidator(validator)

        # Estilo moderno como el formulario
        line.setStyleSheet("""
            QLineEdit {
                border: 1px solid #dcdcdc;
                border-radius: 8px;
                padding: 8px;
                font-size: 12px;
                background: white;
            }

            QLineEdit:focus {
                border: 1px solid #4a90e2;
            }
        """)

        # Guardar valor cuando cambia
        line.textChanged.connect(lambda v: self.update_dict(key, v))

        # Guardar widget
        self.widgets[key] = line

        # Agregar al layout
        layout.addWidget(lbl)
        layout.addWidget(line)

        return container

    def labeled_textedit(self, key, label_text, max_chars = 1000):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        lbl = QLabel(label_text)
        te = QTextEdit()

        te.setStyleSheet("""
        QTextEdit {
            border: 1px solid #dcdcdc;
            border-radius: 4px;
            padding: 8px;
            font-size: 12px;
            background: white;
        }

        QTextEdit:focus {
            border: 1px solid #4a90e2;
        }
        """)

        #te.textChanged.connect(lambda: self.update_dict(key, te.toPlainText()))
        te.setFixedHeight(130)

        # Counter characters

        counter_lbl = QLabel(f"0 /{max_chars}")
        counter_lbl.setAlignment(Qt.AlignRight)
        counter_lbl.setStyleSheet("""
            QLabel {
                font-size: 12px;
                color: gray;
            }

        """)

        # Funcion

        def on_text_changed():
            text = te.toPlainText()
            if len(text) > max_chars:
                te.blockSignals(True)
                te.setPlainText(text[:max_chars])
                te.blockSignals(False)
                # mover cursor al final
                cursor = te.textCursor()
                cursor.movePosition(cursor.End)
                te.setTextCursor(cursor)

            # 
            current_len = len(te.toPlainText())
            counter_lbl.setText(f"{current_len} / {max_chars}")

            # Guardar en dict
            self.update_dict(key, te.toPlainText())

        te.textChanged.connect(on_text_changed)
        self.widgets[key] = te
        layout.addWidget(lbl)
        layout.addWidget(te)
        layout.addWidget(counter_lbl)
        return container

    def on_generate_clicked(self):
        # 1) Recolectar datos del UI → dict
        #self.collect_data()
        
        #self.data
        
        # 2) Desactivar botones
        self.btn_generate.setEnabled(False)
        self.btn_cancel.setEnabled(False)

        # 3) Mostrar spinner (texto simple)
        self.btn_generate.setText("Procesando...")

        # 4) Lanzar worker
        # self.worker = PdfGeneratorWorker(self.data)
        # self.worker.finished.connect(self.on_pdf_ready)
        # self.worker.failed.connect(self.on_pdf_error)
        # self.worker.start()


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
    

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Gestor de Bandas")
        self.setStyleSheet("background-color: white;")
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(30, 30, 30, 20)

        card = ReportDialog()
        main_layout.addWidget(card)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())