from PySide6.QtWidgets import QApplication, QWidget, QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QVBoxLayout, QHBoxLayout, QListWidget, QStackedWidget, QLabel, QListWidgetItem, QPushButton, QFrame, QProgressBar, QSizePolicy, QDialog, QLineEdit, QFileDialog, QTableWidget, QTableWidgetItem, QScrollArea, QGroupBox,  QFrame, QSizePolicy
from PySide6.QtGui import QIcon, QImage, QPixmap, QPainter, QPalette, QColor
from PySide6.QtCore import Qt, QSize, Signal, QRectF, QMutex, Signal, Slot, Qt, QThread, QObject
import os
import folium
from PySide6.QtWebEngineWidgets import QWebEngineView
import pandas as pd
import time
import re
from dotenv import load_dotenv
from osgeo import gdal
from utils import get_gps_coordinates, get_image_resolution, get_metadata
import numpy as np
from tempfile import mkstemp
import torch
from sahi import AutoDetectionModel
from sahi.predict import get_prediction
from datetime import datetime
import traceback
import gc
import json
import random

load_dotenv()

MAPBOX_TOKEN = os.getenv("MAPBOX_TOKEN")

import sys

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
            model_path='./yolo11s-seg-finituned.pt',
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
            final_path = self.result_storage.merge_results()
            self.finished.emit()

        except Exception as e:
            self.error_occurred.emit(f"Error en el procesador: {str(e)}")
            traceback.print_exc()

    def stop(self):
        self.is_running = False

class InitialConfigureScreen(QFrame):
    def __init__(self, parent = None, dialog_parent=None):
        super().__init__(parent)
        self.dialog_parent = dialog_parent  # Almacena la referencia a NewAnalysisDialog
        layout = QVBoxLayout()

        name_layout = QHBoxLayout()
        name_label = QLabel("Nombre:")
        self.name_input = QLineEdit()
        self.name_input.textChanged.connect(self.validate_inputs)  # Validar al escribir
        name_layout.addWidget(name_label)
        name_layout.addWidget(self.name_input)
        layout.addLayout(name_layout)

        folder_layout = QHBoxLayout()
        folder_label = QLabel("Crear en:")
        self.folder_input = QLineEdit()
        self.folder_input.setReadOnly(True)  # Para evitar que el usuario escriba manualmente
        self.folder_input.textChanged.connect(self.validate_inputs)  # Validar al escribir
        self.folder_button = QPushButton("Seleccionar")
        self.folder_button.clicked.connect(self.select_folder)
        
        folder_layout.addWidget(folder_label)
        folder_layout.addWidget(self.folder_input)
        folder_layout.addWidget(self.folder_button)
        layout.addLayout(folder_layout)

        button_layout = QHBoxLayout()
        self.next_button = QPushButton("Siguiente")
        self.next_button.setEnabled(False)  # Deshabilitado al inicio
        self.next_button.clicked.connect(self.go_to_image_selection_screen)
        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.clicked.connect(self.close_dialog)
        
        button_layout.addWidget(self.next_button)
        button_layout.addWidget(self.cancel_button)
        button_layout.setAlignment(Qt.AlignBottom)
        layout.addLayout(button_layout)

        self.setLayout(layout)

    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Seleccionar Carperta")
        if folder:
            self.folder_input.setText(folder)
    
    def go_to_image_selection_screen(self):
        """Crea la carpeta del análisis y avanza a la siguiente pantalla."""

        
        name = self.name_input.text().strip()
        folder_path = self.folder_input.text().strip()
        # Construir la ruta final
        final_path = os.path.join(folder_path, name)

        try:
            os.makedirs(final_path, exist_ok=True)  # Crea la carpeta si no existe
            print(f"Carpeta creada: {final_path}")  # Debug (puedes eliminar esto después)

            self.dialog_parent.new_analysis_data_store.set_base_dir(final_path)

           
            self.dialog_parent.new_analysis_data_store.set_name(name)
            # Llamar al método para cambiar de pantalla
            self.dialog_parent.go_to_image_selection_screen()
        except Exception as e:
            print(f"Error al crear la carpeta: {e}")  # Debug (puedes manejar errores de otra forma)
        #self.dialog_parent.go_to_image_selection_screen()
    
    def close_dialog(self):
        parent = self.dialog_parent
        if isinstance(parent, QDialog):
            parent.reject() 
        else:
            parent.close()

    def validate_inputs(self):
        """Habilita el botón 'Siguiente' solo si ambos campos están llenos y cambia el color de los vacíos."""
        name_filled = bool(self.name_input.text().strip())
        folder_filled = bool(self.folder_input.text().strip())

        # Estilo rojo si está vacío, normal si está lleno
        self.name_input.setStyleSheet("border: 2px solid red;" if not name_filled else "")
        self.folder_input.setStyleSheet("border: 2px solid red;" if not folder_filled else "")

        # Habilitar o deshabilitar el botón de siguiente
        self.next_button.setEnabled(name_filled and folder_filled)
    
    def validate_and_continue(self):
        """Verifica si los campos están llenos antes de avanzar a la siguiente pantalla."""
        self.validate_inputs()  # Actualiza los estilos visuales
        if self.next_button.isEnabled():  # Solo avanza si está habilitado
            self.go_to_image_selection_screen()


