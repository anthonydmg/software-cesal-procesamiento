from PySide6.QtWidgets import QWidget, QApplication, QVBoxLayout, QHBoxLayout, QGridLayout, QButtonGroup, QComboBox, QSpacerItem, \
    QLabel, QProgressBar, QPushButton, QSizePolicy, QSlider, QFrame, QDialog, QScrollArea, QRadioButton, QGraphicsDropShadowEffect,\
    QFileDialog, QMessageBox, QGraphicsView, QGraphicsEllipseItem, QGraphicsScene, QGraphicsPolygonItem, QGraphicsLineItem, QStackedWidget, QLineEdit
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtCore import QMutex, QThread, QObject, Signal, Slot, QSize, QPointF, QRegularExpression
from PySide6.QtGui import QIcon, QPainter, QColor, QBrush, QPixmap, QImage, QPolygonF, QPen, QRegularExpressionValidator
from PySide6.QtCore import Qt
from PySide6.QtSvg import QSvgRenderer
import folium
import os
import json
import traceback
from datetime import datetime
import numpy as np
from core.constants import DEFAULT_PROCESS_CONFIG, ETAPAS_FENOLOGICAS, THRESH_STAGES_DEFAULT, TIPOS_RIEGOS, TIPOS_SUELOS, UNCERTANTY_VALUE
from core.deficiency_classifier import get_class_def_nitrogen
from core.inference import TreeDetectorYolo
from core.processing import ImageSticher, create_map_trees_ids, create_map_trees_ids_zinc
from core.utils import resource_path
from views.dialog_new_analysis import ImageManagerDialog, read_metadata_worker
from views.home import AppDataManager
import cv2


#MAPBOX_TOKEN = os.getenv("MAPBOX_TOKEN")

class ResultStorage:
    def __init__(self, output_dir: str = "results"):
        self.mutex = QMutex()
        self.output_dir = output_dir
        os.makedirs(f"./{self.output_dir}", exist_ok=True)
        self.current_file_index = 0
        self.results_cache = {}
        self.partial_files = []
    def add_result(self, image_id, result):
        self.mutex.lock()
        try:
            self.results_cache[image_id] = result
            self._save_to_disk()
        finally:
            self.mutex.unlock()
    
    def _save_to_disk(self):
        if not self.results_cache:
            return
        os.makedirs(f"./{self.output_dir}", exist_ok=True)     
        output_file =f"./{self.output_dir}/results_{self.current_file_index}.json" #os.path.join(self.output_dir, f"results_{self.current_file_index}.json")
        try:
            with open(output_file, 'w') as f:
                json.dump(self.results_cache, f, indent=2)
            print(f"Resultados guardados en: {output_file}")
            self.current_file_index += 1
            self.partial_files.append(output_file)
            self.results_cache = {}
        except Exception as e:
            print(f"Error al guardar resultados: {str(e)}")
            traceback.print_exc()
    
    def save_remaining(self):
        self._save_to_disk()
  
    def merge_results(self, final_filename: str = "final_results.json"):
        self.mutex.lock()
        try:
            final_results = {}
            
            # Leer todos los archivos parciales
            for partial_file in self.partial_files:
                try:
                    with open(partial_file, 'r') as f:
                        data = json.load(f)
                        final_results.update(data)
                except Exception as e:
                    print(f"Error leyendo {partial_file}: {str(e)}")
                    continue
            print("final_results:", final_results.keys())
            # Guardar archivo final
            final_path = os.path.join(self.output_dir, final_filename)
            with open(final_path, 'w') as f:
                json.dump(final_results, f, indent=2)
            
            # Opcional: eliminar archivos parciales
            for partial_file in self.partial_files:
                try:
                    os.remove(partial_file)
                except:
                    pass
            
            return final_path
        finally:
            self.mutex.unlock()    

class ImageProcessor(QObject):
    progress_updated = Signal(int)  # progress, message, current, total
    progrees_status = Signal(str)
    finished = Signal()
    cancelled = Signal()

    def __init__(self, image_data, result_dir = "./", name_analysis = None, 
                 target_resolution = None, thresh_stages = THRESH_STAGES_DEFAULT, field_stage = None, method_cal = None):
        super().__init__()
        self.image_data = image_data
        self.is_running = True
        self.batch_size = 2
        self.result_dir = result_dir
        self.images_sticher = None
        self.name_analysis = name_analysis
        self.target_resolution = target_resolution
        self.field_stage = field_stage
        self.thresh_stages = thresh_stages
        self.method_cal = method_cal

    def trees_detection_process(self, metadata_rgb_files):
        total = len(metadata_rgb_files)
        detector = TreeDetectorYolo.get_instance()
        all_predictions = []
        processed = 0
        
        self.progrees_status.emit("Procesando Imagenes...")

        for img_id, img_data in enumerate(metadata_rgb_files):
                if not self.is_running:
                    self.cancelled.emit()
                    break

                img_path = img_data['relative_path']
                try:
                    predictions = detector.predict([img_path], save_dir = f"{self.result_dir}/results")
                    all_predictions.extend(predictions)
                    processed += 1
                    progress = int((processed / total) * 30)
                    self.progress_updated.emit(
                        progress 
                    )

                except Exception as e:
                    print(f"Error en {img_id}: {str(e)}")
            
        assert len(all_predictions) == len(metadata_rgb_files), "El numero de predicciones deber ser igual a la cantidad de imaganes"

    def init_config_cal_exist_ok(self):
        config_radiometric_cal = {
                        "options" : ["DLS", "ELC"],
                        "option_choiced": 0,
                        "elc_data": { "bands": None } 
                    }
        path_config_cal = f"{self.result_dir}/config_radiometric_cal.json"
        if not os.path.exists(path_config_cal):
            with open(path_config_cal, "w") as fp:
                json.dump(config_radiometric_cal, fp)
        
    def process(self):
        try:
            self.progrees_status.emit("Inciando Procesamiento...")

            self.init_config_cal_exist_ok()

            all_images_data_metadata = list(self.image_data.values())
            print("Numero de Imagenes Orignales:", len(all_images_data_metadata))
            # Filtramos que no son perpendiculares
            all_images_data_metadata = [ im_data for im_data in all_images_data_metadata if im_data["pitch_degree"] < -89 and im_data['pitch_degree'] > -91]

            print("Numero de Imagenes Perpendiculares:", len(all_images_data_metadata))

            metadata_rgb_files = [img_m for img_m in all_images_data_metadata if "_D.JPG" in img_m['relative_path']]
            
            print("Numero de Imagenes RGB:", len(metadata_rgb_files))
            
            self.trees_detection_process(metadata_rgb_files)
            
            for row in metadata_rgb_files:
                row["detections_path"] = f"{self.result_dir}/results/detections/{row['name'][:-4]}_DETECTIONS.json"
            # (progress // 100)*60 + 40
            print("Comienza Generacion de Mosaico")
            
            self.images_sticher = ImageSticher(
                        images_data = all_images_data_metadata, 
                        on_progress_change = lambda progress: self.progress_updated.emit( int((progress / 100) * 70) + 30),
                        on_cancel = lambda: self.cancelled.emit(),
                        on_message = lambda text: self.progrees_status.emit(text),
                        result_dir = self.result_dir)
            
            self.progrees_status.emit("Generando Mosiaco...")

            self.images_sticher.run_process(prefix_name = self.name_analysis, 
                                            target_resolution =  self.target_resolution,
                                            thresh_stages =  self.thresh_stages,
                                            field_stage = self.field_stage,
                                            method_cal = self.method_cal)

            if self.is_running:
                self.progrees_status.emit("Procesamiento Terminado")
                self.finished.emit()

        except Exception as e:
            print("e:", e)
            traceback.print_exc()

    def stop(self):
        self.is_running = False
        print("Parando Proceso...")
        if self.images_sticher:
            self.images_sticher.stop()

class RoundedProgressBar(QProgressBar):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setTextVisible(False)
        self.setMinimumHeight(14)
        self.radius = 7  # mitad de la altura
        self.bg_color = QColor("#E5E8EB")
        self.chunk_color = QColor("#07C553")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Dibujar fondo
        painter.setBrush(QBrush(self.bg_color))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(self.rect(), self.radius, self.radius)

        # Dibujar progreso
        progress_width = int(self.width() * (self.value() / self.maximum()))
        if progress_width > 0:
            rect = self.rect().adjusted(0, 0, -(self.width() - progress_width), 0)
            painter.setBrush(QBrush(self.chunk_color))
            painter.drawRoundedRect(rect, self.radius, self.radius)

        painter.end()

class ItemDetails(QWidget):
    def __init__(self, item_name, value,  bold_value = False):
        super().__init__()
        layout = QVBoxLayout()

        name_label = QLabel(item_name)
        name_label.setStyleSheet("padding-left: 5px; color: #626263; font-size: 14px;")

        if bold_value:
            name_content_label = QLabel(value)
            name_content_label.setWordWrap(True)
            name_content_label.setStyleSheet("padding-left: 5px; color: #05893A; font-size: 14px;  font-weight: bold;")
        else:
            name_content_label = QLabel(value)
            name_content_label.setStyleSheet("padding-left: 5px; color: #000000; font-size: 14px;")
        
        layout.addWidget(name_label)
        layout.addWidget(name_content_label)
        layout.addStretch()
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.setMaximumHeight(70 if bold_value else 55)
        self.setLayout(layout)


class ProcessingConfigDialog(QDialog):
    def __init__(self, parent = None):
        super().__init__(parent)
        self.setWindowTitle("Configuración de Procesamiento")
        self.setFixedSize(450, 580)
        
        # Eliminar el marco de la ventana predeterminada para un look más moderno
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.appdata_manager = AppDataManager()
        self.init_ui()

    def init_ui(self):
        # Contenedor principal con fondo blanco y bordes redondeados

        process_config = self.appdata_manager.load_process_config()
        print("process_config:", process_config)
        if process_config is None:
            process_config = DEFAULT_PROCESS_CONFIG

        self.target_resolution_option = process_config["target_resolution_option"]
        self.states = process_config["tresh_stages"].copy()

        main_frame = QFrame(self)
        main_frame.setObjectName("MainFrame")
        main_layout = QVBoxLayout(main_frame)
        main_layout.setContentsMargins(24, 24, 24, 24)
        main_layout.setSpacing(20)

        # Layout general de la ventana
        window_layout = QVBoxLayout(self)
        window_layout.addWidget(main_frame)
        window_layout.setContentsMargins(0, 0, 0, 0)

        # --- HEADER ---
        header_layout = QHBoxLayout()
        title_label = QLabel("Configuración de Procesamiento")
        title_label.setObjectName("Title")
        
        close_btn = QPushButton("✕")
        close_btn.setObjectName("CloseBtn")
        close_btn.setFixedSize(24, 24)
        close_btn.clicked.connect(self.reject)
        
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        header_layout.addWidget(close_btn)
        main_layout.addLayout(header_layout)

        # Separador
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color: #f0f0f0;")
        main_layout.addWidget(line)

        # --- SECCIÓN 1: Resolución de Salida ---
        res_layout = QVBoxLayout()
        res_header = QHBoxLayout()
        res_title = QLabel("Resolución de Salida")
        res_title.setObjectName("SectionTitle")
        self.res_badge = QLabel("Baja")
        self.res_badge.setObjectName("Badge")
        
        res_header.addWidget(res_title)
        res_header.addStretch()
        res_header.addWidget(self.res_badge)
        res_layout.addLayout(res_header)

        # Slider de resolución (3 posiciones: 0, 1, 2)
        self.res_slider = QSlider(Qt.Horizontal)
        self.res_slider.setRange(0, 2)
        self.res_slider.setValue(self.target_resolution_option)
        self.res_slider.setTickPosition(QSlider.TicksBelow)
        self.res_slider.valueChanged.connect(self.update_res_label)
        res_layout.addWidget(self.res_slider)

         
        
             
        self.target_resols = self.parent().main_window.analysis_data_store.options_resolutions

        qualities = ["BAJA", "MEDIA", "ALTA"]
        #self.target_resols = [gsd_avg * 8 , gsd_avg * 6, gsd_avg * 4]
        print("self.target_resols:", self.target_resols)
        # Etiquetas del slider de resolución
        res_labels_layout = QHBoxLayout()
        for quality, resol in zip(qualities, self.target_resols):
            resol_cm = resol * 100
            res_labels_layout.addWidget(self.create_sub_label(f"{quality}\n({resol_cm:.2f} cm/px)", Qt.AlignLeft))
        res_layout.addLayout(res_labels_layout)
        
        main_layout.addLayout(res_layout)


        # 3. UMBRAL DE NITRÓGENO (Nitrogen Thresholds)
        nit_title = QLabel("Umbral de nitrógeno óptimo por estado")
        nit_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #555;")
        main_layout.addWidget(nit_title)
        
        nit_subtitle = QLabel("Limite de nitrógeno optimo segun el estado fenologico.")
        nit_subtitle.setStyleSheet("color: #888; font-size: 11px;")
        main_layout.addWidget(nit_subtitle)

        # Container for nitrogen sliders
        nit_container = QFrame()
        nit_container.setStyleSheet("""
            QFrame { background-color: #f8f9fa; border-radius: 10px; }
        """)
        nit_layout = QGridLayout(nit_container)
        nit_layout.setContentsMargins(15, 15, 15, 15)
        nit_layout.setVerticalSpacing(12)

        # Define the states and default values
        
        #self.states = THRESH_STAGES_DEFAULT.copy()
        
        #states = [
        #    ("Inicio de brote", 2.5),
        #    ("Pre-floración", 2.8),
        #    ("Floración", 3.0),
        #    ("Cuajado", 2.6),
        #    ("Maduración", 2.2),
        #    ("Cosecha", 2.0)
        #]

        self.nit_value_labels = []
        self.sliders = dict()
        for row, (state_name, default_val) in enumerate(self.states.items()):
            # Label
            lbl = QLabel(state_name)
            lbl.setStyleSheet("font-size: 12px; font-weight: bold; color: #444;")
            lbl.setFixedWidth(100)
            
            # Slider
            slider = QSlider(Qt.Horizontal)
            slider.setMinimum(0)
            slider.setMaximum(50) # Range 0.0 to 5.0
            slider.setValue(int(default_val * 10))
            slider.setStyleSheet(self.get_slider_style())
            
            self.sliders[state_name] = slider
            # Value Label
            val_lbl = QLabel(f"{default_val:.1f}")
            val_lbl.setStyleSheet("font-size: 12px; font-weight: bold; color: #0ba64a;")
            val_lbl.setFixedWidth(25)
            val_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            
            # Connect slider to update label
            slider.valueChanged.connect(lambda val, l=val_lbl: l.setText(f"{val / 10:.1f}"))
            
            nit_layout.addWidget(lbl, row, 0)
            nit_layout.addWidget(slider, row, 1)
            nit_layout.addWidget(val_lbl, row, 2)

        main_layout.addWidget(nit_container)


        main_layout.addStretch()

        # --- SECCIÓN 4: Botones inferiores ---
        bottom_layout = QHBoxLayout()
        reset_btn = QPushButton("Restablecer")
        reset_btn.setObjectName("ResetBtn")
        reset_btn.clicked.connect(self.reset_values)

        save_btn = QPushButton("Guardar Cambios")
        save_btn.setObjectName("SaveBtn")
        save_btn.setFixedSize(160, 40)

        save_btn.clicked.connect(self.save_config)
        
        bottom_layout.addWidget(reset_btn)
        bottom_layout.addStretch()
        bottom_layout.addWidget(save_btn)
        
        main_layout.addLayout(bottom_layout)

        self.update_res_label(self.target_resolution_option)
        # Aplicar estilos
        self.apply_styles()

    def get_slider_style(self):
        # Common QSS for all modern green sliders
        return """
            QSlider::groove:horizontal {
                border-radius: 3px;
                height: 6px;
                background: #e0e0e0;
            }
            QSlider::handle:horizontal {
                background: #0ba64a;
                width: 14px;
                height: 14px;
                margin: -4px 0;
                border-radius: 7px;
            }
            QSlider::handle:horizontal:hover {
                background: #098b3e;
                width: 16px;
                height: 16px;
                margin: -5px 0;
                border-radius: 8px;
            }
        """
    
    def create_sub_label(self, text, alignment):
        lbl = QLabel(text)
        lbl.setAlignment(alignment)
        lbl.setObjectName("SliderLabel")
        return lbl

    def update_res_label(self, value):
        labels = ["Baja", "Media", "Alta"]
        self.target_resolution_option = value
        self.res_badge.setText(labels[value])

    def update_nitro_label(self, value):
        # Convierte el valor entero (25) a float (2.5)
        float_val = value / 10.0
        self.nitro_badge.setText(f"{float_val:.1f} %")

    def get_data(self):
        new_stages = dict()
        
        for stage_name in self.states.keys():
            new_stages[stage_name]= self.sliders[stage_name].value() / 10

        processing_config = dict(target_resolution_option = self.target_resolution_option,
                                 tresh_stages = new_stages)
        
        return processing_config
    

    def save_config(self):
        
        processing_config = self.get_data()
        
        self.appdata_manager.update_process_config(processing_config)

        

        self.accept()  

    def reset_values(self):
        # 1. Bajamos la resolución al índice 0 (Baja)
        self.res_slider.setValue(0)
        
        for stage_name in self.states.keys():
            self.sliders[stage_name].setValue(int(THRESH_STAGES_DEFAULT[stage_name] * 10))
            
        # Nota: No es necesario llamar a update_res_label() o update_nitro_label() 
        # manualmente, porque setValue() dispara la señal valueChanged.
    
    def update_thesh_values(self, thresh_values):
        self.states = thresh_values
        for stage_name in self.states.keys():
            self.sliders[stage_name].setValue(int(self.states[stage_name] * 10))

    def apply_styles(self):
        style_sheet = """
        #MainFrame {
            background-color: #ffffff;
            border-radius: 16px;
            border: 1px solid #e0e0e0;
        }
        #Title {
            font-size: 18px;
            font-weight: bold;
            color: #2c3e50;
        }
        #SectionTitle {
            font-size: 14px;
            font-weight: bold;
            color: #34495e;
        }
        #Subtitle {
            font-size: 11px;
            color: #7f8c8d;
        }
        #Badge {
            background-color: #e8f5e9;
            color: #27ae60;
            border-radius: 12px;
            padding: 4px 10px;
            font-weight: bold;
            font-size: 12px;
        }
        #SliderLabel {
            font-size: 10px;
            color: #95a5a6;
        }
        #CloseBtn {
            background: transparent;
            border: none;
            color: #95a5a6;
            font-size: 16px;
            font-weight: bold;
        }
        #CloseBtn:hover {
            color: #e74c3c;
        }
        
        /* Estilos de los Sliders */
        QSlider::groove:horizontal {
            height: 6px;
            background: #ecf0f1;
            border-radius: 3px;
        }
        QSlider::handle:horizontal {
            background: #27ae60;
            width: 16px;
            height: 16px;
            margin: -5px 0;
            border-radius: 8px;
        }
        QSlider::sub-page:horizontal {
            background: #27ae60;
            border-radius: 3px;
        }


        /* Botones inferiores */
        #ResetBtn {
            background: transparent;
            border: none;
            color: #7f8c8d;
            font-weight: bold;
            font-size: 14px;
        }
        #ResetBtn:hover {
            color: #34495e;
        }
        #SaveBtn {
            background-color: #00b84c;
            color: white;
            border-radius: 8px;
            font-weight: bold;
            font-size: 14px;
        }
        #SaveBtn:hover {
            background-color: #00993e;
        }
        """
        self.setStyleSheet(style_sheet)

