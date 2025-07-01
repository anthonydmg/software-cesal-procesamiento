from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar, QPushButton
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtCore import QMutex, QThread, QObject, Signal, Slot
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
                        processed += 0.5#1
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
            generate_mosaic(self.image_data, signal_progress=self.progress_updated)

            final_path = self.result_storage.merge_results()
            self.finished.emit()

        except Exception as e:
            self.error_occurred.emit(f"Error en el procesador: {str(e)}")
            traceback.print_exc()

    def stop(self):
        self.is_running = False

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
        self.images_data = {}

        self.update_map_view(images_data = self.images_data)

        # Sección inferior con barra de progreso y botón
        processing_layout = QVBoxLayout()
        progress_layout = QHBoxLayout()

        processing_label = QLabel("Procesamiento")
        processing_label.setStyleSheet("font-size: 18px; font-weight: bold; padding: 0px;")

        self.progress_bar = QProgressBar()
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 2px solid grey;
                border-radius: 5px;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #76e900;
                width: 20px;
            }
        """)
        self.progress_bar.setMinimumWidth(400)
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(20)

        start_button = QPushButton("Iniciar")
        start_button.setStyleSheet("""
            QPushButton {
                background-color: #2d6a4f;
                color: white;
                border: 2px solid #1b4d3e;
                border-radius: 5px;
                padding: 10px 20px;
                font-size: 16px;
            }
            QPushButton:hover {
                background-color: #3a8d72;
                border-color: #2c5e47;
            }
            QPushButton:pressed {
                background-color: #1f4f39;
            }
        """)
        start_button.clicked.connect(self.start_progress)

        progress_layout.addWidget(self.progress_bar)
        progress_layout.addWidget(start_button)

        processing_layout.addWidget(processing_label)
        processing_layout.addLayout(progress_layout)

        layout.addWidget(self.web_view)
        layout.addLayout(processing_layout)

        layout.setStretchFactor(self.web_view, 9)
        layout.setStretchFactor(processing_layout, 1)

        self.setLayout(layout)

    def create_map(self, images_data):
        """Crea un nuevo mapa y actualiza los datos"""
        self.m = folium.Map(
            location=[-13.881719661927868, -73.03486801134967], 
            zoom_start=19,
            max_zoom=22, 
            tiles=f"https://api.mapbox.com/styles/v1/mapbox/satellite-v9/tiles/{{z}}/{{x}}/{{y}}?access_token={MAPBOX_TOKEN}",
            attr="Mapbox"
        )
        self.update_data(images_data)

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