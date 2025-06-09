import sys
import os
import gc
import json
import traceback
import pandas as pd
import numpy as np
from PySide6.QtWidgets import (QApplication, QMainWindow, QPushButton, QProgressBar, 
                             QVBoxLayout, QWidget, QLabel)
from PySide6.QtCore import (QThread, QMutex, QObject, Signal, Slot, Qt)
from sahi import AutoDetectionModel
from sahi.predict import get_prediction
import torch
from typing import Dict, Any

class MemoryAwareYOLOModel:
    _instance = None
    _mutex = QMutex()
    
    def __init__(self):
        if MemoryAwareYOLOModel._instance is not None:
            raise Exception("Esta clase es un singleton. Usa get_instance()")
        
        self.device = self._select_device()
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
            return "cuda:0"
        return "cpu"
    
    def _load_model(self):
        model = AutoDetectionModel.from_pretrained(
            model_type='yolo11',
            model_path='./yolo11s-seg-finituned.pt',
            confidence_threshold=0.5,
            device=self.device,
        )
        if hasattr(model, 'model'):
            for param in model.model.parameters():
                param.requires_grad = False
        return model
    
    def predict_with_memory_management(self, image_path):
        try:
            if not os.path.exists(image_path):
                raise FileNotFoundError(f"Imagen no encontrada: {image_path}")
            
            self._clean_memory()
            
            result = get_prediction(image_path, self.model)
            print("result:", result)
            predictions = {
                'bboxes': [], 'masks': [], 'segmentations': [],
                'classes': [], 'scores': []
            }
            
            for obj in result.object_prediction_list:
                seg = self._process_segmentation(obj.mask.segmentation)
                predictions['bboxes'].append(obj.bbox.to_xywh())
                predictions['masks'].append(obj.mask.bool_mask.tolist())
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

class ResultStorage:
    def __init__(self, max_memory_items: int = 5):
        self.mutex = QMutex()
        self.segmentations = {}
        self.max_memory_items = max_memory_items
        self.partial_file_counter = 0
    
    def add_results(self, results: Dict[str, Any]):
        with self.mutex:
            self.segmentations.update(results)
            if len(self.segmentations) >= self.max_memory_items:
                self._save_to_disk()
    
    def _save_to_disk(self):
        if not self.segmentations:
            return
        
        filename = f"./segmentations_part_{self.partial_file_counter}.json"
        try:
            with open(filename, 'w') as f:
                json.dump(self.segmentations, f, indent=2)
            self.partial_file_counter += 1
            self.segmentations.clear()
        except Exception as e:
            print(f"Error guardando resultados parciales: {e}")
    
    def save_remaining(self):
        self._save_to_disk()

