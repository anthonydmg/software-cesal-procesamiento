from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QHBoxLayout, QSizePolicy, QPushButton, QSpacerItem, QFrame
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QIcon, QColor, QPixmap, QFontMetrics, QPainterPath, QPainter, QFont
from PySide6.QtWidgets import QGraphicsDropShadowEffect
from views.dialog_new_analysis import NewAnalysisDialog

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
    def __init__(self, image_path, title, image_count, creation_date, parent = None):
        super().__init__()
        # Layout principal
        self.setMaximumWidth(200)
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
                box-shadow: 0px 4px 12px rgba(0,0,0,0.15);
            }
        """)
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(0, 0, 0, 0)
        frame_layout.setSpacing(10)
        #layout.setSpacing(5)
        img_label = QLabel()
        #img_label.setPixmap(QPixmap(image_path).scaled(200,350, Qt.KeepAspectRatio,  Qt.SmoothTransformation))
        img_label = RoundedImageLabel(image_path, 8)
        img_label.setAlignment(Qt.AlignCenter)
        img_label.setStyleSheet("""
            background-color: transparent;
            border-top-left-radius: 8px;
            border-top-right-radius: 8px;
        """)
        frame_layout.addWidget(img_label)
        
        # Contenedor de texto
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
        self.setMinimumHeight(120)  # Altura mínima adecuada
        self.setMinimumWidth(300)  # Ancho mínimo ajustado
        self.adjustSize()
       
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


class Home(QWidget):
    def __init__(self, main_window=None):
        super().__init__()
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
        button_new = AnalysisButton("./assets/new.svg", "Nuevo Análisis", "Genera un nuevo analisis a partir de imagenes aereas para identificar deficiencias nutricionales.")
        button_new.clicked.connect(self.open_new_analysis_dialog)
        button_open = AnalysisButton("./assets/open.svg", "Abrir Análisis", "Abre un análisis guardado y revisa la informacion obtenida.")
        
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
        cards_layout = QHBoxLayout()
        cards_layout.setContentsMargins(0,0,0,0)
        for i in range(4):
            cards_layout.addWidget(AnalysisCard("./assets/card-example.png","Vuelo-Julio-15-2025-Campo-Acampampa-1", 312, "15/07/2025"))
            #spacer = QSpacerItem(0, 0, QSizePolicy.Expanding, QSizePolicy.Minimum)
            #cards_layout.addSpacerItem(spacer)
            spacer_widget = QWidget()
            spacer_widget.setMaximumWidth(50)
            spacer_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            cards_layout.addWidget(spacer_widget)
            #cards_layout.addStretch()

        cards_layout.setAlignment(Qt.AlignLeft) 

        recientes_layout.addLayout(cards_layout)
        layout.addWidget(title)
        layout.addLayout(buttons_layout)
        #layout.addWidget(analysis_recientes)
        layout.addLayout(recientes_layout)
        self.setLayout(layout)

  
    def open_new_analysis_dialog(self):
        dialog = NewAnalysisDialog(self)
        
        def handle_finished_configure():
            self.main_window.update_analysis_data(dialog.new_analysis_data_store)
        
        dialog.image_data_screen.finished_configure.connect(handle_finished_configure)

        dialog.exec()