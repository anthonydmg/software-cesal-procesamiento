from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QGroupBox, QLabel, QGraphicsScene, QGraphicsView, QGraphicsPixmapItem, QToolButton
from PySide6.QtGui import QPalette, QColor, QPainter, QPixmap, QImage, QIcon
from PySide6.QtGui import QFont
from PySide6.QtCore import Qt, QRectF
import re
import os
from osgeo import gdal
import numpy as np
from tempfile import mkstemp
import folium
from PySide6.QtWebEngineWidgets import QWebEngineView
import json

class GeoTIFFViewer(QWidget):
    def __init__(self, mosaic_dir, masks_dirs  = None, parent=None):
        super().__init__(parent)
        self.mosaic_dir = mosaic_dir
        self.masks_dirs = masks_dirs
        #self.setAutoFillBackground(True)
        #self.setStyleSheet("background-color: white;")
        self.init_ui()
        self.load_layers()
    
    def init_ui(self):
        """Inicializa la interfaz del widget"""
        self.layout = QVBoxLayout(self)
        
        # Configuración de la vista de mapa
        self.scene = QGraphicsScene()
        self.view = QGraphicsView(self.scene)
        self.view.setDragMode(QGraphicsView.ScrollHandDrag)
        self.view.setRenderHint(QPainter.Antialiasing)
        self.view.setStyleSheet("""
        /* ScrollBar vertical */
        QScrollBar:vertical {
            background: #f0f0f0;
            width: 12px;
            margin: 0px;
        }
        QScrollBar::handle:vertical {
            background: #888;
            min-height: 20px;
            border-radius: 6px;
        }
        QScrollBar::handle:vertical:hover {
            background: #555;
        }
        QScrollBar::add-line:vertical,
        QScrollBar::sub-line:vertical {
            height: 0px;
            background: none;
        }

        /* ScrollBar horizontal */
        QScrollBar:horizontal {
            background: #f0f0f0;
            height: 12px;
            margin: 0px;
        }
        QScrollBar::handle:horizontal {
            background: #888;
            min-width: 20px;
            border-radius: 6px;
        }
        QScrollBar::handle:horizontal:hover {
            background: #555;
        }
        QScrollBar::add-line:horizontal,
        QScrollBar::sub-line:horizontal {
            width: 0px;
            background: none;
        }
        background: #f0f0f0;
        """)
        
        # Botones de la barra superiores
        tool_bar_layout = QHBoxLayout()
        self.zoom_in_btn = QToolButton()
        self.zoom_in_btn.setIcon(QIcon("./assets/zoom_in.svg"))
        self.zoom_out_btn = QToolButton()
        self.zoom_out_btn.setIcon(QIcon("./assets/zoom_out.svg"))
        self.zoom_in_btn.setStyleSheet("padding: 8px;")
        self.zoom_out_btn.setStyleSheet("padding: 8px;")
        # Iconos simples
        #self.zoom_in_btn.setText("+")
        #self.zoom_out_btn.setText("-")

        self.zoom_in_btn.setToolTip("Zoom In")
        self.zoom_out_btn.setToolTip("Zoom Out")

        tool_bar_layout.addWidget(self.zoom_in_btn)
        tool_bar_layout.addWidget(self.zoom_out_btn)
        tool_bar_layout.addStretch()

        toolbar_container = QWidget()
        toolbar_container.setLayout(tool_bar_layout)
        toolbar_container.setStyleSheet("""
            border-bottom: 1px solid #cccccc;
        """)

        self.layout.addWidget(toolbar_container)
        # Añadir vista al layout
        self.layout.addWidget(self.view)

        self.zoom_in_btn.clicked.connect(self.zoom_in)
        self.zoom_out_btn.clicked.connect(self.zoom_out)
         # Estado de zoom
        self.zoom_factor = 1.25

    def zoom_in(self):
        self.view.scale(self.zoom_factor, self.zoom_factor)

    def zoom_out(self):
        self.view.scale(1 / self.zoom_factor, 1 / self.zoom_factor)

    def load_layers(self):
        """Carga ambas capas (mosaico y máscara)"""
        self.load_tiles(self.mosaic_dir, is_mask=False)
        if self.masks_dirs:
            #colors = [[0, 255, 0, 128], [255, 140, 80, 128], [50, 205, 255, 128]]
            for mask_dir in self.masks_dirs:
                self.load_tiles(mask_dir, is_mask=True)
        self.view.fitInView(self.scene.itemsBoundingRect(), Qt.KeepAspectRatio)
   

    def load_tiles(self, tiles_dir, is_mask, color_mask = None):
        """Carga tiles individuales"""
        for tile_file in os.listdir(tiles_dir):
            if not tile_file.endswith(".tif"):
                continue
                
            match = re.search(r"tile_(\d+)_(\d+)\.tif", tile_file)
            if not match:
                continue
                
            x_pos, y_pos = map(int, match.groups())
            tile_path = os.path.join(tiles_dir, tile_file)
            
            qimage = self.mask_to_qimage(tile_path, color_mask) if is_mask else self.geotiff_to_qimage(tile_path)
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
        
        num_bands = ds.RasterCount
        width = ds.RasterXSize
        height = ds.RasterYSize

         # Leer las bandas
        bands = [ds.GetRasterBand(i+1).ReadAsArray() for i in range(num_bands)]
        if bands[0].dtype != np.uint8:
            bands = [(b * 255 / (b.max() or 1)).astype(np.uint8) for b in bands]
        
        if num_bands >= 4:
            rgba = np.dstack(bands[:4])
            return QImage(rgba.data, width, height, 4 * width, QImage.Format_RGBA8888).copy()
        else:
            rgb = np.dstack(bands[:3]) if num_bands >= 3 else np.dstack([bands[0]] * 3)
            return QImage(rgb.data, width, height, 3 * width, QImage.Format_RGB888).copy()

    def mask_to_qimage(self, path, color_mask = None):
        """Convierte máscara a QImage transparente"""
        ds = gdal.Open(path)
        if not ds:
            return QImage()
        
        bands = ds.RasterCount
        width = ds.RasterXSize
        height = ds.RasterYSize
        
        if bands>= 4:
            r = ds.GetRasterBand(1).ReadAsArray()
            g = ds.GetRasterBand(2).ReadAsArray()
            b = ds.GetRasterBand(3).ReadAsArray()
            a = ds.GetRasterBand(4).ReadAsArray()
            rgba = np.stack((r, g, b, a), axis=-1).astype(np.uint8)
        else:
            mask = ds.GetRasterBand(1).ReadAsArray()
            height, width = mask.shape
            rgba = np.zeros((height, width, 4), dtype=np.uint8)
            rgba[mask > 0] = color_mask if color_mask else [0, 255, 0, 128]
        
        return QImage(rgba.data, width, height, 4 * width, QImage.Format_RGBA8888).copy()

    def save_scene_to_image(self):
        """Guarda la escena actual como imagen temporal"""
        try:
            view_rect = self.view.viewport().rect()
            target_rect = self.view.mapToScene(view_rect).boundingRect()
            
            fd, temp_path = mkstemp(suffix='.png')
            os.close(fd)
            
            img = QImage(target_rect.size().toSize(), QImage.Format_ARGB32)
            img.fill(Qt.transparent)
            
            painter = QPainter(img)
            self.scene.render(painter, 
                            target=QRectF(img.rect()), 
                            source=target_rect)
            painter.end()
            
            if img.save(temp_path):
                return temp_path
            return None
            
        except Exception as e:
            print(f"Error al guardar imagen: {str(e)}")
            return None

    def wheelEvent(self, event):
        """Control de zoom"""
        factor = 1.1 ** (event.angleDelta().y() / 120)
        self.view.scale(factor, factor)
    
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.view.fitInView(self.scene.itemsBoundingRect(), Qt.KeepAspectRatio)
    
    def showEvent(self, event):
        """Ajusta la vista al tamaño inicial de la ventana cuando se muestra por primera vez."""
        super().showEvent(event)
        self.view.fitInView(self.scene.itemsBoundingRect(), Qt.KeepAspectRatio)

