from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QHBoxLayout, QSizePolicy, QPushButton
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from views.dialog_new_analysis import NewAnalysisDialog

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

        button_new = CustomButton("./assets/new.svg", "Nuevo Análisis", "Genera un nuevo analisis a partir de imagenes aereas para identificar deficiencias nutricionales.")
        button_new.clicked.connect(self.open_new_analysis_dialog)
        button_open = CustomButton("./assets/open.svg", "Abrir Análisis", "Abre un análisis guardado y revisa la informacion obtenida.")
        
        layout.addWidget(title)
        layout.addWidget(button_new)
        layout.addWidget(button_open)
        
        self.setLayout(layout)

  
    def open_new_analysis_dialog(self):
        dialog = NewAnalysisDialog(self)
        
        def handle_finished_configure():
            self.main_window.update_analysis_data(dialog.new_analysis_data_store)
        
        dialog.image_data_screen.finished_configure.connect(handle_finished_configure)

        dialog.exec()