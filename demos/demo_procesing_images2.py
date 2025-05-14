import sys
import os
import gc
import json
import traceback
import pandas as pd
import numpy as np
from PySide6.QtWidgets import (QApplication, QMainWindow, QPushButton, QProgressBar, 
                             QVBoxLayout, QHBoxLayout, QWidget, QLabel)
from PySide6.QtCore import (QRunnable, QThreadPool, QThread, QMutex, QObject, 
                           Signal, Slot, QMetaObject, Qt)
from sahi import AutoDetectionModel
from sahi.predict import get_prediction, get_sliced_prediction
import torch

class YoloModelSegmentation:
    _instance = None
    
    def __init__(self):
        if YoloModelSegmentation._instance is not None:
            raise Exception("¡Usa YOLOModelHandler.get_instance() en lugar de crear una nueva instancia!")
        
        # Configuración optimizada del modelo
        self.device = "cuda:0" if torch.cuda.is_available() else "cpu"
        print("self.device:", self.device)
        self.detection_model = AutoDetectionModel.from_pretrained(
            model_type='yolo11',
            model_path='./yolo11s-seg-finituned.pt',
            confidence_threshold=0.5,
            device=self.device,
        )

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = YoloModelSegmentation()
        return cls._instance
    
    def predict(self, image_path):
        try:
            if not image_path or not os.path.exists(image_path):
                raise FileNotFoundError(f"Ruta inválida o inexistente: {image_path}")
            
            result = get_prediction(image_path, self.detection_model)

            print("image_path:", image_path)
            print("result:", result)
            predictions = {
                'bboxes': [],
                #'masks': [],
                'segmentations': [],
                'classes': [],
                'scores': []
            }
            
            for object_pred in result.object_prediction_list:
                segmentation = object_pred.mask.segmentation
                if isinstance(segmentation, list):
                    if all(isinstance(v, (int, float)) for v in segmentation):
                        segmentation = np.array(segmentation, dtype=np.int32).reshape((-1, 2)).tolist()
                    elif all(isinstance(v, list) for v in segmentation):
                        segmentation = [np.array(s, dtype=np.int32).reshape((-1, 2)).tolist() for s in segmentation]
                
                predictions['bboxes'].append(object_pred.bbox.to_xywh())
                #predictions['masks'].append(object_pred.mask.bool_mask.tolist())
                predictions['segmentations'].append(segmentation)
                predictions['classes'].append(object_pred.category.name)
                predictions['scores'].append(object_pred.score.value)
            
            return predictions
        except Exception as e:
            print(f"Error durante la predicción: {str(e)}")
            traceback.print_exc()
            return None
        finally:
            # Limpieza de memoria
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            gc.collect()

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
            self.segmentations[id_img] = dict(img_path=img_path, **results)
        finally:
            self.mutex.unlock()

    def save_to_disk(self):
        if not self.segmentations:
            return
        try:
            with open("./segmentations_partial.json", "a") as f:
                json.dump(self.segmentations, f)
                f.write("\n")
        except Exception as e:
            print(f"Error saving partial results: {e}")

