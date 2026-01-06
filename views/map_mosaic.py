from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QGroupBox, 
                               QLabel, QGraphicsScene, QGraphicsView, QGraphicsPixmapItem, 
                               QToolButton, QFrame, QPushButton, QFileDialog, QRadioButton, 
                               QToolTip, QDialog, QMessageBox, QSpacerItem, QSizePolicy,
                               QLineEdit, QComboBox, QButtonGroup, QTextEdit, QCheckBox, QStackedWidget
                               )
from PySide6.QtGui import QLinearGradient, QPalette, QColor, QPainter, QPixmap, QImage, QIcon
from PySide6.QtGui import QFont, QPen, QBrush
from PySide6.QtCore import Qt, QRectF, Signal, QPoint, QEvent, QThread, Slot, QSize, QRect
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
import re
import os
from osgeo import gdal
import numpy as np
from tempfile import mkstemp
import folium
from PySide6.QtWebEngineWidgets import QWebEngineView
import json
from datetime import datetime
import cv2
import copy
from core.report_generator import crear_reporte, EXAMPLE_DATOS_ARBOLES, EXAMPLE_MAP_IMAGE, EXAMPLE_COMENTARIOS
import sys, time, tempfile, os, shutil, json

from core.utils import resource_path

class ColorTreeState:
    MAP = {
        "SALUDABLE": {
            "color_hex": "#00FF32",
            "color_rgb": (0, 255, 50)
        },
        "DEFICIENCIA": {
            "color_hex": "#BFF700",
            "color_rgb": (191, 247, 0)
        }
    }

    @staticmethod
    def get_rgb(name: str):
        return ColorTreeState.MAP.get(name.upper(), {"color_rgb": (0, 255, 50)})['color_rgb']
    


class ColorNdvi:

    @staticmethod
    def get_color(ndvi_value):
        # Define segments (low, high, color_low(RGB), color_high(RGB))

        color_dark_orange = np.array([220, 100, 0], dtype=np.float32)
        color_soft_orange = np.array([220, 170, 0], dtype=np.float32) # Intermedio
        color_yellow      = np.array([220, 240, 0], dtype=np.float32)
        color_lime        = np.array([120, 200, 0], dtype=np.float32) # Intermedio hacia verde
        color_green       = np.array([20, 80, 0], dtype=np.float32)

        color_scale = [
            (-1.0, -0.6, np.array([0, 0, 0], dtype=np.float32),   np.array([0, 0, 251], dtype=np.float32)),   # black -> blue
            (-0.6, 0.0, np.array([0, 0, 251], dtype=np.float32), np.array([220, 0, 251], dtype=np.float32)), # blue -> purple
            (0.0, 0.5, np.array([220, 0, 251], dtype=np.float32), np.array([220, 0, 120], dtype=np.float32)), # purple -> pink
            (0.5, 0.6, np.array([220, 0, 120], dtype=np.float32),  np.array([220, 100, 0], dtype=np.float32)), # pink -> dark orange
            # --- RANGO 0.6 a 0.9 (Dividido en dos partes) ---
            # De 0.80 a 0.85: Naranja oscuro a Naranja suave
            (0.60, 0.70, color_dark_orange, color_soft_orange),
            
            # De 0.85 a 0.90: Naranja suave a Amarillo
            (0.70, 0.80, color_soft_orange, color_yellow),

            # --- RANGO 0.9 a 1.0 (Dividido en dos partes) ---
            # De 0.90 a 0.95: Amarillo a Verde Lima (hace que el 0.92 se vea muy distinto al 0.98)
            (0.80, 0.85, color_yellow, color_lime),
            
            # De 0.95 a 1.00: Verde Lima a Verde Oscuro
            (0.85, 1.00, color_lime, color_green),
        ]

        segments = [
            (-1.0, -0.6, np.array([0, 0, 0], dtype=np.float32),   np.array([0, 0, 251], dtype=np.float32)),   # black -> blue
            (-0.6, 0.0, np.array([0, 0, 251], dtype=np.float32), np.array([220, 0, 251], dtype=np.float32)), # blue -> purple
            (0.0, 0.5, np.array([220, 0, 251], dtype=np.float32), np.array([220, 0, 120], dtype=np.float32)), # purple -> pink
            (0.5, 0.8, np.array([220, 0, 120], dtype=np.float32),  np.array([220, 100, 0], dtype=np.float32)),  # pink -> dark orange
            (0.80, 0.85, color_dark_orange, color_soft_orange),
            
            # De 0.85 a 0.90: Naranja suave a Amarillo
            (0.85, 0.90, color_soft_orange, color_yellow),

            # --- RANGO 0.9 a 1.0 (Dividido en dos partes) ---
            # De 0.90 a 0.95: Amarillo a Verde Lima (hace que el 0.92 se vea muy distinto al 0.98)
            (0.90, 0.95, color_yellow, color_lime),
            
            # De 0.95 a 1.00: Verde Lima a Verde Oscuro
            (0.95, 1.00, color_lime, color_green),
        ]

        # Assign for each segment
        for low, high, c_low, c_high in color_scale:
            if ((ndvi_value >= low) & (ndvi_value < high)) or (high == 1.0 and ndvi_value >=1.0):
                t = (ndvi_value - low) / (high - low)
            # Interpolate per-channel
                color = (c_low * (1.0 - t) + c_high * t).astype(np.uint8) 
                return list(color)
        return [0, 0, 0]



class LeyendaSaludWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Layout principal (Vertical)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5) # Espacio entre título y caja

        # 1. Título "Leyenda" (Afuera de la caja, como tu foto)
        lbl_titulo = QLabel("Leyenda")
        lbl_titulo.setStyleSheet("font-weight: bold; font-size: 14px; color: #333333;")
        layout.addWidget(lbl_titulo)

        # 2. El contenedor (Caja con borde)
        self.caja_contenedor = QFrame()
        self.caja_contenedor.setStyleSheet("""
            QFrame {
                background-color: white;
                border: 1px solid #CCCCCC;
                border-radius: 5px;
            }
        """)
        caja_layout = QVBoxLayout(self.caja_contenedor)
        caja_layout.setContentsMargins(15, 15, 15, 15) # Margen interno para que no pegue al borde
        
        # 3. El Widget que dibuja la barra y textos
        self.contenido_grafico = ContenidoLeyenda()
        caja_layout.addWidget(self.contenido_grafico)

        layout.addWidget(self.caja_contenedor)

