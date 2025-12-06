from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QGroupBox, QLabel, QGraphicsScene, QGraphicsView, QGraphicsPixmapItem, QToolButton, QFrame, QPushButton, QFileDialog, QRadioButton, QToolTip
from PySide6.QtGui import QPalette, QColor, QPainter, QPixmap, QImage, QIcon
from PySide6.QtGui import QFont
from PySide6.QtCore import Qt, QRectF, Signal, QPoint, QEvent
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
import re
import os
from osgeo import gdal
import numpy as np
from tempfile import mkstemp
import folium
from PySide6.QtWebEngineWidgets import QWebEngineView
import json
from datetime import datetime
import cv2
import copy
from core.report_generator import ReportGenerator

class ColorTreeState:
    MAP = {
        "SALUDABLE": {
            "color_hex": "#00FF32",
            "color_rgb": (0, 255, 50)
        },
        "DEFICIENCIA": {
            "color_hex": "#BFF700",
            "color_rgb": (191, 247, 0)
        }
    }

    @staticmethod
    def get_rgb(name: str):
        return ColorTreeState.MAP.get(name.upper(), {"color_rgb": (0, 255, 50)})['color_rgb']
    


class ColorNdvi:

    @staticmethod
    def get_color(ndvi_value):
        # Define segments (low, high, color_low(RGB), color_high(RGB))

        color_dark_orange = np.array([220, 100, 0], dtype=np.float32)
        color_soft_orange = np.array([220, 170, 0], dtype=np.float32) # Intermedio
        color_yellow      = np.array([220, 240, 0], dtype=np.float32)
        color_lime        = np.array([120, 200, 0], dtype=np.float32) # Intermedio hacia verde
        color_green       = np.array([20, 80, 0], dtype=np.float32)

        color_scale = [
            # --- RANGO 0.8 a 0.9 (Dividido en dos partes) ---
            # De 0.80 a 0.85: Naranja oscuro a Naranja suave
            (0.80, 0.85, color_dark_orange, color_soft_orange),
            
            # De 0.85 a 0.90: Naranja suave a Amarillo
            (0.85, 0.90, color_soft_orange, color_yellow),

            # --- RANGO 0.9 a 1.0 (Dividido en dos partes) ---
            # De 0.90 a 0.95: Amarillo a Verde Lima (hace que el 0.92 se vea muy distinto al 0.98)
            (0.90, 0.95, color_yellow, color_lime),
            
            # De 0.95 a 1.00: Verde Lima a Verde Oscuro
            (0.95, 1.00, color_lime, color_green),
        ]

        segments = [
            (-1.0, -0.6, np.array([0, 0, 0], dtype=np.float32),   np.array([0, 0, 251], dtype=np.float32)),   # black -> blue
            (-0.6, 0.0, np.array([0, 0, 251], dtype=np.float32), np.array([220, 0, 251], dtype=np.float32)), # blue -> purple
            (0.0, 0.5, np.array([220, 0, 251], dtype=np.float32), np.array([220, 0, 120], dtype=np.float32)), # purple -> pink
            (0.5, 0.8, np.array([220, 0, 120], dtype=np.float32),  np.array([220, 100, 0], dtype=np.float32)),  # pink -> dark orange
            (0.80, 0.85, color_dark_orange, color_soft_orange),
            
            # De 0.85 a 0.90: Naranja suave a Amarillo
            (0.85, 0.90, color_soft_orange, color_yellow),

            # --- RANGO 0.9 a 1.0 (Dividido en dos partes) ---
            # De 0.90 a 0.95: Amarillo a Verde Lima (hace que el 0.92 se vea muy distinto al 0.98)
            (0.90, 0.95, color_yellow, color_lime),
            
            # De 0.95 a 1.00: Verde Lima a Verde Oscuro
            (0.95, 1.00, color_lime, color_green),
        ]

        # Assign for each segment
        for low, high, c_low, c_high in segments:
            if ((ndvi_value >= low) & (ndvi_value < high)) or (high == 1.0 and ndvi_value >=1.0):
                t = (ndvi_value - low) / (high - low)
            # Interpolate per-channel
                color = (c_low * (1.0 - t) + c_high * t).astype(np.uint8) 
                return list(color)
        return [0, 0, 0]

