import os
import numpy as np
from PySide6.QtWidgets import (QApplication, QMainWindow, QGraphicsView, 
                              QGraphicsScene, QGraphicsPixmapItem, QSlider, 
                              QVBoxLayout, QWidget, QLabel, QComboBox)
from PySide6.QtGui import QPixmap, QImage, QWheelEvent, QMouseEvent, QPainter
from PySide6.QtCore import Qt, QRectF
from osgeo import gdal
import re

class GeoTIFFViewer(QMainWindow):
    def __init__(self, mosaic_dir, mask_dir):
        super().__init__()
        self.setWindowTitle("Visor de Mosaico con Máscara de Árboles")
        self.setGeometry(100, 100, 1000, 800)
        
        # Configuración de directorios
        self.mosaic_dir = mosaic_dir
        self.mask_dir = mask_dir
        self.current_zoom = 0
        self.max_zoom = self.detect_max_zoom()
        
        # Escena gráfica con dos capas
        self.scene = QGraphicsScene()
        self.view = QGraphicsView(self.scene)
        self.view.setDragMode(QGraphicsView.ScrollHandDrag)
        self.view.setRenderHint(QPainter.Antialiasing)
        
        # Interfaz de usuario
        self.setup_ui()
        self.load_zoom_level(self.current_zoom)

    def setup_ui(self):
        """Configura la interfaz con selector de zoom"""
        layout = QVBoxLayout()
        
        # Selector de zoom
        self.zoom_combo = QComboBox()
        self.zoom_combo.addItems([f"Zoom {i}" for i in range(self.max_zoom + 1)])
        self.zoom_combo.currentIndexChanged.connect(self.change_zoom_level)
        
        layout.addWidget(QLabel("Nivel de Zoom:"))
        layout.addWidget(self.zoom_combo)
        layout.addWidget(self.view)
        
        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

    def detect_max_zoom(self):
        """Detecta el máximo nivel de zoom disponible"""
        max_z = 0
        while os.path.exists(os.path.join(self.mosaic_dir, f"zoom_{max_z}")):
            max_z += 1
        return max_z - 1 if max_z > 0 else 0

    def change_zoom_level(self, zoom_level):
        """Cambia entre niveles de zoom"""
        self.current_zoom = zoom_level
        self.scene.clear()
        self.load_zoom_level(zoom_level)

    def load_zoom_level(self, zoom_level):
        """Carga ambas capas (mosaico y máscara) para el nivel de zoom actual"""
        zoom_dir_mosaic = os.path.join(self.mosaic_dir, f"zoom_{zoom_level}")
        zoom_dir_mask = os.path.join(self.mask_dir, f"zoom_{zoom_level}")
        
        if not os.path.exists(zoom_dir_mosaic) or not os.path.exists(zoom_dir_mask):
            print(f"Directorios no encontrados para zoom {zoom_level}")
            return
        
        # Primero cargar el mosaico (capa base)
        self.load_tiles(zoom_dir_mosaic, is_mask=False)
        
        # Luego cargar la máscara (capa superior)
        self.load_tiles(zoom_dir_mask, is_mask=True)
        
        # Ajustar vista
        self.view.fitInView(self.scene.itemsBoundingRect(), Qt.KeepAspectRatio)

    def load_tiles(self, zoom_dir, is_mask):
        """Carga tiles de mosaico o máscara según el parámetro is_mask"""
        for tile_file in os.listdir(zoom_dir):
            if not tile_file.startswith("tile_") or not tile_file.endswith(".tif"):
                continue
                
            match = re.search(r"tile_(\d+)_(\d+)\.tif", tile_file)
            if not match:
                continue
                
            x_pos = int(match.group(1)) // (2 ** self.current_zoom)
            y_pos = int(match.group(2)) // (2 ** self.current_zoom)
            
            tile_path = os.path.join(zoom_dir, tile_file)
            
            if is_mask:
                qimage = self.mask_to_qimage(tile_path)
            else:
                qimage = self.geotiff_to_qimage(tile_path)
            
            if qimage:
                item = QGraphicsPixmapItem(QPixmap.fromImage(qimage))
                item.setPos(x_pos, y_pos)
                
                # La máscara se coloca encima del mosaico
                if is_mask:
                    item.setZValue(1)  # Capa superior
                
                self.scene.addItem(item)

    def geotiff_to_qimage(self, geotiff_path):
        """Convierte GeoTIFF del mosaico a QImage"""
        ds = gdal.Open(geotiff_path)
        if not ds:
            print(f"Error al abrir mosaico: {geotiff_path}")
            return None
        
        # Leer bandas RGB
        bands = [ds.GetRasterBand(i+1).ReadAsArray() for i in range(min(3, ds.RasterCount))]
        
        # Convertir a 8-bit si es necesario
        if bands[0].dtype != np.uint8:
            bands = [(band * 255 / band.max()).astype(np.uint8) for band in bands]
        
        # Crear QImage (BGR -> RGB)
        height, width = bands[0].shape
        if len(bands) >= 3:
            rgb = np.dstack((bands[2], bands[1], bands[0]))
        else:
            rgb = np.dstack([bands[0]]*3)
        
        return QImage(rgb.data, width, height, 3 * width, QImage.Format_RGB888).copy()

    def mask_to_qimage(self, mask_path):
        """Convierte la máscara binaria a QImage transparente con áreas verdes"""
        ds = gdal.Open(mask_path)
        if not ds:
            print(f"Error al abrir máscara: {mask_path}")
            return None
        
        # Leer máscara (1 banda)
        mask_array = ds.GetRasterBand(1).ReadAsArray()
        
        # Crear imagen RGBA (32-bit)
        height, width = mask_array.shape
        rgba = np.zeros((height, width, 4), dtype=np.uint8)
        
        # Áreas con árboles (valor > 0) -> verde semitransparente
        tree_mask = mask_array > 0
        rgba[tree_mask] = [0, 255, 0, 64]  # RGBA: verde con 25% opacidad
        
        # Áreas sin árboles -> completamente transparentes
        rgba[~tree_mask] = [0, 0, 0, 0]
        
        return QImage(rgba.data, width, height, 4 * width, QImage.Format_RGBA8888).copy()

    def wheelEvent(self, event):
        """Control de zoom con la rueda del mouse"""
        zoom_delta = event.angleDelta().y()
        
        if zoom_delta > 0 and self.current_zoom < self.max_zoom:
            self.current_zoom += 1
            self.zoom_combo.setCurrentIndex(self.current_zoom)
        elif zoom_delta < 0 and self.current_zoom > 0:
            self.current_zoom -= 1
            self.zoom_combo.setCurrentIndex(self.current_zoom)

if __name__ == "__main__":
    app = QApplication([])
    
    # Directorios deben tener la misma estructura de zoom levels
    viewer = GeoTIFFViewer(
        mosaic_dir="./mosaico_10_images/tiles_pyramid",
        mask_dir="./mosaico_10_images/tiles_mask_pyramid"
    )
    viewer.show()
    app.exec()