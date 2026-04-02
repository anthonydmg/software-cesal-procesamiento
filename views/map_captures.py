from PySide6.QtWidgets import QWidget, QApplication, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar, QPushButton, QSizePolicy
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtCore import QMutex, QThread, QObject, Signal, Slot, QSize
from PySide6.QtGui import QIcon, QPainter, QColor, QBrush
from PySide6.QtCore import Qt
import folium
import os
import json
import traceback
import torch
from datetime import datetime
import gc
import numpy as np
from core.inference import TreeDetectorYolo
from core.processing import generate_mosaic, ImageSticher
from core.utils import resource_path


MAPBOX_TOKEN = os.getenv("MAPBOX_TOKEN")

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

class MemoryAwareYOLOModel:
    _instance = None
    _mutex = QMutex()
    
    def __init__(self):
        if MemoryAwareYOLOModel._instance is not None:
            raise Exception("Esta clase es un singleton. Usa get_instance()")
        
        self.device = self._select_device()
        print("self.device:", self.device)
        self.model = self._load_model()
        
    @classmethod
    def get_instance(cls):
        cls._mutex.lock()
        try:
            if cls._instance is None:
                cls._instance = MemoryAwareYOLOModel()
            return cls._instance
        finally:
            cls._mutex.unlock()
    
    def _select_device(self):
        if torch.cuda.is_available():
            torch.backends.cudnn.benchmark = True
            return "cuda"
        return "cpu"
    
    def _load_model(self):
        model = None
        #AutoDetectionModel.from_pretrained(
        #    model_type='yolo11',
        #    model_path='C:/Users/Anthony/Local/cesal-proyecto/avocado-trees-identication/yolo11s-seg-finituned.pt',
        #    confidence_threshold=0.5,
        #    device=self.device,
        #)
        
        #if hasattr(model, 'model'):
        #    for param in model.model.parameters():
        #        param.requires_grad = False
        return model
    
    def predict_with_memory_management(self, image_path: str):
        try:
            if not os.path.exists(image_path):
                raise FileNotFoundError(f"Imagen no encontrada: {image_path}")
            
            self._clean_memory()
            print("image_path:", image_path)
            result = None #get_prediction(image_path, self.model)
            print("result:", result)
            predictions = {
                'bboxes': [], 
                #'masks': [], 
                'segmentations': [],
                'classes': [], 
                'scores': [], 
                'timestamp': datetime.now().isoformat()
            }
            
            for obj in result.object_prediction_list:
                seg = self._process_segmentation(obj.mask.segmentation)
                predictions['bboxes'].append(obj.bbox.to_xywh())
                #predictions['masks'].append(obj.mask.bool_mask.tolist())
                predictions['segmentations'].append(seg)
                predictions['classes'].append(obj.category.name)
                predictions['scores'].append(obj.score.value)
            
            return predictions
            
        except Exception as e:
            print(f"Error en predicción: {str(e)}")
            traceback.print_exc()
            return None
        finally:
            self._clean_memory()
    
    def _process_segmentation(self, segmentation):
        if isinstance(segmentation, list):
            if all(isinstance(v, (int, float)) for v in segmentation):
                return np.array(segmentation, dtype=np.int32).reshape((-1, 2)).tolist()
            elif all(isinstance(v, list) for v in segmentation):
                return [np.array(s, dtype=np.int32).reshape((-1, 2)).tolist() for s in segmentation]
        return segmentation
    
    def _clean_memory(self):
        gc.collect()
        if self.device.startswith('cuda'):
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()

