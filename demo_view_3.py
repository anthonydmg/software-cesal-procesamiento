import os
import numpy as np
from PySide6.QtWidgets import (QApplication, QMainWindow, QGraphicsView, 
                              QGraphicsScene, QGraphicsPixmapItem, QPushButton,
                              QVBoxLayout, QWidget, QHBoxLayout)
from PySide6.QtGui import QPixmap, QImage, QPainter
from PySide6.QtCore import Qt, QRectF, QSize
from osgeo import gdal
import re
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from tempfile import mkstemp

class GeoTIFFViewer(QWidget):
    def __init__(self, mosaic_dir, mask_dir, parent=None):
        super().__init__(parent)
        self.mosaic_dir = mosaic_dir
        self.mask_dir = mask_dir
        
        self.init_ui()
        self.load_layers()

    def init_ui(self):
        """Inicializa la interfaz del widget"""
        self.layout = QVBoxLayout(self)
        
        # Configuración de la vista
        self.scene = QGraphicsScene()
        self.view = QGraphicsView(self.scene)
        self.view.setDragMode(QGraphicsView.ScrollHandDrag)
        self.view.setRenderHint(QPainter.Antialiasing)
        
        # Añadir vista al layout
        self.layout.addWidget(self.view)

    def load_layers(self):
        """Carga ambas capas (mosaico y máscara)"""
        self.load_tiles(self.mosaic_dir, is_mask=False)
        self.load_tiles(self.mask_dir, is_mask=True)
        self.view.fitInView(self.scene.itemsBoundingRect(), Qt.KeepAspectRatio)

    def load_tiles(self, tiles_dir, is_mask):
        """Carga tiles individuales"""
        for tile_file in os.listdir(tiles_dir):
            if not tile_file.endswith(".tif"):
                continue
                
            match = re.search(r"tile_(\d+)_(\d+)\.tif", tile_file)
            if not match:
                continue
                
            x_pos, y_pos = map(int, match.groups())
            tile_path = os.path.join(tiles_dir, tile_file)
            
            qimage = self.mask_to_qimage(tile_path) if is_mask else self.geotiff_to_qimage(tile_path)
            if not qimage.isNull():
                item = QGraphicsPixmapItem(QPixmap.fromImage(qimage))
                item.setPos(x_pos, y_pos)
                if is_mask:
                    item.setZValue(1)
                self.scene.addItem(item)

    def geotiff_to_qimage(self, path):
        """Convierte GeoTIFF a QImage"""
        ds = gdal.Open(path)
        if not ds:
            return QImage()
        
        bands = [ds.GetRasterBand(i+1).ReadAsArray() for i in range(min(3, ds.RasterCount))]
        if bands[0].dtype != np.uint8:
            bands = [(b * 255 / (b.max() or 1)).astype(np.uint8) for b in bands]
        
        height, width = bands[0].shape
        rgb = np.dstack(bands[:3][::-1]) if len(bands) >= 3 else np.dstack([bands[0]]*3)
        
        return QImage(rgb.data, width, height, 3 * width, QImage.Format_RGB888).copy()

    def mask_to_qimage(self, path):
        """Convierte máscara a QImage transparente"""
        ds = gdal.Open(path)
        if not ds:
            return QImage()
        
        mask = ds.GetRasterBand(1).ReadAsArray()
        height, width = mask.shape
        rgba = np.zeros((height, width, 4), dtype=np.uint8)
        rgba[mask > 0] = [0, 255, 0, 128]  # Verde semitransparente
        
        return QImage(rgba.data, width, height, 4 * width, QImage.Format_RGBA8888).copy()

    def save_scene_to_image(self):
        """Versión corregida para garantizar que se genera la imagen"""
        try:
            # 1. Calcular el área visible con márgenes adecuados
            view_rect = self.view.viewport().rect()
            target_rect = self.view.mapToScene(view_rect).boundingRect()
            
            # Ajustar para evitar imágenes vacías
            if target_rect.width() <= 0 or target_rect.height() <= 0:
                target_rect = self.scene.itemsBoundingRect()
            
            # 2. Crear imagen con tamaño razonable (máx 3000px)
            max_size = 3000
            aspect = target_rect.height() / target_rect.width()
            if target_rect.width() > max_size:
                target_rect.setWidth(max_size)
                target_rect.setHeight(max_size * aspect)
            
            img_size = target_rect.size().toSize()
            img = QImage(img_size, QImage.Format_ARGB32)
            img.fill(Qt.transparent)
            
            # 3. Renderizar con parámetros explícitos
            painter = QPainter(img)
            self.scene.render(
                painter,
                QRectF(0, 0, img_size.width(), img_size.height()),  # target
                target_rect  # source
            )
            painter.end()
            
            # 4. Guardar como JPEG con compresión controlada
            temp_path = os.path.join(os.path.expanduser("~"), "temp_export.jpg")
            if img.save(temp_path, "JPEG", quality=90):
                print(f"Imagen temporal generada en: {temp_path}")  # Debug
                return temp_path
                
        except Exception as e:
            print(f"Error crítico al guardar imagen: {str(e)}")
        
        return None

    def wheelEvent(self, event):
        """Control de zoom"""
        factor = 1.1 ** (event.angleDelta().y() / 120)
        self.view.scale(factor, factor)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Aplicación de Visualización GeoTIFF")
        self.setGeometry(100, 100, 1200, 900)
        
        self.init_ui()
        
    def init_ui(self):
        """Configura la ventana principal"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout()
        central_widget.setLayout(main_layout)
        
        # Crear instancia del visualizador
        self.viewer = GeoTIFFViewer(
            mosaic_dir="./mosaico_10_images/tiles_pyramid/zoom_0",
            mask_dir="./mosaico_10_images/tiles_mask_pyramid/zoom_0",
            parent=self
        )
        
        # Botón para generar PDF
        btn_layout = QHBoxLayout()
        btn_pdf = QPushButton("Exportar a PDF")
        btn_pdf.clicked.connect(self.generate_pdf)
        btn_layout.addWidget(btn_pdf)
        btn_layout.addStretch()
        
        # Añadir componentes al layout principal
        main_layout.addLayout(btn_layout)
        main_layout.addWidget(self.viewer)
    
    def generate_pdf(self):
        """Versión corregida del generador de PDF"""
        try:
            # 1. Generar imagen temporal (con debug)
            img_path = self.viewer.save_scene_to_image()
            if not img_path or not os.path.exists(img_path):
                print("Error: No se generó la imagen temporal")
                return
            
            print(f"Tamaño de la imagen: {os.path.getsize(img_path)} bytes")  # Debug
            
            # 2. Configurar PDF
            pdf_path = os.path.join(os.path.expanduser("~"), "mapa_arboles.pdf")
            c = canvas.Canvas(pdf_path, pagesize=letter)
            
            # 3. Cargar imagen verificando errores
            try:
                img = ImageReader(img_path)
                img_width, img_height = img.getSize()
                print(f"Dimensiones de la imagen: {img_width}x{img_height}")  # Debug
            except Exception as e:
                print(f"Error al cargar imagen: {str(e)}")
                return
            
            # 4. Calcular tamaño para el PDF (80% del ancho)
            pdf_width = letter[0] * 0.8
            pdf_height = pdf_width * (img_height / img_width)
            
            # 5. Posicionar centrado con margen
            x_pos = (letter[0] - pdf_width) / 2
            y_pos = letter[1] - pdf_height - 40
            
            # 6. Dibujar elementos en orden:
            #    - Imagen primero
            c.drawImage(img_path, x_pos, y_pos, width=pdf_width, height=pdf_height)
            
            #    - Título después (para que esté encima)
            c.setFont("Helvetica-Bold", 16)
            c.drawString(letter[0]/2 - 100, letter[1] - 30, "Mapa de Cobertura Arbórea")
            
            #    - Leyenda
            c.setFont("Helvetica", 10)
            c.drawString(x_pos, y_pos - 20, "Áreas verdes: Zonas con cobertura arbórea")
            
            c.showPage()
            c.save()
            
            print(f"PDF generado exitosamente en: {pdf_path}")
            
            ## 7. Limpieza opcional (comentar para debug)
            #os.remove(img_path)
            
        except Exception as e:
            print(f"Error al generar PDF: {str(e)}")

if __name__ == "__main__":
    app = QApplication([])
    
    # Verificar directorios
    
    window = MainWindow()
    window.show()
    app.exec()