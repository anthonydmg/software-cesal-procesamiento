import sys
import folium
from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget
from PySide6.QtWebEngineWidgets import QWebEngineView
import os


load_dotenv()

MAPBOX_TOKEN = os.getenv("MAPBOX_TOKEN")

class MapApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Mapa con Folium y Mapbox")
        self.setGeometry(100, 100, 800, 600)
        
        # Crear el mapa con Folium usando Mapbox
        map_html = "map.html"
        m = folium.Map(location=[37.7749, -122.4194], zoom_start=12, 
                       tiles="https://api.mapbox.com/styles/v1/mapbox/streets-v11/tiles/{z}/{x}/{y}?access_token=TU_ACCESS_TOKEN",
                       attr="Mapbox")
        m.save(map_html)
        
        # Crear el widget de navegación
        self.browser = QWebEngineView()
        self.browser.setHtml(open(map_html, 'r', encoding='utf-8').read())
        
        # Layout principal
        central_widget = QWidget()
        layout = QVBoxLayout()
        layout.addWidget(self.browser)
        central_widget.setLayout(layout)
        self.setCentralWidget(central_widget)

        # Eliminar el archivo HTML temporal al cerrar
        self.map_html_path = map_html

    def closeEvent(self, event):
        if os.path.exists(self.map_html_path):
            os.remove(self.map_html_path)
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MapApp()
    window.show()
    sys.exit(app.exec())