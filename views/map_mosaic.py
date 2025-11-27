from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QGroupBox, QLabel, QGraphicsScene, QGraphicsView, QGraphicsPixmapItem, QToolButton, QFrame, QPushButton, QFileDialog, QRadioButton
from PySide6.QtGui import QPalette, QColor, QPainter, QPixmap, QImage, QIcon
from PySide6.QtGui import QFont
from PySide6.QtCore import Qt, QRectF, Signal, QPoint
import re
import os
from osgeo import gdal
import numpy as np
from tempfile import mkstemp
import folium
from PySide6.QtWebEngineWidgets import QWebEngineView
import json
from datetime import datetime

from core.report_generator import ReportGenerator

class GeoTIFFViewer(QWidget):
    layer_selected = Signal(str)
    def __init__(self, mosaic_dir, masks_dirs  = None, parent=None):
        super().__init__(parent)
        self.mosaic_dir = mosaic_dir
        self.masks_dirs = masks_dirs
        #self.setAutoFillBackground(True)
        self.setStyleSheet("background-color: black;")
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
        #tool_bar_layout = QHBoxLayout()
        self.zoom_in_btn = QToolButton(self)
        self.zoom_in_btn.setFixedSize(30, 30)
        self.zoom_in_btn.setIcon(QIcon("./assets/zoom_in.svg"))
        self.zoom_in_btn.setStyleSheet("""
            QToolButton {
                background-color: white;
                border-radius: 5px;
                padding: 8px;
            }
            QToolButton:hover {
                background-color: #E0E0E0;
            }
        """)


        self.zoom_out_btn = QToolButton(self)
        self.zoom_out_btn.setFixedSize(30, 30)
        self.zoom_out_btn.setIcon(QIcon("./assets/zoom_out.svg"))
        
        self.zoom_out_btn.setStyleSheet("""
            QToolButton {
                background-color: white;
                border-radius: 5px;
                padding: 8px;
            }
            QToolButton:hover {
                background-color: #E0E0E0;
            }
        """)
        
        self.layers_btn = QToolButton(self)
        self.layers_btn.setFixedSize(30, 30)
        self.layers_btn.setIcon(QIcon("./assets/layers.svg"))

        self.layers_btn.setStyleSheet("""
            QToolButton {
                background-color: white;
                border-radius: 5px;
                padding: 8px;
            }
            QToolButton:hover {
                background-color: #E0E0E0;
            }
        """)

        ## # ---------- MENÚ FLOTANTE CAPAS ----------

        self.layers_menu = QFrame(self)
        self.layers_menu.setFrameShape(QFrame.StyledPanel)
        self.layers_menu.setStyleSheet("""
            QFrame {
                background-color: white;
                border-radius: 8px;
                border: 1px solid #ccc;
            }
            QRadioButton {
                    background-color: transparent;
                    color: black;
            }
        """)

        self.layers_menu.setFixedSize(200, 120)
        self.layers_menu.hide()  # Oculto por defecto

        layout_layers = QVBoxLayout(self.layers_menu)

        self.rb_ndvi = QRadioButton("NDVI")
        self.rb_mapa = QRadioButton("MAPA")
        self.rb_def = QRadioButton("MAPA DE DEFICIENCIAS")
        #self.rb_ndvi.setStyleSheet("""
        #        QRadioButton {
        #            background-color: transparent;
        #            color: black;
        #        }
        #    """)
        # Por defecto MAPA seleccionado
        self.rb_mapa.setChecked(True)
        
        layout_layers.addWidget(self.rb_ndvi)
        layout_layers.addWidget(self.rb_mapa)
        layout_layers.addWidget(self.rb_def)


        # Conectar cambios de radio
        self.rb_ndvi.toggled.connect(lambda: self.on_layer_selected("ndvi"))
        self.rb_mapa.toggled.connect(lambda: self.on_layer_selected("rgb"))
        self.rb_def.toggled.connect(lambda: self.on_layer_selected("map_deficiencies"))
        # Iconos simples
        #self.zoom_in_btn.setText("+")
        #self.zoom_out_btn.setText("-")

        self.zoom_in_btn.setToolTip("Zoom In")
        self.zoom_out_btn.setToolTip("Zoom Out")
       
        # Acción del botón de layers
        self.layers_btn.clicked.connect(self.toggle_layers_menu)
        #self.layout.addWidget(toolbar_container)
        # Añadir vista al layout
        self.layout.addWidget(self.view)

        self.zoom_in_btn.clicked.connect(self.zoom_in)
        self.zoom_out_btn.clicked.connect(self.zoom_out)
         # Estado de zoom
        self.zoom_factor = 1.25

        # Al final de init_ui
        self.zoom_in_btn.raise_()
        self.zoom_out_btn.raise_()
        self.layers_btn.raise_()
        self.layers_menu.raise_()

    def zoom_in(self):
        self.view.scale(self.zoom_factor, self.zoom_factor)

    def zoom_out(self):
        self.view.scale(1 / self.zoom_factor, 1 / self.zoom_factor)

    def on_selected_layer(self, option):
        self.layer_selected.emit(option)

    def toggle_layers_menu(self):
        print("Load menu toggle")
        if self.layers_menu.isVisible():
            self.layers_menu.hide()
        else:
            # Obtener posición del botón dentro del widget principal
            pos = self.layers_btn.mapToParent(QPoint(0, 0))
            
            x = pos.x() + self.layers_btn.width() + 10
            y = pos.y()

            print("Menu pos:", x, y)

            self.layers_menu.move(x, y)
            self.layers_menu.show()

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
        spacing = 10
        self.zoom_out_btn.move(30, self.height() - self.zoom_out_btn.height() - 30)
        self.zoom_in_btn.move(30, self.zoom_out_btn.y() - self.zoom_in_btn.height() - spacing)
        self.layers_btn.move(30, self.zoom_in_btn.y() - self.layers_btn.height() - spacing)
        super().resizeEvent(event)
        self.view.fitInView(self.scene.itemsBoundingRect(), Qt.KeepAspectRatio)
    
    def showEvent(self, event):
        """Ajusta la vista al tamaño inicial de la ventana cuando se muestra por primera vez."""
        super().showEvent(event)
        spacing = 10
        self.zoom_out_btn.move(30, self.height() - self.zoom_out_btn.height() - 30)
        self.zoom_in_btn.move(30, self.zoom_out_btn.y() - self.zoom_in_btn.height() - spacing)
        self.layers_btn.move(30, self.zoom_in_btn.y() - self.layers_btn.height() - spacing)
        self.view.fitInView(self.scene.itemsBoundingRect(), Qt.KeepAspectRatio)

    def update_layers(self,  mosaic_dir=None, masks_dirs=None):
        """
        Actualiza las capas cargadas en el viewer.
        mosaic_dir: nueva ruta del mosaico
        masks_dirs: nuevas rutas de máscaras (lista)
        """
        if mosaic_dir:
            self.mosaic_dir = mosaic_dir
        if masks_dirs is not None:
            self.masks_dirs = masks_dirs

        # Limpiar escena anterior
        self.scene.clear()

        # Volver a cargar con las nuevas rutas
        self.load_layers()

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
        #text_label.setWordWrap(True) 
        text_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        text_label.setStyleSheet("""
            color: #000000;
            font-size: 11px;
            font-weight: 500;
        """)
        layout.addWidget(color_label)
        layout.addWidget(text_label)
        layout.addStretch()