class ImageProcessor(QObject):
    progress_updated = Signal(int, str, int, int)  # progress, message, current, total
    batch_completed = Signal(int)  # current batch
    finished = Signal()
    error_occurred = Signal(str)

    def __init__(self, image_data: Dict[str, Any]):
        super().__init__()
        self.image_data = image_data
        self.is_running = True
        self.batch_size = 3  # Reducido para mejor manejo de memoria
        self.model = MemoryAwareYOLOModel.get_instance()

    def process(self):
        try:
            total = len(self.image_data)
            processed = 0
            batch_results = {}

            for img_id, img_data in self.image_data.items():
                if not self.is_running:
                    break

                img_path = img_data['im_relative_path'].replace("//", "/")
                print("img_path:", img_path)
                try:
                    result = self.model.predict_with_memory_management(img_path)
                    if result:
                        batch_results[img_id] = {'img_path': img_path, **result}
                        processed += 1

                        # Emitir progreso cada imagen
                        progress = int((processed / total) * 100)
                        self.progress_updated.emit(
                            progress, 
                            f"Procesando {img_id}", 
                            processed, 
                            total
                        )

                        # Manejar lotes
                        if processed % self.batch_size == 0:
                            self.batch_completed.emit(processed)
                            batch_results = {}
                            QThread.msleep(50)  # Pequeña pausa

                except Exception as e:
                    self.error_occurred.emit(f"Error en {img_id}: {str(e)}")

            # Procesar resultados restantes
            if batch_results:
                self.batch_completed.emit(processed)

            self.finished.emit()

        except Exception as e:
            self.error_occurred.emit(f"Error en el procesador: {str(e)}")
            traceback.print_exc()

    def stop(self):
        self.is_running = False

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setup_ui()
        self.setup_variables()
        self.setup_connections()

    def setup_ui(self):
        self.setWindowTitle("Procesador de Imágenes con Gestión de Memoria")
        self.setGeometry(100, 100, 800, 200)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)

        self.status_label = QLabel("Preparado para comenzar")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("font-weight: bold;")

        self.details_label = QLabel("")
        self.details_label.setAlignment(Qt.AlignCenter)

        self.start_btn = QPushButton("Iniciar Procesamiento")
        self.stop_btn = QPushButton("Detener")
        self.stop_btn.setEnabled(False)

        layout = QVBoxLayout()
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.status_label)
        layout.addWidget(self.details_label)
        layout.addWidget(self.start_btn)
        layout.addWidget(self.stop_btn)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

    def setup_variables(self):
        self.processor_thread = None
        self.processor = None
        self.result_storage = ResultStorage(max_memory_items=3)
        self.image_data = {}

    def setup_connections(self):
        self.start_btn.clicked.connect(self.start_processing)
        self.stop_btn.clicked.connect(self.stop_processing)

    def load_image_data(self):
        try:
            df = pd.read_csv("./df_images_metadata.csv")
            return {
                idx: {'im_relative_path': data['im_relative_path']} 
                for idx, data in df.iloc[:10].to_dict('index').items()
            }
        except Exception as e:
            self.show_error(f"Error cargando datos: {str(e)}")
            return {}

    def start_processing(self):
        self.image_data = self.load_image_data()
        if not self.image_data:
            return

        self.setup_processing_thread()
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.status_label.setText("Procesamiento iniciado")
        self.progress_bar.setValue(0)

    def setup_processing_thread(self):
        # Crear y configurar el hilo
        self.processor_thread = QThread()
        self.processor = ImageProcessor(self.image_data)
        self.processor.moveToThread(self.processor_thread)

        # Conectar señales
        self.processor_thread.started.connect(self.processor.process)
        self.processor.progress_updated.connect(self.update_progress)
        self.processor.batch_completed.connect(self.handle_batch_completion)
        self.processor.finished.connect(self.processing_finished)
        self.processor.error_occurred.connect(self.handle_error)

        # Limpieza al finalizar
        self.processor.finished.connect(self.processor_thread.quit)
        self.processor.finished.connect(self.processor.deleteLater)
        self.processor_thread.finished.connect(self.processor_thread.deleteLater)

        # Iniciar el hilo
        self.processor_thread.start()

    @Slot(int, str, int, int)
    def update_progress(self, progress, message, current, total):
        self.progress_bar.setValue(progress)
        self.status_label.setText(message)
        self.details_label.setText(f"Imagen {current} de {total}")

    @Slot(int)
    def handle_batch_completion(self, current_count):
        self.result_storage.save_remaining()
        self.status_label.setText(f"Lote completado - {current_count} imágenes")

    @Slot()
    def processing_finished(self):
        self.result_storage.save_remaining()
        self.cleanup_processing()
        self.status_label.setText("Procesamiento completado con éxito")
        self.details_label.setText("")

    @Slot(str)
    def handle_error(self, error_msg):
        self.show_error(error_msg)
        self.cleanup_processing()

    def stop_processing(self):
        if self.processor:
            self.processor.stop()
        self.cleanup_processing()
        self.status_label.setText("Procesamiento detenido")

    def cleanup_processing(self):
        if self.processor_thread and self.processor_thread.isRunning():
            self.processor_thread.quit()
            self.processor_thread.wait()

        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

    def show_error(self, message):
        self.status_label.setText("Error ocurrido")
        self.details_label.setText(message[:150] + "..." if len(message) > 150 else message)
        self.cleanup_processing()

    def closeEvent(self, event):
        self.stop_processing()
        super().closeEvent(event)

def main():
    # Configuración inicial de PyTorch para mejor manejo de memoria
    torch.backends.cudnn.benchmark = True
    torch.set_flush_denormal(True)

    app = QApplication(sys.argv)
    app.setStyle('Fusion')  # Mejor aspecto visual

    window = MainWindow()
    window.show()

    ret = app.exec()

    # Limpieza final de memoria GPU
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        torch.cuda.ipc_collect()

    sys.exit(ret)

if __name__ == "__main__":
    main()