import sys
import os
import folium
from dotenv import load_dotenv
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget
import json

load_dotenv()

MAPBOX_TOKEN = os.getenv("MAPBOX_TOKEN")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Software de Procesamiento")
        self.setGeometry(100,100,800,800)

        m = folium.Map(location=[-13.881719661927868, -73.03486801134967], 
                       zoom_start=18,
                       max_zoom=22, 
                        tiles=f"https://api.mapbox.com/styles/v1/mapbox/satellite-v9/tiles/{{z}}/{{x}}/{{y}}?access_token={MAPBOX_TOKEN}",
                        attr="Mapbox")

        # Cargar el archivo GeoJSON con los polígonos
        with open('./mascara_arboles.geojson', 'r') as f:
            geojson_data = json.load(f)
        # Lista de colores (Verde, Amarillo, Azul, Naranja)
        colores = ["#008000", "#FFFF00", "#0000FF", "#FFA500"]

        def style_function(feature):
            idx = feature["properties"].get("treeID", 1) -1
            color = colores[idx % len(colores)]  # Seleccionar color cíclicamente
            return {
                "fillColor": color,
                 "color": color,
                "weight": 2,
                "fillOpacity": 0.5
            }
        # Agregar el archivo GeoJSON al mapa
       
                # Crear el polígono y agregarlo al mapa
        #folium.Marker(location=[
        #                    -13.881719661927868,
        #                    -73.03486801134967
        #                ], popup='Ubicación de Árbol').add_to(m)

        #folium.Marker([-13.78866, -72.9511], popup="Nueva York", tooltip="Click para ver").add_to(m)
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
        # Widget principal
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

         # Layout vertical
        layout = QVBoxLayout()
        central_widget.setLayout(layout)

        # Vista Web
        self.browser = QWebEngineView()
        # Cargar el HTML generado en memoria
        self.browser.setHtml(html_page)
        layout.addWidget(self.browser)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())