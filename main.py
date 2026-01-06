from PySide6.QtWidgets import QApplication, QMainWindow, QMenuBar, QWidget, QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QVBoxLayout, QHBoxLayout, QListWidget, QStackedWidget, QLabel, QListWidgetItem, QPushButton, QFrame, QProgressBar, QSizePolicy, QDialog, QLineEdit, QFileDialog, QTableWidget, QTableWidgetItem, QScrollArea, QGroupBox,  QFrame, QSizePolicy
from PySide6.QtGui import QIcon, QImage, QPixmap, QPainter, QPalette, QColor
from PySide6.QtCore import Qt, QSize, Signal, QRectF, QMutex, Signal, Slot, Qt, QThread, QObject

import os
from dotenv import load_dotenv
import sys
from core.utils import resource_path
from views.dialog_new_analysis import AnalysisData, NewAnalysisDialog
from views.home import Home
from views.map_captures import MapCaptures
from views.map_mosaic import MapTreeScreen
import multiprocessing 
from datetime import datetime
import json

load_dotenv(resource_path('.env'))

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
        # Estilo base transparente
        self.setStyleSheet("""
            QWidget {
                background-color: transparent;
            }
        """)

    def leaveEvent(self, event):
        # Restaura el fondo al salir el mouse
        self.setStyleSheet("""
            QWidget {
                background-color: transparent;
            }
        """)
        super().leaveEvent(event)