class ImageSelectionScreen(QFrame):
    def __init__(self, parent = None, dialog_parent=None):
        super().__init__(parent)
        self.dialog_parent = dialog_parent  # Almacena la referencia a NewAnalysisDialog
        layout = QVBoxLayout()

        self.info_label = QLabel("\u274C Se requieren al menos 3 imágenes en formato JPG o TIFF.")
        self.info_label.setStyleSheet("color: red;")
        layout.addWidget(self.info_label)
        
        self.image_list = QListWidget()
        self.image_list.setSelectionMode(QListWidget.ExtendedSelection)

        self.image_list.setStyleSheet(""" QListWidget::item:hover { background-color: rgba(100, 149, 237, 0.5); } 
                                          QListWidget::item:selected { background-color: rgba(70, 130, 180, 0.8); color: white; }""")
        
        button_layout = QHBoxLayout()
        self.add_images_button = QPushButton("Añadir Imágenes...")
        self.add_images_button.clicked.connect(self.add_images)
        button_layout.addWidget(self.add_images_button)
        
        self.add_folder_button = QPushButton("Añadir Carpeta...")
        self.add_folder_button.clicked.connect(self.add_folder)
        button_layout.addWidget(self.add_folder_button)

        self.remove_selected_button = QPushButton("Eliminar Seleccionado")
        self.remove_selected_button.clicked.connect(self.remove_selected)
        button_layout.addWidget(self.remove_selected_button)
        
        layout.addLayout(button_layout)
        layout.addWidget(self.image_list)

        self.progress_bar = QProgressBar()
        self.progress_bar.setStyleSheet(""" QProgressBar { border: 2px solid grey; border-radius: 5px; text-align: center; }
                                           QProgressBar::chunk { background-color: #76e900; width: 20px; }""")

        self.progress_bar.setMinimumWidth(400)
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(20)
        self.progress_bar.setTextVisible(False)

        self.progress_bar.setFormat("Leyendo EXIF Metadata: %p%") 

        layout.addWidget(self.progress_bar)
        self.progress_bar.setVisible(False)

        button_layout = QHBoxLayout()
        self.back_button = QPushButton("< Atrás")
        self.back_button.clicked.connect(self.go_back_to_initial)
        button_layout.addWidget(self.back_button)
        
        self.next_button = QPushButton("Siguiente >")
        self.next_button.clicked.connect(self.start_read_metadata)
        self.next_button.setEnabled(False)
        button_layout.addWidget(self.next_button)
        layout.addLayout(button_layout)
        self.setLayout(layout)

    def add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Seleccionr carpeta")
        if folder:
            files = [os.path.join(folder, f) for f in os.listdir(folder) if f.lower().endswith(('.jpg','.jpeg','.tiff','.tif'))]
            self.image_list.addItems(files)
        
        self.validate_selection()
    
    def add_images(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Seleccionar imágenes", "", "Imágenes (*.jpg *.jpeg *.tiff *.tif)")
        if files:
            self.image_list.addItems(files)
        self.validate_selection()
    
    def validate_selection(self):
        if self.image_list.count() >= 3:
            self.info_label.setText("✔ Imágenes seleccionadas correctamente.")
            self.info_label.setStyleSheet("color: green;")
            self.next_button.setEnabled(True)
        else:
            self.info_label.setText("\u274C Se requieren al menos 3 imágenes en formato JPG o TIFF.")
            self.info_label.setStyleSheet("color: red;")
            self.next_button.setEnabled(False)

    def remove_selected(self):
        for item in self.image_list.selectedItems():
            self.image_list.takeItem(self.image_list.row(item))

    def start_read_metadata(self):
        self.progress_bar.setVisible(True)
        self.progress_bar.setTextVisible(True)
        image_paths = [self.image_list.item(i).text() for i in range(self.image_list.count())]
        total_images = len(image_paths)
        metadata_list = []

        for i, path in enumerate(image_paths):
            # Actualizar progreso
            progress = int((i + 1) / total_images * 100)
            self.progress_bar.setValue(progress)
            QApplication.processEvents()

            # Leer metadatos
            metadata = self.get_exif_data(path)
            
            if metadata:
                self.dialog_parent.new_analysis_data_store.add_image_data(i, dict(img_relative_path = path, **metadata))
                metadata_list.append([
                    metadata["name"],
                    metadata["image_width"],
                    metadata["image_height"],
                    metadata["latitude"],
                    metadata["longitude"],
                    metadata["yaw_degree"],
                    metadata["pitch_degree"],
                    metadata["roll_degree"],
                    metadata["DateTimeOriginal"],
                ])
        
        #self.dialog_parent.image_data_screen.load_metadata(metadata_list)

        self.dialog_parent.go_to_image_data_table()
    
    def go_back_to_initial(self):
        self.dialog_parent.go_back_to_initial()

    def get_exif_data(self, image_path):
        metadata = get_metadata(image_path)
        latitude, longitude = get_gps_coordinates(metadata)
        print(f"Latitud: {latitude}, Longitud: {longitude}")
        image_width, image_height = get_image_resolution(metadata)
        yaw_degree = metadata.get("XMP:GimbalYawDegree")
        pitch_degree = metadata.get("XMP:GimbalPitchDegree")
        roll_degree = metadata.get("XMP:GimbalRollDegree")

        if not isinstance(yaw_degree, float):
            signo, yaw_degree = (yaw_degree[0], yaw_degree[1:]) if yaw_degree[0] in '+-' else ("+", yaw_degree[0])
            yaw_degree =  float(yaw_degree) if signo == '+' else -float(yaw_degree)
        
        datetime = metadata.get("EXIF:DateTimeOriginal")
        basename = os.path.basename(image_path)
        metadata_data = {
            "name": basename,
            "latitude": latitude,
            "longitude" : longitude,
            "yaw_degree": yaw_degree,
            "pitch_degree": pitch_degree,
            "roll_degree": roll_degree,
            "DateTimeOriginal": datetime,
            "image_width": image_width,
            "image_height": image_height
        }
       
        return metadata_data

class ImageDataTableScreen(QFrame):
    finished_configure = Signal()
    def __init__(self, parent = None, dialog_parent=None):
        super().__init__(parent)
        self.dialog_parent = dialog_parent  # Almacena la referencia a NewAnalysisDialog
        layout = QVBoxLayout()

        # Título de la pantalla
        self.title_label = QLabel("Propiedades de Imagen")
        self.title_label.setAlignment(Qt.AlignCenter)  # Centra el título
        layout.addWidget(self.title_label)

        # Crear la tabla
        self.table = QTableWidget()
        self.table.setRowCount(0)
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(["Nombre","Ancho","Alto", "Latitud", "Longitud", "Ángulo Yaw", "Ángulo Pitch", "Ángulo Roll", "Fecha"])
        #self.add_image_data()

        # Crear un área de desplazamiento para la tabla
        scroll_area = QScrollArea()
        scroll_area.setWidget(self.table)
        scroll_area.setWidgetResizable(True)  # Hacer que la tabla se ajuste al tamaño del área
        layout.addWidget(scroll_area)

        # Botones en la parte inferior
        button_layout = QHBoxLayout()
        self.back_button = QPushButton("< Atrás")
        self.back_button.clicked.connect(self.go_back_to_image_selection)
        button_layout.addWidget(self.back_button)

        self.finished_button = QPushButton('Finalizar')
        self.finished_button.clicked.connect(self.finish_configure)
        button_layout.addWidget(self.finished_button)

        layout.addLayout(button_layout)

        self.setLayout(layout)
    
    def update_data_table(self, images_data):
        table_data = [[ metadata["name"],
            metadata["image_width"],
            metadata["image_height"],
            metadata["latitude"],
            metadata["longitude"],
            metadata["yaw_degree"],
            metadata["pitch_degree"],
            metadata["roll_degree"],
            metadata["DateTimeOriginal"],
                ] for metadata in images_data.values()]

        self.table.setRowCount(0)
        for data in table_data:
            row_position = self.table.rowCount()
            self.table.insertRow(row_position)
            for column, value in enumerate(data):
                self.table.setItem(row_position, column, QTableWidgetItem(str(value)))

    def load_metadata(self, metadata_list):
        print("metadata_list:", metadata_list)
        self.table.setRowCount(0)
        for data in metadata_list:
            row_position = self.table.rowCount()
            self.table.insertRow(row_position)
            for column, value in enumerate(data):
                self.table.setItem(row_position, column, QTableWidgetItem(str(value)))
    
    def go_back_to_image_selection(self):
        self.dialog_parent.go_back_to_image_selection()
    
    def add_image_data(self):
        image_data = [["Imagen1.jpg", "12.345", "-67.890", "139.5", "-90.0", "180.00" , "2025-01-28"],
            ["Imagen2.tiff", "45.678", "-123.456", "2025-01-27",  "-90.0", "180.00" , "2025-01-28"],
            ["Imagen3.jpg", "23.456", "-98.765", "2025-01-26",  "-90.0", "180.00" , "2025-01-28"]]
        
        for data in image_data:
            row_position = self.table.rowCount()
            self.table.insertRow(row_position)
            for column, value in enumerate(data):
                self.table.setItem(row_position, column, QTableWidgetItem(value))

    def finish_configure(self):
        self.finished_configure.emit()
        if isinstance(self.dialog_parent, QDialog):
            self.dialog_parent.accept()  
        else:
            self.dialog_parent.close()

class NewAnalysisDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Nuevo Análisis")
        self.setFixedSize(800, 600)

        self.stacked_widget = QStackedWidget(self)  # Contenedor principal de pantallas
        self.setLayout(QVBoxLayout())
        self.layout().addWidget(self.stacked_widget)

        self.new_analysis_data_store = AnalysisData()
        # Crear pantallas
        self.initial_screen = InitialConfigureScreen(dialog_parent = self)

        #self.create_initial_screen()
        self.image_selection_screen = ImageSelectionScreen(dialog_parent = self)

        self.image_data_screen = ImageDataTableScreen(dialog_parent = self)
        #ImageDataTableScreen
        self.stacked_widget.addWidget(self.initial_screen)
        self.stacked_widget.addWidget(self.image_selection_screen)
        self.stacked_widget.addWidget(self.image_data_screen)

        self.current_step = 0  # Variable para llevar el control de los pasos
        self.stacked_widget.setCurrentIndex(self.current_step)  # Mostrar la pantalla inicial
    
    def save_metadata(self, columns, metadata):
        df = pd.DataFrame(metadata, columns=columns)
        name =  self.initial_screen.name_input.text().strip()
        folder_path =  self.initial_screen.folder_input.text().strip()
        # Construir la ruta final
        final_path = os.path.join(folder_path, name, "image_metadata.csv")
        df.to_csv(final_path, index=False)

    def go_to_image_selection_screen(self):
        """Método para ir al paso de selección de imágenes"""
        if self.initial_screen.name_input.text().strip() and self.initial_screen.folder_input.text().strip():
            self.stacked_widget.setCurrentIndex(1)  # Ir al segundo paso
        else:
            # Validar los campos (puedes agregar lógica de validación aquí)
            self.initial_screen.name_input.setStyleSheet("border: 1px solid red;")
            self.initial_screen.folder_input.setStyleSheet("border: 1px solid red;")
    
    def go_back_to_initial(self):
        """Método para volver al primer paso"""
        self.stacked_widget.setCurrentIndex(0)

    def go_to_image_data_table(self):
        print("self.new_analysis_data_store.images_data:", self.new_analysis_data_store.images_data)
        self.image_data_screen.update_data_table(self.new_analysis_data_store.images_data)
        """Método para ir al paso de tabla de datos de imagen"""
        self.stacked_widget.setCurrentIndex(2)


class CustomButton(QPushButton):
    def __init__(self, icon_path, title, description, parent=None):
        super().__init__(parent)

        # Layout horizontal para el icono y el texto
        h_layout = QHBoxLayout()
        h_layout.setContentsMargins(5, 5, 5, 5)  # Margen interno del botón
        h_layout.setSpacing(8)  # Reduce el espacio entre el icono y el texto

        # Icono en el lado izquierdo
        icon_label = QLabel()
        icon_label.setPixmap(QIcon(icon_path).pixmap(32, 32))  # Ajusta el tamaño del icono
        icon_label.setStyleSheet("padding-left: 10px; padding-right: 5px;")
        icon_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)  # Evita que se expanda
        h_layout.addWidget(icon_label)

        # Layout vertical para el título y la descripción
        text_layout = QVBoxLayout()
        text_layout.setSpacing(0)  # Reduce el espacio entre el título y la descripción
        text_layout.setAlignment(Qt.AlignCenter)
        title_label = QLabel(title)
        description_label = QLabel(description)

        # Establecer estilos y alineación
        title_label.setStyleSheet("color: black; font-size: 16px; font-weight: bold; padding: 0px 5px 0px 0px;")
        description_label.setStyleSheet("color: gray; font-size: 12px; padding: 0px 5px 0px 0px;")
        title_label.setAlignment(Qt.AlignLeft)
        description_label.setAlignment(Qt.AlignLeft)
        description_label.setWordWrap(True)
        description_label.setMaximumWidth(750)  # Ajusta este valor a lo que desees como máximo de ancho

        # Agregar el título y la descripción al layout vertical
        text_layout.addWidget(title_label)
        text_layout.addWidget(description_label)

        # Agregar el layout de texto al layout horizontal
        h_layout.addLayout(text_layout)

        # Configurar el layout del botón
        self.setLayout(h_layout)

        # Ajustar el tamaño del botón para que se acomode al contenido
        self.setMinimumHeight(100)  # Altura mínima adecuada
        self.setMinimumWidth(250)  # Ancho mínimo ajustado

        self.adjustSize()

        #self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)  # Expansión horizontal automática

