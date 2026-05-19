from PySide6.QtWidgets import QWidget, QScrollArea, QVBoxLayout, QLabel, QHBoxLayout, QSizePolicy, QPushButton, QSpacerItem, QFrame, QFileDialog
from PySide6.QtCore import Qt, QRectF, QSize
from PySide6.QtGui import QIcon, QColor, QPixmap, QFontMetrics, QPainterPath, QPainter, QFont
from PySide6.QtWidgets import QGraphicsDropShadowEffect
from PySide6.QtCore import QStandardPaths
from core.constants import DEFAULT_PROCESS_CONFIG
from core.utils import resource_path
from views.dialog_new_analysis import NewAnalysisDialog
import json
from views.dialog_new_analysis import AnalysisData
import os
import shutil
from datetime import datetime
import uuid


class TarjetaLogo(QLabel):
    def __init__(self, ruta_imagen):
        super().__init__()
        # Estilo: Fondo blanco, borde suave y esquinas redondeadas
        self.setStyleSheet("""
            background-color: white;
            border: 1px solid #e0e0e0;
            border-radius: 8px;
            padding: 5px;
        """)
        self.setFixedSize(90, 80) # Tamaño fijo para uniformidad
        self.setAlignment(Qt.AlignCenter)
        
        # Cargar y escalar imagen
        pixmap = QPixmap(ruta_imagen)
        if not pixmap.isNull():
            self.setPixmap(pixmap.scaled(
                70, 70, Qt.KeepAspectRatio, Qt.SmoothTransformation
            ))
        else:
            self.setText("Logo") # Fallback si no encuentra la imagen

class SeccionInformativa(QWidget):
    def __init__(self, titulo, logos):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        
        # Título superior
        lbl_titulo = QLabel(titulo)
        lbl_titulo.setAlignment(Qt.AlignCenter)
        lbl_titulo.setStyleSheet("""
            color: #7f8c8d; 
            font-weight: bold; 
            font-size: 10px;
            letter-spacing: 1px;
        """)
        layout.addWidget(lbl_titulo)
        
        # Contenedor horizontal para los logos
        layout_logos = QHBoxLayout()
        layout_logos.setSpacing(10)
        layout_logos.addStretch() # Empuja logos al centro
        for img in logos:
            layout_logos.addWidget(TarjetaLogo(img))
        layout_logos.addStretch() # Empuja logos al centro
        
        layout.addLayout(layout_logos)

