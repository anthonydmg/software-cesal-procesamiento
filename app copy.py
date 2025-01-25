import sys
import os
import folium
from dotenv import load_dotenv
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget
import json

load_dotenv()

MAPBOX_TOKEN = os.getenv("MAPBOX_TOKEN")


import sys
import folium
from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget
from PySide6.QtWebEngineWidgets import QWebEngineView

class MapaWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Mapa con PySide6, Folium y Mapbox")
        self.setGeometry(100, 100, 800, 600)

        # Crear el visor de la web
        self.web_view = QWebEngineView()
        
        # Crear el layout
        central_widget = QWidget()
        layout = QVBoxLayout()
        layout.addWidget(self.web_view)
        central_widget.setLayout(layout)
        self.setCentralWidget(central_widget)

        # Crear el mapa
        self.crear_mapa()

    def crear_mapa(self):
        # Ubicación inicial del mapa
        mapa = folium.Map(
            location=[19.4326, -99.1332],  # Coordenadas (Ejemplo: Ciudad de México)
            zoom_start=14,
            tiles=f"https://api.mapbox.com/styles/v1/mapbox/streets-v11/tiles/{{z}}/{{x}}/{{y}}?access_token={MAPBOX_TOKEN}",
            attr="Mapbox",
        )

        # Script JavaScript para cargar el GeoJSON local con Leaflet
        js_script = """
        <script>
        document.addEventListener("DOMContentLoaded", function() {
            fetch('sample.geojson')
                .then(response => response.json())
                .then(data => {
                    L.geoJSON(data, {
                        style: function(feature) {
                            var colors = ['#008000', '#FFFF00', '#0000FF', '#FFA500']; // Verde, Amarillo, Azul, Naranja
                            var id = feature.properties.id || 1;
                            return { color: colors[(id - 1) % colors.length], fillOpacity: 0.5 };
                        }
                    }).addTo(map);
                });
        });
        </script>
        """

        # Agregar el script al mapa
        mapa.get_root().html.add_child(folium.Element(js_script))

        # Cargar el HTML en QWebEngineView sin guardar en disco
        self.web_view.setHtml(mapa._repr_html_())

if __name__ == "__main__":
    app = QApplication(sys.argv)
    ventana = MapaWindow()
    ventana.show()
    sys.exit(app.exec())