class LegendWidget(QWidget):
    def __init__(self):
        super().__init__()

        group_box = QGroupBox("Leyenda")
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
        
        with open("./mosaicos/output_layers/leyend_colors_2.json", "r") as f:
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
                "./mosaicos/output_layers/tiles_nutritional_N_status"
                ],
            parent=self
        )
        
        layout.addWidget(self.viewer)
    
    def update_layers(self, mosaic_dir=None, masks_dirs=None):
        self.viewer.update_layers(mosaic_dir, masks_dirs)


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
        self.name_analysis_title = QLabel(name_analysis)
        self.name_analysis_title.setWordWrap(True)
        self.name_analysis_title.setStyleSheet("""
            color: #05893A;
            padding: 5px 10px;
            font-size: 15px;
            font-weight: bold;
        """)
        self.name_analysis_title.setAlignment(Qt.AlignLeft)

        # Subtítulo
        subtitle = QLabel("Resultados del Análisis")
        subtitle.setStyleSheet("""
            color: #626263;
            padding: 5px 10px;
            font-size: 12px;
            font-weight: 600;
        """)

        # Añadir widgets al contenedor
        container_layout.addWidget(self.name_analysis_title)
        container_layout.addWidget(subtitle)

        # Layout principal
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(container)

    def update_title(self, title):
        self.name_analysis_title.setText(title)