class VentanaFooter(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Footer Estilizado")
        self.setMinimumWidth(700)
        #self.setStyleSheet("background-color: #f4f7f6;") # Color de fondo suave
        
        # Layout principal horizontal
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(30, 20, 30, 20)
        
        # SECCIÓN IZQUIERDA
        izq = SeccionInformativa(
            "DESARROLLADO POR:",
            [resource_path(os.path.join("assets", "inictel-uni-logo.png")), 
             #resource_path(os.path.join("assets", "cesal-logo.png")),
             #resource_path(os.path.join("assets", "CITE_logo.jpg"))
             ] # Cambia por tus rutas
        )

        med = SeccionInformativa(
            "EN CONVENIO CON:",
            [resource_path(os.path.join("assets", "cesal-logo.png")), 
             #resource_path(os.path.join("assets", "cesal-logo.png")),
             #resource_path(os.path.join("assets", "CITE_logo.jpg"))
             ] # Cambia por tus rutas
        )

        # SEPARADOR VERTICAL (La mejor forma)
        linea = QFrame()
        linea.setFrameShape(QFrame.VLine)
        linea.setFrameShadow(QFrame.Plain)
        linea.setStyleSheet("color: #d1d1d1;") # Color de la línea
        linea.setFixedWidth(1)
        
        # SECCIÓN DERECHA
        der = SeccionInformativa(
            "FINANCIADO POR:",
            [resource_path(os.path.join("assets", "AECID_logo.svg"))] # Cambia por tu ruta
        )
        
        # Agregar al layout con proporciones
        main_layout.addWidget(izq, stretch=1)
        #main_layout.addWidget(linea)
        main_layout.addWidget(med)
        #main_layout.addWidget(linea)
        main_layout.addWidget(der, stretch=1)

def rounded_top_pixmap(image_path, radius, size):
    """Carga la imagen, la escala completa y le aplica solo esquinas superiores redondeadas."""
    # Escalar manteniendo toda la imagen visible
    pixmap = QPixmap(image_path).scaled(size.width(), size.height(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    
    # Fondo transparente para que respete esquinas
    rounded = QPixmap(size)
    rounded.fill(Qt.transparent)

    painter = QPainter(rounded)
    painter.setRenderHint(QPainter.Antialiasing)

    # Crear path con solo esquinas superiores redondeadas
    path = QPainterPath()
    path.moveTo(0, radius)
    path.quadTo(0, 0, radius, 0)  # esquina sup. izq.
    path.lineTo(size.width() - radius, 0)
    path.quadTo(size.width(), 0, size.width(), radius)  # esquina sup. der.
    path.lineTo(size.width(), size.height())
    path.lineTo(0, size.height())
    path.closeSubpath()

    painter.setClipPath(path)

    # Centrar la imagen
    x = (size.width() - pixmap.width()) // 2
    y = (size.height() - pixmap.height()) // 2
    painter.drawPixmap(x, y, pixmap)
    painter.end()

    return rounded

class RoundedImageLabel(QLabel):
    def __init__(self, image_path, radius):
        super().__init__()
        self.image_path = image_path
        self.radius = radius
        self.setFixedSize(200, 180)  # Tamaño fijo
        self.setPixmap(rounded_top_pixmap(image_path, radius, self.size()))


class AnalysisCard(QWidget):
    def __init__(self, 
                 image_path, 
                 title, 
                 image_count, 
                 creation_date,
                 base_dir, 
                 on_click = None,
                 on_delete=None,  # nuevo callback 
                 parent = None):
        super().__init__()

        self.on_click = on_click
        self.on_delete = on_delete
        self.base_dir = base_dir
        self.setMaximumWidth(200)

        # Layout principal
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)
        
        # Marco con borde
        frame = QFrame()
        frame.setObjectName("cardFrame")
        frame.setStyleSheet("""
            QFrame#cardFrame {
                background-color: black;
                border: 1px solid #dcdcdc;
                border-radius: 8px;
            }
            QFrame#cardFrame:hover {
                border: 1px solid #a0a0a0;
            }
        """)
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(0, 0, 0, 0)
        frame_layout.setSpacing(10)

        # --- Contenedor superior con imagen y botón borrar ---
        top_frame = QFrame()
        top_layout = QHBoxLayout(top_frame)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(0)

        img_label = RoundedImageLabel(image_path, 8)
        img_label.setAlignment(Qt.AlignCenter)
        img_label.setStyleSheet("""
            background-color: transparent;
            border-top-left-radius: 8px;
            border-top-right-radius: 8px;
        """)

        # Botón de eliminar (icono tacho)
        delete_btn = QPushButton()
        delete_btn.setIcon(QIcon(resource_path(os.path.join("assets", "trash.svg"))))  # coloca tu ícono de tacho
        delete_btn.setIconSize(QSize(16,16))
        delete_btn.setFixedSize(24,24)
        delete_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255,255,255,120);
                border-radius: 4px;
            }
            QPushButton:hover {
                background: red;
            }
        """)
        delete_btn.clicked.connect(self.confirm_delete)

         # Añadir imagen y botón en misma fila
        top_layout.addWidget(img_label)
        top_layout.addWidget(delete_btn, alignment=Qt.AlignTop | Qt.AlignRight)

        
        #frame_layout.addWidget(img_label)
        
        frame_layout.addWidget(top_frame)
        # --- Contenedor inferior con texto ---
        text_frame = QFrame()
        text_frame.setStyleSheet("""
            QFrame {
                background-color: white;
                border-bottom-left-radius: 8px;
                border-bottom-right-radius: 8px;
            }
        """)
        text_layout = QVBoxLayout(text_frame)
        text_layout.setContentsMargins(8,8,8,8)

        title_label = QLabel(title)
        title_label.setWordWrap(True)
        title_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        title_label.setAlignment(Qt.AlignLeft)
        title_label.setMaximumWidth(180)
        # Calcular elipsis
        #fm = QFontMetrics(title_label.font())
        #elided_text = fm.elidedText(title, Qt.ElideRight, 120)  # 180 px de ancho máximo
        #title_label.setText(elided_text)

        # Tooltip para mostrar el texto completo
        #if elided_text != title:
        #    title_label.setToolTip(title)

        title_label.setStyleSheet("""
            color: black;
            font-size: 16px; 
            font-weight: bold; 
        """)

        text_layout.addWidget(title_label)
        ## Informacion Extra
        info_images_label = QLabel(f"{image_count} imágenes ")
        info_images_label.setStyleSheet("color: gray; font-size: 11px; font-weight: 600;")
        info_date_label = QLabel(f"Fecha de creacion: {creation_date}")
        info_date_label.setStyleSheet("color: gray; font-size: 11px; font-weight: 600;")

        text_layout.addWidget(info_images_label)
        text_layout.addWidget(info_date_label)
        frame_layout.addWidget(text_frame)
        #layout.addWidget(img_label)
        #layout.addWidget(text_frame)
        layout.addWidget(frame)

    def mousePressEvent(self, event):
        print("Ir a otro projecto")
        self.on_click(self.base_dir)
        super().mousePressEvent(event)

    # def confirm_delete(self):
    #     from PySide6.QtWidgets import QMessageBox
    #     reply = QMessageBox.question(
    #         None,
    #         "Confirmar eliminación",
    #         "¿Estás seguro de eliminar este análisis?",
    #         QMessageBox.Yes | QMessageBox.No
    #     )
    #     if reply == QMessageBox.Yes and self.on_delete:
    #         self.on_delete(self.base_dir)  # ejecutar callback para borrar
    #         print("Elminar Analisis")

    
    def confirm_delete(self):
        from PySide6.QtWidgets import QMessageBox
        
        # 1. Instanciamos el objeto en lugar de usar el método estático
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Confirmar eliminación")
        msg_box.setText("¿Estás seguro de eliminar este análisis?")
        msg_box.setIcon(QMessageBox.Icon.Warning) # Agrega un icono de advertencia nativo
        msg_box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        
        # 2. Forzamos un estilo limpio para evitar la herencia oscura
        msg_box.setStyleSheet("""
            QMessageBox {
                background-color: #ffffff; /* Fondo blanco forzado */
            }
            QLabel {
                color: #1f2937; /* Texto gris muy oscuro/casi negro */
                font-size: 13px;
            }
            QPushButton {
                background-color: #f3f4f6;
                color: #1f2937;
                padding: 6px 16px;
                border-radius: 4px;
                border: 1px solid #d1d5db;
                min-width: 60px;
            }
            QPushButton:hover {
                background-color: #e5e7eb;
            }
        """)
        
        # 3. Ejecutamos el diálogo y capturamos la respuesta
        reply = msg_box.exec()
        
        if reply == QMessageBox.StandardButton.Yes and self.on_delete:
            self.on_delete(self.base_dir)
            print("Eliminar Analisis")
        

class AnalysisButton(QPushButton):
    def __init__(self, icon_path, title, description, parent=None):
        super().__init__(parent)
        #self.setObjectName("analysisButton")
        h_layout = QHBoxLayout()
        h_layout.setContentsMargins(10, 20, 10, 20)  # Margen interno del botón
        h_layout.setSpacing(8)  # Reduce el espacio entre el icono y el texto

        self.shadow_effect = QGraphicsDropShadowEffect(self)
        self.shadow_effect.setBlurRadius(0)  # Inicialmente sin sombra
        self.shadow_effect.setOffset(0, 0)
        self.setGraphicsEffect(self.shadow_effect)

        # Icono en el lado izquierdo
        self.icon_label = QLabel()
        self.icon_label.setPixmap(QIcon(icon_path).pixmap(32, 32))  # Ajusta el tamaño del icono
        self.icon_label.setStyleSheet("""
                                 padding-top: 18px;
                                 padding-left: 15px; 
                                 padding-right: 15px;
                                 padding-bottom: 18px;
                                 margin-left: 15px; 
                                 background-color: #F1F1F1;
                                 border-radius: 14px;
                                 """)
        self.icon_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)  # Evita que se expanda
        h_layout.addWidget(self.icon_label)
        # Layout vertical para el título y la descripción
        text_layout = QVBoxLayout()
        text_layout.setSpacing(0)  # Reduce el espacio entre el título y la descripción
        text_layout.setAlignment(Qt.AlignCenter)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("title")
        print("title stylesheet:", self.title_label.styleSheet())

        description_label = QLabel(description)

        # Establecer estilos y alineación
        self.title_label.setStyleSheet("font-size: 16px; font-weight: bold; padding: 0px 5px 0px 0px; background: transparent;")
        description_label.setStyleSheet("color: gray; font-size: 12px; padding: 5px 5px 0px 0px; background: transparent;")
        self.title_label.setAlignment(Qt.AlignLeft)
        description_label.setAlignment(Qt.AlignLeft)
        description_label.setWordWrap(True)
        description_label.setMaximumWidth(900)  # Ajusta este valor a lo que desees como máximo de ancho
        
         # Agregar el título y la descripción al layout vertical
        text_layout.addWidget(self.title_label)
        text_layout.addWidget(description_label)

        # Agregar el layout de texto al layout horizontal
        h_layout.addLayout(text_layout)

        # Configurar el layout del botón
        self.setLayout(h_layout)
        
        self.setStyleSheet("""
    QPushButton:hover {
        background-color: #EBFFF2; /* Color cuando pasas el mouse */
        border: 1px solid #E5E8EB; /* Opcional: cambiar borde en hover */
    }
