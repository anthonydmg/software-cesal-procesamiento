import os
import numpy as np
from PySide6.QtWidgets import (QApplication, QMainWindow, QGraphicsView, 
                              QGraphicsScene, QGraphicsPixmapItem, QSlider, 
                              QVBoxLayout, QWidget, QLabel)
from PySide6.QtGui import QPixmap, QImage, QWheelEvent, QMouseEvent, QPainter
from PySide6.QtCore import Qt, QRectF
from osgeo import gdal
import re

class GeoTIFFViewer(QMainWindow):
    def __init__(self, tile_dir):
        super().__init__()
        self.setWindowTitle("Visor de Tiles GeoTIFF")
        self.setGeometry(100, 100, 800, 600)
        
        # Variables
        self.tile_dir = tile_dir
        self.scale_factor = 1.0
        self.brightness = 100
        self.contrast = 100
        
        # Configurar la escena y vista
        self.scene = QGraphicsScene()
        self.view = QGraphicsView(self.scene)
        self.view.setDragMode(QGraphicsView.ScrollHandDrag)
        self.view.setRenderHint(QPainter.Antialiasing)
        
        # Controles
        self.setup_ui()
        self.load_tiles()

    def setup_ui(self):
        """Configura la interfaz de usuario"""

        layout = QVBoxLayout()
        layout.addWidget(self.view)
        
        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

    def load_tiles(self):
        """Carga y posiciona los tiles correctamente"""
        import glob
        tile_files = glob.glob(os.path.join(self.tile_dir, "tile_*.tif"))
        
        if not tile_files:
            print("¡No se encontraron tiles GeoTIFF!")
            return
        
        for tile_path in tile_files:
            # Extraer coordenadas X,Y del nombre del archivo
            match = re.search(r"tile_(\d+)_(\d+)\.tif", os.path.basename(tile_path))
            if not match:
                continue
                
            x_pos = int(match.group(1))
            y_pos = int(match.group(2))
            
            qimage = self.geotiff_to_qimage(tile_path)
            if qimage:
                pixmap = QPixmap.fromImage(qimage)
                item = QGraphicsPixmapItem(pixmap)
                item.setPos(x_pos, y_pos)  # Posicionar el tile correctamente
                self.scene.addItem(item)
        
        self.view.fitInView(self.scene.itemsBoundingRect(), Qt.KeepAspectRatio)

    def geotiff_to_qimage(self, geotiff_path):
        """Convierte GeoTIFF a QImage optimizado"""
        ds = gdal.Open(geotiff_path)
        if not ds:
            print(f"Error al abrir: {geotiff_path}")
            return None

        # Leer y combinar bandas (asumiendo RGB)
        bands = [ds.GetRasterBand(i+1).ReadAsArray() for i in range(min(3, ds.RasterCount))]
        
        # Escalar a 8-bit si es necesario
        if bands[0].dtype != np.uint8:
            bands = [(band * 255 / band.max()).astype(np.uint8) for band in bands]
        
        # Crear QImage (convertir BGR a RGB si es necesario)
        height, width = bands[0].shape
        if len(bands) >= 3:
            combined = np.dstack(bands[:3])  # Invertir orden si es BGR
        else:
            combined = np.dstack([bands[0]]*3)  # Escala de grises a RGB
        
        qimage = QImage(combined.data, width, height, 3 * width, QImage.Format_RGB888)
        return qimage.copy()


    def wheelEvent(self, event):
        """Zoom suavizado con la rueda del mouse"""
        factor = 1.2 ** (event.angleDelta().y() / 240)
        self.view.scale(factor, factor)

if __name__ == "__main__":
    app = QApplication([])
    viewer = GeoTIFFViewer("./mosaico_10_images/tiles_mask_pyramid/zoom_1")
    viewer.show()
    app.exec()