class CabeceraClickeable(QFrame):
    """Un QFrame personalizado para detectar clics en toda la zona de la cabecera."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        
    def mousePressEvent(self, event):
        self.parent().toggle_colapso()
        super().mousePressEvent(event)

class SeccionPanel(QFrame):
    """Clase base para crear las secciones colapsables visualmente separadas."""
    def __init__(self, titulo, icono_accion=None, parent=None, on_click_icon = None):
        super().__init__(parent)
        self.setObjectName("SeccionPanel")
        self.on_click_icon = on_click_icon
        self.layout_principal = QVBoxLayout(self)
        # 1. Quitamos los márgenes globales para que la cabecera toque los bordes
        self.layout_principal.setContentsMargins(0, 0, 0, 0)
        self.layout_principal.setSpacing(0) # Sin espacio entre cabecera y contenido
        self.expandido = True
        
        self.renderer_arriba = QSvgRenderer(resource_path("assets/icon_top.svg"))
        self.renderer_abajo = QSvgRenderer(resource_path("assets/icon_bottom.svg"))
        
        # Validación de seguridad: Comprobar si los archivos se cargaron correctamente
        if not self.renderer_arriba.isValid():
            print(f"⚠️ Advertencia: No se pudo cargar el archivo icon_top")
        if not self.renderer_abajo.isValid():
            print(f"⚠️ Advertencia: No se pudo cargar el archivo icon_bottom")
        
        # 2. Definir un tamaño para los iconos
        tamanio_icono = QSize(20, 20)
        # 3. Crear Pixmaps vacíos del tamaño deseado
        self.pixmap_arriba = QPixmap(tamanio_icono)
        self.pixmap_arriba.fill(Qt.transparent)

        self.pixmap_abajo = QPixmap(tamanio_icono)
        self.pixmap_abajo.fill(Qt.transparent)
        
        # 5. Renderizar (dibujar) los SVG físicos en los Pixmaps
        painter_arriba = QPainter(self.pixmap_arriba)
        self.renderer_arriba.render(painter_arriba)
        painter_arriba.end()
        
        painter_abajo = QPainter(self.pixmap_abajo)
        self.renderer_abajo.render(painter_abajo)
        painter_abajo.end()

        # Cabecera clickeable con su propio identificador para el fondo
        self.cabecera = CabeceraClickeable(self)
        self.cabecera.setObjectName("FondoCabecera")
        self.cabecera_layout = QHBoxLayout(self.cabecera)
        # 2. Márgenes internos solo para la cabecera
        self.cabecera_layout.setContentsMargins(15, 12, 15, 12)
        
        self.lbl_titulo = QLabel(titulo)
        self.lbl_titulo.setObjectName("TituloSeccion")
        
        self.cabecera_layout.addWidget(self.lbl_titulo)
        self.cabecera_layout.addStretch()
        
        if icono_accion:
            self.btn_accion = QPushButton()
            self.btn_accion.setIcon(QIcon(icono_accion))  # ⚙️
            self.btn_accion.setIconSize(QSize(20, 20))
            self.btn_accion.setFixedSize(32, 32)
            self.btn_accion.setCursor(Qt.PointingHandCursor)

            self.btn_accion.setObjectName("BotonIconoCabecera")
            #self.btn_accion.setCursor(Qt.PointingHandCursor)
            if self.on_click_icon:
                self.btn_accion.clicked.connect(self.on_click_icon) 
            self.cabecera_layout.addWidget(self.btn_accion)

        self.lbl_icono_colapso = QLabel() 
        self.lbl_icono_colapso.setObjectName("IconoColapso")
        self.lbl_icono_colapso.setPixmap(self.pixmap_arriba)

        self.cabecera_layout.addWidget(self.lbl_icono_colapso)
        
        self.layout_principal.addWidget(self.cabecera)
        
        # Contenedor para el contenido específico
        self.contenido_widget = QWidget()
        self.contenido_widget.setObjectName("FondoContenido")
        self.contenido_layout = QVBoxLayout(self.contenido_widget)
        # 3. Márgenes internos para el contenido
        self.contenido_layout.setContentsMargins(15, 15, 15, 15)
        self.layout_principal.addWidget(self.contenido_widget)

    def toggle_colapso(self):
        self.expandido = not self.expandido
        self.contenido_widget.setVisible(self.expandido)
        self.lbl_icono_colapso.setPixmap(self.pixmap_arriba if self.expandido else self.pixmap_abajo)

    def ejecutar_accion_icono(self):
        print(f"Acción ejecutada en: {self.lbl_titulo.text()}")


class PlaceholderImagen(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("FondoPlaceholder")
        
        # Layout principal centrado
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(10) # Espacio entre el icono, título y texto
        
        # 1. Crear el icono renderizando el SVG
        self.lbl_icono = QLabel()
        self.lbl_icono.setAlignment(Qt.AlignCenter)
        
        renderer = QSvgRenderer(resource_path("assets/empty_image.svg"))
        pixmap = QPixmap(QSize(48, 48))
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        
        self.lbl_icono.setPixmap(pixmap)
        
        # 2. Etiqueta del Título
        self.lbl_titulo = QLabel("Área de visualización de imagen")
        self.lbl_titulo.setObjectName("TituloPlaceholder")
        self.lbl_titulo.setAlignment(Qt.AlignCenter)
        
        # 3. Etiqueta del Subtítulo (Descriptivo)
        self.lbl_subtitulo = QLabel("Carga las bandas multiespectrales y selecciona los paneles de referencia necesarios para la calibración.")
        self.lbl_subtitulo.setObjectName("TextoPlaceholder")
        self.lbl_subtitulo.setAlignment(Qt.AlignCenter)
        self.lbl_subtitulo.setWordWrap(True) # Permite que el texto baje a la siguiente línea
        
        self.setStyleSheet("""
            #FondoPlaceholder {
                background-color: #F8F9FA; /* Gris muy suave, casi blanco */
                border: 1px dashed #D1D5DB; /* Borde punteado opcional para indicar "zona de caída" */
                border-radius: 8px;
            }
            #TituloPlaceholder {
                font-size: 14px;
                font-weight: bold;
                color: #6B7280; /* Gris medio-oscuro */
                margin-top: 5px;
            }
            #TextoPlaceholder {
                font-size: 12px;
                color: #9CA3AF; /* Gris claro */
                margin-top: 0px;
            }
        """)
        # Añadir al layout
        layout.addWidget(self.lbl_icono)
        layout.addWidget(self.lbl_titulo)
        layout.addWidget(self.lbl_subtitulo)

class DraggablePoint(QGraphicsEllipseItem):
    def __init__(self, x, y, radius, viewer):
        super().__init__(-radius, -radius, radius * 2, radius * 2)
        self.setPos(x, y)
        self    .setBrush(QBrush(QColor(0, 255, 0)))
        self.setZValue(10) # Encima del poligono
        self.viewer = viewer

        self.setFlags(
            QGraphicsEllipseItem.ItemIsMovable |    
            QGraphicsEllipseItem.ItemSendsGeometryChanges
        )

    def itemChange(self, change, value):
        if change == QGraphicsEllipseItem.ItemPositionChange:
            self.viewer.update_polygon()
        return super().itemChange(change, value)
        
class ImageViewer(QGraphicsView):
    def __init__(self, parent = None, on_validate_complete = None, on_save_rois = None):
        super().__init__(parent)
        self.scene = QGraphicsScene()
        self.setScene(self.scene)
        self.on_validate_complete = on_validate_complete
        self.on_save_rois = on_save_rois
        self.image = None
        self.pixmap_item = None
        self.drawing = True
        self.points = []
        self.point_items = []
        self.temp_line = None
        self.pan_mode = False
        self.rois_names = ["black", "gray", "red"]
        
        self.current_roi = self.rois_names[0]
        
        self.rois = {}
        
        for roi_name in self.rois_names:
            self.rois[roi_name] = dict(
                points = [],
                point_items = [],
                lines = [],
                polygon_item = None
            )
        
        self.lines = []
        self.polygon_item = None

        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
    

    def set_pan_mode(self, enabled):
        self.pan_mode = enabled
        if enabled:
            self.setDragMode(QGraphicsView.ScrollHandDrag)
        else:
            self.setDragMode(QGraphicsView.NoDrag)

    def load_image(self, img):
        self.scene.clear()
        self.image = img.astype(np.float32)
        
        disp = cv2.normalize(self.image, None, 0, 255, cv2.NORM_MINMAX)
        disp = disp.astype(np.uint8)
        h, w = disp.shape
        qimg = QImage(disp.data, w, h, w, QImage.Format_Grayscale8)
        pixmap = QPixmap.fromImage(qimg)

        self.pixmap_item = self.scene.addPixmap(pixmap)
        self.fit_image()
        #self.setSceneRect(0,0, w, h)
        #self.resetTransform()
        #self.fitInView(self.sceneRect(), Qt.KeepAspectRatio)

    def reset(self):
        self.scene.clear()
        
        for roi_name in self.rois_names:
            self.rois[roi_name] = dict(
                points = [],
                point_items = [],
                lines = [],
                polygon_item = None
        )

    def remove_roi(self, current_roi):
        self.rois[current_roi]["points"] = []
        self.rois[current_roi]["point_items"] = []
        self.rois[current_roi]["lines"] = []
        self.rois[current_roi]["polygon_item"] = None 

    def restore_rois(self, targets_pts):
        self.drawing = True
        for roi_name, pts in targets_pts.items():
            if pts is None:
                continue
            is_active = self.current_roi == roi_name
            point_color, poly_color, line_color = self._color_poly(is_active)
            # Dibuja los Puntos
            
            # Clean all
            self.rois[roi_name]["points"] = []
            self.rois[roi_name]["point_items"] = []
            self.rois[roi_name]["lines"] = [] 
            
            # Redibuja

            for x, y in pts:
                pos = QPointF(x, y)
                self.rois[roi_name]["points"].append(pos)
                self.add_point(pos, roi_name=roi_name, point_color = point_color)
            
            # Reconstruir Lineas
            for i in range(4):
                p1 = self.rois[roi_name]["point_items"][i].pos()
                p2 = self.rois[roi_name]["point_items"][(i + 1) % 4].pos()
                self.add_line(p1, p2, roi_name=roi_name, line_color=line_color)

            # Dibijar poligonos
            polygon = QPolygonF([p.pos() for p in self.rois[roi_name]["point_items"]])
            pen = QPen(poly_color)
            pen.setWidth(2)

            polygon_item = QGraphicsPolygonItem(polygon)
            polygon_item.setPen(pen)
            polygon_item.setBrush(poly_color)
            polygon_item.setZValue(1)
            
            self.rois[roi_name]["polygon_item"] = polygon_item

            self.scene.addItem(polygon_item)

    def fit_image(self):
        if not self.pixmap_item:
            return
        self.setSceneRect(self.pixmap_item.boundingRect())
        self.resetTransform()
        self.fitInView(self.sceneRect(), Qt.KeepAspectRatioByExpanding)

    def fit_width(self):
        if not self.pixmap_item:
            return

        view_width = self.viewport().width()
        scene_width = self.sceneRect().width()

        if scene_width == 0:
            return

        scale_factor = view_width / scene_width
        self.resetTransform()
        self.scale(scale_factor, scale_factor)

    def wheelEvent(self, event):
        zoom_in_factor = 1.25
        zoom_out_factor = 1 / zoom_in_factor

        if event.angleDelta().y() > 0:
            zoom_factor = zoom_in_factor
        else:
            zoom_factor = zoom_out_factor

        self.scale(zoom_factor, zoom_factor)

        scale = self.transform().m11()
        self.zoom_label.setText(f"Zoom: {int(scale*100)}%")

    
    def add_point(self, pos, roi_name = None, point_color = None):
        point = DraggablePoint(pos.x(), pos.y(), 5, self)
        
        if point_color is not None:
            point.setBrush(QBrush(point_color))
            #p.setFlag(QGraphicsEllipseItem.ItemIsMovable, is_active)
        
        if roi_name is None:
            self.rois[self.current_roi]["point_items"].append(point)
        else:
            self.rois[roi_name]["point_items"].append(point)

        self.scene.addItem(point)

    def add_line(self, p1, p2, roi_name = None, line_color = None):
        if line_color is None:
            pen = QPen(QColor(0, 255, 0))
        else:
            pen = QPen(line_color)
        pen.setWidth(2)

        line = QGraphicsLineItem(
            p1.x(), p1.y(),
            p2.x(), p2.y()
        )
        line.setPen(pen)

        if roi_name is None:
            self.rois[self.current_roi]["lines"].append(line)
        else:
            self.rois[roi_name]["lines"].append(line)
        self.scene.addItem(line)


    def get_rois(self):
        rois = {}
        for current_roi in self.rois_names:
            #print("current_roi:", current_roi)
            #print("self.rois[current_roi]:", self.rois[current_roi])
            point_items = self.rois[current_roi]["point_items"]
            if len(point_items) >= 4:
                roi_points = [p.pos() for p in point_items]
                rois[current_roi] = [(p.x(), p.y()) for p in roi_points]
            else:
                rois[current_roi] = None
        
        return rois
    
    def close_polygon(self):
        
        # Bloquer dibujo
        
        self.drawing = False
       
        # eliminar línea dinámica si existe
        if self.temp_line:
            self.scene.removeItem(self.temp_line)
            self.temp_line = None
        
        # cerrar figura
        # Cerrando figura
        #print("self.rois[self.current_roi][lines]:", len(self.rois[self.current_roi]["lines"]))
        
        #self.add_line(self.rois[self.current_roi]["points"][-1],
        #              self.rois[self.current_roi]["points"][0])
        
        
        #print("self.rois[self.current_roi][lines]:", len(self.rois[self.current_roi]["lines"]))



        # actualizar líneas 
        for line in self.rois[self.current_roi]["lines"]:
            self.scene.removeItem(line)
        self.rois[self.current_roi]["lines"].clear()

        pts = [p.pos() for p in self.rois[self.current_roi]["point_items"]]
        
        for i in range(len(pts)):
            p1 = pts[i]
            p2 = pts[(i + 1) % len(pts)]
            self.add_line(p1, p2)

        polygon = QPolygonF([p.pos() for p in self.rois[self.current_roi]["point_items"]])

        pen = QPen(QColor(0, 255, 0))
        pen.setWidth(2)

        self.rois[self.current_roi]["polygon_item"] = QGraphicsPolygonItem(polygon)
        self.rois[self.current_roi]["polygon_item"].setPen(pen)
        self.rois[self.current_roi]["polygon_item"].setBrush(QColor(0, 255, 0, 40))
        self.rois[self.current_roi]["polygon_item"].setZValue(1)
        self.scene.addItem(self.rois[self.current_roi]["polygon_item"])

        if self.temp_line:
            self.scene.removeItem(self.temp_line)
            self.temp_line = None
        
    
    def _color_poly(self, is_active):
        if is_active:
            point_color = QColor(0, 255, 0)        # verde fuerte
            poly_color = QColor(0, 255, 0, 40)
            line_color = QColor(0, 255, 0)
        else:
            point_color = QColor(150, 150, 150)    # gris
            poly_color = QColor(150, 150, 150, 20)
            line_color = QColor(150, 150, 150)
    
        return point_color, poly_color, line_color

    def change_roi(self, idx):
        self.current_roi = self.rois_names[idx]
        if not self.rois[self.current_roi]["polygon_item"]:
            self.drawing = True

        for roi_name, roi_data in self.rois.items():
            is_active = (roi_name == self.current_roi)    
             # 🎨 colores
            point_color, poly_color, line_color = self._color_poly(is_active)

            for p in self.rois[roi_name]["point_items"]:
                p.setBrush(QBrush(point_color))
                p.setFlag(QGraphicsEllipseItem.ItemIsMovable, is_active)

             # 📏 líneas

            for line in roi_data["lines"]:
                pen = QPen(line_color)
                pen.setWidth(2)
                line.setPen(pen)

            # 🔺 polígono
            poly = roi_data["polygon_item"]
            if poly:
                pen = QPen(line_color)
                pen.setWidth(2)
                poly.setPen(pen)
                poly.setBrush(QBrush(poly_color))


    def update_polygon(self):

        # actualizar ultima linea agregada
        if len(self.rois[self.current_roi]["point_items"]) > 1 and self.drawing and self.rois[self.current_roi]["lines"]: 
            last_line = self.rois[self.current_roi]["lines"].pop()
            self.scene.removeItem(last_line)
            self.add_line(self.rois[self.current_roi]["point_items"][-2].pos(), self.rois[self.current_roi]["point_items"][-1].pos())

            if self.temp_line:
                self.scene.removeItem(self.temp_line)
                self.temp_line = None
                    
        if not self.rois[self.current_roi]["polygon_item"]:
            return
        
        polygon = QPolygonF([p.pos() for p in self.rois[self.current_roi]["point_items"]])
        self.rois[self.current_roi]["polygon_item"].setPolygon(polygon)

        # actualizar líneas 
        for line in self.rois[self.current_roi]["lines"]:
            self.scene.removeItem(line)
        self.rois[self.current_roi]["lines"].clear()

        pts = [p.pos() for p in self.rois[self.current_roi]["point_items"]]
        
        for i in range(len(pts)):
            p1 = pts[i]
            p2 = pts[(i + 1) % len(pts)]
            self.add_line(p1, p2)


    # Click para agregar punto
    def mousePressEvent(self, event):
        if self.pan_mode:
            super().mousePressEvent(event)
            return
    
        if not self.drawing or self.image is None:
            super().mousePressEvent(event)
            return
        
        pos = self.mapToScene(event.pos())
        if len(self.rois[self.current_roi]["points"]) < 4:
            self.rois[self.current_roi]["points"].append(pos)
            self.add_point(pos)
            
            if len(self.rois[self.current_roi]["points"]) > 1:
                self.add_line(
                    self.rois[self.current_roi]["point_items"][-2].pos(),
                    self.rois[self.current_roi]["point_items"][-1].pos()
                )
            
            if len(self.rois[self.current_roi]["points"]) == 4:
                self.close_polygon()
                self.on_save_rois()

        super().mousePressEvent(event)
        return 
    
    # Línea dinámica
    def mouseMoveEvent(self, event):
        if self.pan_mode:
            super().mouseMoveEvent(event)
            return
    
        if not self.drawing:
            super().mouseMoveEvent(event)
            return
        
        if event.buttons() != Qt.NoButton:
            super().mouseMoveEvent(event)
            return
    
        if len(self.rois[self.current_roi]["points"]) > 0 and len(self.rois[self.current_roi]["points"]) < 4:
            pos = self.mapToScene(event.pos())
            
            if self.temp_line:
                self.scene.removeItem(self.temp_line)
                self.temp_line = None
            
            pen = QPen(QColor(0,255,0))
            pen.setWidth(1)
            last = self.rois[self.current_roi]["point_items"][-1].pos()

            self.temp_line = QGraphicsLineItem(
                last.x(), last.y(),
                pos.x(), pos.y()
            )

            self.temp_line.setPen(pen)
            self.scene.addItem(self.temp_line)
            
        super().mouseMoveEvent(event)

class BottomBar(QWidget):
    def __init__(self):
        super().__init__()

        self.setFixedHeight(48)

        self.setStyleSheet("""
            QWidget {
                background-color: #E9EBF1;
                border-radius: 12px;
            }

            QPushButton {
                border: none;
                background: transparent;
                padding: 6px;
            }

            QPushButton:hover {
                background-color: rgba(0,0,0,0.08);
                border-radius: 6px;
            }


            QPushButton:checked {
                background-color: rgba(0,120,255,0.2);  /* 🔵 azul suave */
                border-radius: 6px;
            }
                            
            QLabel {
                color: #5A5F6A;
                font-size: 13px;
            }
        """)

        layout = QHBoxLayout()
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(6)

        # 🔍 Zoom out
        self.zoom_out = QPushButton()
        self.zoom_out.setIcon(QIcon(resource_path("assets/zoom_out.svg")))
        self.zoom_out.setIconSize(QSize(18, 18))

        # 🔍 Zoom in
        self.zoom_in = QPushButton()
        self.zoom_in.setIcon(QIcon(resource_path("assets/zoom_in.svg")))
        self.zoom_in.setIconSize(QSize(18, 18))

        # ✋ Pan (mano)
        self.pan_btn = QPushButton()
        self.pan_btn.setIcon(QIcon(resource_path("assets/hand.svg")))
        self.pan_btn.setIconSize(QSize(18, 18))
        self.pan_btn.setCheckable(True)
        

        # separador
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.VLine)
        sep1.setStyleSheet("color: #C5C7CE;")

        # 🗑 limpiar
        self.clear_btn = QPushButton(" LIMPIAR SELECCIÓN")
        self.clear_btn.setIcon(QIcon(resource_path("assets/trash.svg")))

        layout.addWidget(self.zoom_out)
        layout.addWidget(self.zoom_in)
        layout.addWidget(self.pan_btn)
        layout.addWidget(sep1)
        layout.addWidget(self.clear_btn)

        layout.addStretch()

        # zoom label
        self.zoom_label = QLabel("Zoom: 100%")
        layout.addWidget(self.zoom_label)

        self.setLayout(layout)


class BandCard(QFrame):
    def __init__(self, title, band_name, load_image_cb, select_band_cb):
        super().__init__()
        self.band_name = band_name
        self.load_image_cb = load_image_cb
        self.select_band_cb = select_band_cb
        self.selected = False
        
        self.setFixedSize(155, 190)
        self.setCursor(Qt.PointingHandCursor)
        #         background-color: #FFFFFF;d
        
        self.setStyleSheet("""
            BandCard {
                background-color: #f8fafd;
                border: 1px solid #e2e8f0;
                border-radius: 15px;
            }
        """)
        ## Agregar sombra
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(15)
        shadow.setOffset(0,12)
        shadow.setColor(QColor(0, 0, 0, 20))
        self.setGraphicsEffect(shadow)

        # UI
        self.title = QLabel(title)
        self.title.setStyleSheet("""
            font-size: 18px; 
            font-weight: bold; 
            color: #334155; 
            border: none;
            background: transparent;
        """)

        self.target_label = QLabel("Paneles: 0/3")
        self.target_label.setStyleSheet("""
            color: #94a3b8; 
            font-size: 14px; 
            font-weight: 500;
            border: none;
            background: transparent;
        """)

        self.miniature = QLabel("No cargada")
        self.miniature.setAlignment(Qt.AlignCenter)
        self.miniature.setFixedHeight(75)
        self.miniature.setStyleSheet("""
            background-color: #e9eff6;
            border-radius: 10px;
            border: 2px dashed #cbd5e1;
            color: #64748b;
            font-size: 18px;
            font-weight: 500;
        """)
        self.load_button = QPushButton("Cargar")
        self.load_button.setFixedHeight(30)
        self.load_button.clicked.connect(self.load_image)

        self.load_button.setStyleSheet("""
            QPushButton {
                background-color: white;
                color: #334155;
                border: 1.5px solid #cbd5e1;
                border-radius: 10px;
                font-size: 18px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #f1f5f9;
                border: 1.5px solid #94a3b8;
            }
            QPushButton:pressed {
                background-color: #e2e8f0;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10) # Espacio interno para que no toque los bordes
        layout.setSpacing(2)
        layout.addWidget(self.title, alignment=Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self.target_label, alignment=Qt.AlignmentFlag.AlignTop)
        layout.addSpacing(8) # Este es el espacio real entre el texto y la imagen
        layout.addWidget(self.miniature)
        layout.addSpacing(8) # Espacio extra antes de la imagen
        layout.addWidget(self.load_button)
    
    def card_style(self):
        if self.selected:
            return """
                BandCard {
                    background-color: #ecfdf5;
                    border: 3px solid #1f7a6e;
                    border-radius: 18px;
                }
            """
        else:
            return """
                BandCard {
                    background-color: #f8fafd;
                    border: 1px solid #e2e8f0;
                    border-radius: 15px;
                }
                BandCard:hover {
                    border: 2px solid #94a3b8;cd .
                }
            """

    def set_rois_completed(self, num_rois):
        self.target_label.setText(f"Paneles: {num_rois}/3")
        #self.target_label.setStyleSheet("color: #E4A65E;")
        if num_rois > 0 and num_rois < 3:
            self.target_label.setStyleSheet("""
                color: #E4A65E; 
                font-size: 14px; 
                font-weight: 500;
                border: none;
                background: transparent;
            """)
        elif num_rois == 3:
            self.target_label.setStyleSheet("""
                color: #4CAF50; 
                font-size: 14px; 
                font-weight: 500;
                border: none;
                background: transparent;
            """)


    def set_selected(self, value):
        self.selected = value
        self.setStyleSheet(self.card_style())

    def mousePressEvent(self, event):
        self.select_band_cb(self.band_name)
        self.set_selected(True)
        return super().mousePressEvent(event)
    
    def set_thumbnail(self, img):
        disp = cv2.normalize(img, None, 0, 255, cv2.NORM_MINMAX)
        disp = disp.astype(np.uint8)

        h, w = disp.shape
        qimg = QImage(disp.data, w, h, w, QImage.Format_Grayscale8)
        pixmap = QPixmap.fromImage(qimg).scaled(
            145, 145, Qt.KeepAspectRatio
        )

        self.miniature.setPixmap(pixmap)

    def load_image(self):
        self.load_image_cb(self.band_name)

class RadCalibrationPanel(QDialog):
    def __init__(self, parent = None):
        super().__init__(parent)
        self.setWindowTitle("Calibración Radiométrica")
        self.setFixedSize(1300, 750)    
        self.setModal(True)

        self.band2name = {
            "Red": "Roja",
            "Green": "Verde",
            "NIR": "NIR",
            "RedEdge": "RedEdge",
        }

        self.data = {
            "Red": {
                "image_path": None,
                "image" : None,
                "rois": {
                    "black": None,
                    "gray": None,
                    "red": None
                },
                "reflectance_panels" : {
                    "black": None,
                    "gray": None,
                    "red": None
                },
                "card": None
            },
            "Green": {
                "image_path": None,
                "image" : None,
                "rois": {
                    "black": None,
                    "gray": None,
                    "red": None
                },
                "reflectance_panels" : {
                    "black": None,
                    "gray": None,
                    "red": None
                },
                "card": None
            }, 
            "NIR": {
                "image_path": None,
                "image" : None,
                "rois": {
                    "black": None,
                    "gray": None,
                    "red": None
                },
                "reflectance_panels" : {
                    "black": None,
                    "gray": None,
                    "red": None
                },
                "card": None
            }, 
            "RedEdge": {
                "image_path": None,
                "image" : None,
                "rois": {
                    "black": None,
                    "gray": None,
                    "red": None
                },
                "reflectance_panels" : {
                    "black": None,
                    "gray": None,
                    "red": None
                },
                "card": None
            }, 
        }

        self.setStyleSheet("""
            #calibrationCard {
                background-color: #FFFFFF;
                border: 1px solid #DADDE5;
                border-radius: 12px;
            }

            #calibrationCard QLabel {
                font-weight: bold;
                color: #4A4F5A;
            }

            #msCard {
                background-color: #FFFFFF;
                border: 1px solid #DADDE5;
                border-radius: 12px;
            }

            #msTitle {
                font-weight: bold;
                color: #6B778C;
                font-size: 14px;
                text-transform: uppercase;
            }            

            #btnLoadAll {
                background-color: #00695C;
                color: white;
                font-weight: bold;
                border-radius: 8px;
                padding: 8px;
                font-size: 14px;
            }
            #btnLoadAll:hover {
                background-color: #004D40;
            }
                           
            /* Estilos añadidos para el panel de reflectancia */
            #bandBadge {
                background-color: #E8F5E9; /* Fondo verde claro */
                color: #046C4E; /* Texto verde oscuro */
                font-weight: bold;
                border-radius: 12px;
                padding: 4px 12px;
                font-size: 12px;
            }
                           
            /* Botón Secundario (Cancelar) */
            QPushButton#BotonSecundario {
                background-color: #FFFFFF;
                border: 1px solid #D1D5DB; /* Borde gris claro */
                color: #4B5563;            /* Texto gris oscuro */
                font-size: 13px;
                font-weight: normal;       /* Según la imagen, no es negrita */
                padding: 6px 16px;
                border-radius: 6px;        /* Bordes redondeados suaves */
            }
            QPushButton#BotonSecundario:hover {
                background-color: #F9FAFB; /* Gris muy clarito al pasar el mouse */
                border: 1px solid #9CA3AF; /* Borde un poco más oscuro */
            }
            QPushButton#BotonSecundario:pressed {
                background-color: #F3F4F6;
            }

            /* Botón Primario (Guardar) */
            QPushButton#BotonPrimario {
                background-color: #046C4E; /* Verde oscuro elegante de tu imagen */
                border: 1px solid #046C4E;
                color: #FFFFFF;            /* Texto blanco */
                font-size: 13px;
                font-weight: normal;
                padding: 6px 16px;
                border-radius: 6px;
            }
            QPushButton#BotonPrimario:hover {
                background-color: #03543F; /* Verde un tono más oscuro al pasar el mouse */
                border: 1px solid #03543F;
            }
            QPushButton#BotonPrimario:pressed {
                background-color: #014735;
            }
            QPushButton#BotonPrimario:disabled {
                background-color: #9CA3AF; /* Gris si se llega a deshabilitar */
                border: 1px solid #9CA3AF;
                color: #E5E7EB;
            }
        """)

          
        reflectance_panels = None
    
        with open(resource_path("assets/reflectance_panels.json"), "r") as fp:
            reflectance_panels = json.load(fp)
        
        if reflectance_panels:
            for band_name, band_info in self.data.items():
                self.data[band_name]["reflectance_panels"]
                for target_name in ['black', "gray", "red"]:
                    band_info["reflectance_panels"][target_name] = round(reflectance_panels[target_name]["reflectance_bands"][band_name.lower()], 3)
        
        self.current_band = None
        self.viewer = ImageViewer(#parent = self,
                                  on_save_rois = self.save_rois,
                                  on_validate_complete = self.validar_completitud)

        self.current_reference = "black"
        #self.load_band_image("Green")
        
        # Reference Selector
        # --- Black ---
        self.black_radio = QRadioButton("Panel Negro (Tela Negra)")
        self.black_radio.setChecked(True)

        self.black_ref_input = QLineEdit()
        regex = QRegularExpression(r"^(0(\.\d{1,3})?|1(\.0{1,3})?)$")
        validador = QRegularExpressionValidator(regex, self.black_ref_input)
        self.black_ref_input.setValidator(validador)

        self.black_ref_input.setObjectName("reflectanceInput")
        self.black_ref_input.setAlignment(Qt.AlignCenter)
        self.black_ref_input.setPlaceholderText("0.00")
        self.black_ref_input.textChanged.connect(lambda val: self.update_reflactance("black", self.black_ref_input))
        self.black_ref_input.setEnabled(False)

        self.rois_labels_status = {}

        #self.black_status = QLabel("No Seleccionado")
        #self.black_status.setFixedWidth(120)
        #self.black_status.setAlignment(Qt.AlignCenter)

        black_layout = QHBoxLayout()
        black_layout.addWidget(self.black_radio)
        black_layout.addStretch()
        black_layout.addWidget(QLabel("Reflectancia [", objectName="refLabel"))
        black_layout.addWidget(self.black_ref_input)
        black_layout.addWidget(QLabel("]", objectName="refLabel"))
        #black_layout.addWidget(self.black_status)
        
        # --- Gray ---
        self.gray_radio = QRadioButton("Panel Gris (Tela Gris)")
        self.gray_ref_input = QLineEdit()
        self.gray_ref_input.setObjectName("reflectanceInput")
        self.gray_ref_input.setAlignment(Qt.AlignCenter)
        self.gray_ref_input.setPlaceholderText("0.00") # Valor de tu imagen
        self.gray_ref_input.textChanged.connect(lambda val: self.update_reflactance("gray", self.gray_ref_input))
        self.gray_ref_input.setEnabled(False)
        regex = QRegularExpression(r"^(0(\.\d{1,3})?|1(\.0{1,3})?)$")
        validador = QRegularExpressionValidator(regex, self.gray_ref_input)
        self.gray_ref_input.setValidator(validador)

        #self.gray_status.setFixedWidth(120)
        #self.gray_status.setAlignment(Qt.AlignCenter)

        

        gray_layout = QHBoxLayout()
        gray_layout.addWidget(self.gray_radio)
        gray_layout.addStretch()
        gray_layout.addWidget(QLabel("Reflectancia [", objectName="refLabel"))
        gray_layout.addWidget(self.gray_ref_input)
        gray_layout.addWidget(QLabel("]", objectName="refLabel"))
        #gray_layout.addWidget(self.gray_status)

        # --- Red ---

        self.red_radio = QRadioButton("Panel Rojo (Tela Roja)")
        self.red_ref_input = QLineEdit()
        self.red_ref_input.setObjectName("reflectanceInput")
        self.red_ref_input.setAlignment(Qt.AlignCenter)
        self.red_ref_input.setPlaceholderText("0.00") # Valor de tu imagen
        self.red_ref_input.textChanged.connect(lambda val: self.update_reflactance("red", self.red_ref_input))
        self.red_ref_input.setEnabled(False)
        regex = QRegularExpression(r"^(0(\.\d{1,3})?|1(\.0{1,3})?)$")
        validador = QRegularExpressionValidator(regex, self.red_ref_input)
        self.red_ref_input.setValidator(validador)

        #self.red_status = QLabel("No Seleccionado")
        #self.red_status.setFixedWidth(120)
        #self.red_status.setAlignment(Qt.AlignCenter)

        red_layout = QHBoxLayout()
        red_layout.addWidget(self.red_radio)
        red_layout.addStretch()
        red_layout.addWidget(QLabel("Reflectancia [", objectName="refLabel"))
        red_layout.addWidget(self.red_ref_input)
        red_layout.addWidget(QLabel("]", objectName="refLabel"))
        #red_layout.addWidget(self.red_status)

        # self.rois_labels_status["black"] = self.black_status
        # self.rois_labels_status["gray"] = self.black_status
        # self.rois_labels_status["red"] = self.red_status

        self.ref_group = QButtonGroup()
        self.ref_group.addButton(self.black_radio)
        self.ref_group.addButton(self.gray_radio)
        self.ref_group.addButton(self.red_radio)
        self.ref_group.buttonClicked.connect(self.change_reference)

        # Panel Derecho
        right_layout = QVBoxLayout()
        
        # Crear Card Grande
        multispec_card = QFrame()
        multispec_card.setObjectName("msCard")
        multispec_layout = QVBoxLayout(multispec_card)
        multispec_layout.setContentsMargins(20, 20, 20, 20)
        multispec_layout.setSpacing(15)

        # Titulo de la Seccion

        title_ms_label = QLabel("BANDAS MULTIESPECTRALES")
        title_ms_label.setObjectName("msTitle")
        multispec_layout.addWidget(title_ms_label)

        # Boton Cargar Bandas
        self.btn_load_all = QPushButton("Cargar Todas las Bandas")
        
        self.btn_load_all.clicked.connect(self.load_bands)
        self.rutas_archivos_tif = []

        self.btn_load_all.setObjectName("btnLoadAll")
        self.btn_load_all.setCursor(Qt.PointingHandCursor)
        multispec_layout.addWidget(self.btn_load_all)

        # Grid para las 4 Bandas
        grid_layout = QGridLayout()
        grid_layout.setSpacing(15)

        # Instanciamos las tarjetas

        self.card_band_green = BandCard(title = "Verde", 
                                        band_name="Green",
                                        load_image_cb = self.load_band_image,
                                        select_band_cb = self.select_band)
        
        self.data["Green"]["card"]  = self.card_band_green
        

        self.card_band_red = BandCard(title = "Roja", 
                                      band_name="Red",
                                      load_image_cb = self.load_band_image,
                                      select_band_cb = self.select_band)
        

        self.data["Red"]["card"]  = self.card_band_red

        self.card_band_re = BandCard(title = "Red Edge", 
                                     band_name="RedEdge",
                                     load_image_cb = self.load_band_image,
                                     select_band_cb = self.select_band)
        
        self.data["RedEdge"]["card"]  = self.card_band_re

        self.card_band_nir = BandCard(title = "NIR", 
                                      band_name="NIR",
                                      load_image_cb = self.load_band_image,
                                      select_band_cb = self.select_band)

        self.data["NIR"]["card"]  = self.card_band_nir
        
        self.band_widgets = dict(Green =  self.card_band_green,
                                 Red = self.card_band_red,
                                 RedEdge = self.card_band_re,
                                 NIR = self.card_band_nir
                                 )
        
        # Agregamos al grid
        grid_layout.addWidget(self.card_band_green, 0, 0)
        grid_layout.addWidget(self.card_band_red, 0, 1)
        grid_layout.addWidget(self.card_band_re, 1, 0)
        grid_layout.addWidget(self.card_band_nir, 1, 1)

        multispec_layout.addLayout(grid_layout)

        right_layout.addWidget(multispec_card)
        right_layout.addStretch()

        
        card_panels = QFrame()
        card_panels.setObjectName("calibrationCard")
        card_layout = QVBoxLayout()
        card_layout.setContentsMargins(15, 15, 15, 15)
        card_layout.setSpacing(10)
        
        # Header con Título y Badge
        header_calib_layout = QHBoxLayout()
        title_calib_label = QLabel("OBJETIVOS DE CALIBRACIÓN")
        title_calib_label.setObjectName("msTitle") # Reutiliza el estilo del título

        # Aquí creamos el Badge indicador
        self.band_badge = QLabel("Banda: No Selecionada") #QLabel("Banda: Verde")
        self.band_badge.setObjectName("bandBadge")

        header_calib_layout.addWidget(title_calib_label)
        header_calib_layout.addStretch()
        header_calib_layout.addWidget(self.band_badge)

        card_layout.addLayout(header_calib_layout)
        #card_layout.addWidget(QLabel("OBJETIVOS DE CALIBRACION"))
        card_layout.addLayout(black_layout)
        card_layout.addLayout(gray_layout)
        card_layout.addLayout(red_layout)

        card_panels.setLayout(card_layout)

        right_layout.addWidget(card_panels)
        # right_layout.addWidget(QLabel("PANELES DE CALIBRACION"))
        # right_layout.addLayout(black_layout)
        # right_layout.addLayout(gray_layout)
        right_layout.addStretch()
        right_widget = QWidget()
        right_widget.setLayout(right_layout)

        left_layout = QVBoxLayout()

        self.bottom_bar = BottomBar()
        self.bottom_bar.zoom_in.clicked.connect(lambda: self.viewer.scale(1.25, 1.25))
        self.bottom_bar.zoom_out.clicked.connect(lambda: self.viewer.scale(0.8, 0.8))
        self.bottom_bar.clear_btn.clicked.connect(self.clear_current_roi)
        # zoom label
        self.viewer.zoom_label = self.bottom_bar.zoom_label


        self.bottom_bar.pan_btn.toggled.connect(self.viewer.set_pan_mode)

        self.stack_visor = QStackedWidget()
        self.pantalla_vacia = PlaceholderImagen()

        # Índice 0: El mensaje de "No hay imagen"
        self.stack_visor.addWidget(self.pantalla_vacia) 
        # Índice 1: Tu visor real para hacer los polígonos
        self.stack_visor.addWidget(self.viewer)

        # Por defecto, mostramos la pantalla vacía
        self.stack_visor.setCurrentIndex(0)

        left_layout.addWidget(self.stack_visor)
        left_layout.addWidget(self.bottom_bar)

        left_widget = QWidget()
        left_widget.setLayout(left_layout)

        layout = QHBoxLayout()
        layout.addWidget(left_widget, 2)
        layout.addWidget(right_widget, 1)

         # 🔥 BOTONES (nuevo)
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_cancel = QPushButton("Cancelar")
        self.btn_cancel.setObjectName("BotonSecundario")
        self.btn_cancel.setCursor(Qt.PointingHandCursor)

        self.btn_save = QPushButton("Guardar")
        self.btn_save.setObjectName("BotonPrimario")
        self.btn_save.setCursor(Qt.PointingHandCursor)

        # 2. BLOQUEAR EL BOTÓN POR DEFECTO
        self.btn_save.setEnabled(False)

        self.btn_cancel.clicked.connect(self.reject)
        self.btn_save.clicked.connect(self.on_save)

        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_save)
        main_layout = QVBoxLayout()
        main_layout.addLayout(layout)
        main_layout.addLayout(btn_layout)

        self.setLayout(main_layout)
    

    def load_bands(self):
        """
        Abre un cuadro de diálogo para seleccionar archivos .tif y valida que sean 4.
        """
        # Abrir el explorador de archivos. 
        # getOpenFileNames devuelve una tupla: (lista de rutas, filtro usado)
        archivos, _ = QFileDialog.getOpenFileNames(
            self,                                   # Parent
            "Seleccionar 4 bandas (.tif)",          # Título de la ventana
            "",                                     # Directorio inicial (vacío = último usado)
            "Imágenes TIF (*.tif *.tiff)"           # Filtro para mostrar solo TIFs
        )

        # Si el usuario cierra la ventana sin seleccionar nada
        if not archivos:
            return

        # Validar que se hayan seleccionado exactamente 4 archivos
        if len(archivos) != 4:
            QMessageBox.warning(
                self,
                "Selección incorrecta",
                f"Debes seleccionar exactamente 4 archivos .tif.\nHas seleccionado {len(archivos)}."
            )
            return
        
        # 2. NUEVA VALIDACIÓN: Verificar los sufijos de las bandas
        bands_sufxs = ["_MS_G.TIF", "_MS_R.TIF", "_MS_RE.TIF", "_MS_NIR.TIF"]
        bandas_faltantes = []
        
        # Convertimos las rutas a mayúsculas para una comparación segura
        archivos_upper = [ruta.upper() for ruta in archivos]
        
        for sufijo in bands_sufxs:
            # Buscamos si el sufijo actual coincide con el final de alguna de las rutas
            if not any(ruta.endswith(sufijo) for ruta in archivos_upper):
                bandas_faltantes.append(sufijo)
                
        # Si la lista de faltantes tiene elementos, mostramos el error y abortamos
        if bandas_faltantes:
            QMessageBox.warning(
                self,
                "Bandas incorrectas o faltantes",
                f"Los archivos seleccionados no contienen todas las bandas requeridas.\n"
                f"Faltan los siguientes sufijos:\n{', '.join(bandas_faltantes)}\n\n"
                "Asegúrate de seleccionar el grupo correcto de imágenes."
            )
            return
        
        for path in archivos:
            if "_MS_G.TIF" in path:
                self._load_image(path, "Green")
            elif "_MS_R.TIF" in path:
                self._load_image(path, "Red")
            elif "_MS_RE.TIF" in path:
                self._load_image(path, "RedEdge")
            elif "_MS_NIR.TIF" in path:
                self._load_image(path, "NIR")
        
        # Si pasó la validación, guardamos las rutas
        #self.rutas_archivos_tif = archivos
        
        # Notificar al usuario o continuar con el flujo
        QMessageBox.information(
            self, 
            "Éxito", 
            "Las 4 bandas se han cargado correctamente."
        )
        
        # Puedes imprimir para verificar o llamar a tu método de procesamiento de imágenes


    def update_reflactance(self, target_panel, input):
        if self.current_band is None:
            return
        if input.hasAcceptableInput():
            val_str = input.text()
            if val_str:
                print("band:", self.current_band, " target_panel:", target_panel, " val_str:", val_str)
                self.data[self.current_band]["reflectance_panels"][target_panel] = float(val_str)
    
    def on_save(self):
        if self.current_band:
            self.save_rois()

        # puedes validar si falta algo
        # if not valid: return

        self.accept()

    def get_data(self):
        save_data = {
            key: {k: v for k, v in value.items() if k not in ("image", "card")}
            for key, value in self.data.items()
        }
        
        return save_data
    
    def change_reference(self, button):
        if button == self.black_radio:
            self.current_reference = "black"
            self.viewer.change_roi(0)
        elif button == self.gray_radio:
            self.current_reference = "gray"
            self.viewer.change_roi(1)
        elif button == self.red_radio:
            self.current_reference = "red"
            self.viewer.change_roi(2)

    def clear_current_roi(self):
        roi = self.viewer.rois[self.viewer.current_roi]

        # eliminar puntos
        for p in roi["point_items"]:
            self.viewer.scene.removeItem(p)
        roi["point_items"].clear()

        # eliminar líneas
        for l in roi["lines"]:
            self.viewer.scene.removeItem(l)
        roi["lines"].clear()

        # eliminar polígono
        if roi["polygon_item"]:
            self.viewer.scene.removeItem(roi["polygon_item"])
            roi["polygon_item"] = None  

        roi["points"].clear()

        
        self.viewer.remove_roi(self.viewer.current_roi)

        self.viewer.drawing = True
        
        self.save_rois()
        self.validar_completitud()


    def _load_image(self, path, band_name):
        img = cv2.imread(path, cv2.IMREAD_UNCHANGED)

        if img.ndim == 3:
            img = img[:, :, 0]
        
        self.data[band_name]["image_path"] = path 
        self.data[band_name]["image"] = img

        metadata = read_metadata_worker(path)
        self.data[band_name]["metadata"] = metadata

        self.band_widgets[band_name].set_thumbnail(img)
        self.band_widgets[band_name].set_selected(band_name)

        if self.current_band != band_name:
            self.select_band(band_name)
        else:
            # MUESTRA EL VISOR DE IMAGEN
            self.stack_visor.setCurrentIndex(1)
            self.bottom_bar.setEnabled(True)
            self.viewer.load_image(img)
            #self.drawing = True
            targets_pts = self.data[band_name]["rois"]
            self.viewer.restore_rois(targets_pts)
            self.drawing = True

    def restore_images_and_rois(self, data):
        if data is None:
            return
        
        for band_name, band_info in data.items():
            image_path = band_info["image_path"]
            rois = band_info["rois"]
            reflectance_panels = band_info["reflectance_panels"]
            self.data[band_name]["image_path"] = image_path
            self.data[band_name]["rois"] = rois
            self.data[band_name]["reflectance_panels"] = reflectance_panels

            img = cv2.imread(image_path, cv2.IMREAD_UNCHANGED)

            if img.ndim == 3:
                img = img[:, :, 0]
            
            self.data[band_name]["image"] = img
            self.band_widgets[band_name].set_thumbnail(img)
        
        self.select_band("Green")

        self.validar_completitud()

    def load_band_image(self, band_name):
        path, _ = QFileDialog.getOpenFileName(
            self, f"Selecciona archivo", "", "TIFF (*.tif *.tiff)")
        if not path:
            return
        
        img = cv2.imread(path, cv2.IMREAD_UNCHANGED)

        if img.ndim == 3:
            img = img[:, :, 0]
        
        self.data[band_name]["image_path"] = path 
        self.data[band_name]["image"] = img
        metadata = read_metadata_worker(path)
        self.data[band_name]["metadata"] = metadata

        self.band_widgets[band_name].set_thumbnail(img)
        self.band_widgets[band_name].set_selected(band_name)

        if self.current_band != band_name:
            self.select_band(band_name)
        else:
            # MUESTRA EL VISOR DE IMAGEN
            self.stack_visor.setCurrentIndex(1)
            self.bottom_bar.setEnabled(True)
            self.viewer.load_image(img)
            #self.drawing = True
            targets_pts = self.data[band_name]["rois"]
            self.viewer.restore_rois(targets_pts)
            self.drawing = True

            #self.select_band(band_name)

    def select_band(self, band_name):
        print("select_band self.current_band:", self.current_band)
        if self.current_band is not None:
            self.save_rois()
            if self.current_band == band_name:
                return
            else:
                self.viewer.reset()
        
        self.current_band = band_name

        self.band_badge.setText(f"Banda: {self.band2name[band_name]}")
        
        reflectance_panels = self.data[band_name]["reflectance_panels"]
        ref_black = str(reflectance_panels["black"] or "")
        self.black_ref_input.setText(ref_black)

        ref_gray = str(reflectance_panels["gray"] or "")
        self.gray_ref_input.setText(ref_gray)

        ref_red = str(reflectance_panels["red"] or "")
        self.red_ref_input.setText(ref_red)

        self.black_ref_input.setEnabled(True)
        self.gray_ref_input.setEnabled(True)
        self.red_ref_input.setEnabled(True)
        
        for b_name, b_widget in self.band_widgets.items():
            if b_name != band_name:
                b_widget.set_selected(False)
            else:
                b_widget.set_selected(True)

        img = self.data[band_name]["image"]
        
        if img is None:
            self.viewer.reset()
            self.stack_visor.setCurrentIndex(0)
            # Podrías desactivar también la bottom_bar si quieres
            self.bottom_bar.setEnabled(False)
            return
        print("Muestra imagen")
        # MUESTRA EL VISOR DE IMAGEN
        self.stack_visor.setCurrentIndex(1)
        self.bottom_bar.setEnabled(True)
        self.viewer.load_image(img)

        print("Restaura Rois")
        targets_pts = self.data[band_name]["rois"]
        self.viewer.restore_rois(targets_pts)
        self.drawing = True
        
        #roi = self.data[band_name]["rois"][self.current_reference]
        
        
    def save_rois(self):
        rois = self.viewer.get_rois()
        band = self.current_band
        print("rois:", rois)
        for key, values in rois.items():
            self.data[band]["rois"][key] = values
        
        print(" self.data[band]:",  self.data[band])

        self.validar_completitud()

        #rois = self.data[self.current_band]['rois']
        #num_completed_rois = sum([1 for roi in rois if roi >= 4])
        #set_rois_completed

    
    def validar_completitud(self):
        """Revisa si todas las imágenes y todos los ROIs están completos."""
        todo_completo = True
        # set_rois_completed
        for band_name, band_info in self.data.items():
            # 1. ¿Falta cargar la imagen de esta banda?
            if band_info["image"] is None:
                todo_completo = False
                #break
            # 2. ¿Falta algún polígono (ROI) en esta imagen?
            num_completed_rois = 0
            for roi_name, puntos in band_info["rois"].items():
                if puntos is None or len(puntos) < 4:
                    todo_completo = False
                else:
                    num_completed_rois +=1
            
            if num_completed_rois < 3:
                todo_completo = False

            print("Band:", band_name, "num:", num_completed_rois)
            band_info["card"].set_rois_completed(num_completed_rois)

            # Falta algun valore de reflactance
            for target_name, value in band_info["reflectance_panels"].items():
                if value is None or value =="":
                    todo_completo == False

            

            #if not todo_completo:
            #    break
        
        # Si todo está perfecto (True), se enciende. Si falta algo (False), se apaga.
        if todo_completo:
            self.btn_save.setEnabled(todo_completo)
        else:
            self.btn_save.setEnabled(False)

        return todo_completo

