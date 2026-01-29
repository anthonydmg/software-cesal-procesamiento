import sys
from PySide6.QtWidgets import (QApplication, QWidget, QHBoxLayout, QVBoxLayout, 
                               QLabel, QFrame, QSizePolicy)
from PySide6.QtGui import QPixmap
from PySide6.QtCore import Qt

# --- 1. CLASE PARA EL LOGO CON ESTILO DE TARJETA ---
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
        self.setFixedSize(80, 80) # Tamaño fijo para uniformidad
        self.setAlignment(Qt.AlignCenter)
        
        # Cargar y escalar imagen
        pixmap = QPixmap(ruta_imagen)
        if not pixmap.isNull():
            self.setPixmap(pixmap.scaled(
                70, 70, Qt.KeepAspectRatio, Qt.SmoothTransformation
            ))
        else:
            self.setText("Logo") # Fallback si no encuentra la imagen

# --- 2. CLASE PARA LA SECCIÓN (TÍTULO + LOGOS) ---
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

# --- 3. VENTANA PRINCIPAL ---
class VentanaFooter(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Footer Estilizado")
        self.setMinimumWidth(700)
        self.setStyleSheet("background-color: #ffffff;") # Color de fondo suave
        
        # Layout principal horizontal
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(30, 20, 30, 20)
        
        # SECCIÓN IZQUIERDA
        izq = SeccionInformativa(
            "DESARROLLADO EN COLABORACIÓN CON:",
            ["./assets/INICTEL-LOGO.jpg", "./assets/cesal-logo.png"] # Cambia por tus rutas
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
            ["./assets/AECID_logo.svg"] # Cambia por tu ruta
        )
        
        # Agregar al layout con proporciones
        main_layout.addWidget(izq, stretch=2)
        main_layout.addWidget(linea)
        main_layout.addWidget(der, stretch=1)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = VentanaFooter()
    window.show()
    sys.exit(app.exec())