class MainContent(QWidget):
    def __init__(self):
        super().__init__()
        #self.setWindowTitle("NutriMap Palta")
        3#self.setGeometry(100,100,800,600)
        self.resize(1300, 720)
        #self.showMaximized()
        # Principal
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)  # <- elimina márgenes internos
        main_layout.setSpacing(0)  # <- elimina espacio entre widgets intern
        # Navbar lateral
        self.navbar = QListWidget()
        self.analysis_data_store = AnalysisData()

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
        self.navbar.setItemWidget(item1, NavItem(resource_path(os.path.join("assets", "home.svg")), "Inicio"))
        self.navbar.addItem(item2)
        item2.setSizeHint(QSize(100, 100))
        self.navbar.setItemWidget(item2, NavItem(resource_path(os.path.join("assets", "map.svg")), "Mapa Capturas"))
        self.navbar.addItem(item3)
        item3.setSizeHint(QSize(100, 100))
        self.navbar.setItemWidget(item3, NavItem(resource_path(os.path.join("assets", "map-marker.svg")), "Mapa Arboles"))
        self.navbar.setFixedWidth(105)
        self.navbar.currentRowChanged.connect(self.switch_page)

        # Desabilitados los items
        #self.disable_nav_item(1)
        #self.disable_nav_item(2)
       
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
        
        self.setLayout(main_layout)


    def disable_nav_item(self, index: int):
        """
        Deshabilita un item del navbar tanto a nivel de QListWidgetItem
        como visualmente en su widget asociado.
        """
        item = self.navbar.item(index)
        if item:
            # Quitar flag de enabled al QListWidgetItem
            item.setFlags(item.flags() & ~Qt.ItemIsEnabled)

            # Si tiene un widget asociado (NavItem), deshabilitarlo también
            widget = self.navbar.itemWidget(item)
            if widget:
                widget.setDisabled(True)
    
    def enable_nav_item(self, index: int):
        """
        Habilita un item del navbar tanto a nivel de QListWidgetItem
        como visualmente en su widget asociado.
        """
        item = self.navbar.item(index)
        if item:
            # Restaurar flag de enabled al QListWidgetItem
            item.setFlags(item.flags() | Qt.ItemIsEnabled)

            # Si tiene un widget asociado (NavItem), habilitarlo también
            widget = self.navbar.itemWidget(item)
            if widget:
                widget.setDisabled(False)
        

    def switch_page(self, index, setNavItem = False):
        self.stack.setCurrentIndex(index)
        if setNavItem:
            self.navbar.setCurrentRow(index) 
        
    def update_analysis_data(self, analysis_data_store):
        self.analysis_data_store = analysis_data_store
        self.page_map_images.update_map_view(self.analysis_data_store.images_data)
        self.navbar.setCurrentRow(1)  # Cambiar al segundo ítem del navbar
        self.enable_nav_item(1)

    def on_finish_configure(self):
        #self.page_map_images.update_map_view()
        self.navbar.setCurrentRow(1)  # Cambiar al segundo ítem del navbar

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AgroHass")
        ruta_icono = resource_path(os.path.join("assets", "icon_software.ico"))
        self.setWindowIcon(QIcon(ruta_icono))
        #self.setGeometry(100,100,800,600)
        self.resize(1300, 720)
        #self.setGeometry(100, 100, 800, 600)
        self.create_menu_bar()
        main_widget = QWidget()
        main_widget.setStyleSheet("background-color: white;")  # fondo blanco
        main_layout = QHBoxLayout(main_widget)  # Asignamos el layout al widget
        main_layout.setContentsMargins(0,0,0,0)
        self.main_content = MainContent()  # Asegúrate de que MainContent sea un QWidget
        main_layout.addWidget(self.main_content)
        
        self.setCentralWidget(main_widget)  # Usar setCentralWidget en lugar de setLayout
        # Crear la barra de menú    
    
    def open_new_analysis_dialog(self):
        dialog = NewAnalysisDialog(self)
        
        def handle_finished_configure():
            self.main_content.update_analysis_data(dialog.new_analysis_data_store)
            base_dir = dialog.new_analysis_data_store.base_dir
            images_data = dialog.new_analysis_data_store.images_data
            name = dialog.new_analysis_data_store.name
            
            project_info = {
                    "name": name,
                    "creation_date": datetime.now().isoformat(),
                    "num_images": len(images_data),
                    "base_dir": base_dir
                }
            
            config = {
                    "project_info": project_info,
                    "image_metatada": images_data
                }

            self.main_content.page_home.save_configure_analysis(base_dir, config)

            self.main_content.page_home.appdata_manager.add_new_project(project_info)
        
        dialog.image_data_screen.finished_configure.connect(handle_finished_configure)

        dialog.exec()

    def load_analysis(self, path_dir):
        with open(f"{path_dir}/config.json", "r") as f:
            config = json.load(f)
        
        project_info = config['project_info']
        print("project_info:", project_info)
        
        images_data = config['image_metatada']
        print("Cargando datos.....")
        images_data = {i: images_data[str(i)] for i in range(len(images_data))}
        

        analysis_data = AnalysisData(base_dir = project_info['base_dir'], name = project_info['name'], images_data=images_data)
        print("Actualizando Vistas.....")
        
        self.main_content.update_analysis_data(analysis_data)

        result_dir = self.main_content.analysis_data_store.base_dir

        print("Cargando result_dir:", result_dir)

        mosaic_path = f"{result_dir}/mosaic/rgb/tiles"
        
        if os.path.exists(mosaic_path):
            self.main_content.page_map_trees.layers_ready.emit(result_dir)
            self.main_content.switch_page(2, True)
        else:
            self.main_content.switch_page(1, True)

    def open_analysis(self):
        path_dir = QFileDialog.getExistingDirectory(
            self,
            "Seleciona Carpeta de Analisis Anterior",
            "",
        )

        if path_dir:
            print("Ruta de analisis:", path_dir)
            self.load_analysis(path_dir)


    def create_menu_bar(self):
        # Obtener o crear la barra de menú
        menu_bar = self.menuBar()
        menu_bar.setStyleSheet("""
        QMenuBar {
            background-color: #ffffff;  /* Tono claro */
        }
        QMenuBar::item {
            background-color: transparent;
        }
        QMenuBar::item:selected {
            background-color: #d0d0d0;
        }
    """)
        # Menú Archivo
        file_menu = menu_bar.addMenu("Analisis")
        
        # Acciones del menú Archivo
        new_action = file_menu.addAction("Nuevo")
        new_action.triggered.connect(self.open_new_analysis_dialog)
        open_action = file_menu.addAction("Abrir...")
        open_action.triggered.connect(self.open_analysis)
        file_menu.addSeparator()  # Línea separadora
        exit_action = file_menu.addAction("Salir")
        
        # Conectar acciones a funciones
        exit_action.triggered.connect(self.close)
        
        # Menú Ayuda
        help_menu = menu_bar.addMenu("Ayuda")
        
        # Acciones del menú Ayuda
        about_action = help_menu.addAction("Manual de Usuario")
        about_action.triggered.connect(self.show_about)
    
    def show_about(self):
        pass

if __name__ == "__main__":
    multiprocessing.freeze_support()
    
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())