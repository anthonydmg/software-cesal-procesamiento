import sys
import os 
from PySide6.QtWidgets import (QApplication, QMainWindow, QPushButton, QProgressBar, QVBoxLayout, QHBoxLayout, QWidget, QLabel)
from PySide6.QtCore import (QRunnable, QThreadPool, QThread, QMutex, QObject, Signal, Slot, QMetaObject, Qt, QTimer)
import pandas as pd
from sahi import AutoDetectionModel
from sahi.utils.cv import read_image
from sahi.utils.file import download_from_url
from sahi.predict import get_prediction, get_sliced_prediction, predict
import numpy as np
import traceback  # asegúrate de tenerlo arriba
import json

class YoloModelSegmentation:
    _instance = None
    
    def __init__(self):
        if YoloModelSegmentation._instance is not None:
            raise Exception("¡Usa YOLOModelHandler.get_instance() en lugar de crear una nueva instancia!")
        self.detection_model = AutoDetectionModel.from_pretrained(
            model_type='yolo11', # or 'yolov8'
            model_path='./yolo11s-seg-finituned.pt',
            confidence_threshold=0.5,
            device="cpu", # or 'cuda:0'
        )

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = YoloModelSegmentation()
        return cls._instance
    
    def predict(self, image_path):
        # Obtiene la instancia singleton (y carga el modelo si es la primera vez)
        print("image_path:", image_path)
        try:
            if not image_path or not os.path.exists(image_path):
                raise FileNotFoundError(f"Ruta inválida o inexistente: {image_path}")
            
            result = get_prediction(image_path, self.detection_model)
            
            
            print("result:", result)
            predictions = dict(bboxes = [], 
                            masks = [], 
                            segmentations = [], 
                            classes = [], 
                            scores = [])
            for object_pred in result.object_prediction_list:
                segmentation = object_pred.mask.segmentation
                if isinstance(segmentation, list) and all(isinstance(v, (int, float)) for v in segmentation):
                    # Lista plana: [x1, y1, x2, y2, ...]
                    segmentation = np.array(segmentation, dtype=np.int32).reshape((-1, 2)).tolist()
                elif isinstance(segmentation, list) and all(isinstance(v, list) for v in segmentation):
                    # Lista de listas: [[x1, y1, x2, y2, ...], [...]]
                    segmentation = [np.array(s, dtype=np.int32).reshape((-1, 2)).tolist() for s in segmentation]
                else:
                    raise ValueError("Formato de segmentación no reconocido")

                bbox =  object_pred.bbox.to_xywh()
                #segmentation = np.array(segmentation, dtype=np.int32).reshape((-1, 2))
                class_name = object_pred.category.name
                score = object_pred.score.value
                mask = object_pred.mask.bool_mask.tolist()
                data_pred = [bbox, 
                            mask, 
                            segmentation, 
                            class_name, 
                            score]
                for key, value in zip(predictions.keys(), data_pred):
                    predictions[key].append(value)
            #print("predictions:", predictions)
            # Realiza la predicción
            
            return predictions
        finally:
            # Limpiar memoria después de la predicción
            import gc
            gc.collect()
    
def yolo_segmentation(image_path):
    model_handler = YoloModelSegmentation.get_instance()
    results = model_handler.predict(image_path)  # Ejemplo simplificado
    return results


class ResultSegmentation:
    def __init__(self):
        self.mutex = QMutex()
        self.segmentations = {}
        self.max_memory_items = 10

    def add_segmentation(self, id_img, img_path, results):
        self.mutex.lock()
        try:
            if len(self.segmentations) >= self.max_memory_items:
                self.save_to_disk()
                self.segmentations.clear()
            self.segmentations[id_img] = dict(img_path = img_path, **results)
        finally:
            self.mutex.unlock()

    def save_to_disk(self):
        if not self.segmentations:
            return
        try:
            # Guardar incrementalmente en archivo
            with open("./segmentations_partial.json", "a") as f:
                json.dump(self.segmentations, f)
                f.write("\n")  # Para separar chunks
        except Exception as e:
            print(f"Error saving partial results: {e}")
    
class SignalProxy(QObject):
    _instance = None
    progress_update = Signal(int, str)
    finished = Signal()
    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = SignalProxy()

        return cls._instance
    
