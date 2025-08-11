from PySide6.QtWidgets import QWidget, QApplication, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar, QPushButton
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtCore import QMutex, QThread, QObject, Signal, Slot, QSize
from PySide6.QtGui import QIcon, QPainter, QColor, QBrush
from PySide6.QtCore import Qt
import folium
import os
import json
import traceback
import torch
from sahi import AutoDetectionModel
from sahi.predict import get_prediction
from datetime import datetime
import gc
import numpy as np
from core.processing import generate_mosaic

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
        model = AutoDetectionModel.from_pretrained(
            model_type='yolo11',
            model_path='C:/Users/Anthony/Local/cesal-proyecto/avocado-trees-identication/yolo11s-seg-finituned.pt',
            confidence_threshold=0.5,
            device=self.device,
        )
        
        if hasattr(model, 'model'):
            for param in model.model.parameters():
                param.requires_grad = False
        return model
    
    def predict_with_memory_management(self, image_path: str):
        try:
            if not os.path.exists(image_path):
                raise FileNotFoundError(f"Imagen no encontrada: {image_path}")
            
            self._clean_memory()
            print("image_path:", image_path)
            result = get_prediction(image_path, self.model)
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
    finished = Signal()

    def __init__(self, image_data, result_storage):
        super().__init__()
        self.image_data = image_data
        self.result_storage = result_storage
        self.is_running = True
        self.batch_size = 2
        self.model = MemoryAwareYOLOModel.get_instance()

    def process(self):
        try:
            total = len(self.image_data)
            processed = 0
            batch_results = {}

            for img_id, img_data in self.image_data.items():
                if not self.is_running:
                    break

                img_path = img_data['img_relative_path']
                try:
                    result = self.model.predict_with_memory_management(img_path)
                    if result:
                        # Guardar resultado inmediatamente
                        print("Enviando a agregar resultados")
                        self.result_storage.add_result(img_id, {
                            'image_path': img_path,
                            'results': result,
                            'processed_at': datetime.now().isoformat()
                        })
                        print("Termino de a agregar nuevo resultados")
                        processed += 1
                        progress = int((processed / total) * 100)
                        self.progress_updated.emit(
                            progress 
                        )

                        if processed % self.batch_size == 0:
                            batch_results = {}
                            QThread.msleep(100)
                except Exception as e:
                    print(f"Error en {img_id}: {str(e)}")
            print("Comienza Generacion de Mosaico")
            #generate_mosaic(self.image_data, signal_progress=self.progress_updated)

            final_path = self.result_storage.merge_results()
            self.finished.emit()

        except Exception as e:
            self.error_occurred.emit(f"Error en el procesador: {str(e)}")
            traceback.print_exc()

    def stop(self):
        self.is_running = False
class RoundedProgressBar(QProgressBar):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setTextVisible(False)
        self.setMinimumHeight(14)
        self.radius = 7  # mitad de la altura
        self.bg_color = QColor("#E5E8EB")
        self.chunk_color = QColor("#76e900")

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
        name_label.setStyleSheet("color: #626263; font-size: 14px;")

        if bold_value:
            name_content_label = QLabel(value)
            name_content_label.setStyleSheet("color: #05893A; font-size: 14px;")
        else:
            name_content_label = QLabel(value)
            name_content_label.setStyleSheet("color: #000000; font-size: 14px;")
        
        layout.addWidget(name_label)
        layout.addWidget(name_label)

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

        details_web_layout = QHBoxLayout()

        # Titulo Detalles
        details_content_layout = QVBoxLayout()
        
        details_title = QLabel("Detalles de Analisis")
        details_title.setStyleSheet("color: #05893A; font-size: 14px; background-color: #B9FFD3;")
        details_content_layout.addWidget(details_title)

        name_label = QLabel("Nombre del Análisis")
        name_label.setStyleSheet("color: #626263; font-size: 14px;")

        name_content_label = QLabel("Análisis Ejemplo 1")
        name_content_label.setStyleSheet("color: #000000; font-size: 14px;")

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
        status_procesing = QLabel("Estado del procesameinto de imagenes")
        status_procesing.setStyleSheet("font-size: 14px; padding-top: 5px; padding-bottom: 5px; color: #5F5F60;")
        processing_info_layout.addWidget(status_procesing)

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
        self.start_button.setIcon(QIcon("./assets/play.svg"))
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
        percentage_label = QLabel("45% Completado")
        percentage_label.setStyleSheet("font-size: 14px;  padding-top: 0px; color: #5F5F60;")
        percentage_label.setAlignment(Qt.AlignRight)
        
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
        processing_main_layout.addWidget(percentage_label)


        layout.addWidget(self.web_view)
        layout.addLayout(processing_main_layout)
        #layout.addWidget(self.progress_bar)
        #layout.addWidget(percentage_label)

        layout.setStretchFactor(self.web_view, 9)
        layout.setStretchFactor(processing_info_layout, 1)

        self.setLayout(layout)

    def create_map(self, images_data):
        """Crea un nuevo mapa y actualiza los datos"""
        self.m = folium.Map(
            location=[-13.881719661927868, -73.03486801134967], 
            zoom_start=19,
            max_zoom=22, 
            tiles=f"https://api.mapbox.com/styles/v1/mapbox/satellite-v9/tiles/{{z}}/{{x}}/{{y}}?access_token=pk.eyJ1IjoiYW50aG9ueW1nMSIsImEiOiJjbTNuajBzamwxZXMxMmtweDV3anZkcHRxIn0.1ZlgQwJcn4msckpzTNSSJg",
            attr="Mapbox"
        )
        self.update_data(images_data)

    def show_cancel(self):
        self.start_button.clicked.disconnect()
        self.start_button.setText("  Cancelar Procesamiento")
        self.start_button.setIcon(QIcon("./assets/cancel.svg"))
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
        
    def cancel_processing(self):
        print("Cancelar")
        self.restaurar_boton()

    def restaurar_boton(self):
        """Vuelve a poner el botón en su estado inicial."""
        self.start_button.clicked.disconnect()
        self.start_button.setText("  Iniciar Procesamiento")
        self.start_button.setIcon(QIcon("./assets/play.svg"))
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
        #self.setup_processing_thread()
        for i in range(101):
            self.progress_bar.setValue(i)
            QApplication.processEvents()
            time.sleep(0.05)
            
        #self.main_window.switch_page(2)
        # Simular actualización de datos y regenerar el mapa
    
        #self.update_map_view()
    def setup_variables(self):
        self.processor_thread = None
        self.processor = None
        self.result_storage = ResultStorage(output_dir="segmentacion_results")
        self.image_data = {}

    def setup_processing_thread(self):
        self.processor_thread = QThread()
        self.processor = ImageProcessor(self.images_data, self.result_storage)
        self.processor.moveToThread(self.processor_thread)

        self.processor_thread.started.connect(self.processor.process)
        self.processor.progress_updated.connect(self.update_progrees_bar)
        self.processor.finished.connect(self.processing_finished)

        self.processor.finished.connect(self.processor_thread.quit)
        self.processor.finished.connect(self.processor.deleteLater)
        self.processor_thread.finished.connect(self.processor_thread.deleteLater)

        self.processor_thread.start()

    @Slot(int)
    def update_progrees_bar(self, progress):
        self.progress_bar.setValue(progress)

    @Slot()
    def processing_finished(self):
        self.result_storage.save_remaining()
        self.cleanup_processing()
        self.main_window.switch_page(2)

    def cleanup_processing(self):
        if self.processor_thread and self.processor_thread.isRunning():
            self.processor_thread.quit()
            self.processor_thread.wait()