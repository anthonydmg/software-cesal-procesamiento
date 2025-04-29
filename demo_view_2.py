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
        
        # Configuración de la vista
        self.scene = QGraphicsScene()
        self.view = QGraphicsView(self.scene)
        self.view.setDragMode(QGraphicsView.ScrollHandDrag)
        self.view.setRenderHint(QPainter.Antialiasing)
        
        # Cargar y mostrar las capas
        self.setup_ui()
        self.load_layers()
        
        # Debug: Mostrar información de carga
        print(f"Tiles de mosaico cargados: {len(os.listdir(mosaic_dir))}")
        print(f"Tiles de máscara cargados: {len(os.listdir(mask_dir))}")

    def setup_ui(self):
        """Configura la interfaz de usuario"""

        layout = QVBoxLayout()
        layout.addWidget(self.view)
        
        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

    def load_layers(self):
        """Carga ambas capas verificando errores"""
        try:
            # Verificar existencia de directorios
            if not os.path.exists(self.mosaic_dir):
                raise FileNotFoundError(f"Directorio no encontrado: {self.mosaic_dir}")
            if not os.path.exists(self.mask_dir):
                raise FileNotFoundError(f"Directorio no encontrado: {self.mask_dir}")
                
            # Cargar capas
            self.load_tiles(self.mosaic_dir, is_mask=False)
            self.load_tiles(self.mask_dir, is_mask=True)
            
            # Ajustar vista
            if self.scene.items():
                self.view.fitInView(self.scene.itemsBoundingRect(), Qt.KeepAspectRatio)
            else:
                print("Advertencia: No se cargaron tiles")
                
        except Exception as e:
            print(f"Error al cargar capas: {str(e)}")

    def load_tiles(self, tiles_dir, is_mask):
        """Carga tiles con verificación de errores"""
        try:
            for tile_file in sorted(os.listdir(tiles_dir)):
                if not (tile_file.startswith("tile_") and tile_file.endswith(".tif")):
                    continue
                    
                # Extraer coordenadas
                match = re.search(r"tile_(\d+)_(\d+)\.tif", tile_file)
                if not match:
                    print(f"Formato de nombre incorrecto: {tile_file}")
                    continue
                    
                x_pos, y_pos = map(int, match.groups())
                tile_path = os.path.join(tiles_dir, tile_file)
                
                # Debug: Verificar existencia de archivo
                if not os.path.exists(tile_path):
                    print(f"Archivo no encontrado: {tile_path}")
                    continue
                
                # Convertir a QImage
                qimage = self.mask_to_qimage(tile_path) if is_mask else self.geotiff_to_qimage(tile_path)
                if qimage.isNull():
                    print(f"Error al convertir imagen: {tile_path}")
                    continue
                
                # Crear item y añadir a escena
                pixmap = QPixmap.fromImage(qimage)
                if pixmap.isNull():
                    print(f"Error al crear QPixmap: {tile_path}")
                    continue
                    
                item = QGraphicsPixmapItem(pixmap)
                item.setPos(x_pos, y_pos)
                if is_mask:
                    item.setZValue(1)
                self.scene.addItem(item)
                
                # Debug: Mostrar información del tile cargado
                print(f"Cargado {'máscara' if is_mask else 'mosaico'}: {tile_file} en ({x_pos}, {y_pos})")
                
        except Exception as e:
            print(f"Error al cargar tiles: {str(e)}")

    def geotiff_to_qimage(self, geotiff_path):
        """Conversión robusta de GeoTIFF a QImage"""
        try:
            ds = gdal.Open(geotiff_path)
            if not ds:
                print(f"No se pudo abrir: {geotiff_path}")
                return QImage()
            
            # Leer bandas
            bands = []
            for i in range(min(3, ds.RasterCount)):
                band = ds.GetRasterBand(i+1)
                arr = band.ReadAsArray()
                if arr is None:
                    print(f"Error al leer banda {i+1} de {geotiff_path}")
                    return QImage()
                
                # Normalizar a 8-bit si es necesario
                if arr.dtype != np.uint8:
                    arr = (arr * 255 / (arr.max() or 1)).astype(np.uint8)
                bands.append(arr)
            
            # Crear imagen RGB
            height, width = bands[0].shape
            if len(bands) >= 3:
                rgb = np.dstack((bands[0], bands[1], bands[2]))  # BGR a RGB
            else:
                rgb = np.dstack([bands[0]]*3)  # Escala de grises a RGB
            
            # Crear QImage asegurando que los datos persistan
            rgb_contiguous = np.ascontiguousarray(rgb)
            return QImage(rgb_contiguous.data, width, height, 3 * width, QImage.Format_RGB888).copy()
            
        except Exception as e:
            print(f"Error en geotiff_to_qimage: {str(e)}")
            return QImage()

    def mask_to_qimage(self, mask_path):
        """Conversión robusta de máscara a QImage transparente"""
        try:
            ds = gdal.Open(mask_path)
            if not ds:
                print(f"No se pudo abrir: {mask_path}")
                return QImage()
            
            # Leer máscara
            mask_array = ds.GetRasterBand(1).ReadAsArray()
            if mask_array is None:
                print(f"Error al leer máscara: {mask_path}")
                return QImage()
            
            height, width = mask_array.shape
            rgba = np.zeros((height, width, 4), dtype=np.uint8)
            
            # Aplicar máscara (verde semitransparente donde haya valores > 0)
            tree_mask = mask_array > 0
            rgba[tree_mask] = [0, 255, 0, 128]  # Verde con 50% opacidad
            rgba[~tree_mask] = [0, 0, 0, 0]     # Transparente
            
            # Crear QImage asegurando que los datos persistan
            rgba_contiguous = np.ascontiguousarray(rgba)
            return QImage(rgba_contiguous.data, width, height, 4 * width, QImage.Format_RGBA8888).copy()
            
        except Exception as e:
            print(f"Error en mask_to_qimage: {str(e)}")
            return QImage()

    def wheelEvent(self, event):
        """Zoom con la rueda del mouse"""
        factor = 1.1 ** (event.angleDelta().y() / 120)
        self.view.scale(factor, factor)

if __name__ == "__main__":
    app = QApplication([])
    
    # Directorios deben tener la misma estructura de zoom levels
    viewer = GeoTIFFViewer(
        mosaic_dir="./mosaico_10_images/tiles_pyramid/zoom_0",
        mask_dir="./mosaico_10_images/tiles_mask_pyramid/zoom_0"
    )
    viewer.show()
    app.exec()