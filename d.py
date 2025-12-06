from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QApplication
from PySide6.QtGui import QFont
from PySide6.QtCore import Qt
import sys


class StatCard(QFrame):
    def __init__(self, title: str, value: int, parent=None):
        super().__init__(parent)

        # Configurar borde, fondo y esquinas redondeadas
        self.setFrameShape(QFrame.StyledPanel)
     

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


if __name__ == "__main__":
    app = QApplication(sys.argv)
    card = StatCard("Total Trees Detected", 200)
    card.show()
    sys.exit(app.exec())
