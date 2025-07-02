import sys
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QLabel,
                               QPushButton, QVBoxLayout, QHBoxLayout,
                               QGridLayout, QFrame, QToolButton)
from PySide6.QtGui import QIcon, QPixmap, QFont, QColor
from PySide6.QtCore import Qt, QSize

class SidebarButton(QToolButton):
    def __init__(self, icon_path, text):
        super().__init__()
        self.setIcon(QIcon.fromTheme(icon_path))
        self.setIconSize(QSize(32,32))
        self.setText(text)
        self.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        self.setFixedHeight(80)
        self.setStyleSheet("""
            QToolButton {
                border: none;
                background: transparent;
                font-size: 12px;
            }
            QToolButton:hover {
                background-color: #e0e0e0;
            }
        """)

class AgroHassApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AgroHass")
        self.setMinimumSize(1200, 800)
        self.initUI()

    def initUI(self):
        # Widget central
        central_widget = QWidget()
        central_widget.setStyleSheet("background-color: white;")  # fondo blanco
        central_layout = QHBoxLayout()
        central_widget.setLayout(central_layout)
        self.setCentralWidget(central_widget)

        # Sidebar izquierda
        sidebar = QFrame()
        sidebar.setFrameShape(QFrame.StyledPanel)
        sidebar.setFixedWidth(80)  # más delgada
        sidebar.setStyleSheet("background-color: white;")  # fondo blanco
        sidebar_layout = QVBoxLayout()
        sidebar_layout.setAlignment(Qt.AlignTop)
        sidebar.setLayout(sidebar_layout)

        # Logo AgroHass arriba en negrita
        logo_label = QLabel("AgroHass")
        logo_label.setAlignment(Qt.AlignCenter)
        font_logo = QFont()
        font_logo.setPointSize(10)
        font_logo.setBold(True)
        logo_label.setFont(font_logo)
        sidebar_layout.addWidget(logo_label)

        # Menú con iconos arriba y texto abajo
        btn_inicio = SidebarButton("go-home", "Inicio")
        sidebar_layout.addWidget(btn_inicio)

        btn_mapa = SidebarButton("emblem-photos", "Mapa de Capturas")
        sidebar_layout.addWidget(btn_mapa)

        btn_mosaico = SidebarButton("image-x-generic", "Mosaico")
        sidebar_layout.addWidget(btn_mosaico)

        sidebar_layout.addStretch()

        # Panel principal
        main_panel = QWidget()
        main_layout = QVBoxLayout()
        main_panel.setLayout(main_layout)

        # Título superior
        title_label = QLabel("Análisis de salud del cultivo")
        font_title = QFont()
        font_title.setPointSize(16)
        font_title.setBold(True)
        title_label.setFont(font_title)
        main_layout.addWidget(title_label)

        # Toolbar debajo del título
        toolbar_layout = QHBoxLayout()

        btn_zoom_in = QToolButton()
        btn_zoom_in.setIcon(QIcon.fromTheme("zoom-in"))
        btn_zoom_in.setToolTip("Zoom In")
        btn_zoom_in.setIconSize(QSize(24,24))

        btn_zoom_out = QToolButton()
        btn_zoom_out.setIcon(QIcon.fromTheme("zoom-out"))
        btn_zoom_out.setToolTip("Zoom Out")
        btn_zoom_out.setIconSize(QSize(24,24))

        btn_download = QToolButton()
        btn_download.setIcon(QIcon.fromTheme("document-save"))
        btn_download.setToolTip("Descargar")
        btn_download.setIconSize(QSize(24,24))

        # Botón Generar Reporte
        btn_report = QPushButton("Generar Reporte")
        btn_report.setStyleSheet("background-color: #4CAF50; color: white; padding:6px 12px; border-radius:5px;")
        btn_report.setIcon(QIcon.fromTheme("document-new"))
        btn_report.setIconSize(QSize(20,20))
        btn_report.setCursor(Qt.PointingHandCursor)

        toolbar_layout.addWidget(btn_zoom_in)
        toolbar_layout.addWidget(btn_zoom_out)
        toolbar_layout.addWidget(btn_download)
        toolbar_layout.addStretch()
        toolbar_layout.addWidget(btn_report)

        main_layout.addLayout(toolbar_layout)

        # Layout horizontal para mapa y leyenda
        map_legend_layout = QHBoxLayout()

        # Mapa (placeholder)
        map_label = QLabel()
        map_pixmap = QPixmap(700, 500)
        map_pixmap.fill(QColor("#2e7d32"))  # verde oscuro como placeholder
        map_label.setPixmap(map_pixmap)
        map_label.setScaledContents(True)

        map_legend_layout.addWidget(map_label)

        # Leyenda en vertical
        right_panel = QVBoxLayout()

        # Leyenda Nutricional
        legend_title = QLabel("Leyenda Nutricional")
        font_legend = QFont()
        font_legend.setBold(True)
        legend_title.setFont(font_legend)
        right_panel.addWidget(legend_title)

        legend_items = [
            ("SALUDABLE", "#00ff00"),
            ("DEFICIENCIA NITROGENO", "#aaff00"),
            ("DEFICIENCIA ZINC", "#ffaa00"),
            ("DEFICIENCIA MAGNESIO", "#ffcc00"),
            ("DEFICIENCIA NITROGENO Y ZINC", "#ff8800"),
            ("DEFICIENCIA NITROGENO Y MAGNESIO", "#ff6600"),
            ("DEFICIENCIA ZINC Y MAGNESIO", "#ff4400"),
            ("DEFICIENCIA NITROGENO ZINC Y MAGNESIO", "#ff0000")
        ]

        # Leyenda en grid
        legend_grid = QGridLayout()
        row = 0
        for name, color in legend_items:
            # Color box
            color_label = QLabel()
            color_pixmap = QPixmap(20,20)
            color_pixmap.fill(QColor(color))
            color_label.setPixmap(color_pixmap)

            # Texto
            text_label = QLabel(name)

            # Layout horizontal para cada item
            item_layout = QHBoxLayout()
            item_layout.addWidget(color_label)
            item_layout.addWidget(text_label)
            item_layout.addStretch()

            # Contenedor del item
            item_widget = QWidget()
            item_widget.setLayout(item_layout)

            # Añade el item al grid
            legend_grid.addWidget(item_widget, row, 0, 1, 2)

            # Línea de separación
            line = QFrame()
            line.setFrameShape(QFrame.HLine)
            line.setFrameShadow(QFrame.Sunken)
            line.setStyleSheet("color: #cccccc;")
            legend_grid.addWidget(line, row + 1, 0, 1, 2)

            row += 2  # Incrementa por 2 debido al item + línea

        right_panel.addLayout(legend_grid)
        right_panel.addStretch()

        map_legend_layout.addLayout(right_panel)

        main_layout.addLayout(map_legend_layout)

        # Añadir sidebar y main panel al layout central
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        central_layout.addWidget(sidebar)
        central_layout.addWidget(main_panel)

        # Estilos generales
        self.setStyleSheet("""
            QToolButton {
                padding:5px;
            }
            QToolButton:hover {
                background-color: #e0e0e0;
            }
        """)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = AgroHassApp()
    window.show()
    sys.exit(app.exec())




