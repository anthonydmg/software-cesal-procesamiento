import sys
import folium
from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget
from PySide6.QtWebEngineWidgets import QWebEngineView
import os
from dotenv import load_dotenv

import json

load_dotenv()

MAPBOX_TOKEN = os.getenv("MAPBOX_TOKEN")

class MapWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        # Crear el layout principal
        layout = QVBoxLayout()

        # Crear el mapa con Folium
        self.m = folium.Map(location=[0, 0], zoom_start=2)

        # Usar Mapbox como capa base (necesitas tu access_token)
        mapbox_token = "tu_mapbox_access_token"
        folium.TileLayer(
            tiles=f"https://api.mapbox.com/styles/v1/mapbox/satellite-v9/tiles/{{z}}/{{x}}/{{y}}?access_token={MAPBOX_TOKEN}",
            attr="Mapbox",
            name="Mapbox",
            overlay=False
        ).add_to(self.m)

        # Ruta al archivo GeoTIFF
        geo_tiff_path = "imagen_georreferenciada.tif"

        # Agregar el GeoTIFF como capa
        folium.raster_layers.ImageOverlay(
            image=geo_tiff_path,
            bounds=[[10, 10], [-10, -10]],  # Define las coordenadas que cubre la imagen
            opacity=0.7
        ).add_to(self.m)

        # Guardar el mapa en un archivo HTML
        map_html = "mapa_con_geotiff_mapbox.html"
        self.m.save(map_html)

        # Agregar un visor web para mostrar el mapa
        self.web_view = QWebEngineView()
        self.web_view.setUrl(f"file://{map_html}")

        # Añadir la vista web al layout
        layout.addWidget(self.web_view)

        # Configurar la ventana principal
        main_widget = QWidget()
        main_widget.setLayout(layout)
        self.setCentralWidget(main_widget)
        self.setWindowTitle("Mapbox con GeoTIFF")
        self.setGeometry(100, 100, 800, 600)

# Ejecutar la aplicación
app = QApplication(sys.argv)
window = MapWindow()
window.show()
sys.exit(app.exec())