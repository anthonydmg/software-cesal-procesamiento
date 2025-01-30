import sys
import folium
import rasterio
from folium import raster_layers
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget
from PySide6.QtWebEngineWidgets import QWebEngineView

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Mapa con GeoTIFF usando Folium")
        self.setGeometry(100, 100, 800, 600)

        # Crear QWebEngineView
        self.web_view = QWebEngineView()

        # Crear el mapa con Folium
        self.create_folium_map()

        # Configurar el layout
        layout = QVBoxLayout()
        layout.addWidget(self.web_view)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

    def create_folium_map(self):
        # Crear un mapa básico centrado en una ubicación
        m = folium.Map(location=[-13.881719661927868, -73.03486801134967], zoom_start=18)

        # Cargar la imagen GeoTIFF usando Rasterio
        with rasterio.open("imagen_georreferenciada.tif") as src:
            # Obtener los límites del raster
            bounds = src.bounds
            # Crear una capa de imagen
            image = raster_layers.ImageOverlay(
                image=src.read(1),  # Leer la primera banda
                bounds=[[(bounds[1], bounds[0]), (bounds[3], bounds[2])]],  # Coordenadas en el espacio geográfico
                opacity=0.6,
            )
            # Añadir la capa de imagen al mapa
            image.add_to(m)

        # Guardar el mapa como archivo HTML
        map_html = "map_with_geotiff.html"
        m.save(map_html)

        # Cargar el archivo HTML con QWebEngineView
        with open(map_html, 'r') as f:
            html_content = f.read()
        self.web_view.setHtml(html_content)

app = QApplication(sys.argv)
window = MainWindow()
window.show()
sys.exit(app.exec())