class ImageProcessor(QObject):
    progress_updated = Signal(int)  # progress, message, current, total
    progrees_status = Signal(str)
    finished = Signal()
    cancelled = Signal()

    def __init__(self, image_data, result_dir = "./", name_analysis = None):
        super().__init__()
        self.image_data = image_data
        self.is_running = True
        self.batch_size = 2
        self.result_dir = result_dir
        self.images_sticher = None
        self.name_analysis = name_analysis
        #self.model = MemoryAwareYOLOModel.get_instance()

    def trees_detection_process(self, metadata_rgb_files):
        total = len(metadata_rgb_files)
        detector = TreeDetectorYolo.get_instance()
        all_predictions = []
        processed = 0
        
        self.progrees_status.emit("Dectando Arboles...")

        for img_id, img_data in enumerate(metadata_rgb_files):
                if not self.is_running:
                    self.cancelled.emit()
                    break

                img_path = img_data['relative_path']
                try:
                    predictions = detector.predict([img_path], save_dir = f"{self.result_dir}/results")
                    all_predictions.extend(predictions)
                    processed += 1
                    progress = int((processed / total) * 40)
                    self.progress_updated.emit(
                        progress 
                    )

                except Exception as e:
                    print(f"Error en {img_id}: {str(e)}")
            
        assert len(all_predictions) == len(metadata_rgb_files), "El numero de predicciones deber ser igual a la cantidad de imaganes"

    def process(self):
        try:
            self.progrees_status.emit("Inciando Procesamiento...")

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
            
            self.images_sticher = ImageSticher(images_data = all_images_data_metadata, 
                         on_progress_change = lambda progress: self.progress_updated.emit( int((progress / 100) * 60) + 40),
                         on_cancel = lambda: self.cancelled.emit(),
                         result_dir = self.result_dir)
            
            self.progrees_status.emit("Generando Mosiaco...")

            self.images_sticher.run(prefix_name = self.name_analysis)

            if self.is_running:
                self.progrees_status.emit("Procesamiento Terminado")
                self.finished.emit()

        except Exception as e:
            print("e:", e)
            traceback.print_exc()

    def stop(self):
        self.is_running = False
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

        self.setLayout(layout)


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
        
        details_web_layout = QHBoxLayout()
        details_web_layout.setSpacing(0)
        details_web_layout.addWidget(self.web_view)

        
        # Titulo Detalles
        details_content_widget = QWidget()
        self.details_content_layout = QVBoxLayout()
        self.details_content_layout.setContentsMargins(0, 0, 0, 0)  # Quita márgenes internos
        details_content_widget.setLayout(self.details_content_layout)
        details_content_widget.setStyleSheet("background-color: #ffffff; padding: 0px;")
        details_content_widget.setMaximumWidth(240)
        #details_content_widget.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)  # Evita que crezca más de lo necesario

        #details_title = QLabel("Detalles de Analisis")
        #details_title.setStyleSheet("color: #05893A; padding-right: 10px; padding-left: 10px; padding-top: 5px; padding-bottom: 5px; font-size: 12px; font-weight: bold; background-color: #B9FFD3;")
        #details_title.setAlignment(Qt.AlignCenter)
        #details_content_layout.addWidget(details_title)
        
        #name = self.main_window.analysis_data_store.name

        #if name is None:
        #    name =  "Análisis Ejemplo 1"

        #items_detalis = [("Nombre del Análisis", name, True), 
        #                 ("Cantidad de Imágenes", "331", False),
        #                 ("Modelo de Cámara", "M3M", False),
        #                ("GSD promedio", "0.5 cm/px", False),
        #                 ("Altura Promedio", "14.92 m", False)]
        
        #for item in items_detalis:
        #    items_det = ItemDetails(*item)
        #    details_content_layout.addWidget(items_det)

        self.details_content_layout.setAlignment(Qt.AlignTop)
        details_web_layout.setAlignment(Qt.AlignTop)
        details_web_layout.addWidget(details_content_widget)
        details_web_layout.setStretch(0, 10)  # El mapa ocupa mucho más
        details_web_layout.setStretch(1, 2)   # Detalles ocupan menos
        self.images_data = {}

        self.update_map_view(images_data = self.images_data)

        # Sección inferior con barra de progreso y botón

        processing_info_layout = QVBoxLayout()
        processing_button_layout = QHBoxLayout()
        

        progress_layout = QHBoxLayout()

        processing_info_layout.setSpacing(0)
        processing_info_layout.setAlignment(Qt.AlignTop)
        processing_label = QLabel("Procesamiento")
        processing_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        processing_info_layout.addWidget(processing_label)
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
        """)
        self.start_button.setMaximumWidth(240)
        self.start_button.clicked.connect(self.start_progress)

        self.percentage_label = QLabel("45% Completado")
        self.percentage_label.setStyleSheet("font-size: 14px;  padding-top: 0px; color: #5F5F60;")
        self.percentage_label.setAlignment(Qt.AlignRight)
        
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
        layout.setStretchFactor(processing_main_layout, 0)

        self.setLayout(layout)
        # Generar detalles iniciales
        self.update_details()

    def update_details(self):
        """Regenera dinámicamente los detalles de análisis"""
        # limpiar layout
        while self.details_content_layout.count():
            child = self.details_content_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        # título
        details_title = QLabel("Detalles de Análisis")
        details_title.setStyleSheet(
            "color: #05893A; padding: 5px; font-size: 12px; font-weight: bold; background-color: #B9FFD3;"
        )
        details_title.setAlignment(Qt.AlignCenter)
        self.details_content_layout.addWidget(details_title)

        # datos actuales
        analysis_data_store = self.main_window.analysis_data_store
        name = analysis_data_store.name
        if name is None:
            name = "Análisis Ejemplo 1"
        
        num_images = 303
        avg_alt = 14.925
        avg_gsd = 0.353

        print("Actualizando details....")
        if analysis_data_store.images_data:
            images_data = analysis_data_store.images_data
            num_images = len(images_data)
            alts = [im_data['relative_altitude'] for im_data in images_data.values()]
            avg_alt = sum(alts) / num_images
            print("avg_alt:", avg_alt)

            gsds = [im_data['gsd_horizontal'] * 100 for im_data in images_data.values()]
            avg_gsd = sum(gsds) / num_images
           

        items_detalis = [
            ("Nombre del Análisis", name, True),
            ("Cantidad de Imágenes", str(num_images), False),
            ("Modelo de Cámara", "M3M", False),
            ("GSD promedio", f"{avg_gsd:.2f} cm/px", False),
            ("Altura Promedio", f"{avg_alt:.2f} m", False),
        ]

        for item in items_detalis:
            items_det = ItemDetails(*item)
            self.details_content_layout.addWidget(items_det)

        self.details_content_layout.setAlignment(Qt.AlignTop)

    def showEvent(self, event):
        """Cada vez que se muestre el widget, actualizamos los detalles"""
        super().showEvent(event)
        self.update_details()

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
            tiles= None #"https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
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
        
        for id, metadata in images_data.items():
            lat, lon, name = metadata["latitude"], metadata["longitude"], metadata["name"]
            folium.CircleMarker(
                location=[lat, lon],  
                radius=5, 
                color='red', 
                fill=True, 
                fill_color='red', 
                fill_opacity=1,
                tooltip=name
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

        """Genera el HTML actualizado del mapa y lo muestra en la vista"""
        html_map = self.m._repr_html_()
        html_page = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/leaflet.js"></script>
            <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/leaflet.css"/>
            <style>
                html, body {{
                    margin: 0;
                    padding: 0;
                    height: 100%;
                }}
                #map {{
                    height: 100%;
                    width: 100%;
                }}  
            </style>
        </head>
        <body>
            {html_map}
        </body>
        </html>
        """
        self.web_view.setHtml(html_page)
    
    def set_view(self, path_base, folder_name):
        self.update_map_view(f"{path_base}/{folder_name}/image_metada.csv")

    def start_progress(self):
        self.show_cancel()
        import time
        """Simula el progreso y actualiza el mapa al finalizar"""
        self.images_data = self.main_window.analysis_data_store.images_data
        self.setup_processing_thread()
        #for i in range(101):
        #    self.progress_bar.setValue(i)
        #    QApplication.processEvents()
        #    time.sleep(0.05)
            
        #self.main_window.switch_page(2)
        # Simular actualización de datos y regenerar el mapa
    
        #self.update_map_view()
    def setup_variables(self):
        self.processor_thread = None
        self.processor = None
        #self.result_storage = ResultStorage(output_dir="segmentacion_results")
        self.image_data = {}

    def setup_processing_thread(self):
        self.processor_thread = QThread()
        result_dir = self.main_window.analysis_data_store.base_dir
        name = self.main_window.analysis_data_store.name
        print("result_dir:", result_dir)
        print()
        self.processor = ImageProcessor(
            self.images_data, 
            result_dir,
            name_analysis = name)
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
        
        self.main_window.switch_page(2, True)
        self.restaurar_boton()

    def cleanup_processing(self):
        if self.processor_thread and self.processor_thread.isRunning():
            self.processor_thread.quit()
            self.processor_thread.wait()