class NavItem(QWidget):
    def __init__(self, icon_path, text):
        super().__init__()
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)
        
        icon_label = QLabel()
        icon_label.setPixmap(QIcon(icon_path).pixmap(32, 32))
        icon_label.setAlignment(Qt.AlignCenter)
        
        text_label = QLabel(text)
        text_label.setAlignment(Qt.AlignCenter)
        
        layout.addWidget(icon_label)
        layout.addWidget(text_label)
        self.setLayout(layout)

class Home(QWidget):
    def __init__(self, main_window=None):
        super().__init__()
        self.main_window = main_window
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)

        title = QLabel("NutriMap Palta")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size:24px; font-weight: bold; padding: 0px 0px 10px 0px;")

        button_new = CustomButton("./assets/new.svg", "Nuevo Análisis", "Genera un nuevo analisis a partir de imagenes aereas para identificar deficiencias nutricionales.")
        button_new.clicked.connect(self.open_new_analysis_dialog)
        button_open = CustomButton("./assets/open.svg", "Abrir Análisis", "Abre un análisis guardado y revisa la informacion obtenida.")
        
        layout.addWidget(title)
        layout.addWidget(button_new)
        layout.addWidget(button_open)
        
        self.setLayout(layout)

  
    def open_new_analysis_dialog(self):
        dialog = NewAnalysisDialog(self)
        
        def handle_finished_configure():
            self.main_window.update_analysis_data(dialog.new_analysis_data_store)
        
        dialog.image_data_screen.finished_configure.connect(handle_finished_configure)

        dialog.exec()
 
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