class ContenidoLeyenda(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        # Definir tamaño mínimo obligatorio para que no se descuadre
        self.setMinimumHeight(220) 
        self.setMinimumWidth(200)

        # Colores
        self.c_green       = QColor(20, 80, 0)     # Verde Oscuro
        self.c_medium_green = QColor(70, 140, 0)
        self.c_lime        = QColor(120, 200, 0)   # Lima
        self.c_yellow      = QColor(220, 240, 0)   # Amarillo
        self.c_soft_orange = QColor(220, 170, 0)   # Naranja Suave
        self.c_dark_orange = QColor(220, 100, 0)   # Naranja Oscuro

        # Marcadores: (Valor, Color, Texto Principal)
        self.markers = [
            (1.00, self.c_green,       "MUY SALUDABLE (1.0)"),
            (0.90, self.c_medium_green,      "SALUDABLE (0.9)"),
            (0.80, self.c_lime, "ACEPTABLE (0.8)"),
            (0.70, self.c_soft_orange, "DEFICIENTE (0.7)"),
            (0.60, self.c_dark_orange, "BAJO (< 0.6)")
        ]
        
        # Gradiente visual (Stops para QGradient)
        self.gradient_stops = [
            (0.00, self.c_green),
            (0.20, self.c_medium_green),
            (0.40, self.c_lime),
            (0.60, self.c_yellow),
            (0.70, self.c_soft_orange),
            (1.00, self.c_dark_orange)
        ]

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Geometría disponible
        rect = self.rect()
        w = rect.width()
        h = rect.height()
        
        # Configuración de diseño
        bar_width = 20        # Ancho de la barra de color
        bar_x = 0             # Pegado a la izquierda del contenido
        text_offset_x = 35    # Donde empieza el texto
        
        # 1. DIBUJAR LA BARRA DE COLOR VERTICAL
        grad = QLinearGradient(bar_x, 0, bar_x, h) # De arriba a abajo
        for stop, color in self.gradient_stops:
            grad.setColorAt(stop, color)
            
        painter.setBrush(QBrush(grad))
        painter.setPen(Qt.NoPen)
        # Dibujamos un rectángulo redondeado para la barra
        painter.drawRoundedRect(bar_x, 0, bar_width, h, 5, 5)

        # 2. DIBUJAR LOS TEXTOS ALINEADOS
        # Fuentes
        font_main = QFont("Segoe UI", 9)
        painter.setFont(font_main)
        
        # Rango matemático para calcular posiciones
        max_val = 1.00
        min_val = 0.60
        span = max_val - min_val

        for val, color, label in self.markers:
            # Cálculo de posición Y (Invertido: 1.0 arriba, 0.6 abajo)
            ratio = (max_val - val) / span
            y_center = ratio * h
            
            # Corrección de bordes para que el texto no se corte arriba/abajo
            # Mantenemos el texto dentro del área visible
            y_center = max(10, min(h - 10, y_center))

            # Dibujar línea conectora pequeña (opcional, ayuda a leer)
            painter.setPen(QPen(QColor(200, 200, 200), 1))
            painter.drawLine(bar_x + bar_width + 2, int(y_center), bar_x + bar_width + 8, int(y_center))

            # Dibujar Texto
            painter.setPen(QColor(50, 50, 50)) # Gris oscuro (más elegante que negro)
            text_rect = QRect(text_offset_x, int(y_center) - 10, w - text_offset_x, 20)
            painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, label)

    # Esto es CRUCIAL: Le dice al layout cuánto espacio necesita como mínimo
    def sizeHint(self):
        return QSize(200, 250)

# ============================================================
# WORKER: Generación del PDF (simulada con espera)
# ============================================================
class PdfGeneratorWorker(QThread):
    finished = Signal(str, str)     # envía ruta del PDF temporal
    failed = Signal(str)       # envía mensaje de error

    def __init__(self, data: dict, parent=None):
        super().__init__(parent)
        self.data = data
    
    def load_trees_data(self, base_dir):
        trees_results = []
        
        try:
            path = f"{base_dir}/mosaic/trees/trees_results.json"
            
            with open(path, "r") as f:
                trees_results = json.load(f)
           
        except Exception as e: 
            print(e)
        
        trees_data = []
        
        for r in trees_results:
            trees_data.append(dict(
                id = r["id"], 
                diagnostico = "POSIBLE DEFICIENCIA" if r['class'] == "deficiencia" else "SALUDABLE",
                ndvi = round(r['avg_ndvi'], 2)
                ))
        
        return trees_data
    
    def load_sumary_processing(self, base_dir):
        try:
            with open(f"{base_dir}/processing_sumary.json", "r") as f:
                processing_sumary = json.load(f)
                return processing_sumary
        except Exception as e:
            print(e)

        return None
    
    def run(self):
        try:
            # Simulación de un proceso pesado
            time.sleep(3)

            
            # Crear PDF vacío en carpeta temporal
            temp_dir = tempfile.gettempdir()
            temp_pdf = os.path.join(temp_dir, "reporte_temp.pdf")
        #       self.data = {
        #     "nombre_analisis": "Análisis Predeterminado 2024-07-26",
        #     "solicitante": "",
        #     "departamento": "",
        #     "provincia": "Seleccionar Provincia",
        #     "distrito": "Seleccionar Distrito",

        #     # Opciones
        #     "incl_area": False,
        #     "incl_detalles": True,
        #     "incl_fecha": False,
        #     "incl_mapa": False,

        #     # Formato
        #     "formato": "A3",
        #     # Comentarios
        #     "comentarios": ""
        # }

            location = ""
            
            if self.data['departamento'] != "":
                location = self.data['departamento']
  
            if self.data['provincia'] != "":
                location = location + "/ " + self.data['provincia']

            if self.data['distrito'] != "":
                location = location + "/ " + self.data['distrito']

            
            general_info = [
                    ("Nombre del Análisis:", self.data['nombre_analisis']),
                    ("Nombre del Solicitante:", self.data['solicitante'] if self.data['solicitante'] != "" else "Anonimo"),
                    ("Localidad:", location if location else "No se indica")
                ]
            

            base_dir = self.data['base_dir']
            
            sumary_processing = self.load_sumary_processing(base_dir)
            
            if sumary_processing:
                if self.data['incl_area']:
                    general_info.append(("Area Apox. Terreno:", f'{round(sumary_processing["area_mosaic"],2)} ha'))

                if self.data["incl_fecha"]:
                    general_info.append(("Fecha de Adquisición:", sumary_processing["adquisition_date"]))
                sumary_processing

                if self.data['incl_detalles']:
                    general_info.append(("Cantidad de Imágenes:", sumary_processing["total_images"]))
                    general_info.append(("Modelo de Cámara:", "M3M"))
                    general_info.append(("GSD Promedio:", round(sumary_processing["avg_gsd_multispec"],2)))
                    general_info.append(("Altura de Vuelo Promedio:", str(round(sumary_processing["avg_alt"], 2))))
            # EXAMPLE_GENERAL_INFO = [("Nombre del Análisis:", "Análisis de ejemplo 1"),
            #         ("Nombre del Solicitante:", "Carlos Quispe"),
            #         ("Localidad:", "Apurimac/ Abancay/ Pichirhua"),
            #         ("Area Apox. Terreno:", "0.5 ha"),
            #         ("Cantidad de Imágenes:", "331"), 
            #         ("Modelo de Cámara:", "M3M"), 
            #         ("GSD Promedio:", "0.5 cm/px"), 
            #         ("Altura Promedio:", "14.92 m"), 
            #         ("Fecha de Captura:", "2024-08-12")]
           
            trees_data = self.load_trees_data(base_dir)
            crear_reporte(
                filename = temp_pdf,
                general_info= general_info,
                trees_data= trees_data,
                comments = self.data['comentarios'],
                map_image= sumary_processing['map_trees'] if sumary_processing else None,
                final_page_size = self.data["formato"] if self.data['incl_mapa'] else None)

            #with open(temp_pdf, "wb") as f:
            #    f.write(b"%PDF-1.4\n%EOF\n")  # PDF mínimo válido

            self.finished.emit(temp_pdf, self.data["nombre_analisis"])

        except Exception as e:
            self.failed.emit(str(e))


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
        
        #self.data
        
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
    
    
class MapGraphicsView(QGraphicsView):
    def __init__(self, scene, parent = None):
        super().__init__(parent)
        self.setScene(scene)
        # IMPORTANTE para hover
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self.controller = parent

    
    def mouseMoveEvent(self, event):
        if self.controller is not None:
            pos_scene = self.mapToScene(event.pos())
            print("pos_scene:", pos_scene)
            self.controller.handle_hover(pos_scene, event.globalPos())
        super().mouseMoveEvent(event)