class ModelWorker(QObject):
    progress_updated = Signal(int, str)
    batch_finished = Signal(dict)
    processing_complete = Signal()
    error_occurred = Signal(str)

    def __init__(self, images_data):
        super().__init__()
        self.images_data = images_data
        self._is_running = True
        self.batch_size = 5

    def stop(self):
        self._is_running = False

    def process_images(self):
        try:
            model = YoloModelSegmentation.get_instance()
            total_images = len(self.images_data)
            processed_count = 0
            batch_results = {}

            for img_id, img_data in self.images_data.items():
                if not self._is_running:
                    break

                img_path = img_data['im_relative_path'].replace("//", "/")
                try:
                    results = model.predict(img_path)
                    if results:
                        #batch_results[img_id] = dict(img_path=img_path, **results)
                        processed_count += 1
                        print("processed_count:", processed_count)
                        # Emitir progreso cada 5 imágenes para reducir carga
                        if processed_count % self.batch_size == 0:
                            self.progress_updated.emit(
                                int((processed_count / total_images) * 100),
                                f"Procesando {processed_count}/{total_images}"
                            )
                            self.batch_finished.emit(batch_results)
                            #batch_results = {}
                            QThread.msleep(100)  # Pequeña pausa para mantener UI responsive

                except Exception as e:
                    self.error_occurred.emit(f"Error procesando {img_id}: {str(e)}")

            # Procesar cualquier resultado restante
            if batch_results:
                self.batch_finished.emit(batch_results)

            self.progress_updated.emit(100, "Procesamiento completado")
            self.processing_complete.emit()

        except Exception as e:
            self.error_occurred.emit(f"Error en el worker: {str(e)}")
            traceback.print_exc()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setup_ui()
        self.setup_connections()
        self.results_store = ResultSegmentation()
        self.images_data = {}
        self.worker_thread = None
        self.worker = None

    def setup_ui(self):
        self.setWindowTitle("Procesamiento de Imágenes Optimizado")
        self.setGeometry(100, 100, 600, 200)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)

        self.process_label = QLabel("Listo para procesar")
        self.process_label.setAlignment(Qt.AlignCenter)

        self.start_button = QPushButton("Iniciar")
        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.setEnabled(False)

        layout = QVBoxLayout()
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.process_label)
        layout.addWidget(self.start_button)
        layout.addWidget(self.cancel_button)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

    def setup_connections(self):
        self.start_button.clicked.connect(self.start_processing)
        self.cancel_button.clicked.connect(self.cancel_processing)

    def get_images_data(self):
        df = pd.read_csv("./df_images_metadata.csv")
        return {
            i: im_data for i, im_data in 
            df[["im_relative_path"]].iloc[0:10].to_dict(orient="index").items()
        }

    def start_processing(self):
        self.images_data = self.get_images_data()
        if not self.images_data:
            self.process_label.setText("No hay imágenes para procesar")
            return

        self.progress_bar.setValue(0)
        self.start_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.process_label.setText("Preparando procesamiento...")

        # Configurar el sistema de procesamiento en segundo plano
        self.setup_worker_thread()

    def setup_worker_thread(self):
        # Crear worker y thread
        self.worker = ModelWorker(self.images_data)
        self.worker_thread = QThread()

        # Mover worker al thread
        self.worker.moveToThread(self.worker_thread)

        # Conectar señales
        self.worker_thread.started.connect(self.worker.process_images)
        self.worker.progress_updated.connect(self.update_progress)
        self.worker.batch_finished.connect(self.handle_batch_results)
        self.worker.processing_complete.connect(self.processing_finished)
        self.worker.error_occurred.connect(self.handle_error)

        # Limpieza cuando termine
        self.worker.processing_complete.connect(self.worker_thread.quit)
        self.worker.processing_complete.connect(self.worker.deleteLater)
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)

        # Iniciar el thread
        self.worker_thread.start()

    @Slot(int, str)
    def update_progress(self, progress, message):
        self.progress_bar.setValue(progress)
        self.process_label.setText(message)

    @Slot(dict)
    def handle_batch_results(self, batch_results):
        for img_id, results in batch_results.items():
            continue
            #self.results_store.add_segmentation(img_id, results['img_path'], results)

    @Slot()
    def processing_finished(self):
        self.save_segmentation_data()
        self.start_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.process_label.setText("¡Procesamiento completado!")
        self.worker = None
        self.worker_thread = None

    @Slot(str)
    def handle_error(self, error_message):
        self.process_label.setText(f"Error: {error_message}")
        self.cancel_processing()

    def cancel_processing(self):
        if self.worker:
            self.worker.stop()
        if self.worker_thread and self.worker_thread.isRunning():
            self.worker_thread.quit()
            self.worker_thread.wait()

        self.start_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.process_label.setText("Procesamiento cancelado")

    def save_segmentation_data(self):
        if hasattr(self.results_store, 'segmentations') and self.results_store.segmentations:
            try:
                with open("./segmentations_final.json", "w") as f:
                    json.dump(self.results_store.segmentations, f)
            except Exception as e:
                print(f"Error guardando resultados finales: {e}")

    def closeEvent(self, event):
        self.cancel_processing()
        super().closeEvent(event)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Establecer estilo para mejor visualización
    app.setStyle('Fusion')
    
    window = MainWindow()
    window.show()
    
    # Asegurar limpieza al cerrar
    ret = app.exec()
    
    # Limpiar memoria de GPU si se usó
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    
    sys.exit(ret)