class DiagramWidget(QWidget):
    def __init__(self, title, image_path):
        super().__init__()
        layout = QVBoxLayout()

        # Contenedor con borde
        content_frame = QFrame()
        content_frame.setFrameShape(QFrame.StyledPanel)  # forma del marco
        content_frame.setFrameShadow(QFrame.Plain)       # sombra simple
      
        # Layout interno del QFrame
        content_layout = QVBoxLayout(content_frame)
        content_layout.setAlignment(Qt.AlignCenter)
        content_layout.setContentsMargins(2, 2, 2, 2)  # margen interno

        title_widget = QLabel(title)
        title_widget.setAlignment(Qt.AlignCenter)
        title_widget.setWordWrap(True)  # Habilita salto de línea
        title_widget.setStyleSheet("""
            color: #000000;
            font-size: 13px;
            font-weight: 600;
        """)

        image_label = QLabel()
        image_label.setPixmap(QPixmap(image_path).scaled(250,250, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        image_label.setAlignment(Qt.AlignCenter)
    
        content_layout.setAlignment(Qt.AlignCenter)

        content_layout.addWidget(title_widget)
        content_layout.addWidget(image_label)
   
        layout.addWidget(content_frame)

        self.setLayout(layout)

class RightPanelResults(QWidget):
    def __init__(self, name_analysis, diagram_path, main_window):
        super().__init__()

        self.main_window = main_window
        
        container = QWidget()
        container_layout = QVBoxLayout()
        container_layout.setContentsMargins(0, 0, 0, 0)  # sin márgenes laterales
        container_layout.setSpacing(0)
        
        # Espaciador arriba (por ejemplo, 20px)
        container_layout.addSpacing(30)

        self.title_results = TitleResults(name_analysis)
        container_layout.addWidget(self.title_results)

        ## Diagrama
        diagram_widget = DiagramWidget("Distribucion de  arboles con deficiencias nutricionales", diagram_path)
        container_layout.addWidget(diagram_widget)
        legend_widget = LegendWidget()
        container_layout.addWidget(legend_widget)
        report_button = QPushButton("  Generar Reporte")
        report_button.setIcon(QIcon("./assets/file.svg"))

        report_button.clicked.connect(self.generate_report)
        
        report_button.setStyleSheet("""
            QPushButton {
                color: white;
                background-color: #07C553;
                font-weight: bold;
                font-size: 16px;
                padding-top: 5px;
                padding-bottom: 5px;
            }

            QPushButton:hover {
                background-color: #05A644; /* Un verde más oscuro */
            }
            QPushButton:pressed {
                background-color: #048C38; /* Aún más oscuro al presionar */
            }
        """)

        export_button = QPushButton("  Exportar Resultados")
        export_button.setIcon(QIcon("./assets/file.svg"))
        
        export_button.setStyleSheet("""
            QPushButton {
                color: white;
                background-color: #07C553;
                font-weight: bold;
                font-size: 16px;
                padding-top: 5px;
                padding-bottom: 5px;
            }
                                    
            QPushButton:hover {
                background-color: #05A644; /* Un verde más oscuro */
            }
            QPushButton:pressed {
                background-color: #048C38; /* Aún más oscuro al presionar */
            }
        """)


        container_layout.addWidget(report_button)
        container_layout.addWidget(export_button)

        container.setLayout(container_layout)

        layout = QVBoxLayout()
        layout.addWidget(container, 0, Qt.AlignTop)
        self.setLayout(layout)

    def update_title(self, title):
        self.title_results.update_title(title)
    
    def showEvent(self, event):
        super().showEvent(event)
        name = self.main_window.analysis_data_store.name

        print("name:", name)

        if name is None:
            name =  "Análisis Ejemplo 1"
        self.update_title(name)

    def generate_report(self):
        date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_dir = self.analysis_data_store.base_dir
        print("base_dir:", base_dir)
        pdf_file = f"{base_dir}/RESULTADOS_{date_str}.pdf"
        
        report_generator = ReportGenerator()

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Guardar archivo PDF",
            pdf_file,
            "Archivos PDF (*.pdf)"
        )
        print("Path:", path)

        report_generator.create_report(path)
        

class MapTreeScreen(QWidget):
    layers_ready = Signal(str, dict)
    layer_mode = Signal(str)

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.current_layer = "RGB"
        self.layers_path = dict()
        self.setup_ui()

    def setup_ui(self):
        outer_layout = QVBoxLayout(self)
        outer_layout.setAlignment(Qt.AlignCenter)  # Centra el contenedor completo

        inner_widget = QWidget()
        inner_layout = QHBoxLayout(inner_widget)
        inner_layout.setContentsMargins(0, 0, 0, 0)
        inner_layout.setSpacing(0)  # Espacio fijo entre mapa y leyenda
        
        self.layers_ready.connect(
            self.set_layers#lambda mosaic, layers: self.mosaic_view.update_layers(mosaic, layers)
        )

        self.mosaic_view = MosaicView(self.main_window)
        
        self.mosaic_view.viewer.layer_selected.connect(self.update_mosaic)
        #self.analysis_data_store = self.main_window.analysis_data_store

        self.right_panel = RightPanelResults(name_analysis = "Análisis Ejemplo 1", 
                                        diagram_path = "./assets/diagram2.png",
                                        main_window = self.main_window)
        
        self.right_panel.setMaximumWidth(350)

        inner_layout.addWidget(self.mosaic_view, stretch=4)
        inner_layout.addWidget(self.right_panel, stretch=1)
        outer_layout.addWidget(inner_widget)   

    def update_mosaic(self, current_layer):
        if current_layer == "rgb":
            mosaic_path = f"{self.layers_path[current_layer]}/tiles"
            self.mosaic_view.update_layers(mosaic_path, None)
        elif current_layer == "ndvi":
            mosaic_path = f"{self.layers_path[current_layer]}/tiles"
            self.mosaic_view.update_layers(mosaic_path, None)
        elif current_layer == "map_deficiencies":
            mosaic_path = f'{self.layers_path["rgb"]}/tiles'
            deficientes_mask = f'{self.layers_path["map_deficiencies"]}/tiles'
            self.mosaic_view.update_layers(mosaic_path, [deficientes_mask])
        else:
            mosaic_path = f"{self.layers_path[current_layer]}/tiles"
            self.mosaic_view.update_layers(mosaic_path, None)

    def set_layers(self, mosaic, layers):
        self.layers_path = layers
        self.update_mosaic(self.current_layer)
    
 
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