class LegendItem(QWidget):
    def __init__(self, color, label_text, parent = None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2,2,2,2)
        # Color square
        color_label = QLabel()
        color_label.setFixedSize(20,20)
        color_label.setStyleSheet(f"background-color: {color};")
        #pallete = color_label.palette()
        #pallete.setColor(QPalette.Window, QColor(color))
        #color_label.setAutoFillBackground(True)
        #color_label.setPalette(pallete)

        # Text Label
        text_label = QLabel(label_text)
        text_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        layout.addWidget(color_label)
        layout.addWidget(text_label)
        layout.addStretch()

class LegendWidget(QWidget):
    def __init__(self):
        super().__init__()

        group_box = QGroupBox("Leyenda de Estado Nutricional")
        group_box.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 16px;
                color: #333;
                border: 1px solid #cccccc;
                border-radius: 5px;
                margin-top: 35px;
            }

            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 5px;
                margin-left: 10px;
            }
        """)

        group_layout = QVBoxLayout(group_box)
        group_layout.setContentsMargins(10, 10, 40, 10)
        group_layout.setSpacing(12)

        leyend_data = [
            ("#00FF32", "Saludable"),
            ("#F49632", "Deficiencia Nutricional"),
            ("#00B6FF", "Exceso Nutricional")
        ]
        
        with open("./mosaicos/output_layers/leyend_colors.json", "r") as f:
            leyend_colors = json.load(f)
            print("leyend_colors:", leyend_colors)
            
        for leyend in leyend_colors:
            group_layout.addWidget(LegendItem(leyend['color_hex'], leyend['name'].replace("_", " ")))

        main_layout = QVBoxLayout(self)
        main_layout.addWidget(group_box)
        main_layout.addStretch()

class MosaicView(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        # Configuración de la vista
        
        # Cargar y mostrar las capas
        #self.setStyleSheet("background-color: black;")
        self.setup_ui()
        
        # Debug: Mostrar información de carga
    
    def setup_ui(self):
        """Configura la interfaz de usuario"""

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0) 
        self.setLayout(layout)
         # Crear instancia del visualizador
        self.viewer = GeoTIFFViewer(
            mosaic_dir="./mosaicos/output_layers/tiles_mosaic_map_layer",
            masks_dirs = [
                "./mosaicos/output_layers/tiles_nutritional_all_status"
                ],
            parent=self
        )
        
        layout.addWidget(self.viewer)

class TitleResults(QWidget):
    def __init__(self, name_analysis):
        super().__init__()

        # Contenedor con color de fondo
        container = QWidget()
        container.setStyleSheet("background-color: #B9FFD3;")

        # Layout del contenedor
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)  # Sin márgenes
        container_layout.setSpacing(0)  # Sin espacios

        # Título principal
        name_analysis_title = QLabel(name_analysis)
        name_analysis_title.setStyleSheet("""
            color: #05893A;
            padding: 5px 10px;
            font-size: 14px;
            font-weight: bold;
        """)
        name_analysis_title.setAlignment(Qt.AlignLeft)

        # Subtítulo
        subtitle = QLabel("Resultados del Análisis")
        subtitle.setStyleSheet("""
            color: #626263;
            padding: 5px 10px;
            font-size: 11px;
            font-weight: 600;
        """)

        # Añadir widgets al contenedor
        container_layout.addWidget(name_analysis_title)
        container_layout.addWidget(subtitle)

        # Layout principal
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(container)


class DiagramWidget():
    def __init__(self, title, image_path):
        layout = QVBoxLayout()
        title_widget = QLabel(title)
        title_widget.setStyleSheet("""
            color: #000000;
            font-size: 13px;
            font-weight: 600;
        """)
        image_label = QLabel()
        image_label.setPixmap(QPixmap(image_path).scaled(200,200, Qt.Keep))

class MapTreeScreen(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.setup_ui()
    
    def setup_ui(self):
        outer_layout = QVBoxLayout(self)
        outer_layout.setAlignment(Qt.AlignCenter)  # Centra el contenedor completo

        inner_widget = QWidget()
        inner_layout = QHBoxLayout(inner_widget)
        inner_layout.setContentsMargins(0, 0, 0, 0)
        inner_layout.setSpacing(0)  # Espacio fijo entre mapa y leyenda
        
        
        #self.setLayout(layout)
        self.mosaic_view = MosaicView(self.main_window)
    
        self.legend_widget = LegendWidget()

        legend_container = QWidget()
        legend_layout = QVBoxLayout()
        legend_layout.setContentsMargins(0, 0, 0, 0)  # sin márgenes laterales
        legend_layout.setSpacing(0)

        # Espaciador arriba (por ejemplo, 20px)
        legend_layout.addSpacing(30)
        
        title_results = TitleResults("Análisis Ejemplo 1")
        legend_layout.addWidget(title_results)
        legend_layout.addWidget(self.legend_widget)
        legend_container.setLayout(legend_layout)

        #self.legend_widget.setMaximumWidth(200)
        inner_layout.addWidget(self.mosaic_view, stretch=4)
        inner_layout.addWidget(legend_container, stretch=1)
        title_section_widget = QLabel("Análisis de salud del cultivo")
        font = QFont()
        font.setPointSize(18)  # Ajusta el tamaño según tu diseño en Figma
        font.setBold(True)
        title_section_widget.setFont(font)
        title_section_widget.setStyleSheet("padding-left: 15px;")
        outer_layout.addWidget(title_section_widget)
        outer_layout.addWidget(inner_widget)    
        #layout.addWidget(self.mosaic_view, stretch=4)
        #layout.addSpacing(10)
        #layout.addWidget(self.legend_widget, stretch=1)
        #label = QLabel()


class MapTrees(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout()
        
        # Crear un mapa con Folium
        m = folium.Map(location=[-13.881719661927868, -73.03486801134967], 
                       zoom_start=18,
                        max_zoom=22, 
                        tiles=f"https://api.mapbox.com/styles/v1/mapbox/satellite-v9/tiles/{{z}}/{{x}}/{{y}}?access_token={MAPBOX_TOKEN}",
                        attr="Mapbox")
        
        # Guardar el mapa en un archivo temporal
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
        
        # Mostrar el mapa en QWebEngineView
        self.web_view = QWebEngineView()
        self.web_view.setHtml(html_page)
        
        layout.addWidget(self.web_view)
        self.setLayout(layout)
