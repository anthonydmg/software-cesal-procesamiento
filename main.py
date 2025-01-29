from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QStackedWidget, QLabel, QListWidgetItem, QPushButton, QFrame, QProgressBar, QSizePolicy, QDialog, QLineEdit, QFileDialog, QTableWidget, QTableWidgetItem, QScrollArea
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtCore import Qt, QSize, Signal
import os
import folium
from PySide6.QtWebEngineWidgets import QWebEngineView
import pandas as pd
import time

from dotenv import load_dotenv

load_dotenv()

MAPBOX_TOKEN = os.getenv("MAPBOX_TOKEN")


import sys

class InitialConfigureScreen(QFrame):
    def __init__(self, parent = None, dialog_parent=None):
        super().__init__(parent)
        self.dialog_parent = dialog_parent  # Almacena la referencia a NewAnalysisDialog
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
        self.dialog_parent.go_to_image_selection_screen()
    
    def close_dialog(self):
        parent = self.dialog_parent
        if isinstance(parent, QDialog):
            parent.reject() 
        else:
            parent.close()

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
        for i in range(0,101):
            self.progress_bar.setValue(i)
            QApplication.processEvents()
            time.sleep(0.05)
        
        self.dialog_parent.go_to_image_data_table()
    
    def go_back_to_initial(self):
        self.dialog_parent.go_back_to_initial()

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
        self.table.setHorizontalHeaderLabels(["Nombre", "Latitud", "Longitud", "Ángulo Yaw", "Ángulo Pitch", "Ángulo Roll", "Fecha"])
        self.add_image_data()

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

        # Crear pantallas
        self.initial_screen = InitialConfigureScreen(dialog_parent = self)

        #self.create_initial_screen()
        self.image_selection_screen = ImageSelectionScreen(dialog_parent = self)

        self.image_data_screen = ImageDataTableScreen(dialog_parent = self)
        #
        self.stacked_widget.addWidget(self.initial_screen)
        self.stacked_widget.addWidget(self.image_selection_screen)
        self.stacked_widget.addWidget(self.image_data_screen)

        self.current_step = 0  # Variable para llevar el control de los pasos
        self.stacked_widget.setCurrentIndex(self.current_step)  # Mostrar la pantalla inicial

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
        dialog.image_data_screen.finished_configure.connect(self.main_window.on_finish_configure)
        dialog.exec()
 
class MapCaptures(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout()
        
        # Crear un mapa con Folium
        m = folium.Map(location=[-13.881719661927868, -73.03486801134967], 
                       zoom_start=19,
                        max_zoom=22, 
                        tiles=f"https://api.mapbox.com/styles/v1/mapbox/satellite-v9/tiles/{{z}}/{{x}}/{{y}}?access_token={MAPBOX_TOKEN}",
                        attr="Mapbox")
        
        df = pd.read_csv("./df_images_metadata.csv")

        for latitud, longitude, name in zip(df["latitude"].to_list(),df["longitude"].to_list(), df["basename"].to_list()):
            folium.CircleMarker(location=[latitud, longitude],  
                                radius=6, 
                                color='red', 
                                fill=True, 
                                fill_color='red', 
                                fill_opacity=1,
                                tooltip = name).add_to(m)
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
        
        # Seccion inferior
        processing_layout = QVBoxLayout()
        progress_layout = QHBoxLayout()
        processing_label = QLabel("Procesamiento")
        processing_label.setStyleSheet("font-size: 18px; font-weight: bold; padding: 0px;")
        processing_bar = QProgressBar()
        processing_bar.setStyleSheet("""
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
        processing_bar.setMinimumWidth(400)
        processing_bar.setMinimum(0)
        processing_bar.setMaximum(100)
        processing_bar.setValue(0)
        processing_bar.setFixedHeight(20)

        self.progress_bar = processing_bar


        start_button = QPushButton("Iniciar")
        start_button.setStyleSheet("""
    QPushButton {
        background-color: #2d6a4f;  # Verde oscuro
        color: white;  # Texto blanco
        border: 2px solid #1b4d3e;  # Borde oscuro para resaltar
        border-radius: 5px;  # Bordes redondeados
        padding: 10px 20px;  # Espaciado dentro del botón
        font-size: 16px;  # Tamaño de fuente
    }
    QPushButton:hover {
        background-color: #3a8d72;  # Verde ligeramente más claro al pasar el mouse
        border-color: #2c5e47;  # Cambiar el borde en hover
    }
    QPushButton:pressed {
        background-color: #1f4f39;  # Verde más oscuro cuando se presiona
    }
""")
        start_button.clicked.connect(self.start_progress)
        progress_layout.addWidget(processing_bar)
        progress_layout.addWidget(start_button)

        processing_layout.addWidget(processing_label)
        processing_layout.addLayout(progress_layout)

        layout.addWidget(self.web_view)
        layout.addLayout(processing_layout)
         # Asignar factores de estiramiento
        layout.setStretchFactor(self.web_view, 9)  # El primer widget ocupa el 80% (8 partes)
        layout.setStretchFactor(processing_layout, 1)  # El segundo layout ocupa el 20% (2 partes)

        self.setLayout(layout)

    def start_progress(self):
        for i in range(101):
            self.progress_bar.setValue(i)
            QApplication.processEvents()  # Esto permite que la interfaz se actualice
            time.sleep(0.05)  # Simulando una tarea que tarda

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
        self.page_map_images = MapCaptures()
        self.page_map_trees= MapTrees()

        self.stack.addWidget(self.page_home)
        self.stack.addWidget(self.page_map_images)
        self.stack.addWidget(self.page_map_trees)
        # Agregar widgets al layout principal
        main_layout.addWidget(self.navbar)
        main_layout.addWidget(self.stack)

        self.setLayout(main_layout)

    def switch_page(self, index):
        self.stack.setCurrentIndex(index)

    def on_finish_configure(self):
        self.navbar.setCurrentRow(1)  # Cambiar al segundo ítem del navbar

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())