class FloatingToolTip(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Tool |
    Qt.WindowType.FramelessWindowHint |
    Qt.WindowType.WindowStaysOnTopHint)
        self.setFont(QFont("Segoe UI", 10))
        self.setMargin(6)
        self.setStyleSheet("""
            QLabel {
                background-color: #f0f7ff;
                border: 1px solid #a7c5ff;
                border-radius: 6px;
                color: #003366;
            }
        """)
        self.hide()

    def show_at(self, global_pos, html_text, offset=QPoint(12, 16)):
        self.setText(html_text)
        self.adjustSize()
        self.move(global_pos + offset)
        self.show()
        self.raise_()

    def hide_tooltip(self):
        self.hide()

class GeoTIFFViewer(QWidget):
    layer_selected = Signal(str)
    def __init__(self, layers_base_dir = None, parent=None):
        super().__init__(parent)
        #self.layers_base_dir = layers_base_dir
        self.rgb_items = []
        self.ndvi_items = []
        self.trees_masks_items = []
        self.trees_mask_hover = []
        self.avg_ndvi_masks_items = []
        self.active_mask_hover = None
        self.floating_tooltip = None
        #self.setAutoFillBackground(True)
        self.setStyleSheet("background-color: black;")
        self.init_ui()
        if layers_base_dir:
            self.update_layers_map(layers_base_dir)
            self.show_mosaic_rgb()
    
    def init_ui(self):
        """Inicializa la interfaz del widget"""
        self.layout = QVBoxLayout(self)
        # Configuración de la vista de mapa
        self.scene = QGraphicsScene()
        self.view = MapGraphicsView(self.scene, self)
        self.view.setDragMode(QGraphicsView.ScrollHandDrag)
        self.view.setRenderHint(QPainter.Antialiasing)
        self.view.setStyleSheet("""
        /* ScrollBar vertical */
        QScrollBar:vertical {
            background: #f0f0f0;
            width: 12px;
            margin: 0px;
        }
        QScrollBar::handle:vertical {
            background: #888;
            min-height: 20px;
            border-radius: 6px;
        }
        QScrollBar::handle:vertical:hover {
            background: #555;
        }
        QScrollBar::add-line:vertical,
        QScrollBar::sub-line:vertical {
            height: 0px;
            background: none;
        }

        /* ScrollBar horizontal */
        QScrollBar:horizontal {
            background: #f0f0f0;
            height: 12px;
            margin: 0px;
        }
        QScrollBar::handle:horizontal {
            background: #888;
            min-width: 20px;
            border-radius: 6px;
        }
        QScrollBar::handle:horizontal:hover {
            background: #555;
        }
        QScrollBar::add-line:horizontal,
        QScrollBar::sub-line:horizontal {
            width: 0px;
            background: none;
        }
        background: #f0f0f0;
        """)
        
        # Botones de la barra superiores
        #tool_bar_layout = QHBoxLayout()
        self.floating_tooltip = FloatingToolTip(self.view.viewport())
        self.zoom_in_btn = QToolButton(self)
        self.zoom_in_btn.setFixedSize(30, 30)
        self.zoom_in_btn.setIcon(QIcon(resource_path(os.path.join("assets", "zoom_in.svg"))))
        self.zoom_in_btn.setStyleSheet("""
            QToolButton {
                background-color: white;
                border-radius: 5px;
                padding: 8px;
            }
            QToolButton:hover {
                background-color: #E0E0E0;
            }
        """)


        self.zoom_out_btn = QToolButton(self)
        self.zoom_out_btn.setFixedSize(30, 30)
        self.zoom_out_btn.setIcon(QIcon(resource_path(os.path.join("assets", "zoom_out.svg"))))
        
        self.zoom_out_btn.setStyleSheet("""
            QToolButton {
                background-color: white;
                border-radius: 5px;
                padding: 8px;
            }
            QToolButton:hover {
                background-color: #E0E0E0;
            }
        """)
        
        self.layers_btn = QToolButton(self)
        self.layers_btn.setFixedSize(30, 30)
        self.layers_btn.setIcon(QIcon(resource_path(os.path.join("assets", "layers.svg"))))

        self.layers_btn.setStyleSheet("""
            QToolButton {
                background-color: white;
                border-radius: 5px;
                padding: 8px;
            }
            QToolButton:hover {
                background-color: #E0E0E0;
            }
        """)

        ## # ---------- MENÚ FLOTANTE CAPAS ----------

        self.layers_menu = QFrame(self)
        self.layers_menu.setFrameShape(QFrame.StyledPanel)
        self.layers_menu.setStyleSheet("""
            QFrame {
                background-color: white;
                border-radius: 8px;
                border: 1px solid #ccc;
            }
            QRadioButton {
                    background-color: transparent;
                    color: black;
            }
        """)

        self.layers_menu.setFixedSize(200, 120)
        self.layers_menu.hide()  # Oculto por defecto

        layout_layers = QVBoxLayout(self.layers_menu)

        #self.rb_ndvi = QRadioButton("MAPA NDVI")
        self.rb_mapa = QRadioButton("MAPA")
        self.rb_def = QRadioButton("MAPA DE DEFICIENCIAS")
        self.rb_ndvi_avg = QRadioButton("MAPA NDVI PROMEDIO")
        #self.rb_ndvi.setStyleSheet("""
        #        QRadioButton {
        #            background-color: transparent;
        #            color: black;
        #        }
        #    """)
        # Por defecto MAPA seleccionado
        self.rb_mapa.setChecked(True)
        layout_layers.addWidget(self.rb_mapa)
        #layout_layers.addWidget(self.rb_ndvi)
        layout_layers.addWidget(self.rb_def)
        layout_layers.addWidget(self.rb_ndvi_avg)


        # Conectar cambios de radio
        #self.rb_ndvi.toggled.connect(lambda: self.show_mosaic_ndvi())
        self.rb_mapa.toggled.connect(lambda: self.show_mosaic_rgb())
        self.rb_def.toggled.connect(lambda: self.show_deficients_map())
        self.rb_ndvi_avg.toggled.connect(lambda: self.show_avg_ndvi_masks())
        # Iconos simples
        #self.zoom_in_btn.setText("+")
        #self.zoom_out_btn.setText("-")

        self.zoom_in_btn.setToolTip("Zoom In")
        self.zoom_out_btn.setToolTip("Zoom Out")
       
        # Acción del botón de layers
        self.layers_btn.clicked.connect(self.toggle_layers_menu)
        #self.layout.addWidget(toolbar_container)
        # Añadir vista al layout
        self.layout.addWidget(self.view)

        self.zoom_in_btn.clicked.connect(self.zoom_in)
        self.zoom_out_btn.clicked.connect(self.zoom_out)
         # Estado de zoom
        self.zoom_factor = 1.25

        # Al final de init_ui
        self.zoom_in_btn.raise_()
        self.zoom_out_btn.raise_()
        self.layers_btn.raise_()
        self.layers_menu.raise_()
    
    def event(self, e):
        if e.type() in (QEvent.Type.WindowDeactivate, QEvent.Type.ApplicationDeactivate):
            if self.floating_tooltip:
                self.floating_tooltip.hide_tooltip()
        return super().event(e)

    def zoom_in(self):
        self.view.scale(self.zoom_factor, self.zoom_factor)

    def zoom_out(self):
        self.view.scale(1 / self.zoom_factor, 1 / self.zoom_factor)

    def on_selected_layer(self, option):
        self.layer_selected.emit(option)

    def toggle_layers_menu(self):
        print("Load menu toggle")
        if self.layers_menu.isVisible():
            self.layers_menu.hide()
        else:
            # Obtener posición del botón dentro del widget principal
            pos = self.layers_btn.mapToParent(QPoint(0, 0))
            
            x = pos.x() + self.layers_btn.width() + 10
            y = pos.y()

            print("Menu pos:", x, y)

            self.layers_menu.move(x, y)
            self.layers_menu.show()

    def load_layers(self):
        """Carga ambas capas (mosaico y máscara)"""
        self.load_tiles(self.mosaic_dir, is_mask=False)
        if self.masks_dirs:
            #colors = [[0, 255, 0, 128], [255, 140, 80, 128], [50, 205, 255, 128]]
            for mask_dir in self.masks_dirs:
                self.load_tiles(mask_dir, is_mask=True, z_value = 1)
        self.view.fitInView(self.scene.itemsBoundingRect(), Qt.KeepAspectRatio)
   

    def load_tiles(self, tiles_dir, is_mask = False, color_mask = None, z_value = 0):
        """Carga tiles individuales"""
        items = []
        
        for tile_file in os.listdir(tiles_dir):
            if not tile_file.endswith(".tif"):
                continue
                
            match = re.search(r"tile_(\d+)_(\d+)\.tif", tile_file)
            if not match:
                continue
                
            x_pos, y_pos = map(int, match.groups())
            tile_path = os.path.join(tiles_dir, tile_file)
            
            qimage = self.geotiff_mask_to_qimage(tile_path, color_mask) if is_mask else self.geotiff_to_qimage(tile_path)
            if not qimage.isNull():
                item = QGraphicsPixmapItem(QPixmap.fromImage(qimage))
                item.setPos(x_pos, y_pos)
                if is_mask:
                    item.setZValue(z_value)
                else:
                    item.setZValue(z_value)
                self.scene.addItem(item)
                items.append(item)
            
        return items

    
    def read_trees_results(self, trees_result_file):
        
        with open(trees_result_file, "r") as fp:
            trees_results = json.load(fp)
        
        for trees_r in trees_results:
            mask_path = trees_r['mask_path']
            print("mask_path:", mask_path)
            mask_file = os.path.basename(mask_path) 
           
            match = re.search(r"tree_(\d+)_(\d+)\.png", mask_file)
            if not match:
                continue
            
            x_pos, y_pos = map(int, match.groups())
            
            mask = cv2.imread(mask_path)
            
            if mask is None:
                continue

            mask = mask.astype(np.uint8)
            
            if mask.ndim == 3 and mask.shape[-1] > 1:
                mask = cv2.cvtColor(mask, cv2.COLOR_BGR2GRAY)

            if mask.shape[-1] == 1:
                mask = mask.squeeze()

            height, width = mask.shape

            trees_r['corner'] = [x_pos, y_pos]
            trees_r['qbbox'] = QRectF(x_pos, y_pos, width, height)
            trees_r['mask'] = mask

            # Items de mascaras de deficiencias
            tree_class = trees_r['class']
            color_class = ColorTreeState.get_rgb(tree_class)

            # Agregar transparencia
            color_class = list(color_class).copy()
            color_class = color_class + [128]

            qimage = self.mask_to_qimage(mask = mask, color_mask = color_class)
            trees_r['class_mask_qimage'] = qimage
            item = QGraphicsPixmapItem(QPixmap.fromImage(qimage))
            item.setPos(x_pos, y_pos)

            trees_r['class_mask_item'] = item

            # Items de mascaras de ndvi promedio

            avg_ndvi = trees_r["avg_ndvi"]
            color_ndvi = ColorNdvi.get_color(avg_ndvi)
            color_ndvi = color_ndvi + [200]
            print("color_ndvi:", color_ndvi)
            qimage_ndvi = self.mask_to_qimage(mask = mask, color_mask = color_ndvi)

            item_ndvi = QGraphicsPixmapItem(QPixmap.fromImage(qimage_ndvi))
            item_ndvi.setPos(x_pos, y_pos)

            trees_r['avg_ndvi_mask'] = item_ndvi

        return trees_results

        
    def load_trees_masks(self, trees_results, z_value = 1):
        masks_items = []
        
        for trees_r in trees_results:
            class_mask_item = trees_r['class_mask_item']
            class_mask_item.setZValue(z_value)
            self.scene.addItem(class_mask_item)
            masks_items.append(class_mask_item)
        
        return masks_items
    

    def load_trees_ndvi_avg(self, trees_results, z_value = 1):
        masks_items = []
        
        for trees_r in trees_results:
            item_ndvi = trees_r['avg_ndvi_mask']
            item_ndvi.setZValue(z_value)
            self.scene.addItem(item_ndvi)
            masks_items.append(item_ndvi)
        
        return masks_items


    def geotiff_to_qimage(self, path):
        """Convierte GeoTIFF a QImage"""
        ds = gdal.Open(path)
        if not ds:
            return QImage()
        
        num_bands = ds.RasterCount
        width = ds.RasterXSize
        height = ds.RasterYSize

         # Leer las bandas
        bands = [ds.GetRasterBand(i+1).ReadAsArray() for i in range(num_bands)]
        if bands[0].dtype != np.uint8:
            bands = [(b * 255 / (b.max() or 1)).astype(np.uint8) for b in bands]
        
        if num_bands >= 4:
            rgba = np.dstack(bands[:4])
            return QImage(rgba.data, width, height, 4 * width, QImage.Format_RGBA8888).copy()
        else:
            rgb = np.dstack(bands[:3]) if num_bands >= 3 else np.dstack([bands[0]] * 3)
            return QImage(rgb.data, width, height, 3 * width, QImage.Format_RGB888).copy()

    def geotiff_mask_to_qimage(self, path, color_mask = None):
        """Convierte máscara a QImage transparente"""
        ds = gdal.Open(path)
        if not ds:
            return QImage()
        
        bands = ds.RasterCount
        width = ds.RasterXSize
        height = ds.RasterYSize
        
        if bands>= 4:
            r = ds.GetRasterBand(1).ReadAsArray()
            g = ds.GetRasterBand(2).ReadAsArray()
            b = ds.GetRasterBand(3).ReadAsArray()
            a = ds.GetRasterBand(4).ReadAsArray()
            rgba = np.stack((r, g, b, a), axis=-1).astype(np.uint8)
        else:
            mask = ds.GetRasterBand(1).ReadAsArray()
            height, width = mask.shape
            rgba = np.zeros((height, width, 4), dtype=np.uint8)
            rgba[mask > 0] = color_mask if color_mask else [0, 255, 0, 128]
        
        return QImage(rgba.data, width, height, 4 * width, QImage.Format_RGBA8888).copy()

    def mask_to_qimage(self, mask = None, path = None, color_mask = None):
        
        if mask is None:
            mask = cv2.imread(path)
            mask = mask.astype(np.uint8)
        
        if mask.ndim == 3 and mask.shape[-1] > 1:
            mask = cv2.cvtColor(mask, cv2.COLOR_BGR2GRAY)

        if mask.shape[-1] == 1:
            mask = mask.squeeze()

        height, width = mask.shape

        rgba = np.zeros((height, width, 4), dtype=np.uint8)
        rgba[mask > 0] = color_mask if color_mask else [0, 255, 0, 128]

        return QImage(rgba.data, width, height, 4 * width, QImage.Format_RGBA8888).copy()

    def save_scene_to_image(self):
        """Guarda la escena actual como imagen temporal"""
        try:
            view_rect = self.view.viewport().rect()
            target_rect = self.view.mapToScene(view_rect).boundingRect()
            
            fd, temp_path = mkstemp(suffix='.png')
            os.close(fd)
            
            img = QImage(target_rect.size().toSize(), QImage.Format_ARGB32)
            img.fill(Qt.transparent)
            
            painter = QPainter(img)
            self.scene.render(painter, 
                            target=QRectF(img.rect()), 
                            source=target_rect)
            painter.end()
            
            if img.save(temp_path):
                return temp_path
            return None
            
        except Exception as e:
            print(f"Error al guardar imagen: {str(e)}")
            return None

    def wheelEvent(self, event):
        """Control de zoom"""
        factor = 1.1 ** (event.angleDelta().y() / 120)
        self.view.scale(factor, factor)
    
    def resizeEvent(self, event):
        spacing = 10
        self.zoom_out_btn.move(30, self.height() - self.zoom_out_btn.height() - 30)
        self.zoom_in_btn.move(30, self.zoom_out_btn.y() - self.zoom_in_btn.height() - spacing)
        self.layers_btn.move(30, self.zoom_in_btn.y() - self.layers_btn.height() - spacing)
        super().resizeEvent(event)
        self.view.fitInView(self.scene.itemsBoundingRect(), Qt.KeepAspectRatio)
    
    def showEvent(self, event):
        """Ajusta la vista al tamaño inicial de la ventana cuando se muestra por primera vez."""
        super().showEvent(event)
        print("Mostrar Mosaico.......")
        print()
        spacing = 10
        self.zoom_out_btn.move(30, self.height() - self.zoom_out_btn.height() - 30)
        self.zoom_in_btn.move(30, self.zoom_out_btn.y() - self.zoom_in_btn.height() - spacing)
        self.layers_btn.move(30, self.zoom_in_btn.y() - self.layers_btn.height() - spacing)
        self.view.fitInView(self.scene.itemsBoundingRect(), Qt.KeepAspectRatio)
    
    def update_layers_map(self, layers_base_dir):
        self.layers_base_dir = layers_base_dir
        
        # Limpiar escena anterior
        self.scene.clear()

        # Volver a cargar con las capas
       
        # Cargar Mosiaco RGB
        mosaic_rgb = f"{layers_base_dir}/mosaic/rgb/tiles"
        if os.path.isdir(mosaic_rgb):
            self.rgb_items = self.load_tiles(mosaic_rgb)

        # Cargar Mosiaco NDVI
        mosaic_ndvi = f"{layers_base_dir}/mosaic/ndvi/tiles"
        if os.path.isdir(mosaic_ndvi):
            self.ndvi_items = self.load_tiles(mosaic_ndvi, z_value=1)

        # Cargar Mascaras de Arboles con Calificaciones

        trees_result_file = f"{layers_base_dir}/mosaic/trees/trees_results.json"

        if os.path.exists(trees_result_file):
            trees_results = self.read_trees_results(trees_result_file)

            self.trees_masks_items = self.load_trees_masks(trees_results, z_value = 2)

            # Inicializar hover de las mascaras
            self.trees_mask_hover = trees_results

            self.avg_ndvi_masks_items = self.load_trees_ndvi_avg(trees_results, z_value = 4)
        
    
    def contains_masks(self, pos_scene, mask_hover):
        x = pos_scene.x()
        y = pos_scene.y()

        x_min, y_min = mask_hover['corner']
        mask = mask_hover['mask']
        h, w = mask.shape

        x_pos, y_pos = int(x), int(y)
        x_pos = min(max(x_pos - x_min, 0), w - 1)
        y_pos = min(max(y_pos - y_min, 0), h - 1)
        return mask[y_pos, x_pos] > 0
        #x_pos = 

    
    def handle_hover(self, pos_scene, pos_global):
        # 1. Buscar si hay máscara bajo el mouse
        hovered_mask = None
        for m in self.trees_mask_hover:
            if m["qbbox"].contains(pos_scene) and self.contains_masks(pos_scene, m):
                hovered_mask = m
                break

        # 2. Si no hay máscara -> ocultar solo si antes había una
        if hovered_mask is None:
            if getattr(self, "active_mask", None) is not None:
                self.active_mask["hover_item"].setVisible(False)
                self.active_mask = None
                if self.floating_tooltip:
                    self.floating_tooltip.hide_tooltip()
                #QToolTip.hideText()
            return
        
        # 3. Si es la misma máscara que ya está activa -> NO volver a llamar tooltip
        if getattr(self, "active_mask", None) is hovered_mask:
            return

        # 4. Ocultar la máscara anterior si fue otra
        if getattr(self, "active_mask", None) is not None and self.active_mask is not hovered_mask:
            self.active_mask["hover_item"].setVisible(False)

        # 5. Crear hover_item si no existe
        if ("hover_item" not in hovered_mask) or (hovered_mask["hover_item"] is None):
            qimage = hovered_mask['class_mask_qimage'].copy()
            item = QGraphicsPixmapItem(QPixmap.fromImage(qimage))
            x_pos, y_pos = hovered_mask['corner']
            item.setPos(x_pos, y_pos)
            item.setZValue(3)
            self.scene.addItem(item)
            hovered_mask["hover_item"] = item

        hovered_mask["hover_item"].setVisible(True)

        # 6. Tooltip solo cuando cambia de máscara
        class_str = hovered_mask['class']
        avg_ndvi = round(hovered_mask["avg_ndvi"], 3)
        state = class_str.capitalize() if class_str.upper() == "SALUDABLE" else "Con " + class_str.capitalize()

        html = f"""
            <div style="
                background-color:#f0f7ff;
                border:1px solid #a7c5ff;
                border-radius:6px;
                padding:8px;
                color:#003366;
            ">
                <div style="font-size:13px; font-weight:bold; margin-bottom:4px;">
                    {hovered_mask['name']}
                </div>

                <div style="font-size:12px;">
                    <b>Estado:</b> {state}<br>
                    <b>NDVI Promedio:</b> {avg_ndvi}
                </div>
            </div>
        """

        self.floating_tooltip.show_at(pos_global, html)


        #QToolTip.showText(pos_global, html, msecShowTime=100000)

        self.active_mask = hovered_mask
            
        
        #QToolTip.hideText()

    def show_mosaic_rgb(self):
        
        self.on_selected_layer("rgb")

        for item in self.rgb_items:
            item.setVisible(True)
        
        for item in self.ndvi_items:
            item.setVisible(False)
        
        for item in self.trees_masks_items:
            item.setVisible(False)

        for item in self.avg_ndvi_masks_items:
            item.setVisible(False)

    def show_mosaic_ndvi(self):
        self.on_selected_layer("ndvi")
        for item in self.rgb_items:
            item.setVisible(False)
        
        for item in self.ndvi_items:
            item.setVisible(True)
        
        for item in self.trees_masks_items:
            item.setVisible(False)
        
        for item in self.avg_ndvi_masks_items:
            item.setVisible(False)
    

    def show_deficients_map(self):
        self.on_selected_layer("deficient_map")
        for item in self.rgb_items:
            item.setVisible(True)
        
        for item in self.ndvi_items:
            item.setVisible(False)
        
        for item in self.trees_masks_items:
            item.setVisible(True)

        for item in self.avg_ndvi_masks_items:
            item.setVisible(False)

        #return super().show()

    def show_avg_ndvi_masks(self):
        self.on_selected_layer("avg_ndvi")
        for item in self.rgb_items:
            item.setVisible(True)
        
        for item in self.ndvi_items:
            item.setVisible(False)
        
        for item in self.trees_masks_items:
            item.setVisible(False)

        for item in self.avg_ndvi_masks_items:
            item.setVisible(True)


    def update_layers(self,  mosaic_dir=None, masks_dirs=None):
        """
        Actualiza las capas cargadas en el viewer.
        mosaic_dir: nueva ruta del mosaico
        masks_dirs: nuevas rutas de máscaras (lista)
        """
        if mosaic_dir:
            self.mosaic_dir = mosaic_dir
        if masks_dirs is not None:
            self.masks_dirs = masks_dirs

        # Limpiar escena anterior
        self.scene.clear()

        # Volver a cargar con las nuevas rutas
        self.load_layers()