class ImageProcessor(QRunnable):
    def __init__(self, img_id, img_path, results_store):
        super().__init__()
        self.img_path = img_path
        self.results_store = results_store
        self.img_id = img_id

    def run(self):
        try:
            if not self.img_path or not os.path.exists(self.img_path):
                raise FileNotFoundError(f"Ruta inválida o inexistente: {self.img_path}")
            seg_results = yolo_segmentation(self.img_path)
            #print("seg_results:", seg_results)
            #self.results_store.add_segmentation(self.img_id, self.img_path, seg_results)
            SignalProxy.instance().progress_update.emit(1,"Procesando Imagenes")
        except Exception as e:
            print(f"Error procesando {self.img_path}: {str(e)}")
            traceback.print_exc()

class MonitorThread(QThread):
    def __init__(self, pool, total_tasks):
        super().__init__()
        self.pool = pool
        self.total_tasks = total_tasks

    def run(self):
        self.pool.waitForDone()
        SignalProxy.instance().finished.emit()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Procesamiento de Imagenes")
        self.setGeometry(100,100,600,200)
        # Widgets
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0,100)
        
        self.process_label = QLabel("Procesamiento")
        self.process_label.setAlignment(Qt.AlignCenter)

        self.start_button = QPushButton("Iniciar")
        self.start_button.clicked.connect(self.start_processing)

        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_processing)
        # Layout Principal
        layout = QVBoxLayout()
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.process_label)
        layout.addWidget(self.start_button)
        layout.addWidget(self.cancel_button)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)
        self.results_store = ResultSegmentation()
        self.images_data = {}
        self.total_images = 0
        self.processed_count = 0

        SignalProxy.instance().progress_update.connect(self.update_progress)
        SignalProxy.instance().finished.connect(self.processing_finished)

        #layout.addWidget(self.status_label)
    def get_images_data(self):
        df = pd.read_csv("./df_images_metadata.csv")
        return {i: im_data for i, im_data in df[["im_relative_path"]].iloc[0:100].to_dict(orient="index").items() }
    
    def process_batch(self, batch):

        for img_id, img_data in batch:
            task = ImageProcessor(img_id, img_data['im_relative_path'].replace("//","/"), self.results_store)
            self.pool.start(task)
        
        # Esperar a que termine el lote actual
        self.pool.waitForDone()
        
        # Forzar actualización de la interfaz
        QApplication.processEvents()

    def process_next_batch(self):
        start = self.current_batch * self.batch_size
        end = start + self.batch_size
        
        if start >= len(self.image_items):
            self.timer.stop()
            SignalProxy.instance().finished.emit()
            return
        
        batch = self.image_items[start:end]
        self.process_batch(batch)
        self.current_batch += 1

    def start_processing(self):
        self.images_data = self.get_images_data()
        #for im_ids in images_data.keys():
        self.total_images = len(self.images_data)
        self.current_batch = 0
        self.batch_size = 5
        self.image_items = list(self.images_data.items())
        self.progress_bar.setValue(0)
        self.progress_bar.setMaximum(100)
        self.start_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.process_label.setText("Procesando Imagens...")
        self.timer = QTimer()
        self.pool = QThreadPool.globalInstance()
        self.pool.setMaxThreadCount(2)  # Reducir hilos concurrentes
        
        self.timer.timeout.connect(self.process_next_batch)
        self.timer.start(100)  # 100ms entre lotes
        #pool = QThreadPool.globalInstance()
        #pool.setMaxThreadCount(4)

        #for img_id, img_data in self.images_data.items():
        #    task = ImageProcessor(img_id, img_data['im_relative_path'].replace("//","/"), self.results_store)
        #    pool.start(task)
        
        #self.monitor_thread = MonitorThread(pool, self.total_images)
        #self.monitor_thread.start()
    def save_segmentation_data(self):
        self.results_store.segmentations
        with open("./segmentations.json","w") as f:
            json.dump(self.results_store.segmentations, f)

    @Slot(int, str)
    def update_progress(self, increment, message):
        self.processed_count += increment
        progress = int((self.processed_count / self.total_images) * 100)
        self.progress_bar.setValue(progress)
        self.process_label.setText(
            f"Procesando {self.processed_count}/{self.total_images}: {message}"
        )
    @Slot()
    def processing_finished(self):
        self.save_segmentation_data()
        self.start_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.process_label.setText(
            f"¡Completado! {self.processed_count} imágenes procesadas"
        )

    def cancel_processing(self):
        QThreadPool.globalInstance().clear()
        self.cancel_button.setEnabled(False)
        self.start_button.setEnabled(True)
        self.status_label.setText("Procesamiento cancelado")

if __name__ =="__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
