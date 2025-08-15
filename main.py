from PySide6.QtWidgets import QApplication, QMainWindow, QMenuBar, QWidget, QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QVBoxLayout, QHBoxLayout, QListWidget, QStackedWidget, QLabel, QListWidgetItem, QPushButton, QFrame, QProgressBar, QSizePolicy, QDialog, QLineEdit, QFileDialog, QTableWidget, QTableWidgetItem, QScrollArea, QGroupBox,  QFrame, QSizePolicy
from PySide6.QtGui import QIcon, QImage, QPixmap, QPainter, QPalette, QColor
from PySide6.QtCore import Qt, QSize, Signal, QRectF, QMutex, Signal, Slot, Qt, QThread, QObject

import os
from dotenv import load_dotenv
import sys
from views.dialog_new_analysis import AnalysisData
from views.home import Home
from views.map_captures import MapCaptures
from views.map_mosaic import MapTreeScreen
load_dotenv()

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
        self.navbar.setFixedWidth(105)
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

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AgroHass")
        #self.setGeometry(100,100,800,600)
        self.resize(1300, 720)
        #self.setGeometry(100, 100, 800, 600)
        self.create_menu_bar()
        main_widget = QWidget()
        main_widget.setStyleSheet("background-color: white;")  # fondo blanco
        main_layout = QHBoxLayout(main_widget)  # Asignamos el layout al widget
        main_layout.setContentsMargins(0,0,0,0)
        main_content = MainContent()  # Asegúrate de que MainContent sea un QWidget
        main_layout.addWidget(main_content)
        
        self.setCentralWidget(main_widget)  # Usar setCentralWidget en lugar de setLayout
        # Crear la barra de menú    
       
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
        open_action = file_menu.addAction("Abrir...")
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

class MainWindowPrev(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NutriHass")
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
        self.page_map_trees= MapTreeScreen(main_window=self) #MapTrees()

        self.stack.addWidget(self.page_home)
        self.stack.addWidget(self.page_map_images)
        self.stack.addWidget(self.page_map_trees)
        # Agregar widgets al layout principal
        main_layout.addWidget(self.navbar)
        main_layout.addWidget(self.stack)
        self.analysis_data_store = AnalysisData()
        self.analysis_data_store = AnalysisData()
        self.setLayout(main_layout)

    def switch_page(self, index):
        self.stack.setCurrentIndex(index)
        self.navbar.setCurrentRow(index)
        
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