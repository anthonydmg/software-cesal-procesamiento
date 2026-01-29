import sys
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QFrame)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

class StatCountWidget(QWidget):
    def __init__(self, color, title, percentage, count, parent=None):
        super().__init__(parent)
        
        # Layout principal vertical
        layout = QVBoxLayout(self)
        layout.setSpacing(2) # Espacio pequeño entre líneas
        
        # --- Fila superior (Punto de color + Título) ---
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)
        
        # El "punto" de color hecho con un QFrame
        dot = QFrame()
        dot.setFixedSize(12, 12)
        dot.setStyleSheet(f"background-color: {color}; border-radius: 6px;")
        
        title_label = QLabel(title.upper())
        title_label.setStyleSheet("color: #8E97A4; font-weight: bold; font-size: 11px;")
        
        header_layout.addWidget(dot)
        header_layout.addWidget(title_label)
        header_layout.addStretch() # Empuja todo a la izquierda
        
        # --- Fila media (Porcentaje) ---
        self.percent_label = QLabel(percentage)
        self.percent_label.setStyleSheet("color: #2D3748; font-size: 22px; font-weight: 800;")
        
        # --- Fila inferior (Subtexto de ejemplares) ---
        self.count_label = QLabel(f"{count} Árboles")
        self.count_label.setStyleSheet("color: #718096; font-size: 12px;")
        
        # Agregar todo al layout principal
        layout.addLayout(header_layout)
        layout.addWidget(self.percent_label)
        layout.addWidget(self.count_label)
    
    def update_stat(self, count, percentage):
        self.percent_label.setText(f"{percentage}%")
        self.count_label.setText(f"{count} Árboles")
        


class StatsDeficiency(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Dashboard Stats")
        self.setStyleSheet("background-color: white;") # Fondo blanco como en la imagen
        
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(40) # Espacio entre los dos bloques

        # Bloque Saludable (Verde)
        self.saludable = StatCountWidget("#108548", "Saludable", "0.0%", 0)
        
        # Bloque Deficiencia (Amarillo/Naranja)
        self.deficiencia = StatCountWidget("#F97316", "Deficiencia", "0.0%", 0)

        main_layout.addWidget(self.saludable)
        main_layout.addWidget(self.deficiencia)
        main_layout.addStretch()
    
    def update_stats(self, num_healty, num_deficency):
        percentage_healthy = round(num_healty * 100 / (num_healty + num_deficency), 2) 
        percentage_deficient = round(num_deficency * 100 / (num_healty + num_deficency),2) 
        
        self.saludable.update_stat(num_healty, percentage_healthy)
        self.deficiencia.update_stat(num_deficency, percentage_deficient)
        


if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Configurar una fuente limpia si está disponible
    #font = QFont("Segoe UI", 10)
    #app.setFont(font)
    
    window = StatsDeficiency()
    window.show()
    sys.exit(app.exec())