class MapGraphicsView(QGraphicsView):
    def __init__(self, scene, parent = None):
        super().__init__(parent)
        self.setScene(scene)
        # IMPORTANTE para hover
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self.controller = parent

    
    def mouseMoveEvent(self, event):
        if self.controller is not None:
            pos_scene = self.mapToScene(event.pos())
            print("pos_scene:", pos_scene)
            self.controller.handle_hover(pos_scene, event.globalPos())
        super().mouseMoveEvent(event)

class FloatingToolTip(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Tool |
    Qt.WindowType.FramelessWindowHint |
    Qt.WindowType.WindowStaysOnTopHint)
        self.setFont(QFont("Segoe UI", 10))
        self.setMargin(6)
        self.setStyleSheet("""
            QLabel {
                background-color: #f0f7ff;
                border: 1px solid #a7c5ff;
                border-radius: 6px;
                color: #003366;
            }
        """)
        self.hide()

    def show_at(self, global_pos, html_text, offset=QPoint(12, 16)):
        self.setText(html_text)
        self.adjustSize()
        self.move(global_pos + offset)
        self.show()
        self.raise_()

    def hide_tooltip(self):
        self.hide()

class GeoTIFFViewer(QWidget):
    layer_selected = Signal(str)
    def __init__(self, layers_base_dir = None, parent=None):
        super().__init__(parent)
        #self.layers_base_dir = layers_base_dir
        self.rgb_items = []
        self.ndvi_items = []
        self.trees_masks_items = []
        self.trees_mask_hover = []
        self.avg_ndvi_masks_items = []
        self.active_mask_hover = None
        self.floating_tooltip = None
        #self.setAutoFillBackground(True)
        self.setStyleSheet("background-color: black;")
        self.init_ui()
        if layers_base_dir:
            self.update_layers_map(layers_base_dir)
            self.show_mosaic_rgb()
    

    def init_ui(self):
        """Inicializa la interfaz del widget"""
        self.layout = QVBoxLayout(self)
        # Configuración de la vista de mapa
        self.scene = QGraphicsScene()
        self.view = MapGraphicsView(self.scene, self)
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
        self.floating_tooltip = FloatingToolTip(self.view.viewport())
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

        self.rb_ndvi = QRadioButton("MAPA NDVI")
        self.rb_mapa = QRadioButton("MAPA")
        self.rb_def = QRadioButton("MAPA DE DEFICIENCIAS")
        self.rb_ndvi_avg = QRadioButton("MAPA NDVI PROMEDIO")
        #self.rb_ndvi.setStyleSheet("""
        #        QRadioButton {
        #            background-color: transparent;
        #            color: black;
        #        }
        #    """)
        # Por defecto MAPA seleccionado
        self.rb_mapa.setChecked(True)
        layout_layers.addWidget(self.rb_mapa)
        layout_layers.addWidget(self.rb_ndvi)
        layout_layers.addWidget(self.rb_def)
        layout_layers.addWidget(self.rb_ndvi_avg)


        # Conectar cambios de radio
        self.rb_ndvi.toggled.connect(lambda: self.show_mosaic_ndvi())
        self.rb_mapa.toggled.connect(lambda: self.show_mosaic_rgb())
        self.rb_def.toggled.connect(lambda: self.show_deficients_map())
        self.rb_ndvi_avg.toggled.connect(lambda: self.show_avg_ndvi_masks())
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
    
    def event(self, e):
        if e.type() in (QEvent.Type.WindowDeactivate, QEvent.Type.ApplicationDeactivate):
            if self.floating_tooltip:
                self.floating_tooltip.hide_tooltip()
        return super().event(e)

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
                self.load_tiles(mask_dir, is_mask=True, z_value = 1)
        self.view.fitInView(self.scene.itemsBoundingRect(), Qt.KeepAspectRatio)
   

    def load_tiles(self, tiles_dir, is_mask = False, color_mask = None, z_value = 0):
        """Carga tiles individuales"""
        items = []
        
        for tile_file in os.listdir(tiles_dir):
            if not tile_file.endswith(".tif"):
                continue
                
            match = re.search(r"tile_(\d+)_(\d+)\.tif", tile_file)
            if not match:
                continue
                
            x_pos, y_pos = map(int, match.groups())
            tile_path = os.path.join(tiles_dir, tile_file)
            
            qimage = self.geotiff_mask_to_qimage(tile_path, color_mask) if is_mask else self.geotiff_to_qimage(tile_path)
            if not qimage.isNull():
                item = QGraphicsPixmapItem(QPixmap.fromImage(qimage))
                item.setPos(x_pos, y_pos)
                if is_mask:
                    item.setZValue(z_value)
                else:
                    item.setZValue(z_value)
                self.scene.addItem(item)
                items.append(item)
            
        return items

    
    def read_trees_results(self, trees_result_file):
        
        with open(trees_result_file, "r") as fp:
            trees_results = json.load(fp)
        
        for trees_r in trees_results:
            mask_path = trees_r['mask_path']
            mask_file = os.path.basename(mask_path) 
           
            match = re.search(r"tree_(\d+)_(\d+)\.png", mask_file)
            if not match:
                continue
            
            x_pos, y_pos = map(int, match.groups())
            
            mask = cv2.imread(mask_path)
            mask = mask.astype(np.uint8)
            
            if mask.ndim == 3 and mask.shape[-1] > 1:
                mask = cv2.cvtColor(mask, cv2.COLOR_BGR2GRAY)

            if mask.shape[-1] == 1:
                mask = mask.squeeze()

            height, width = mask.shape

            trees_r['corner'] = [x_pos, y_pos]
            trees_r['qbbox'] = QRectF(x_pos, y_pos, width, height)
            trees_r['mask'] = mask

            # Items de mascaras de deficiencias
            tree_class = trees_r['class']
            color_class = ColorTreeState.get_rgb(tree_class)

            # Agregar transparencia
            color_class = list(color_class).copy()
            color_class = color_class + [128]

            qimage = self.mask_to_qimage(mask = mask, color_mask = color_class)
            trees_r['class_mask_qimage'] = qimage
            item = QGraphicsPixmapItem(QPixmap.fromImage(qimage))
            item.setPos(x_pos, y_pos)

            trees_r['class_mask_item'] = item

            # Items de mascaras de ndvi promedio

            avg_ndvi = trees_r["avg_ndvi"]
            color_ndvi = ColorNdvi.get_color(avg_ndvi)
            color_ndvi = color_ndvi + [200]
            print("color_ndvi:", color_ndvi)
            qimage_ndvi = self.mask_to_qimage(mask = mask, color_mask = color_ndvi)

            item_ndvi = QGraphicsPixmapItem(QPixmap.fromImage(qimage_ndvi))
            item_ndvi.setPos(x_pos, y_pos)

            trees_r['avg_ndvi_mask'] = item_ndvi

        return trees_results

        
    def load_trees_masks(self, trees_results, z_value = 1):
        masks_items = []
        
        for trees_r in trees_results:
            class_mask_item = trees_r['class_mask_item']
            class_mask_item.setZValue(z_value)
            self.scene.addItem(class_mask_item)
            masks_items.append(class_mask_item)
        
        return masks_items
    

    def load_trees_ndvi_avg(self, trees_results, z_value = 1):
        masks_items = []
        
        for trees_r in trees_results:
            item_ndvi = trees_r['avg_ndvi_mask']
            item_ndvi.setZValue(z_value)
            self.scene.addItem(item_ndvi)
            masks_items.append(item_ndvi)
        
        return masks_items


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

    def geotiff_mask_to_qimage(self, path, color_mask = None):
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

    def mask_to_qimage(self, mask = None, path = None, color_mask = None):
        
        if mask is None:
            mask = cv2.imread(path)
            mask = mask.astype(np.uint8)
        
        if mask.ndim == 3 and mask.shape[-1] > 1:
            mask = cv2.cvtColor(mask, cv2.COLOR_BGR2GRAY)

        if mask.shape[-1] == 1:
            mask = mask.squeeze()

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
    
    def update_layers_map(self, layers_base_dir):
        self.layers_base_dir = layers_base_dir
        
        # Limpiar escena anterior
        self.scene.clear()

        # Volver a cargar con las capas
       
        # Cargar Mosiaco RGB
        mosaic_rgb = f"{layers_base_dir}/mosaic/rgb/tiles"
        self.rgb_items = self.load_tiles(mosaic_rgb)

        # Cargar Mosiaco NDVI
        mosaic_ndvi = f"{layers_base_dir}/mosaic/ndvi/tiles"
        self.ndvi_items = self.load_tiles(mosaic_ndvi, z_value=1)

        # Cargar Mascaras de Arboles con Calificaciones

        trees_result_file = f"{layers_base_dir}/mosaic/trees/trees_results.json"

        trees_results = self.read_trees_results(trees_result_file)

        self.trees_masks_items = self.load_trees_masks(trees_results, z_value = 2)

        # Inicializar hover de las mascaras
        self.trees_mask_hover = trees_results

        self.avg_ndvi_masks_items = self.load_trees_ndvi_avg(trees_results, z_value = 4)
        
    
    def contains_masks(self, pos_scene, mask_hover):
        x = pos_scene.x()
        y = pos_scene.y()

        x_min, y_min = mask_hover['corner']
        mask = mask_hover['mask']
        h, w = mask.shape

        x_pos, y_pos = int(x), int(y)
        x_pos = min(max(x_pos - x_min, 0), w - 1)
        y_pos = min(max(y_pos - y_min, 0), h - 1)
        return mask[y_pos, x_pos] > 0
        #x_pos = 

    
    def handle_hover(self, pos_scene, pos_global):
        # 1. Buscar si hay máscara bajo el mouse
        hovered_mask = None
        for m in self.trees_mask_hover:
            if m["qbbox"].contains(pos_scene) and self.contains_masks(pos_scene, m):
                hovered_mask = m
                break

        # 2. Si no hay máscara -> ocultar solo si antes había una
        if hovered_mask is None:
            if getattr(self, "active_mask", None) is not None:
                self.active_mask["hover_item"].setVisible(False)
                self.active_mask = None
                if self.floating_tooltip:
                    self.floating_tooltip.hide_tooltip()
                #QToolTip.hideText()
            return
        
        # 3. Si es la misma máscara que ya está activa -> NO volver a llamar tooltip
        if getattr(self, "active_mask", None) is hovered_mask:
            return

        # 4. Ocultar la máscara anterior si fue otra
        if getattr(self, "active_mask", None) is not None and self.active_mask is not hovered_mask:
            self.active_mask["hover_item"].setVisible(False)

        # 5. Crear hover_item si no existe
        if ("hover_item" not in hovered_mask) or (hovered_mask["hover_item"] is None):
            qimage = hovered_mask['class_mask_qimage'].copy()
            item = QGraphicsPixmapItem(QPixmap.fromImage(qimage))
            x_pos, y_pos = hovered_mask['corner']
            item.setPos(x_pos, y_pos)
            item.setZValue(3)
            self.scene.addItem(item)
            hovered_mask["hover_item"] = item

        hovered_mask["hover_item"].setVisible(True)

        # 6. Tooltip solo cuando cambia de máscara
        class_str = hovered_mask['class']
        avg_ndvi = round(hovered_mask["avg_ndvi"], 3)
        state = class_str.capitalize() if class_str.upper() == "SALUDABLE" else "Con " + class_str.capitalize()

        html = f"""
            <div style="
                background-color:#f0f7ff;
                border:1px solid #a7c5ff;
                border-radius:6px;
                padding:8px;
                color:#003366;
            ">
                <div style="font-size:13px; font-weight:bold; margin-bottom:4px;">
                    {hovered_mask['name']}
                </div>

                <div style="font-size:12px;">
                    <b>Estado:</b> {state}<br>
                    <b>NDVI Promedio:</b> {avg_ndvi}
                </div>
            </div>
        """

        self.floating_tooltip.show_at(pos_global, html)


        #QToolTip.showText(pos_global, html, msecShowTime=100000)

        self.active_mask = hovered_mask
            
        
        #QToolTip.hideText()

    def show_mosaic_rgb(self):
        
        for item in self.rgb_items:
            item.setVisible(True)
        
        for item in self.ndvi_items:
            item.setVisible(False)
        
        for item in self.trees_masks_items:
            item.setVisible(False)

        for item in self.avg_ndvi_masks_items:
            item.setVisible(False)

    def show_mosaic_ndvi(self):
        
        for item in self.rgb_items:
            item.setVisible(False)
        
        for item in self.ndvi_items:
            item.setVisible(True)
        
        for item in self.trees_masks_items:
            item.setVisible(False)
        
        for item in self.avg_ndvi_masks_items:
            item.setVisible(False)
    

    def show_deficients_map(self):
    
        for item in self.rgb_items:
            item.setVisible(True)
        
        for item in self.ndvi_items:
            item.setVisible(False)
        
        for item in self.trees_masks_items:
            item.setVisible(True)

        for item in self.avg_ndvi_masks_items:
            item.setVisible(False)

        #return super().show()

    def show_avg_ndvi_masks(self):
        for item in self.rgb_items:
            item.setVisible(True)
        
        for item in self.ndvi_items:
            item.setVisible(False)
        
        for item in self.trees_masks_items:
            item.setVisible(False)

        for item in self.avg_ndvi_masks_items:
            item.setVisible(True)


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
            layers_base_dir="./analisis/prueba-biochumbi-150-oct-test",
            parent=self
        )
        
        layout.addWidget(self.viewer)
    
    def update_layers(self, mosaic_dir=None, masks_dirs=None):
        self.viewer.update_layers(mosaic_dir, masks_dirs)

    def update_layers_map(self, layers_base_dir):
        self.viewer.update_layers_map(layers_base_dir)

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


