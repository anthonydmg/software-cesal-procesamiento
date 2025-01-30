from PySide6.QtWidgets import QApplication, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFileDialog, QTableWidget, QTableWidgetItem, QListWidget, QProgressBar, QLineEdit, QStackedWidget, QFrame
import time
import os

from PySide6.QtCore import Qt

class InitialConfigureScreen(QFrame):
    def __init__(self, parent = None):
        super().__init__(parent)
        layout = QVBoxLayout()

        name_layout = QHBoxLayout()
        name_label = QLabel("Nombre:")
        self.name_input = QLineEdit()
        name_layout.addWidget(name_label)
        name_layout.addWidget(self.name_input)
        layout.addLayout(name_layout)

        folder_layout = QHBoxLayout()
        folder_label = QLabel("Crear en:")
        self.folder_input = QLineEdit()
        self.folder_button = QPushButton("Seleccionar")
        self.folder_button.clicked.connect(self.select_folder)
        
        folder_layout.addWidget(folder_label)
        folder_layout.addWidget(self.folder_input)
        folder_layout.addWidget(self.folder_button)
        layout.addLayout(folder_layout)

        button_layout = QHBoxLayout()
        self.next_button = QPushButton("Siguiente")
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
        self.parent().go_to_image_selection_screen()
    
    def close_dialog(self):
        parent = self.parent()
        if isinstance(parent, QDialog):
            parent.reject() 
        else:
            parent.close()

class ImageSelectionScreen(QFrame):
    def __init__(self, parent = None):
        super().__init__(parent)
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
        for i in range(0,101):
            self.progress_bar.setValue(i)
            QApplication.processEvents()
            time.sleep(0.05)
        
        self.parent().go_to_image_data_table()
    
    def go_back_to_initial(self):
        self.parent().go_back_to_initial()

class ImageDataTableScreen(QFrame):
    def __init__(self, parent = None):
        super().__init__(parent)
        
        layout = QVBoxLayout()
        self.table = QTableWidget()
        self.table.setRowCount(0)
        self.table.setHorizontalHeaderLabels(["Nombre", "Latitud", "Longitud", "Fecha"])

        layout.addWidget(self.table)
        button_layout = QHBoxLayout()
        self.back_button = QPushButton("< Atrás")
        self.back_button.clicked.connect(self.go_back_to_image_selection)
        button_layout.addWidget(self.back_button)

        self.finished_button = QPushButton('Finalizar')
        self.finished_button.clicked.connect(self.finish_configure)
        button_layout.addWidget(self.finished_button)

        layout.addLayout(button_layout)
        self.setLayout(layout)
    
    def go_back_to_image_selection(self):
        self.parent().go_back_to_image_selection()
    
    def finish_configure(self):
        parent = self.parent()
        if isinstance(parent, QDialog):
            parent.accept()  
        else:
            parent.close()

class NewAnalysisDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Nuevo Análisis")
        self.setFixedSize(800, 600)

        self.stacked_widget = QStackedWidget(self)  # Contenedor principal de pantallas
        self.setLayout(QVBoxLayout())
        self.layout().addWidget(self.stacked_widget)

        # Crear pantallas
        self.initial_screen = InitialConfigureScreen(self)

        #self.create_initial_screen()
        self.image_selection_screen = ImageSelectionScreen(self)

        self.image_data_screen = ImageDataTableScreen(self)
        #
        self.stacked_widget.addWidget(self.initial_screen)
        self.stacked_widget.addWidget(self.image_selection_screen)
        self.stacked_widget.addWidget(self.image_data_screen)

        self.current_step = 0  # Variable para llevar el control de los pasos
        self.stacked_widget.setCurrentIndex(self.current_step)  # Mostrar la pantalla inicial

    def create_initial_screen(self):
        # Pantalla 1: Ingreso de nombre y carpeta
        self.initial_screen = QFrame()
        layout = QVBoxLayout()
        
        name_layout = QHBoxLayout()
        name_label = QLabel("Nombre:")
        self.name_input = QLineEdit()
        name_layout.addWidget(name_label)
        name_layout.addWidget(self.name_input)
        layout.addLayout(name_layout)

        folder_layout = QHBoxLayout()
        folder_label = QLabel("Crear en:")
        self.folder_input = QLineEdit()
        self.folder_button = QPushButton("Seleccionar")
        self.folder_button.clicked.connect(self.select_folder)
        
        folder_layout.addWidget(folder_label)
        folder_layout.addWidget(self.folder_input)
        folder_layout.addWidget(self.folder_button)
        layout.addLayout(folder_layout)

        button_layout = QHBoxLayout()
        self.next_button = QPushButton("Siguiente")
        self.next_button.clicked.connect(self.go_to_image_selection)
        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.clicked.connect(self.reject)
        
        button_layout.addWidget(self.next_button)
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)

        self.initial_screen.setLayout(layout)
        self.stacked_widget.addWidget(self.initial_screen)

    def create_image_selection_screen(self):
        # Pantalla 2: Selección de imágenes
        self.image_selection_screen = QFrame()
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

        self.image_selection_screen.setLayout(layout)
        self.stacked_widget.addWidget(self.image_selection_screen)

    def create_image_data_table_screen(self):
        # Pantalla 3: Datos de imágenes
        self.image_data_screen = QFrame()
        layout = QVBoxLayout()
        self.table = QTableWidget()
        self.table.setRowCount(0)
        self.table.setHorizontalHeaderLabels(["Nombre", "Latitud", "Longitud", "Fecha"])

        # Agregar datos a la tabla
        layout.addWidget(self.table)
        
        # Botones
        button_layout = QHBoxLayout()
        self.back_button = QPushButton("<Atras")
        self.back_button.clicked.connect(self.go_back_to_image_selection)
        button_layout.addWidget(self.back_button)

        self.finished_button = QPushButton("Finalizar")
        self.finished_button.clicked.connect(self.accept)
        layout.addLayout(button_layout)

        self.image_data_screen.setLayout(layout)
        self.stacked_widget.addWidget(self.image_data_screen)

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
        """Método para ir al paso de tabla de datos de imagen"""
        self.stacked_widget.setCurrentIndex(2)


# Ejecutar la aplicación
if __name__ == "__main__":
    app = QApplication([])
    window = NewAnalysisDialog()
    window.show()
    app.exec()