class GeoTIFFViewer(QWidget):
    def __init__(self, mosaic_dir, mask_dir, masks_dirs  = None, parent=None):
        super().__init__(parent)
        self.mosaic_dir = mosaic_dir
        self.mask_dir = mask_dir
        self.masks_dirs = masks_dirs
        
        self.init_ui()
        self.load_layers()

    def init_ui(self):
        """Inicializa la interfaz del widget"""
        self.layout = QVBoxLayout(self)
        
        # Configuración de la vista
        self.scene = QGraphicsScene()
        self.view = QGraphicsView(self.scene)
        self.view.setDragMode(QGraphicsView.ScrollHandDrag)
        self.view.setRenderHint(QPainter.Antialiasing)
        
        # Añadir vista al layout
        self.layout.addWidget(self.view)

    def load_layers(self):
        """Carga ambas capas (mosaico y máscara)"""
        self.load_tiles(self.mosaic_dir, is_mask=False)
        if self.masks_dirs:
            colors = [[0, 255, 0, 128], [255, 140, 80, 128], [50, 205, 255, 128]]
            for mask_dir, color_mask in zip(self.masks_dirs, colors):
                self.load_tiles(mask_dir, is_mask=True, color_mask=color_mask)
        else:
            self.load_tiles(self.mask_dir, is_mask=True)
        self.view.fitInView(self.scene.itemsBoundingRect(), Qt.KeepAspectRatio)
   

    def load_tiles(self, tiles_dir, is_mask, color_mask = None):
        """Carga tiles individuales"""
        for tile_file in os.listdir(tiles_dir):
            if not tile_file.endswith(".tif"):
                continue
                
            match = re.search(r"tile_(\d+)_(\d+)\.tif", tile_file)
            if not match:
                continue
                
            x_pos, y_pos = map(int, match.groups())
            tile_path = os.path.join(tiles_dir, tile_file)
            
            qimage = self.mask_to_qimage(tile_path, color_mask) if is_mask else self.geotiff_to_qimage(tile_path)
            if not qimage.isNull():
                item = QGraphicsPixmapItem(QPixmap.fromImage(qimage))
                item.setPos(x_pos, y_pos)
                if is_mask:
                    item.setZValue(1)
                self.scene.addItem(item)

    def geotiff_to_qimage(self, path):
        """Convierte GeoTIFF a QImage"""
        ds = gdal.Open(path)
        if not ds:
            return QImage()
        
        bands = [ds.GetRasterBand(i+1).ReadAsArray() for i in range(min(3, ds.RasterCount))]
        if bands[0].dtype != np.uint8:
            bands = [(b * 255 / (b.max() or 1)).astype(np.uint8) for b in bands]
        
        height, width = bands[0].shape
        rgb = np.dstack(bands[:3]) if len(bands) >= 3 else np.dstack([bands[0]]*3)
        
        return QImage(rgb.data, width, height, 3 * width, QImage.Format_RGB888).copy()

    def mask_to_qimage(self, path, color_mask = None):
        """Convierte máscara a QImage transparente"""
        ds = gdal.Open(path)
        if not ds:
            return QImage()
        
        mask = ds.GetRasterBand(1).ReadAsArray()
        height, width = mask.shape
        rgba = np.zeros((height, width, 4), dtype=np.uint8)
        rgba[mask > 0] = color_mask if color_mask else [0, 255, 0, 128]
        #,  # Verde semitransparente
         #random.choices([
           
            #[255, 140, 80, 128],
            #[50, 205, 255, 128]
        #], 
        #weights = [0.65, 0.2, 0.15],
        #k=1
        #)[0]
       
        
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