class DialogoEditarParcela(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Eliminar la barra de título nativa para un diseño 100% personalizado
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.resize(400, 450)

        self.inicializar_ui()
        self.aplicar_estilos()

    def inicializar_ui(self):
        # Widget principal (actúa como el fondo blanco con bordes redondeados)
        self.widget_principal = QWidget(self)
        self.widget_principal.setObjectName("WidgetPrincipal")
        self.combos = {}
        # Layout base del diálogo
        layout_base = QVBoxLayout(self)
        layout_base.setContentsMargins(10, 10, 10, 10) 
        layout_base.addWidget(self.widget_principal)

        # Layout interno del widget principal
        layout = QVBoxLayout(self.widget_principal)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # --- CABECERA ---
        layout_cabecera = QHBoxLayout()
        layout_titulos = QVBoxLayout()
        layout_titulos.setSpacing(4)

        self.lbl_titulo = QLabel("Editar Información de la Parcela")
        self.lbl_titulo.setObjectName("Titulo")

        self.lbl_subtitulo = QLabel("Actualice las especificaciones agronómicas del terreno.")
        self.lbl_subtitulo.setObjectName("Subtitulo")

        layout_titulos.addWidget(self.lbl_titulo)
        layout_titulos.addWidget(self.lbl_subtitulo)

        self.btn_cerrar = QPushButton("✕")
        self.btn_cerrar.setObjectName("BtnCerrar")
        self.btn_cerrar.clicked.connect(self.reject)
        self.btn_cerrar.setFixedSize(24, 24)

        layout_cabecera.addLayout(layout_titulos)
        layout_cabecera.addStretch()
        layout_cabecera.addWidget(self.btn_cerrar, 0, Qt.AlignTop)

        layout.addLayout(layout_cabecera)

        # --- CAMPOS DEL FORMULARIO ---
        # Añadimos opciones simuladas basadas en tu imagen
        
        # --- CAMPOS DEL FORMULARIO (Guardamos referencias en self.combos) ---
        self.combos['etapa'] = self.crear_campo(layout, "ETAPA FENOLÓGICA", 
                                                ["Seleccionar"] + ETAPAS_FENOLOGICAS)
        self.combos['suelo'] = self.crear_campo(layout, "TIPO DE SUELO", 
                                                ["Seleccionar"] + TIPOS_SUELOS)
        self.combos['riego'] = self.crear_campo(layout, "TIPO DE RIEGO", 
                                                ["Seleccionar"] + TIPOS_RIEGOS)
        
        # Espaciador para empujar los botones hacia abajo
        layout.addSpacerItem(QSpacerItem(20, 20, QSizePolicy.Minimum, QSizePolicy.Expanding))

        # --- PIE (BOTONES) ---
        layout_pie = QHBoxLayout()
        layout_pie.setSpacing(12)

        self.btn_cancelar = QPushButton("Cancelar")
        self.btn_cancelar.setObjectName("BtnCancelar")
        self.btn_cancelar.clicked.connect(self.reject)

        # Usamos un checkmark en texto, o podrías usar un QIcon
        self.btn_guardar = QPushButton("✔ Guardar Cambios")
        self.btn_guardar.setObjectName("BtnGuardar")
        self.btn_guardar.clicked.connect(self.accept)

        layout_pie.addStretch()
        layout_pie.addWidget(self.btn_cancelar)
        layout_pie.addWidget(self.btn_guardar)

        # Layout especial para el pie de página con fondo ligeramente distinto (opcional)
        contenedor_pie = QWidget()
        contenedor_pie.setObjectName("ContenedorPie")
        contenedor_pie.setLayout(layout_pie)
        
        layout.addWidget(contenedor_pie)

    def crear_campo(self, layout_padre, texto_label, opciones):
        """Método auxiliar para generar las etiquetas y los ComboBoxes"""
        layout_campo = QVBoxLayout()
        layout_campo.setSpacing(6)

        label = QLabel(texto_label)
        label.setObjectName("LabelCampo")

        combo = QComboBox()
        combo.addItems(opciones)
        combo.setObjectName("ComboCampo")

        layout_campo.addWidget(label)
        layout_campo.addWidget(combo)
        layout_padre.addLayout(layout_campo)

        return combo
    def get_data(self):
        stage = self.combos['etapa'].currentText()
        stage = stage if stage != "Seleccionar" else None
        
        soil = self.combos['suelo'].currentText()
        soil = soil if soil != "Seleccionar" else None

        irrigation = self.combos['riego'].currentText()
        irrigation = irrigation if irrigation != "Seleccionar" else None

        data  = {
            "stage": stage,
            "soil": soil,
            "irrigation": irrigation
        }

        return data
        
    def actualizar_valores(self, etapa=None, suelo=None, riego=None):
        """
        Cambia la selección actual de los combos basándose en el texto.
        Si el valor no existe en la lista, no hará ningún cambio.
        """
        if etapa:
            self.combos['etapa'].setCurrentText(etapa)
        if suelo:
            self.combos['suelo'].setCurrentText(suelo)
        if riego:
            self.combos['riego'].setCurrentText(riego)

    def aplicar_estilos(self):
        # QSS (Qt Style Sheets) para igualar el diseño de Figma/Web
        self.setStyleSheet("""
            #WidgetPrincipal {
                background-color: #FFFFFF;
                border-radius: 8px;
                border: 1px solid #E2E8F0;
            }
            #Titulo {
                font-size: 16px;
                font-weight: bold;
                color: #2D3748;
                font-family: Arial, sans-serif;
            }
            #Subtitulo {
                font-size: 12px;
                color: #718096;
                font-family: Arial, sans-serif;
            }
            #BtnCerrar {
                background: transparent;
                border: none;
                font-size: 16px;
                color: #A0AEC0;
            }
            #BtnCerrar:hover {
                color: #4A5568;
            }
            #LabelCampo {
                font-size: 10px;
                font-weight: 800;
                color: #A0AEC0;
                font-family: Arial, sans-serif;
                letter-spacing: 0.5px;
            }
            #ComboCampo {
                padding: 10px;
                border: 1px solid #E2E8F0;
                border-radius: 4px;
                background-color: #FFFFFF;
                color: #4A5568;
                font-size: 13px;
                font-weight: 600;
            }
            #ComboCampo::drop-down {
                border: none;
                width: 30px;
            }
            #ComboCampo::down-arrow {
                image: none; /* Aquí puedes poner la ruta a un icono SVG de flecha si lo deseas */
            }
            #ComboCampo:focus {
                border: 1px solid #3182CE;
            }
            #BtnCancelar {
                background-color: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 4px;
                padding: 10px 18px;
                color: #718096;
                font-weight: bold;
                font-size: 13px;
            }
            #BtnCancelar:hover {
                background-color: #F7FAFC;
            }
            #BtnGuardar {
                background-color: #00C853; /* Verde vibrante */
                border: none;
                border-radius: 4px;
                padding: 10px 18px;
                color: white;
                font-weight: bold;
                font-size: 13px;
            }
            #BtnGuardar:hover {
                background-color: #00B248;
            }
        """)

class PanelAnalisisVuelo(QWidget):
    def __init__(self, 
                 on_open_settings,
                 on_open_panels_settings,
                 on_open_edit_field_data,
                 on_open_images_manager):
        super().__init__()
        self.setWindowTitle("AgroHass - Panel Lateral")
        self.setFixedWidth(355)
        self.setStyleSheet(self.obtener_estilos())
        self.on_open_settings = on_open_settings
        self.on_open_panels_settings = on_open_panels_settings
        self.on_open_edit_field_data = on_open_edit_field_data
        self.on_open_images_manager = on_open_images_manager

        layout_base = QVBoxLayout(self)
        layout_base.setContentsMargins(0, 0, 0, 0)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        
        contenedor_scroll = QWidget()
        self.layout_principal = QVBoxLayout(contenedor_scroll)
        self.layout_principal.setContentsMargins(0, 0, 0, 0)
        self.layout_principal.setSpacing(0)

        self.crear_seccion_detalles()
        self.crear_seccion_informacion()
        self.crear_seccion_resumen()
        self.crear_seccion_configuracion()
        self.crear_seccion_calibracion()

        self.layout_principal.addStretch() 
        scroll_area.setWidget(contenedor_scroll)
        layout_base.addWidget(scroll_area)

    def actualizar_detalles(self, identificador, camara, fecha, altura, gsd):
        self.lbl_id_valor.setText(identificador)
        self.lbl_camara_valor.setText(camara)
        self.lbl_fecha_valor.setText(fecha)
        # Formatear números para que se vean bien
        self.lbl_altura_valor.setText(f"{float(altura):.2f} m")
        self.lbl_gds_valor.setText(f"{float(gsd):.2f} cm/px")

    def actualizar_informacion(self, etapa, suelo, riego):
        print("Antes que se cierre:")
        # Actualizamos buscando en el diccionario que creamos
        print("self.labels_info:", self.labels_info)
        if "Etapa Fenológica" in self.labels_info:
            self.labels_info["Etapa Fenológica"].setText(etapa)
        if "Tipo de Suelo" in self.labels_info:
            self.labels_info["Tipo de Suelo"].setText(suelo)
        if "Tipo de Riego" in self.labels_info:
            self.labels_info["Tipo de Riego"].setText(riego)

    def actualizar_resumen(self, cantidad_capturas):
        # Formato con separador de miles (ej. 1,248)
        self.lbl_numero.setText(f"{cantidad_capturas:,}")

    def actualizar_configuracion(self, resolucion, umbral, stage):
        self.lbl_res_val.setText(resolucion)
        self.lbl_umbral_val.setText(str(umbral))
        self.lbl_umbral.setText(f"Umbral Def. Nitrógeno ({stage})")

    def crear_seccion_detalles(self):
        seccion = SeccionPanel("DETALLES DE ANÁLISIS DE PARCELA")
        grid = QGridLayout()
        grid.setSpacing(10)

        lbl_id_titulo = QLabel("IDENTIFICADOR")
        lbl_id_titulo.setObjectName("SubtituloGris")
        self.lbl_id_valor = QLabel("prueba-biochumbi-120")
        self.lbl_id_valor.setObjectName("TextoNegrita")
        
        lbl_camara_titulo = QLabel("CÁMARA")
        lbl_camara_titulo.setObjectName("SubtituloGris")
        self.lbl_camara_valor = QLabel("DJI Mavic 3M")
        self.lbl_camara_valor.setObjectName("NormalText")
        
        lbl_fecha_titulo = QLabel("FECHA VUELO")
        lbl_fecha_titulo.setObjectName("SubtituloGris")
        self.lbl_fecha_valor = QLabel("24/10/2023")
        self.lbl_fecha_valor.setObjectName("NormalText")

        lbl_altura_titulo = QLabel("ALTURA DE VUELO")
        lbl_altura_titulo.setObjectName("SubtituloGris")
        self.lbl_altura_valor = QLabel("15.00 m")
        self.lbl_altura_valor.setObjectName("NormalText")

        lbl_gds_titulo = QLabel("GSD PROMEDIO")
        lbl_gds_titulo.setObjectName("SubtituloGris")
        self.lbl_gds_valor = QLabel("0.82 cm/px")
        self.lbl_gds_valor.setObjectName("NormalText")

        grid.addWidget(lbl_id_titulo, 0, 0, 1, 2)
        grid.addWidget(self.lbl_id_valor, 1, 0, 1, 2)
        grid.addWidget(lbl_camara_titulo, 2, 0)
        grid.addWidget(self.lbl_camara_valor, 3, 0)
        grid.addWidget(lbl_fecha_titulo, 2, 1)
        grid.addWidget(self.lbl_fecha_valor, 3, 1)
        grid.addWidget(lbl_altura_titulo, 4, 0)
        grid.addWidget(self.lbl_altura_valor, 5, 0)
        grid.addWidget(lbl_gds_titulo, 4, 1)
        grid.addWidget(self.lbl_gds_valor, 5, 1)

        seccion.contenido_layout.addLayout(grid)
        self.layout_principal.addWidget(seccion)

    def on_click_edit_parcel_info(self):
        self.on_open_edit_field_data()

    def crear_seccion_informacion(self):
        seccion = SeccionPanel("INFORMACIÓN DE LA PARCELA", 
                               icono_accion=resource_path("assets/icon_edit.svg"), 
                               on_click_icon=self.on_click_edit_parcel_info)
        grid = QGridLayout()
        
        datos = [
            ("Etapa Fenológica", "Inicio de brote"),
            ("Tipo de Suelo", "Arcilloso"),
            ("Tipo de Riego", "Microaspersión")
        ]
        
        self.labels_info = {}

        for fila, (clave, valor) in enumerate(datos):
            lbl_clave = QLabel(clave)
            lbl_clave.setObjectName("TextoGris")
            lbl_valor = QLabel(valor)
            lbl_valor.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            lbl_valor.setObjectName("TextoNegrita")
            
            self.labels_info[clave] = lbl_valor
            grid.addWidget(lbl_clave, fila, 0)
            grid.addWidget(lbl_valor, fila, 1)


        seccion.contenido_layout.addLayout(grid)
        self.layout_principal.addWidget(seccion)

    def crear_seccion_resumen(self):
        seccion = SeccionPanel("RESUMEN DE IMÁGENES")
        vbox = QVBoxLayout()
        vbox.setSpacing(10)

        caja_contador = QFrame()
        caja_contador.setObjectName("CajaContador")
        caja_layout = QVBoxLayout(caja_contador)
        
        self.lbl_numero = QLabel("1,248")
        self.lbl_numero.setObjectName("NumeroCapturas")
        self.lbl_numero.setAlignment(Qt.AlignCenter)
        
        lbl_texto = QLabel("IMÁGENES")
        lbl_texto.setObjectName("SubtituloGris")
        lbl_texto.setAlignment(Qt.AlignCenter)
        
        caja_layout.addWidget(self.lbl_numero)
        caja_layout.addWidget(lbl_texto)

        btn_gestionar = QPushButton("Gestionar Imágenes")
        btn_gestionar.setIcon(QIcon(resource_path("assets/icon_img.svg")))
        btn_gestionar.setIconSize(QSize(20, 20))
        #btn_gestionar.setFixedSize(32, 32)
        btn_gestionar.setCursor(Qt.PointingHandCursor)
    
        btn_gestionar.setObjectName("BotonAccion")
        
        btn_gestionar.clicked.connect(self.on_open_images_manager)

        vbox.addWidget(caja_contador)
        vbox.addWidget(btn_gestionar)
        seccion.contenido_layout.addLayout(vbox)
        self.layout_principal.addWidget(seccion)

    def crear_seccion_configuracion(self):
        seccion = SeccionPanel("CONFIGURACIÓN DE PROCESAMIENTO", 
                               icono_accion = resource_path("assets/options.svg"),
                               on_click_icon = self.on_open_settings)
        grid = QGridLayout()

        lbl_res = QLabel("Resolución de Salida")
        lbl_res.setObjectName("TextoGris")
        self.lbl_res_val = QLabel("Media (2.52cm/px)")
        self.lbl_res_val.setObjectName("BadgeGris")
        self.lbl_res_val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.lbl_umbral = QLabel("Umbral Def. Nitrógeno (Cuajado)")
        self.lbl_umbral.setObjectName("TextoGris")
        self.lbl_umbral_val = QLabel("2.1")
        self.lbl_umbral_val.setObjectName("NormalText")
        self.lbl_umbral_val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        
        grid.addWidget(lbl_res, 0, 0)
        grid.addWidget(self.lbl_res_val, 0, 1)
        grid.addWidget(self.lbl_umbral, 1, 0)
        grid.addWidget(self.lbl_umbral_val, 1, 1)

        seccion.contenido_layout.addLayout(grid)
        self.layout_principal.addWidget(seccion)

    def crear_seccion_calibracion(self):
        seccion = SeccionPanel("CALIBRACIÓN RADIOMÉTRICA")
        vbox = QVBoxLayout()
        vbox.setSpacing(8)

        self.rb_dls = QRadioButton("DLS (Sensor Solar)")
        self.rb_dls.setObjectName("NormalText")
        self.rb_elc = QRadioButton("ELC (Paneles de Referencia)")
        self.rb_elc.setObjectName("NormalText")
        self.rb_dls.setChecked(True)

        self.btn_configurar = QPushButton("Configurar Paneles")
        self.btn_configurar.setObjectName("BotonVerde")
        self.btn_configurar.clicked.connect(self.open_configure_panels)
        self.btn_configurar.setEnabled(False)

        self.rb_elc.toggled.connect(self.actualizar_estado_boton)

        lbl_info = QLabel("Seleccione el método de calibración para ajustar los valores de reflectancia. El DLS usa incidencia lumínica en tiempo real, mientras que ELC requiere paneles en tierra.")
        lbl_info.setWordWrap(True)
        lbl_info.setObjectName("CajaInfo")

        vbox.addWidget(self.rb_dls)
        vbox.addWidget(self.rb_elc)
        vbox.addWidget(self.btn_configurar)
        vbox.addWidget(lbl_info)

        seccion.contenido_layout.addLayout(vbox)
        self.layout_principal.addWidget(seccion)

    def open_configure_panels(self):

        self.on_open_panels_settings()
        # rad_calibration_panel = RadCalibrationPanel(self)

        # if rad_calibration_panel.exec():
        #     if rad_calibration_panel.validar_completitud():
        #         data = rad_calibration_panel.get_data()
                

        #         config_radiometric_cal = {
        #             "elc": data
        #         }
        #         with open("./config_radiometric_cal.json", "w") as f:
        #             json.dump(config_radiometric_cal, f, indent=4)
        # else:
        #     print("Cancelado")

    def actualizar_estado_boton(self):
        """Verifica cuál RadioButton está activo y bloquea/desbloquea el botón."""
        if self.rb_elc.isChecked():
            self.btn_configurar.setEnabled(True)
            
        else:
            self.btn_configurar.setEnabled(False)

    def obtener_estilos(self):
        return """
            QWidget {
                background-color: #F8F9FA;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 13px;
                color: #333333;
            }
            QScrollArea { border: none; }
            
            /* --- NUEVOS ESTILOS PARA LOS FONDOS --- */
            SeccionPanel {
                background-color: transparent;
                border-bottom: 2px solid #E0E0E0; /* Separación marcada entre paneles */
            }
            #FondoCabecera {
                background-color: #F4F6F8; /* Fondo gris-azulado claro que llega a los bordes */
                border-bottom: 1px solid #EAECEE;
            }
            #FondoContenido {
                background-color: #FFFFFF; /* Contenido puramente blanco */
            }
            /* -------------------------------------- */

            #TituloSeccion {
                font-weight: bold;
                font-size: 13px;
                color: #2C3E50;
            }
            #IconoColapso {
                color: #7F8C8D;
                font-weight: bold;
                font-size: 16px;
            }
            #BotonIconoCabecera {
                background-color: transparent;
                border: none;
                color: #7F8C8D;
                font-size: 14px;
                padding: 0px 5px;
            }
            #BotonIconoCabecera:hover {
                color: #2C3E50;
            }

            #BotonIconoCabecera:hover {
                background-color: #E5E7EB;  /* gris suave */
                border-radius: 6px;
            }
            #BotonIconoCabecera:pressed {
                background-color: #D1D5DB;
            }

            #SubtituloGris {
                color: #7F8C8D;
                font-size: 10px;
                font-weight: bold;
                text-transform: uppercase;
                background-color: transparent;
            }
            #TextoGris { 
                color: #555555; 
                background-color: transparent;
            }
            #TextoNegrita {
                font-weight: bold;
                color: #2C3E50;
                font-size: 14px;
                background-color: transparent;
            }
            #NormalText {
                background-color: transparent;
            }
            #CajaContador {
                background-color: #F4F6F6;
                border: 1px solid #EAECEE;
                border-radius: 4px;
                padding: 10px;
            }
            #NumeroCapturas {
                font-size: 24px;
                font-weight: bold;
                color: #27AE60;
            }
            #BotonAccion {
                background-color: #FFFFFF;
                border: 1px solid #BDC3C7;
                border-radius: 4px;
                padding: 8px;
                font-weight: bold;
                color: #555555;
            }
            #BotonAccion:hover { background-color: #F4F6F6; }
            #BadgeGris {
                background-color: #EAEDED;
                padding: 2px 6px;
                border-radius: 3px;
                font-size: 11px;
                color: #555555;
            }
            QRadioButton { 
                spacing: 8px; 
            }

            /* Estado normal (desmarcado) */
            QRadioButton::indicator { 
                width: 14px; 
                height: 14px; 
                border-radius: 8px; /* Lo hace circular */
                border: 2px solid #BDC3C7; /* Borde gris */
                background-color: #FFFFFF;
            }
            /* Estado seleccionado (marcado) */
            QRadioButton::indicator:checked { 
                border: 2px solid #27AE60; /* Borde exterior verde */
                border-radius: 9px;
                
                /* Dibujamos el punto verde central usando pintura, sin alterar la forma */
                background-color: qradialgradient(
                    cx: 0.5, cy: 0.5, radius: 0.5, fx: 0.5, fy: 0.5,
                    stop: 0.0 #27AE60,   /* Centro verde */
                    stop: 0.4 #27AE60,   /* Límite del punto verde */
                    stop: 0.5 #FFFFFF,   /* Salto abrupto a blanco para el espacio vacío */
                    stop: 1.0 #FFFFFF
                );
            }
         
            #BotonVerde {
                background-color: #FFFFFF;
                border: 1px solid #27AE60;
                color: #27AE60;
                font-weight: bold;
                padding: 6px;
                border-radius: 4px;
                margin-left: 20px;
                margin-right: 20px;
            }
            #BotonVerde:hover { background-color: #EAFAF1; }

            /* ESTO ES LO QUE HACE QUE SE VEA APAGADO CUANDO ELIGES DLS */
            #BotonVerde:disabled {
                background-color: #F8F9FA;
                border: 1px solid #EAECEE;
                color: #BDC3C7;
            }
            
            #CajaInfo {
                background-color: #F8F9FA;
                border: 1px solid #EAECEE;
                border-radius: 4px;
                padding: 10px;
                color: #7F8C8D;
                font-size: 11px;
                margin-top: 10px;
            }
        """
    
class MapCaptures(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window=main_window
        self.init_ui()
        self.setup_variables()

    def init_ui(self):
        layout = QVBoxLayout()

        #self.create_map()

        # Crear QWebEngineView
        self.web_view = QWebEngineView()
        self.web_view.setStyleSheet("margin: 0; padding: 0; border: none;")
        self.web_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        #self.web_view.setStyleSheet("background-color: #000000;")
        
        self.right_panel = PanelAnalisisVuelo(
            on_open_settings = self.open_settings,
            on_open_panels_settings= self.open_panels_settings,
            on_open_edit_field_data= self.open_edit_field_data,
            on_open_images_manager = self.on_open_images_manager
        )
        details_web_layout = QHBoxLayout()
        details_web_layout.setSpacing(0)
        details_web_layout.addWidget(self.web_view)

        self.right_panel.rb_elc.toggled.connect(self.enabled_precessing)
        
        details_web_layout.setAlignment(Qt.AlignTop)
        details_web_layout.addWidget(self.right_panel)
        details_web_layout.setStretch(0, 10)  # El mapa ocupa mucho más
        details_web_layout.setStretch(1, 2)   # Detalles ocupan menos
        self.images_data = {}

        self.update_map_view(images_data = self.images_data)

        # Sección inferior con barra de progreso y botón

        processing_info_layout = QVBoxLayout()
        processing_button_layout = QHBoxLayout()
        
        processing_info_layout.setSpacing(0)
        processing_info_layout.setAlignment(Qt.AlignTop)
        
        processing_name_layout = QHBoxLayout()

        processing_label = QLabel("Procesamiento")
        processing_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        
        processing_name_layout.addWidget(processing_label)

        # settings_button = QPushButton()
        # settings_button.setIcon(QIcon(resource_path("assets/options.svg")))  # ⚙️
        # settings_button.setIconSize(QSize(20, 20))
        # settings_button.setFixedSize(32, 32)
        # settings_button.setCursor(Qt.PointingHandCursor)
        
        
        # settings_button.clicked.connect(self.open_settings)

        # settings_button.setStyleSheet("""
        #     QPushButton {
        #         border: none;
        #         background-color: transparent;
        #     }
        #     QPushButton:hover {
        #         background-color: #E5E7EB;  /* gris suave */
        #         border-radius: 6px;
        #     }
        #     QPushButton:pressed {
        #         background-color: #D1D5DB;
        #     }
        # """)
        
        #processing_name_layout.addWidget(settings_button)

        processing_info_layout.addLayout(processing_name_layout)

        self.status_procesing = QLabel("Estado del procesameinto de imagenes")
        self.status_procesing.setStyleSheet("font-size: 14px; padding-top: 5px; padding-bottom: 5px; color: #5F5F60;")
        processing_info_layout.addWidget(self.status_procesing)

        self.progress_bar = RoundedProgressBar()
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #E5E8EB;
                border-radius: 4px; /* Igual que el padre */
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #76e900;
                border-radius: 4px; /* Igual que el padre */
                width: 10px;
                margin: 0px;
            }
        """)
        
        self.progress_bar.setMinimumWidth(400)
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(14)
        self.progress_bar.setTextVisible(False)

        self.start_button = QPushButton("  Iniciar Procesamiento")
        self.start_button.setIcon(QIcon(resource_path(os.path.join("assets", "play.svg"))))
        self.start_button.setIconSize(QSize(14, 14))
        self.start_button.setStyleSheet("""
            QPushButton {
                background-color: #07C553;
                color: white;
                border-radius: 10px;
                padding-left: 20px;
                padding-right: 20px;
                padding-top: 6px;
                padding-bottom: 6px;
                font-size: 13px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #05A848 ;
                border-color: #05A848 ;
            }
            QPushButton:pressed {
                background-color: #1f4f39;
            }
                                        
            /* NUEVO: Estado deshabilitado */
            QPushButton:disabled {
                background-color: #cccccc; /* Fondo gris */
                color: #888888;          /* Texto en gris más oscuro */
            }
        """)
        self.start_button.setMaximumWidth(240)
        self.start_button.clicked.connect(self.start_progress)

        self.percentage_label = QLabel("45% Completado")
        self.percentage_label.setStyleSheet("font-size: 14px;  padding-top: 0px; color: #5F5F60;")
        self.percentage_label.setAlignment(Qt.AlignRight)
        
        progress_layout = QHBoxLayout()

        progress_layout.addWidget(self.progress_bar)
        progress_layout.addWidget(self.start_button)
        
        progress_layout.setContentsMargins(0, 0, 0, 10)  # left, top, right, bottom
        
        processing_info_layout.setAlignment(Qt.AlignLeft)
        #self.start_button.setAlignment(Qt.AlignRight)
        processing_button_layout.addLayout(processing_info_layout)
        processing_button_layout.addWidget(self.start_button)
        #processing_info_layout.addLayout(progress_layout)
        processing_main_layout = QVBoxLayout()
        processing_main_layout.setContentsMargins(10, 10, 10, 10)
        processing_main_layout.addLayout(processing_button_layout)
        processing_main_layout.addWidget(self.progress_bar)
        processing_main_layout.addWidget(self.percentage_label)
        
        processing_main_widget = QWidget()
        processing_main_widget.setLayout(processing_main_layout)
        processing_main_widget.setMaximumHeight(120)  # Parte inferior fija
        layout.addLayout(details_web_layout)
        layout.addWidget(processing_main_widget)
        #layout.addWidget(self.progress_bar)
        #layout.addWidget(percentage_label)

        layout.setStretchFactor(details_web_layout, 10)
        layout.setStretchFactor(processing_main_widget, 0)

        self.setLayout(layout)
        # Generar detalles iniciales
        #self.update_details_analysis()
    
    def on_open_images_manager(self):
        analysis_data_store = self.main_window.analysis_data_store
        base_dir = analysis_data_store.base_dir
        identifier_id = analysis_data_store.identifier_id
        images_data = analysis_data_store.images_data
        images_files =[im_data["relative_path"] for im_data in images_data.values()] 
        dialog = ImageManagerDialog(images_files=images_files)
        if dialog.exec():
            images_data_updated, flight_info = dialog.get_data()
            analysis_data_store.set_images_data(images_data_updated)
            analysis_data_store.set_gsd_avg(flight_info["avg_gsd"])
            analysis_data_store.set_alt_avg(flight_info["avg_alt"])

            self.update_details_analysis()

            self.main_window.page_map_images.update_map_view(analysis_data_store.images_data)
            if identifier_id is not None:
                self.main_content.page_home.appdata_manager.update_project_info(identifier_id, 
                                                                                num_images = len(images_data_updated))
            
            ## Update Config
            path_config = f"{base_dir}/config.json"

            with open(path_config, "r") as f:
                config = json.load(f) 

            config["project_info"]["num_images"] = len(images_data_updated)
            config["image_metatada"] = images_data_updated
            #self.main_content.update_analysis_data(dialog.new_analysis_data_store)
            #base_dir = dialog.new_analysis_data_store.base_dir
            #images_data = dialog.new_analysis_data_store.images_data
            #name = dialog.new_analysis_data_store.name
            
            #project_info = {
            #        "name": name,
            #        "creation_date": datetime.now().isoformat(),
            #        "num_images": len(images_data),
            #        "base_dir": base_dir
            #    }
            
            #config = {
            #        "project_info": project_info,
            #        "image_metatada": images_data
            #    }

            #self.main_content.page_home.save_configure_analysis(base_dir, config)

            #self.main_content.page_home.appdata_manager.add_new_project(project_info)

            with open(path_config, "w") as f:
                json.dump(config, f, indent=4)    

            
    
    def open_edit_field_data(self):
        dialog_edit_parcel = DialogoEditarParcela()

        analysis_data_store = self.main_window.analysis_data_store
        
        field_info = analysis_data_store.field_info
        stage = field_info.get("stage") or "Seleccionar"
        soil_type = field_info.get("soil_type", "-")  or "Seleccionar"
        irrigation_type = field_info.get("irrigation_type", "-")  or "Seleccionar"        

        dialog_edit_parcel.actualizar_valores(
            etapa=stage,
            suelo=soil_type,
            riego=irrigation_type
        )

        if dialog_edit_parcel.exec():
            data_field = dialog_edit_parcel.get_data()
            print("data_field:", data_field)

            print("data_field[stage]:", data_field["stage"])
            analysis_data_store.update_field_info(stage = data_field["stage"], 
                                                  soil_type = data_field["soil"], 
                                                  irrigation_type = data_field["irrigation"])
            
            ## Update Config Field

            base_dir = analysis_data_store.base_dir
            path_config = f"{base_dir}/config.json"
            
            data_config = None
            with open(path_config, "r") as fp:
                data_config = json.load(fp)

            if data_config:
                data_config["field_information"]["stage"] = data_field["stage"]
                data_config["field_information"]["soil_type"] = data_field["soil"]
                data_config["field_information"]["irrigation_type"] = data_field["irrigation"]

                with open(path_config, "w") as fp:
                    json.dump(data_config, fp, indent = 4)

        
            self.update_details_analysis()

            self.update_trees_class(analysis_data_store.thresh_stages)
            
            path_mosaic_base = f"{base_dir}/mosaic/rgb/mosaic_base.png"
            mosaic_base = cv2.imread(path_mosaic_base, cv2.IMREAD_UNCHANGED)
            create_map_trees_ids(mosaic_image = mosaic_base, base_dir = base_dir)
            create_map_trees_ids_zinc(mosaic_image = mosaic_base, base_dir = base_dir)
            
            self.right_panel.update()
            self.update()

    def enabled_precessing(self):
        base_dir = self.main_window.analysis_data_store.base_dir
        path_config_cal = f"{base_dir}/config_radiometric_cal.json"
        if self.right_panel.rb_elc.isChecked():
            if os.path.exists(path_config_cal):
                with open(path_config_cal, "r") as fp:
                    data_conf = json.load(fp)
                    if data_conf["elc_data"]["bands"] is not None:
                        self.start_button.setEnabled(True)
                    else:
                        self.start_button.setEnabled(False)
            else:
                self.start_button.setEnabled(False)
        else:
            self.start_button.setEnabled(True)

    def open_panels_settings(self):
        rad_calibration_panel = RadCalibrationPanel()
        base_dir = self.main_window.analysis_data_store.base_dir
        path_config_cal = f"{base_dir}/config_radiometric_cal.json"
        config_radiometric_cal = {
                        "options" : ["DLS", "ELC"],
                        "option_choiced": 0,
                        "elc_data": { "bands": None } 
                    }
        
        if os.path.exists(path_config_cal):
            bands_data = None
            with open(path_config_cal, "r") as f:
                config_radiometric_cal = json.load(f)
                bands_data = config_radiometric_cal["elc_data"]["bands"]

            rad_calibration_panel.restore_images_and_rois(bands_data)

        if rad_calibration_panel.exec():
            if rad_calibration_panel.validar_completitud():
                data = rad_calibration_panel.get_data()
                config_radiometric_cal["option_choiced"] = 1
                config_radiometric_cal["elc_data"]["bands"]= data
        
                with open(f"{base_dir}/config_radiometric_cal.json", "w") as f:
                    json.dump(config_radiometric_cal, f, indent=4)
                
                self.enabled_precessing()
        else:
            print("Cancelado")

    def load_local_process_config(self, path_dir):
        path = f"{path_dir}/processing_config.json"
        print("load_local_process_config path:", path)
        if not os.path.exists(path):
            return None
        
        with open(path, "r") as f:
            config = json.load(f)
            return config
        
    def open_settings(self):
        dialog = ProcessingConfigDialog(self)
        analysis_data_store = self.main_window.analysis_data_store
        base_dir = analysis_data_store.base_dir
        processing_config = self.load_local_process_config(base_dir)

        if processing_config:
            dialog.update_thesh_values(processing_config["tresh_stages"])
            dialog.update_res_label(processing_config["target_resolution_option"])

        if dialog.exec():
            processing_config = dialog.get_data()
            analysis_data_store = self.main_window.analysis_data_store
            analysis_data_store.set_target_resolution(processing_config["target_resolution_option"])
            analysis_data_store.set_thresh_stages(processing_config["tresh_stages"])
           

            with open(f"{base_dir}/processing_config.json", 'w') as f:
                json.dump(processing_config, f, indent=4)
            
            self.update_details_analysis()
            self.update_trees_class(processing_config["tresh_stages"])

            path_mosaic_base = f"{base_dir}/mosaic/rgb/mosaic_base.png"
            mosaic_base = cv2.imread(path_mosaic_base, cv2.IMREAD_UNCHANGED)
            create_map_trees_ids(mosaic_image = mosaic_base, base_dir = base_dir)
            create_map_trees_ids_zinc(mosaic_image = mosaic_base, base_dir = base_dir)

            #mosaic_path = f"{base_dir}/mosaic/rgb/tiles"
            self.main_window.page_map_trees.update_mosaic_view(base_dir)


    def update_trees_class(self, tresh_stages):
        base_dir = self.main_window.analysis_data_store.base_dir
        results_trees_path = f"{base_dir}/mosaic/trees/trees_results.json"
        stage = self.main_window.analysis_data_store.field_info["stage"]
        
        if os.path.exists(results_trees_path):
            print("Actuliazand clasificacion de arboles")
            results = []
            with open(results_trees_path, "r") as fp:
                results = json.load(fp)

            if 0 < len(results):
                for r in results:
                    if "nitrogen_pred" in r:
                        diagnosis_class = get_class_def_nitrogen(tresh_stages, r["nitrogen_pred"], 
                                                              stage, uncertanty = UNCERTANTY_VALUE)
                        N_class = diagnosis_class
                        if diagnosis_class == "posible-deficiencia":
                            N_class = "precaución"

                        r["N_class"] = N_class
                        r["model_class_N"]  = diagnosis_class

            with open(results_trees_path, "w") as fp:
                json.dump(results, fp, indent=4)
            self.main_window.page_map_trees.right_panel.update_view(base_dir)
            print("Actualizar Mosaico...")
            self.main_window.page_map_trees.update_mosaic_view(base_dir)

    def update_details_analysis(self):
        # datos actuales
        analysis_data_store = self.main_window.analysis_data_store
        name = analysis_data_store.name
        images_data = analysis_data_store.images_data

        num_images = len(images_data or [])
        avg_alt = analysis_data_store.alt_avg
        avg_gsd = analysis_data_store.gsd_avg
        avg_gsd = avg_gsd * 100 # cm / pix
        adquisition_date = analysis_data_store.adquisition_date or ""
        print("update_details_analysis adquisition_date:", adquisition_date)
        self.right_panel.actualizar_detalles(
            identificador = name,
            camara = "DJI Mavic 3M",
            altura = avg_alt,
            gsd = avg_gsd,
            fecha = adquisition_date
        )


        field_info = analysis_data_store.field_info
        print("field_info:", field_info)
        stage = field_info.get("stage") or "-"
        print("stage:", stage)
        soil_type = field_info.get("soil_type", "-")  or "-"
        print("soil_type:", soil_type)
        irrigation_type = field_info.get("irrigation_type", "-")  or "-"
        print("irrigation_type:", irrigation_type)
        
        self.right_panel.actualizar_informacion(
            etapa=stage,
            suelo = soil_type,
            riego = irrigation_type
        )

        self.right_panel.actualizar_resumen(
            cantidad_capturas = num_images
        )

        processing_config = analysis_data_store.processing_config
        options = ["Baja", "Media", "Alta"]
        
        option_resolution = processing_config["option_resolution"]
        target_resolution = processing_config["target_resolution"] * 100
        target_resolution = round(target_resolution, 2)

        self.right_panel.actualizar_configuracion(
            resolucion = f"{options[option_resolution]} ({target_resolution}cm/px)",
            umbral = processing_config["threshold_nitrogen"],
            stage = stage
        )


    def showEvent(self, event):
        """Cada vez que se muestre el widget, actualizamos los detalles"""
        super().showEvent(event)
        self.update_details_analysis()
        #self.update_details()

    def create_map(self, images_data):
        """Crea un nuevo mapa y actualiza los datos"""
        if len(images_data) > 0:
            lat = images_data[0]['latitude']
            lon = images_data[0]['longitude']
        else:
            lat = -13.6723252222222
            lon = -72.9468904444444

        
        self.m = folium.Map(
            location=[lat, lon], 
            zoom_start=19,
            max_zoom=22,
            tiles= None,
            width='100%',  # <-- Añadir para forzar el ancho total
            height='100%'  # <-- Añadir para forzar el alto tota 
            #"https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
            #attr="Tiles © Esri"
        )
        

        folium.TileLayer(
            tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
            attr="Tiles © Esri",
            max_zoom=22,
            max_native_zoom=17  # 🔥 clave
        ).add_to(self.m)
        
        
        self.update_data(images_data)

    def show_cancel(self):
        self.start_button.clicked.disconnect()
        self.start_button.setText("  Cancelar Procesamiento")
        self.start_button.setIcon(QIcon(resource_path(os.path.join("assets", "cancel.svg"))))
        self.start_button.setStyleSheet("""
            QPushButton {
                background-color: #E53935;
                color: white;
                border-radius: 10px;
                padding-left: 20px;
                padding-right: 20px;
                padding-top: 6px;
                padding-bottom: 6px;
                font-size: 13px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #C62828 ;
                border-color: #05A848 ;
            }
        """)
        self.start_button.clicked.connect(self.cancel_processing)

    Slot()
    def proccessing_cancelled(self):
        self.progress_bar.setValue(0)
        self.percentage_label.setText(f"0% Completado")
        self.restaurar_boton()
        self.cleanup_processing()
        QApplication.processEvents()
    
    def cancel_processing(self):
        print(" \nCancelar")
        if self.processor:  # detener procesamiento
            self.processor.stop()
        
        #self.cleanup_processing()
        #self.progress_bar.setValue(0)
        #self.percentage_label.setText(f"0% Completado")
        #self.restaurar_boton()
        #QApplication.processEvents()

    def restaurar_boton(self):
        """Vuelve a poner el botón en su estado inicial."""
        self.start_button.clicked.disconnect()
        self.start_button.setText("  Iniciar Procesamiento")
        self.start_button.setIcon(QIcon(resource_path(os.path.join("assets", "play.svg"))))
        self.start_button.setStyleSheet("""
            QPushButton {
                background-color: #07C553;
                color: white;
                border-radius: 10px;
                padding-left: 20px;
                padding-right: 20px;
                padding-top: 6px;
                padding-bottom: 6px;
                font-size: 13px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #05A848 ;
                border-color: #05A848 ;
            }
            QPushButton:pressed {
                background-color: #1f4f39;
            }
        """)
        self.start_button.clicked.connect(self.start_progress)

    def update_data(self, images_data):
        """Actualiza los puntos en el mapa a partir del CSV"""
        if images_data == None or len(images_data) == 0:
            return
        
        rgb_images_data = [d for d in images_data.values() if ".jpg" in d["name"].lower() ]

        for metadata in rgb_images_data:
            lat, lon, name = metadata["latitude"], metadata["longitude"], metadata["name"]
            folium.CircleMarker(
                location=[lat, lon],  
                radius=4.0, 
                color='red', 
                fill=True, 
                fill_color='red', 
                fill_opacity=1,
                tooltip=name[:-4]
            ).add_to(self.m)

        #for lat, lon, name in zip(df["latitude"], df["longitude"], df["basename"]):
        #    folium.CircleMarker(
        #        location=[lat, lon],  
        #        radius=6, 
        #        color='red', 
        #        fill=True, 
        #        fill_color='red', 
        #        fill_opacity=1,
        #        tooltip=name
        #    ).add_to(self.m)

    def update_map_view(self, images_data):
        self.images_data = images_data
        self.create_map(images_data)

        html_page = self.m.get_root().render()
        
        # Inyecta el HTML limpio en el QWebEngineView
        self.web_view.setHtml(html_page)

        # """Genera el HTML actualizado del mapa y lo muestra en la vista"""
        # html_map = self.m._repr_html_()
        # html_page = f"""
        # <!DOCTYPE html>
        # <html>
        # <head>
        #     <meta charset="utf-8">
        #     <meta name="viewport" content="width=device-width, initial-scale=1">
        #     <script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/leaflet.js"></script>
        #     <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/leaflet.css"/>
        #     <style>
        #         html, body {{
        #             margin: 0;
        #             padding: 0;
        #             height: 100%;
        #         }}
        #         #map {{
        #             height: 100%;
        #             width: 100%;
        #         }}  
        #     </style>
        # </head>
        # <body>
        #     {html_map}
        # </body>
        # </html>
        # """
        # self.web_view.setHtml(html_page)
    
    def set_view(self, path_base, folder_name):
        self.update_map_view(f"{path_base}/{folder_name}/image_metada.csv")

    def start_progress(self):
        
        self.show_cancel()
        self.images_data = self.main_window.analysis_data_store.images_data
        self.setup_processing_thread()
            
    def setup_variables(self):
        self.processor_thread = None
        self.processor = None
        self.image_data = {}

    def setup_processing_thread(self):
        self.processor_thread = QThread()
        result_dir = self.main_window.analysis_data_store.base_dir
        name = self.main_window.analysis_data_store.name
        processing_config = self.main_window.analysis_data_store.processing_config
        field_info = self.main_window.analysis_data_store.field_info
        thresh_stages = self.main_window.analysis_data_store.thresh_stages
        print("result_dir:", result_dir)
        print()

        if self.right_panel.rb_elc.isChecked():
            method_cal = "ELC"
        else:
            method_cal = "DLS"
        
        path_config_calib = f"{result_dir}/config_radiometric_cal.json"
        
        config_radiometric_cal = {
            "options": ["DLS","ELC"],
            "option_choiced": 1,
            "elc_data": { "bands": None}
        }
         ## Actualuza options

        if os.path.exists(path_config_calib):
            with open(path_config_calib, "r") as fp:
                config_radiometric_cal = json.load(fp)
        
        options = config_radiometric_cal["options"]
        option_choiced = options.index(method_cal)
        config_radiometric_cal["option_choiced"] = option_choiced

        with open(path_config_calib, "w") as fp:
             json.dump(config_radiometric_cal, fp, indent=4)
        
        #elc_bands = None
        #method_cal = "DLS"

        # self.thresh_stages
        self.processor = ImageProcessor(
            self.images_data, 
            result_dir,
            name_analysis = name,
            target_resolution = processing_config["target_resolution"],
            thresh_stages = thresh_stages,
            field_stage = field_info["stage"],
            method_cal = method_cal)
        
        self.processor.moveToThread(self.processor_thread)

        self.processor_thread.started.connect(self.processor.process)
        self.processor.progrees_status.connect(self.update_status_process)
        self.processor.progress_updated.connect(self.update_progrees_bar)
        self.processor.cancelled.connect(self.proccessing_cancelled)
        self.processor.finished.connect(self.processing_finished)

        self.processor.finished.connect(self.processor_thread.quit)
        self.processor.finished.connect(self.processor.deleteLater)
        self.processor_thread.finished.connect(self.processor_thread.deleteLater)

        self.processor_thread.start()
    @Slot(str)
    def update_status_process(self, status):
        self.status_procesing.setText(status)
    @Slot(int)
    def update_progrees_bar(self, progress):
        print("update process bar slot:", progress)
        self.progress_bar.setValue(progress)
        self.percentage_label.setText(f"{progress}% Completado")

    @Slot()
    def processing_finished(self):
        self.cleanup_processing()
        
        result_dir = self.main_window.analysis_data_store.base_dir
        

        self.main_window.page_map_trees.layers_ready.emit(result_dir)
        
        self.main_window.enable_nav_item(2)
        
        self.main_window.switch_page(2, True)
        self.restaurar_boton()

    def cleanup_processing(self):
        if self.processor_thread and self.processor_thread.isRunning():
            self.processor_thread.quit()
            self.processor_thread.wait()