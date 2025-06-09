from PySide6.QtWidgets import QApplication, QDialog, QStackedWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QFileDialog, QFrame, QListWidget, QProgressBar, QTableWidget, QScrollArea, QTableWidgetItem
from PySide6.QtCore import Qt, Signal
import os
from core.utils import get_gps_coordinates, get_image_resolution, get_metadata, calcule_gsd_teorico
import pandas as pd

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
            print("\nfiles:", len(files))
            print()
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
        print("\ntotal_images:", total_images)
        print()
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
        GSD_horizontal, GSD_vertical = calcule_gsd_teorico(metadata)

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
            "image_height": image_height,
            "gsd_horizontal": GSD_horizontal,
            "gsd_vertical": GSD_vertical
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