class StatCard(QFrame):
    def __init__(self, title: str, value: int, parent=None):
        super().__init__(parent)

        # Configurar borde, fondo y esquinas redondeadas
        #self.setFrameShape(QFrame.StyledPanel)
        self.setObjectName("StatCardFrame")   # ← ID único

        self.setStyleSheet("""
            #StatCardFrame {
                background-color: #FFFFFF;
                border: 2px solid #CCCCCC;
                border-radius: 18px;
                padding-top: 5px;
            }
        """)

        # Título
        lbl_title = QLabel(title)
        lbl_title.setAlignment(Qt.AlignCenter)
        lbl_title.setFont(QFont("Segoe UI", 13))
        lbl_title.setStyleSheet("color: #0A281A;")

        # Valor
        lbl_value = QLabel(str(value))
        lbl_value.setAlignment(Qt.AlignCenter)
        lbl_value.setFont(QFont("Segoe UI", 34, QFont.Bold))
        lbl_value.setStyleSheet("color: #0A281A;")

        # Layout
        layout = QVBoxLayout(self)
        layout.addWidget(lbl_title)
        layout.addWidget(lbl_value)
        layout.setContentsMargins(20, 15, 20, 15)


class DonutChartWidget(QWidget):
    def __init__(self, healthy=65, deficient=35, parent=None):
        super().__init__(parent)

        self.healthy = healthy
        self.deficient = deficient
        self.percentage_healthy = round(healthy * 100 / (healthy + deficient), 1) 
        self.percentage_deficient = round(deficient * 100 / (healthy + deficient),1) 

        # Para una mejor calidad en pantallas HiDPI
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMinimumSize(200, 200)

    # =================================================
    #                  DIBUJAR DONUT
    # =================================================
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        size = min(w, h)

        cx = w / 2
        cy = h / 2
        radius = size * 0.40
        thickness = radius * 0.30

        rect = QRectF(
            cx - radius,
            cy - radius,
            radius * 2,
            radius * 2
        )

        # ========================
        # Arcos (Healthy / Deficient)
        # ========================
        start_angle = 0#90 * 48

        healthy_angle = int(360 * (self.percentage_healthy / 100) * 16)
        deficient_angle = int(360 * (self.percentage_deficient / 100) * 16)

        # HEALTHY (verde)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#22A529"))
        p.drawPie(rect, start_angle, healthy_angle)

        # DEFICIENT (amarillo)
        p.setBrush(QColor("#FFC000"))
        p.drawPie(rect, start_angle + healthy_angle, deficient_angle)

        # ========================
        # agujero interior (donut)
        # ========================
        inner_radius = radius - thickness
        hole = QRectF(
            cx - inner_radius,
            cy - inner_radius,
            inner_radius * 2,
            inner_radius * 2
        )

        p.setBrush(QColor(self.palette().window().color()))
        p.drawEllipse(hole)

        # ==================================================
        #                   TEXTOS
        # ==================================================
        def draw_text(center_x, center_y, text, size_ratio, bold=False, color=QColor("black")):
            font = QFont("Segoe UI", int(size * size_ratio))
            font.setBold(bold)
            p.setFont(font)
            p.setPen(color)

            p.drawText(
                QRectF(center_x - radius, center_y - radius, radius*2, radius*2),
                Qt.AlignCenter,
                text
            )
        # TEXTOS IZQUIERDA (Healthy)
        left_x = cx #- radius * 0.10
        top_left_y = cy - radius * 0.50

        print("left_x:", left_x)
        print("top_left_y:", top_left_y)
        draw_text(left_x, top_left_y, "Saludable", 0.03, True, QColor("#22A529"))
        draw_text(left_x, top_left_y + radius * 0.15, f"{self.percentage_healthy}%", 0.04, True, QColor("black"))
        draw_text(left_x, top_left_y + radius * 0.30, f"({self.healthy} Árboles)", 0.03, False, QColor("gray"))

        # TEXTOS DERECHA (Deficient)
        right_x = cx #+ radius * 0.90
        top_right_y = cy + radius * 0.10

        draw_text(right_x, top_right_y, "Con Deficiencia",  0.03, True, QColor("#FFC000"))
        draw_text(right_x, top_right_y + radius * 0.15, f"{self.percentage_deficient}%", 0.04, True, QColor("black"))
        draw_text(right_x, top_right_y + radius * 0.30, f"({self.deficient} Árboles)", 0.03  , False, QColor("gray"))

    # =================================================
    #       ACTUALIZAR VALORES EXTERNAMENTE
    # =================================================
    def update_values(self, healthy, deficient):
        self.healthy = healthy
        self.deficient = deficient
        
        self.percentage_healthy = round(healthy * 100 / (healthy + deficient), 2) 
        self.percentage_deficient = round(deficient * 100 / (healthy + deficient),2) 
        self.update()

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
        container_layout.addSpacing(15)

        layers_base_dir="./analisis/prueba-biochumbi-150-oct-test"
        trees_results_path = f"{layers_base_dir}/mosaic/trees/trees_results.json"

        with open(trees_results_path, "r") as f:
            trees_result = json.load(f)

        sal_trees = [ r for r in trees_result if r['class'] == "saludable"]
        def_trees = [ r for r in trees_result if r['class'] == "deficiencia"]
        ## Diagrama
        count_trees_card = StatCard("Total de Arboles Detectados", len(trees_result))
        diagram_widget = DonutChartWidget(healthy=len(sal_trees), deficient=len(def_trees)) # 
        
        #diagram_widget = DiagramWidget("Distribucion de  arboles con deficiencias nutricionales", diagram_path)
        container_layout.addWidget(count_trees_card)
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
    layers_ready = Signal(str)
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
            self.load_layers_map#lambda mosaic, layers: self.mosaic_view.update_layers(mosaic, layers)
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
            self.mosaic_view.update_layers(mosaic_path, None)
        else:
            mosaic_path = f"{self.layers_path[current_layer]}/tiles"
            self.mosaic_view.update_layers(mosaic_path, None)


    def update_mosaic_view(self, layers_path):
        self.mosaic_view.update_layers_map(layers_path)

    def set_layers(self, mosaic, layers):
        self.layers_path = layers
        self.update_mosaic(self.current_layer)
    
    def load_layers_map(self, layers_path):
        self.layers_path = layers_path
        self.update_mosaic_view(self.layers_path)

 
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