""")
        # Ajustar el tamaño del botón para que se acomode al contenido
        self.setFixedHeight(150)
        self.setFixedWidth(360)
        #self.setMinimumHeight(120)  # Altura mínima adecuada
        #self.setMinimumWidth(300)  # Ancho mínimo ajustado
        #self.adjustSize()
       
    def enterEvent(self, event):
        self.shadow_effect.setBlurRadius(15)       # Tamaño difuminado
        self.shadow_effect.setXOffset(0)           # Desplazamiento horizontal
        self.shadow_effect.setYOffset(3)           # Desplazamiento vertical
        self.shadow_effect.setColor(QColor(0, 0, 0, 80))  # Negro semi-transparente

        self.title_label.setStyleSheet("color: #00742E; font-size: 16px; font-weight: bold; padding: 0px 5px 0px 0px; background: transparent;")
        self.icon_label.setStyleSheet("""
                                 padding-top: 18px;
                                 padding-left: 15px; 
                                 padding-right: 15px;
                                 padding-bottom: 18px;
                                 margin-left: 15px; 
                                 background-color: #CAFFDD;
                                 border-radius: 14px;
                                 """)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.shadow_effect.setBlurRadius(0)
        self.shadow_effect.setOffset(0, 0)
        self.title_label.setStyleSheet("color: black; font-size: 16px; font-weight: bold; padding: 0px 5px 0px 0px; background: transparent;")
        self.icon_label.setStyleSheet("""
                                 padding-top: 18px;
                                 padding-left: 15px; 
                                 padding-right: 15px;
                                 padding-bottom: 18px;
                                 margin-left: 15px; 
                                 background-color: #F1F1F1;
                                 border-radius: 14px;
                                 """)
        super().leaveEvent(event)

class CustomButton(QPushButton):
    def __init__(self, icon_path, title, description, parent=None):
        super().__init__(parent)

        # Layout horizontal para el icono y el texto
        h_layout = QHBoxLayout()
        h_layout.setContentsMargins(5, 5, 5, 5)  # Margen interno del botón
        h_layout.setSpacing(8)  # Reduce el espacio entre el icono y el texto

        # Icono en el lado izquierdo
        icon_label = QLabel()
        icon_label.setPixmap(QIcon(icon_path).pixmap(32, 32))  # Ajusta el tamaño del icono
        icon_label.setStyleSheet("padding-left: 10px; padding-right: 5px;")
        icon_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)  # Evita que se expanda
        h_layout.addWidget(icon_label)

        # Layout vertical para el título y la descripción
        text_layout = QVBoxLayout()
        text_layout.setSpacing(0)  # Reduce el espacio entre el título y la descripción
        text_layout.setAlignment(Qt.AlignCenter)
        title_label = QLabel(title)
        description_label = QLabel(description)

        # Establecer estilos y alineación
        title_label.setStyleSheet("color: black; font-size: 16px; font-weight: bold; padding: 0px 5px 0px 0px;")
        description_label.setStyleSheet("color: gray; font-size: 12px; padding: 0px 5px 0px 0px;")
        title_label.setAlignment(Qt.AlignLeft)
        description_label.setAlignment(Qt.AlignLeft)
        description_label.setWordWrap(True)
        description_label.setMaximumWidth(750)  # Ajusta este valor a lo que desees como máximo de ancho

        # Agregar el título y la descripción al layout vertical
        text_layout.addWidget(title_label)
        text_layout.addWidget(description_label)

        # Agregar el layout de texto al layout horizontal
        h_layout.addLayout(text_layout)

        # Configurar el layout del botón
        self.setLayout(h_layout)

        # Ajustar el tamaño del botón para que se acomode al contenido
        self.setMinimumHeight(100)  # Altura mínima adecuada
        self.setMinimumWidth(250)  # Ancho mínimo ajustado

        self.adjustSize()


APP_NAME = "AgroHass"
ORG_NAME = "Inicteluni"

class AppDataManager():
    def __init__(self, app_name = APP_NAME, org_name = ORG_NAME):
        self.app_name = app_name
        self.org_name = org_name
    
    def get_config_path(self):
        config_dir = QStandardPaths.writableLocation(QStandardPaths.AppConfigLocation)
         # 2. Verificar si existe, y si no, crearla (incluyendo carpetas padres si faltan)
        if not os.path.exists(config_dir):
            os.makedirs(config_dir, exist_ok=True)

        return os.path.join(config_dir, "recent_projects.json")
    
    def get_process_config_path(self):
        config_dir = QStandardPaths.writableLocation(QStandardPaths.AppConfigLocation)
        print("config_dir:", config_dir)
        # 2. Verificar si existe, y si no, crearla (incluyendo carpetas padres si faltan)
        if not os.path.exists(config_dir):
            os.makedirs(config_dir, exist_ok=True)
            
        return os.path.join(config_dir, "process_config.json")
    
    def load_recent_projects(self):
        config_path = self.get_config_path()
        if os.path.exists(config_path):
            with open(config_path,  "r") as f:
                return json.load(f)
        return []
    
    def load_process_config(self):
        config_path = self.get_process_config_path()
        if os.path.exists(config_path):
            with open(config_path,  "r") as f:
                return json.load(f)
        return None
    
    def update_process_config(self, new_process_config):
        process_config = self.load_process_config()
        if process_config:
            process_config.update(new_process_config)
            self.save_process_config(new_process_config)
        else:
            self.save_process_config(new_process_config)

    def save_process_config(self, process_config):
        config_path = self.get_process_config_path()
        with open(config_path, "w") as f:
            json.dump(process_config, f, indent = 4)

    def init_process_config(self):
        config_path = self.get_process_config_path()
        if not os.path.exists(config_path):
            with open(config_path, "w") as f:
                json.dump(DEFAULT_PROCESS_CONFIG, f, indent = 4)
            
    def save_recent_projects(self, projects):
        config_path = self.get_config_path()
        with open(config_path, "w") as f:
            json.dump(projects, f, indent = 4)
    
    def add_new_project(self, project_info):
        projects = self.load_recent_projects()
        self.save_recent_projects([project_info] + projects)


    def update_project_info(self, identifier_id, num_images):
        projects = self.load_recent_projects()

        for p in projects:
            if "identifier_id" not in p:
                continue

            if p["identifier_id"] == identifier_id:
                p["num_images"] == num_images or p["num_images"]
                break
        

class Home(QWidget):
    def __init__(self, main_window=None):
        super().__init__()

        self.appdata_manager = AppDataManager()
        self.main_window = main_window
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)

        title = QLabel("AgroHass")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size:24px; font-weight: bold; padding: 0px 0px 10px 0px;")

        buttons_layout = QHBoxLayout()
        buttons_layout.setContentsMargins(0,10,0,10)
        buttons_layout.setSpacing(60)
        buttons_layout.addStretch()
        button_new = AnalysisButton(resource_path(os.path.join("assets", "new.svg")), "Nuevo Análisis de Parcela", "Configura un nuevo procesamiento y análisis de imágenes aéreas multiespectrales de una parcela de palta Hass para identificar posibles problemas nutricionales.")
        button_new.clicked.connect(self.open_new_analysis_dialog)
        button_open = AnalysisButton(resource_path(os.path.join("assets", "open.svg")), "Abrir Análisis de Parcela", "Abre el análisis guardado de una parcela y revisa los resultados obtenidos del procesamiento de las imágenes.")
        button_open.clicked.connect(self.open_analysis) 

        buttons_layout.addWidget(button_new)
        #buttons_layout.addSpacerItem(QSpacerItem(20,0, QSizePolicy.Expanding, QSizePolicy.Minimum))
        buttons_layout.addWidget(button_open)
        buttons_layout.addStretch()
        recientes_layout = QVBoxLayout()
        recientes_layout.setContentsMargins(50,20,50,0)
        # Analisis Recientes
        analysis_recientes = QLabel("Análisis Recientes")
        analysis_recientes.setAlignment(Qt.AlignLeft)
        analysis_recientes.setStyleSheet("font-size:18px; font-weight: bold; padding: 0px 0px 10px 0px;")
        recientes_layout.addWidget(analysis_recientes)
        # Cards Analisis
        
        # 1. Creamos el Scroll Area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff) # Solo horizontal
        self.scroll_area.setFrameShape(QFrame.NoFrame) # Quitar borde del scroll area
        self.scroll_area.setStyleSheet("background: transparent;")
        self.scroll_area.setStyleSheet("""
            QScrollArea {
                background: transparent;
                border: none;
            }
            /* Estilo del "carril" de la barra */
            QScrollBar:horizontal {
                border: none;
                background: #f0f0f0; /* Gris muy claro */
                height: 8px; /* Barra más delgada */
                margin: 0px 10px 0px 10px;
                border-radius: 4px;
            }
            /* Estilo del "pulgar" (la parte que se arrastra) */
            QScrollBar::handle:horizontal {
                background: #c0c0c0;
                min-width: 30px;
                border-radius: 4px;
            }
            /* Cambio de color al pasar el ratón */
            QScrollBar::handle:horizontal:hover {
                background: #a0a0a0;
            }
            /* Ocultar las flechas de los extremos */
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                border: none;
                background: none;
                width: 0px; 
            }
        """)

        # 2. Widget contenedor para el layout de las tarjetas
        self.scroll_content = QWidget()
        self.scroll_content.setStyleSheet("background: transparent;")
        self.cards_layout = QHBoxLayout(self.scroll_content) # El layout ahora pertenece al contenedor
        self.cards_layout.setContentsMargins(10, 10, 10, 20) # Margen: izq, arriba, der, abajo
        self.cards_layout.setSpacing(20) # Espacio entre cards
        self.cards_layout.setAlignment(Qt.AlignLeft)

        # 3. Asignamos el contenedor al scroll area
        self.scroll_area.setWidget(self.scroll_content)
        
        recientes_layout.addWidget(self.scroll_area)

        #self.cards_layout = QHBoxLayout()
        #self.cards_layout.setContentsMargins(0,0,0,0)

  
        self.recient_projects = []

        #self.refresh_cards()
        #self.cards_layout.setAlignment(Qt.AlignLeft) 

        #recientes_layout.addLayout(self.cards_layout)
        
        # --Linea Divisora
        #line = QFrame()
        #line.setFrameShape(QFrame.HLine)
        #line.setFrameShadow(QFrame.Sunken)
        #line.setStyleSheet("background-color: #e0e0e0;") # Gris claro
        #line.setStyleSheet("background-color: #d1d1d1; max-height: 1px; border: none;")
        #line.setFixedHeight(1) # Grosor de 1 píxel
        
        #footer = VentanaFooter()
        #layout.addWidget(title)
        #layout.addLayout(buttons_layout)
        #layout.addWidget(analysis_recientes)
        #layout.addLayout(recientes_layout)
        #layout.addStretch()
        #layout.addWidget(line)
        #layout.addWidget(footer)
        
        # --- Footer y Layout Principal ---
        footer = VentanaFooter()
        layout.addWidget(title)
        layout.addLayout(buttons_layout)
        layout.addLayout(recientes_layout)
        layout.addStretch()
        layout.addWidget(footer)
        
        self.appdata_manager.init_process_config()
        self.setLayout(layout)
        
        self.refresh_cards()

        #self.appdata_manager.init_process_config()

        #self.setLayout(layout)


    def refresh_cards(self):
        self.recient_projects = self.appdata_manager.load_recent_projects()#[:5]
        #self.recient_projects = self.recient_projects[1:]

        #self.appdata_manager.save_recent_projects(self.recient_projects)
        #print("recient_projects:", self.recient_projects)
        
        on_click_card = lambda path: self.load_analysis(path)
        
        def on_delete_card(base_dir):
            # Borrar del JSON
            projects = self.appdata_manager.load_recent_projects()
            projects = [p for p in projects if p["base_dir"] != base_dir]
            self.appdata_manager.save_recent_projects(projects)
            # Refrescar vista

            if os.path.exists(base_dir):
                try:
                    shutil.rmtree(base_dir)  # elimina carpeta completa
                    print(f"Carpeta eliminada: {base_dir}")
                except Exception as e:
                    print(f"Error eliminando carpeta {base_dir}: {e}")
            self.refresh_cards()

        
        self.cards_data = [ (self.get_card_image(data["base_dir"]), 
                             data['name'],
                             data['num_images'],
                             datetime.fromisoformat(data['creation_date']).strftime("%d/%m/%Y"),
                             data["base_dir"],
                             on_click_card,
                             on_delete_card
                             ) for data in self.recient_projects]
        
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        for data in self.cards_data:
            self.cards_layout.addWidget(AnalysisCard(*data))
            spacer_widget = QWidget()
            spacer_widget.setMaximumWidth(50)
            spacer_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            self.cards_layout.addWidget(spacer_widget)

    def get_card_image(self, base_dir):
        sumary_path = os.path.join(base_dir, "processing_sumary.json")
        if os.path.exists(sumary_path):
            processing_sumary = None
            with open(sumary_path, "r") as f:
                processing_sumary = json.load(f)
            
            if processing_sumary and "card_map" in processing_sumary:
                    return processing_sumary["card_map"]
        
        return resource_path(os.path.join("assets", "card_default.png"))
        
    def open_new_analysis_dialog(self):
        dialog = NewAnalysisDialog(self)
        
        def handle_finished_configure():
            
            base_dir = dialog.new_analysis_data_store.base_dir
            images_data = dialog.new_analysis_data_store.images_data
            name = dialog.new_analysis_data_store.name
            
            print("Actualizando details....")
            id_unico = str(uuid.uuid4())
            gsd_avg = dialog.new_analysis_data_store.gsd_avg
            alt_avg = dialog.new_analysis_data_store.alt_avg

            project_info = {
                    "name": name,
                    "identifier_id": id_unico,
                    "creation_date": datetime.now().isoformat(),
                    "num_images": len(images_data),
                    "base_dir": base_dir,
                    "gsd_avg": gsd_avg,
                    "alt_avg": alt_avg
                }
            
            fecha_formateada = ""
            hora_ampm = ""
            if len(images_data) > 0:
                exif_str = images_data[0]['datetime_original']
                dt = datetime.strptime(exif_str, "%Y:%m:%d %H:%M:%S")

                # Formatear al formato deseado
                fecha_formateada = dt.strftime("%d/%m/%Y")
                hora_ampm = dt.strftime("%I %p").lstrip("0")

            dialog.new_analysis_data_store.set_adquisition_date(fecha_formateada)
            
            self.main_window.update_analysis_data(dialog.new_analysis_data_store)
            
            project_info["adquisition_date"] = fecha_formateada
            project_info["hora_ampm"] = hora_ampm

            field_information = dialog.new_analysis_data_store.field_info
            
            config = {
                    "project_info": project_info,
                    "image_metatada": images_data,
                    "field_information": field_information
                }
            
            self.save_configure_analysis(base_dir, config)     

            self.appdata_manager.add_new_project(project_info)
            self.refresh_cards()

           
        
        dialog.finished_configure.connect(handle_finished_configure)

        dialog.exec()
    
    def save_configure_analysis(self, base_dir, data):
        import json
        with open(f"{base_dir}/config.json", "w") as f:
            json.dump(data, f, indent=4) 

    def load_local_process_config(self, path_dir):
        path = f"{path_dir}/processing_config.json"
        print("load_local_process_config path:", path)
        if not os.path.exists(path):
            return None
        
        with open(path, "r") as f:
            config = json.load(f)
            return config
        
    def load_analysis(self, path_dir):
        with open(f"{path_dir}/config.json", "r") as f:
            config = json.load(f)
        
        project_info = config['project_info']
        print("project_info:", project_info)
        
        images_data = config['image_metatada']
        print("Cargando datos.....")
        images_data = {i: images_data[str(i)] for i in range(len(images_data))}
        field_information = config["field_information"]
        identifier_id = None if "identifier_id" not in project_info else project_info["identifier_id"]
        analysis_data = AnalysisData(base_dir = project_info['base_dir'],
                                     identifier_id = identifier_id,
                                    name = project_info['name'], 
                                    images_data=images_data,
                                    alt_avg = project_info['alt_avg'],
                                    gsd_avg = project_info['gsd_avg'],
                                    adquisition_date = project_info['adquisition_date']
                                    )
        
        

        
        analysis_data.update_field_info(stage=field_information["stage"],
                                        soil_type=field_information["soil_type"],
                                        irrigation_type = field_information["irrigation_type"])
        
        
        local_process_config = self.load_local_process_config(path_dir)
        print("local_process_config:", local_process_config)
        
        if local_process_config is None:
            local_process_config = self.appdata_manager.load_process_config()
        
        print("local_process_config:", local_process_config)
 
        if local_process_config:
            target_resolution_option = local_process_config["target_resolution_option"]
            tresh_stages = local_process_config["tresh_stages"]
            analysis_data.set_target_resolution(target_resolution_option)
            analysis_data.set_thresh_stages(tresh_stages)


        print("Actualizando Vistas.....")
        
        self.main_window.update_analysis_data(analysis_data)

        result_dir = self.main_window.analysis_data_store.base_dir

        print("Cargando result_dir:", result_dir)

        mosaic_path = f"{result_dir}/mosaic/rgb/tiles"
        
        if os.path.exists(mosaic_path):
            self.main_window.page_map_trees.layers_ready.emit(result_dir)
            self.main_window.enable_nav_item(2)
            self.main_window.switch_page(2, True)
            
        else:
            self.main_window.enable_nav_item(1)
            self.main_window.switch_page(1, True)

    def open_analysis(self):
        path_dir = QFileDialog.getExistingDirectory(
            self,
            "Seleciona Carpeta de Analisis Anterior",
            "",
        )

        if path_dir:
            print("Ruta de analisis:", path_dir)
            self.load_analysis(path_dir)