class LegendItem(QWidget):
    def __init__(self, color, label_text, parent = None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2,2,2,2)
        # Color square
        color_label = QLabel()
        color_label.setFixedSize(20,20)
        color_label.setStyleSheet(f"background-color: {color};")
        #pallete = color_label.palette()
        #pallete.setColor(QPalette.Window, QColor(color))
        #color_label.setAutoFillBackground(True)
        #color_label.setPalette(pallete)

        # Text Label
        text_label = QLabel(label_text)
        #text_label.setWordWrap(True) 
        text_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        text_label.setStyleSheet("""
            color: #000000;
            font-size: 11px;
            font-weight: 500;
        """)
        layout.addWidget(color_label)
        layout.addWidget(text_label)
        layout.addStretch()

class LegendWidget(QWidget):
    def __init__(self):
        super().__init__()

        group_box = QGroupBox("Leyenda")
        group_box.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 16px;
                color: #333;
                border: 1px solid #cccccc;
                border-radius: 5px;
                margin-top: 35px;
            }

            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 5px;
                margin-left: 10px;
            }
        """)

        group_layout = QVBoxLayout(group_box)
        group_layout.setContentsMargins(10, 10, 40, 10)
        group_layout.setSpacing(12)

        leyend_colors = [{
            "name": "SALUDABLE", 
            "color_hex": "#00FF32", 
            "color_rgb": [0, 255, 50]
        }, 
        {
            "name": "DEFICIENCIA", 
            "color_hex": "#BFF700", 
            "color_rgb": [191, 247, 0]
        }]
        
        for leyend in leyend_colors:
            group_layout.addWidget(LegendItem(leyend['color_hex'], leyend['name'].replace("_", " ")))

        main_layout = QVBoxLayout(self)
        main_layout.addWidget(group_box)
        main_layout.addStretch()

class MosaicView(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        # Configuración de la vista
        
        # Cargar y mostrar las capas
        #self.setStyleSheet("background-color: black;")
        self.setup_ui()
        
        # Debug: Mostrar información de carga
    def setup_ui(self):
        """Configura la interfaz de usuario"""

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0) 
        self.setLayout(layout)
         # Crear instancia del visualizador
        self.viewer = GeoTIFFViewer(
            layers_base_dir= None, #"./analisis/prueba-biochumbi-150-oct-test",
            parent=self
        )
        
        layout.addWidget(self.viewer)
    
    def update_layers(self, mosaic_dir=None, masks_dirs=None):
        self.viewer.update_layers(mosaic_dir, masks_dirs)

    def update_layers_map(self, layers_base_dir):
        self.viewer.update_layers_map(layers_base_dir)
        self.viewer.show_mosaic_rgb()

class TitleResults(QWidget):
    def __init__(self, name_analysis):
        super().__init__()

        # Contenedor con color de fondo
        container = QWidget()
        container.setStyleSheet("background-color: #B9FFD3;")

        # Layout del contenedor
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)  # Sin márgenes
        container_layout.setSpacing(0)  # Sin espacios

        # Título principal
        self.name_analysis_title = QLabel(name_analysis)
        self.name_analysis_title.setWordWrap(True)
        self.name_analysis_title.setStyleSheet("""
            color: #05893A;
            padding: 5px 10px;
            font-size: 15px;
            font-weight: bold;
        """)
        self.name_analysis_title.setAlignment(Qt.AlignLeft)

        # Subtítulo
        subtitle = QLabel("Resultados del Análisis")
        subtitle.setStyleSheet("""
            color: #626263;
            padding: 5px 10px;
            font-size: 12px;
            font-weight: 600;
        """)

        # Añadir widgets al contenedor
        container_layout.addWidget(self.name_analysis_title)
        container_layout.addWidget(subtitle)

        # Layout principal
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(container)

    def update_title(self, title):
        self.name_analysis_title.setText(title)

class DiagramWidget(QWidget):
    def __init__(self, title, image_path):
        super().__init__()
        layout = QVBoxLayout()

        # Contenedor con borde
        content_frame = QFrame()
        content_frame.setFrameShape(QFrame.StyledPanel)  # forma del marco
        content_frame.setFrameShadow(QFrame.Plain)       # sombra simple
      
        # Layout interno del QFrame
        content_layout = QVBoxLayout(content_frame)
        content_layout.setAlignment(Qt.AlignCenter)
        content_layout.setContentsMargins(2, 2, 2, 2)  # margen interno

        title_widget = QLabel(title)
        title_widget.setAlignment(Qt.AlignCenter)
        title_widget.setWordWrap(True)  # Habilita salto de línea
        title_widget.setStyleSheet("""
            color: #000000;
            font-size: 13px;
            font-weight: 600;
        """)

        image_label = QLabel()
        image_label.setPixmap(QPixmap(image_path).scaled(250,250, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        image_label.setAlignment(Qt.AlignCenter)
    
        content_layout.setAlignment(Qt.AlignCenter)

        content_layout.addWidget(title_widget)
        content_layout.addWidget(image_label)
   
        layout.addWidget(content_frame)

        self.setLayout(layout)


class StatCard(QFrame):
    def __init__(self, title: str, value: int, parent=None):
        super().__init__(parent)

        # Configurar borde, fondo y esquinas redondeadas
        #self.setFrameShape(QFrame.StyledPanel)
        self.setObjectName("StatCardFrame")   # ← ID único

        self.setStyleSheet("""
            #StatCardFrame {
                background-color: #FFFFFF;
                border: 2px solid #CCCCCC;
                border-radius: 18px;
                padding-top: 5px;
            }
        """)

        # Título
        lbl_title = QLabel(title)
        lbl_title.setAlignment(Qt.AlignCenter)
        lbl_title.setFont(QFont("Segoe UI", 13))
        lbl_title.setStyleSheet("color: #0A281A;")

        # Valor
        self.lbl_value = QLabel(str(value))
        self.lbl_value.setAlignment(Qt.AlignCenter)
        self.lbl_value.setFont(QFont("Segoe UI", 34, QFont.Bold))
        self.lbl_value.setStyleSheet("color: #0A281A;")

        # Layout
        layout = QVBoxLayout(self)
        layout.addWidget(lbl_title)
        layout.addWidget(self.lbl_value)
        layout.setContentsMargins(20, 15, 20, 15)
    
    def update_count(self, num_trees = 0):
        self.lbl_value.setText(str(num_trees))
        

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
        p.setBrush(QColor("#FFC000"))
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
        top_left_y = cy - radius * 0.50

        print("left_x:", left_x)
        print("top_left_y:", top_left_y)
        draw_text(left_x, top_left_y, "Saludable", 0.03, True, QColor("#22A529"))
        draw_text(left_x, top_left_y + radius * 0.15, f"{self.percentage_healthy}%", 0.04, True, QColor("black"))
        draw_text(left_x, top_left_y + radius * 0.30, f"({self.healthy} Árboles)", 0.03, False, QColor("gray"))

        # TEXTOS DERECHA (Deficient)
        right_x = cx #+ radius * 0.90
        top_right_y = cy + radius * 0.10

        draw_text(right_x, top_right_y, "Con Deficiencia",  0.03, True, QColor("#FFC000"))
        draw_text(right_x, top_right_y + radius * 0.15, f"{self.percentage_deficient}%", 0.04, True, QColor("black"))
        draw_text(right_x, top_right_y + radius * 0.30, f"({self.deficient} Árboles)", 0.03  , False, QColor("gray"))

    # =================================================
    #       ACTUALIZAR VALORES EXTERNAMENTE
    # =================================================
    def update_values(self, healthy, deficient):
        self.healthy = healthy
        self.deficient = deficient
        
        self.percentage_healthy = round(healthy * 100 / (healthy + deficient), 2) 
        self.percentage_deficient = round(deficient * 100 / (healthy + deficient),2) 
        self.update()

class RightPanelResults(QWidget):
    def __init__(self, name_analysis, result_dir, main_window):
        super().__init__()

        self.main_window = main_window
        self.result_dir = result_dir
        container = QWidget()
        container_layout = QVBoxLayout()
        container_layout.setContentsMargins(0, 0, 0, 0)  # sin márgenes laterales
        container_layout.setSpacing(0)
        self.name_analysis = name_analysis
        # Espaciador arriba (por ejemplo, 20px)
        container_layout.addSpacing(30)

        self.title_results = TitleResults(name_analysis)
        container_layout.addWidget(self.title_results)
        container_layout.addSpacing(15)

        ## Diagrama
        self.count_trees_card = StatCard("Total de Arboles Detectados", 0)
        self.diagram_widget = DonutChartWidget(healthy=10, deficient=10) # 
        
        if result_dir:
            self.result_dir = result_dir
            self.update_view(self, result_dir)
        
        container_layout.addWidget(self.count_trees_card)
        container_layout.addWidget(self.diagram_widget)
        self.stack_leyends = QStackedWidget()
        self.legend_widget = LegendWidget() 
        self.leyend_ndvi = LeyendaSaludWidget()

        # 4Añadir tus widgets al Stack
        self.stack_leyends.addWidget(self.legend_widget)  # Índice 0
        self.stack_leyends.addWidget(self.leyend_ndvi)     # Índice 1
        self.stack_leyends.setCurrentIndex(0)
        
        container_layout.addWidget(self.stack_leyends)
        report_button = QPushButton("Generar Reporte")
        report_button.setIcon(QIcon(resource_path(os.path.join("assets", "file.svg"))))

        report_button.clicked.connect(self.generate_report)
        
        report_button.setStyleSheet("""
            QPushButton {
                color: white;
                background-color: #07C553;
                font-weight: bold;
                font-size: 16px;
                padding-top: 5px;
                padding-bottom: 5px;
            }

            QPushButton:hover {
                background-color: #05A644; /* Un verde más oscuro */
            }
            QPushButton:pressed {
                background-color: #048C38; /* Aún más oscuro al presionar */
            }
        """)

        export_button = QPushButton("  Exportar Resultados")
        export_button.setIcon(QIcon(resource_path(os.path.join("assets", "file.svg"))))
        
        export_button.setStyleSheet("""
            QPushButton {
                color: white;
                background-color: #07C553;
                font-weight: bold;
                font-size: 16px;
                padding-top: 5px;
                padding-bottom: 5px;
            }
                                    
            QPushButton:hover {
                background-color: #05A644; /* Un verde más oscuro */
            }
            QPushButton:pressed {
                background-color: #048C38; /* Aún más oscuro al presionar */
            }
        """)


        container_layout.addWidget(report_button)
        container_layout.addWidget(export_button)

        container.setLayout(container_layout)

        layout = QVBoxLayout()
        layout.addWidget(container, 0, Qt.AlignTop)
        self.setLayout(layout)

    def change_leyend(self, index):
        self.stack_leyends.setCurrentIndex(index)

    def update_view(self, result_dir):
        print("Actualizar Rigth Panel......")
        self.result_dir = result_dir

        trees_results_path = f"{result_dir}/mosaic/trees/trees_results.json"

        sal_trees = []
        def_trees = []
        trees_result = []

        if os.path.exists(trees_results_path):
            with open(trees_results_path, "r") as f:
                trees_result = json.load(f)

            sal_trees = [ r for r in trees_result if r['class'] == "saludable"]
            def_trees = [ r for r in trees_result if r['class'] == "deficiencia"]

            self.count_trees_card.update_count(len(trees_result))
            self.diagram_widget.update_values(healthy = len(sal_trees), deficient = len(def_trees))

    def update_title(self, title):
        self.name_analysis = title
        self.title_results.update_title(title)
    
    def showEvent(self, event):
        super().showEvent(event)
        print("Mostra Right panel 1..........")
        print()
        name = self.main_window.analysis_data_store.name

        if name is None:
            name =  "Análisis Ejemplo 1"
        
        self.update_title(name)
        
        base_dir = self.main_window.analysis_data_store.base_dir

        if base_dir is not None:
            self.update_view(base_dir)

    def generate_report(self):
        dialog = ReportDialog(self.main_window, self.result_dir, self.name_analysis)
        result = dialog.exec()
        if result == QDialog.Accepted:
            print("Datos recibidos del reporte:")
            print(dialog.data)

class MapTreeScreen(QWidget):
    layers_ready = Signal(str)
    layer_mode = Signal(str)

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.current_layer = "RGB"
        self.layers_path = None
        self.setup_ui()

    def setup_ui(self):
        outer_layout = QVBoxLayout(self)
        outer_layout.setAlignment(Qt.AlignCenter)  # Centra el contenedor completo

        inner_widget = QWidget()
        inner_layout = QHBoxLayout(inner_widget)
        inner_layout.setContentsMargins(0, 0, 0, 0)
        inner_layout.setSpacing(0)  # Espacio fijo entre mapa y leyenda
        
        self.layers_ready.connect(
            self.load_layers_map#lambda mosaic, layers: self.mosaic_view.update_layers(mosaic, layers)
        )

        self.mosaic_view = MosaicView(self.main_window)
        
        self.right_panel = RightPanelResults(name_analysis = "Análisis Ejemplo 1", 
                                        result_dir = self.layers_path,
                                        main_window = self.main_window)
        
        
        self.mosaic_view.viewer.layer_selected.connect(lambda key: self.on_change_layer(key))
        
        self.right_panel.setMaximumWidth(350)

        inner_layout.addWidget(self.mosaic_view, stretch=4)
        inner_layout.addWidget(self.right_panel, stretch=1)
        outer_layout.addWidget(inner_widget)   

    def on_change_layer(self, layer):
        if layer == "avg_ndvi" or layer == "ndvi":
            self.right_panel.change_leyend(1)
        else:
            self.right_panel.change_leyend(0)

    def update_mosaic_view(self, layers_path):
        self.mosaic_view.update_layers_map(layers_path)

    def load_layers_map(self, layers_path):
        self.layers_path = layers_path
        self.update_mosaic_view(self.layers_path)

 
class MapTrees(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout()
        
        # Crear un mapa con Folium
        m = folium.Map(location=[-13.881719661927868, -73.03486801134967], 
                       zoom_start=18,
                        max_zoom=22, 
                        tiles=f"https://api.mapbox.com/styles/v1/mapbox/satellite-v9/tiles/{{z}}/{{x}}/{{y}}?access_token={MAPBOX_TOKEN}",
                        attr="Mapbox")
        
        # Guardar el mapa en un archivo temporal
        html_map = m._repr_html_()

        # Estructura básica de una página HTML para incrustar el mapa
        html_page = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/leaflet.js"></script>
            <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/leaflet.css"/>
        </head>
        <body>
            {html_map}
        </body>
        </html>
        """
        
        # Mostrar el mapa en QWebEngineView
        self.web_view = QWebEngineView()
        self.web_view.setHtml(html_page)
        
        layout.addWidget(self.web_view)
        self.setLayout(layout)
