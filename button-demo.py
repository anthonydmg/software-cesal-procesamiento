from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QPushButton, QVBoxLayout, QHBoxLayout, QLabel, QWidget, QSizePolicy

class CustomButton(QPushButton):
    def __init__(self, title, description, icon_path, parent=None):
        super().__init__(parent)

        # Layout horizontal para el icono y el texto
        h_layout = QHBoxLayout()
        h_layout.setContentsMargins(5, 5, 5, 5)  # Margen interno del botón
        h_layout.setSpacing(8)  # Reduce el espacio entre el icono y el texto

        # Icono en el lado izquierdo
        icon_label = QLabel()
        icon_label.setPixmap(QIcon(icon_path).pixmap(24, 24))  # Ajusta el tamaño del icono
        icon_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)  # Evita que se expanda
        h_layout.addWidget(icon_label)

        # Layout vertical para el título y la descripción
        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)  # Reduce el espacio entre el título y la descripción

        title_label = QLabel(title)
        description_label = QLabel(description)

        # Establecer estilos y alineación
        title_label.setStyleSheet("color: black; font-size: 14px; font-weight: bold;")
        description_label.setStyleSheet("color: gray; font-size: 10px;")
        title_label.setAlignment(Qt.AlignLeft)
        description_label.setAlignment(Qt.AlignLeft)

        # Agregar el título y la descripción al layout vertical
        text_layout.addWidget(title_label)
        text_layout.addWidget(description_label)

        # Agregar el layout de texto al layout horizontal
        h_layout.addLayout(text_layout)

        # Configurar el layout del botón
        self.setLayout(h_layout)

        # Ajustar el tamaño del botón para que se acomode al contenido
        #self.setStyleSheet("QPushButton { padding: 8px; background-color: lightblue; border: none; }")
        self.setMinimumHeight(50)  # Altura mínima adecuada
        self.setMinimumWidth(100)  # Ancho mínimo ajustado
        self.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)  # Expansión horizontal automática


if __name__ == "__main__":
    app = QApplication([])

    # Crear ventana principal
    window = QWidget()
    window.setWindowTitle("Botón Custom")

    # Crear un botón custom
    button = CustomButton("Título", "Descripción del botón", "./assets/new.svg")
    layout = QVBoxLayout()
    layout.addWidget(button)
    
    window.setLayout(layout)
    window.resize(300, 150)
    window.show()

    app.exec()