class LegendItem(QWidget):
    def __init__(self, color, label_text, parent = None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2,2,2,2)
        # Color square
        color_label = QLabel()
        color_label.setFixedSize(20,20)
        pallete = color_label.palette()
        pallete.setColor(QPalette.Window, QColor(color))
        color_label.setAutoFillBackground(True)
        color_label.setPalette(pallete)

        # Text Label
        text_label = QLabel(label_text)
        text_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        layout.addWidget(color_label)
        layout.addWidget(text_label)
        layout.addStretch()
        

class LegendWidget(QWidget):
    def __init__(self):
        super().__init__()

        group_box = QGroupBox("Leyenda de Estado Nutricional")
        group_box.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 13px;
                color: #333;
                border: 1px solid #cccccc;
                border-radius: 5px;
                margin-top: 10px;
            }

            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 5px;
                margin-left: 10px;
            }
        """)

        group_layout = QVBoxLayout(group_box)
        group_layout.setContentsMargins(10, 20, 40, 10)
        group_layout.setSpacing(12)

        leyend_data = [
            ("#00FF32", "Saludable"),
            ("#F49632", "Deficiencia Nutricional"),
            ("#00B6FF", "Exceso Nutricional")
        ]

        for color, text in leyend_data:
            group_layout.addWidget(LegendItem(color, text))

        main_layout = QVBoxLayout(self)
        main_layout.addWidget(group_box)
        main_layout.addStretch()

class MosaicView(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        # Configuración de la vista
        
        # Cargar y mostrar las capas
        self.setup_ui()
        
        # Debug: Mostrar información de carga
    
    def setup_ui(self):
        """Configura la interfaz de usuario"""

        layout = QVBoxLayout()
        self.setLayout(layout)
         # Crear instancia del visualizador
        self.viewer = GeoTIFFViewer(
            mosaic_dir="./mosaico_15_images/tiles_pyramid/zoom_3",
            mask_dir="./mosaico_15_images/tiles_mask_pyramid/zoom_3",
            masks_dirs = [
                "./mosaico_15_images/tiles_mask_saludable_pyramid/zoom_3",
                "./mosaico_15_images/tiles_mask_deficient_pyramid/zoom_3",
                "./mosaico_15_images/tiles_mask_execeso_pyramid/zoom_3"
                ],
            parent=self
        )
        
        layout.addWidget(self.viewer)

class MapTreeScreen(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.setup_ui()
    
    def setup_ui(self):
        layout = QHBoxLayout(self)
        #self.setLayout(layout)
        self.mosaic_view = MosaicView(self.main_window)
        self.legend_widget = LegendWidget()
        layout.addWidget(self.mosaic_view, stretch=4)
        layout.addSpacing(10)
        layout.addWidget(self.legend_widget, stretch=1)
        #label = QLabel()

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

class AnalysisData:
    def __init__(self, base_dir = None, name = None, images_data = None):
        self.images_data = images_data
        self.base_dir = base_dir
        self.name = name
    
    def add_image_data(self, id_img, metadata):
        if self.images_data is None:
            self.images_data = {}
        self.images_data[id_img] = metadata

    def set_base_dir(self, base_dir):
        self.base_dir = base_dir

    def set_name(self, name):
        self.name = name
    
class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NutriMap Palta")
        #self.setGeometry(100,100,800,600)
        self.resize(1200, 768)
        #self.showMaximized()
        # Principal
        main_layout = QHBoxLayout(self)

        # Navbar lateral
        self.navbar = QListWidget()
        #self.navbar.setIconSize(QSize(64, 64))  # Tamaño grande del icono
        self.navbar.setFlow(QListWidget.TopToBottom)  # Icono arriba y texto abajo

        item1 = QListWidgetItem()
        item2 = QListWidgetItem()
        item3 = QListWidgetItem()

        item1.setTextAlignment(Qt.AlignCenter)
        item2.setTextAlignment(Qt.AlignCenter)
        item3.setTextAlignment(Qt.AlignCenter)

        self.navbar.addItem(item1)
        item1.setSizeHint(QSize(100, 100))
        self.navbar.setItemWidget(item1, NavItem("./assets/home.svg", "Inicio"))
        self.navbar.addItem(item2)
        item2.setSizeHint(QSize(100, 100))
        self.navbar.setItemWidget(item2, NavItem("./assets/map.svg", "Mapa Capturas"))
        self.navbar.addItem(item3)
        item3.setSizeHint(QSize(100, 100))
        self.navbar.setItemWidget(item3, NavItem("./assets/map-marker.svg", "Mapa Arboles"))
        self.navbar.setFixedWidth(100)
        self.navbar.currentRowChanged.connect(self.switch_page)

        # Contenedor central
        self.stack = QStackedWidget()
        # Contenido
        self.page_home = Home(main_window=self)
        self.page_map_images = MapCaptures(main_window=self)
        self.page_map_trees= MapTreeScreen(main_window=self) #MapTrees()

        self.stack.addWidget(self.page_home)
        self.stack.addWidget(self.page_map_images)
        self.stack.addWidget(self.page_map_trees)
        # Agregar widgets al layout principal
        main_layout.addWidget(self.navbar)
        main_layout.addWidget(self.stack)
        self.analysis_data_store = AnalysisData()
        self.setLayout(main_layout)

    def switch_page(self, index):
        self.stack.setCurrentIndex(index)
        
    def update_analysis_data(self, analysis_data_store):
        self.analysis_data_store = analysis_data_store
        self.page_map_images.update_map_view(self.analysis_data_store.images_data)
        self.navbar.setCurrentRow(1)  # Cambiar al segundo ítem del navbar

    def on_finish_configure(self):
        #self.page_map_images.update_map_view()
        self.navbar.setCurrentRow(1)  # Cambiar al segundo ítem del navbar

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())