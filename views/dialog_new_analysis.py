from PySide6.QtWidgets import QApplication, QDialog, QStackedWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QFileDialog, QFrame, QListWidget, QProgressBar, QTableWidget, QScrollArea, QTableWidgetItem, QWidget, QComboBox , QAbstractItemView
from PySide6.QtCore import Qt, Signal, QObject, Slot, QThread
import os
import numpy as np
from core.constants import ETAPAS_FENOLOGICAS, THRESH_STAGES_DEFAULT, TIPOS_RIEGOS, TIPOS_SUELOS
from core.utils import get_gps_coordinates, get_image_resolution, get_metadata, calcule_gsd_teorico, get_relative_altitude, get_gimbal_euler_angles
from multiprocessing import Pool
from datetime import datetime
from PySide6.QtWidgets import QHeaderView


class InitialConfigureScreen(QFrame):
    def __init__(self, parent = None, dialog_parent=None):
        super().__init__(parent)
        self.dialog_parent = dialog_parent  # Almacena la referencia a NewAnalysisDialog
        layout = QVBoxLayout()

        name_layout = QHBoxLayout()
        name_label = QLabel('Nombre <span style="color:red;">*</span>:')
        self.name_input = QLineEdit()
        self.name_input.textChanged.connect(self.validate_inputs)  # Validar al escribir
        name_layout.addWidget(name_label)
        name_layout.addWidget(self.name_input)
        layout.addLayout(name_layout)

        folder_layout = QHBoxLayout()
        folder_label = QLabel('Crear en <span style="color:red;">*</span>:')
        self.folder_input = QLineEdit()
        self.folder_input.setReadOnly(True)  # Para evitar que el usuario escriba manualmente
        self.folder_input.textChanged.connect(self.validate_inputs)  # Validar al escribir
        self.folder_button = QPushButton("Seleccionar")
        self.folder_button.clicked.connect(self.select_folder)
        

        folder_layout.addWidget(folder_label)
        folder_layout.addWidget(self.folder_input)
        folder_layout.addWidget(self.folder_button)
        
        layout.addLayout(folder_layout)

        details_field = QLabel("INFORMACION DE LA PARCELA")
        details_field.setStyleSheet("font-weight: bold; font-size: 12px; margin-bottom: 4px; margin-top: 10px;")
        details_field.setAlignment(Qt.AlignTop)

        layout.addWidget(details_field)
 
        #ETAPA_FENOLOGICA = ["Inicio de brote", "Pre-floración", "Floración", 
        #                    "Cuajado", "Maduración", "Cosecha"]

        #stage_layout = QVBoxLayout
        stage_layout = QHBoxLayout()

        stage_label = QLabel('Etapa Fenológica <span style="color:red;">*</span>:')
        stage_label.setAlignment(Qt.AlignTop)
        self.stage_cb = QComboBox()
        self.stage_cb.addItems(["Seleccionar"] + ETAPAS_FENOLOGICAS)
        self.stage_cb.currentIndexChanged.connect(self.validate_inputs)

        self.setStyleSheet("""
            QComboBox {
                padding: 5px 5px;
                min-height: 15px;
            }
            
            QComboBox QAbstractItemView {
               padding: 5px;
            }
        """)
        
        #stage_cb.setAlignment(Qt.AlignTop)
        stage_layout.addWidget(stage_label, 1)
        stage_layout.addWidget(self.stage_cb, 4)
        
        layout.addLayout(stage_layout)

        #TIPO_SUELO = ["Arenoso", "Franco ", "Arcilloso", 
        #                    "Limoso", "Pedregoso"]
        
        soil_layout = QHBoxLayout()

        soil_label = QLabel("Tipo de Suelo:")
        soil_label.setAlignment(Qt.AlignTop)
        self.soil_cb = QComboBox()
        self.soil_cb.addItems(["Seleccionar"] + TIPOS_SUELOS)
        #soil_cb.setAlignment(Qt.AlignTop)
        soil_layout.addWidget(soil_label, 1)
        soil_layout.addWidget(self.soil_cb, 4)
        layout.addLayout(soil_layout)

        #TIPO_RIEGO = ["Gravedad", "Aspersión ", "Geteo", 
        #                    "Microaspersión"]
        
        
        irrigation_layout = QHBoxLayout()
        irrigation_label = QLabel("Tipo de Riego")
        irrigation_label.setAlignment(Qt.AlignTop)
        self.irrigation_cb = QComboBox()
        self.irrigation_cb.addItems(["Seleccionar:"] + TIPOS_RIEGOS)
        #irrigation_cb.setAlignment(Qt.AlignTop)
        irrigation_layout.addWidget(irrigation_label, 1)
        irrigation_layout.addWidget(self.irrigation_cb, 4)
        layout.addLayout(irrigation_layout)

        layout.addStretch()

        button_layout = QHBoxLayout()
        self.next_button = QPushButton("Siguiente")
        self.next_button.setEnabled(False)  # Deshabilitado al inicio
        self.next_button.clicked.connect(self.go_to_image_selection_screen)
        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.clicked.connect(self.close_dialog)
        
        button_layout.addWidget(self.next_button)
        button_layout.addWidget(self.cancel_button)
        button_layout.setAlignment(Qt.AlignBottom)
        layout.addLayout(button_layout)

        self.setLayout(layout)

    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Seleccionar Carperta")
        if folder:
            self.folder_input.setText(folder)
    
    def go_to_image_selection_screen(self):
        """Crea la carpeta del análisis y avanza a la siguiente pantalla."""

        
        name = self.name_input.text().strip()
        folder_path = self.folder_input.text().strip()
        stage = None if self.stage_cb.currentIndex() == 0 else self.stage_cb.currentText()
        soil_type = None if self.soil_cb.currentIndex() == 0 else self.soil_cb.currentText()
        irrigation_type = None if self.irrigation_cb.currentIndex() == 0 else self.irrigation_cb.currentText()
        # Construir la ruta final
        final_path = os.path.join(folder_path, name)
        
        try:
            os.makedirs(final_path, exist_ok=True)  # Crea la carpeta si no existe
            print(f"Carpeta creada: {final_path}")  # Debug (puedes eliminar esto después)

            self.dialog_parent.new_analysis_data_store.set_base_dir(final_path)

           
            self.dialog_parent.new_analysis_data_store.set_name(name)

            self.dialog_parent.new_analysis_data_store.update_field_info(stage, soil_type, irrigation_type)

            # Llamar al método para cambiar de pantalla
            self.dialog_parent.go_to_image_selection_screen()
        except Exception as e:
            print(f"Error al crear la carpeta: {e}")  # Debug (puedes manejar errores de otra forma)
        #self.dialog_parent.go_to_image_selection_screen()
    
    def close_dialog(self):
        parent = self.dialog_parent
        if isinstance(parent, QDialog):
            parent.reject() 
        else:
            parent.close()

    def validate_inputs(self):
        """Habilita el botón 'Siguiente' solo si ambos campos están llenos y cambia el color de los vacíos."""
        name_filled = bool(self.name_input.text().strip())
        folder_filled = bool(self.folder_input.text().strip())

         # Si está en "Seleccionar", índice = 0 → no válido
        stage_ok = self.stage_cb.currentIndex() != 0

        # Estilo rojo si está vacío, normal si está lleno
        self.name_input.setStyleSheet("border: 1px solid red;" if not name_filled else "")
        self.folder_input.setStyleSheet("border: 1px solid red;" if not folder_filled else "")

        # Habilitar o deshabilitar el botón de siguiente
        if name_filled and folder_filled and stage_ok:
            self.next_button.setEnabled(True)
        else:
            self.next_button.setEnabled(False)
        
       
    def validate_and_continue(self):
        """Verifica si los campos están llenos antes de avanzar a la siguiente pantalla."""
        self.validate_inputs()  # Actualiza los estilos visuales
        if self.next_button.isEnabled():  # Solo avanza si está habilitado
            self.go_to_image_selection_screen()

class MetadataWorker(QObject):
    progress_changed = Signal(int)
    metadata_loaded = Signal(int, dict)
    finished = Signal()

    def __init__(self, image_paths):
        super().__init__()
        self.image_paths = image_paths
    
    @Slot()
    def run(self):
        total_images = len(self.image_paths)
        for i, path in enumerate(self.image_paths):
            try:
                metadata = self.get_exif_data(path)
                if metadata:
                    self.metadata_loaded.emit(i, dict(img_relative_path=path, **metadata))

                    progress = int((i + 1) / total_images * 100)
                    self.progress_changed.emit(progress)
            except Exception as e:
                import traceback
                print(f"Error procesando {path}: {e}")
                traceback.print_exc()  # Muestra el stack trace completo

        self.finished.emit()


    def get_exif_data(self, image_path):
        metadata = get_metadata(image_path)
        print("metadata:", metadata)
        latitude, longitude = get_gps_coordinates(metadata)
        print(f"Latitud: {latitude}, Longitud: {longitude}")
        image_width, image_height = get_image_resolution(metadata)


        yaw_degree, pitch_degree, roll_degree = get_gimbal_euler_angles(metadata)
        relative_altitude = get_relative_altitude(metadata)
        GSD_horizontal, GSD_vertical = calcule_gsd_teorico(metadata)

        datetime = metadata.get("EXIF:DateTimeOriginal")
        basename = os.path.basename(image_path)
        
        metadata_data = {
            "name": basename,
            "latitude": latitude,
            "longitude" : longitude,
            "yaw_degree": yaw_degree,
            "pitch_degree": pitch_degree,
            "roll_degree": roll_degree,
            "datetime_original": datetime,
            "image_width": image_width,
            "image_height": image_height,
            "gsd_horizontal": GSD_horizontal,
            "gsd_vertical": GSD_vertical,
            "relative_altitude": relative_altitude
        }
       
        return metadata_data

def read_metadata_worker(path):
    try:
        metadata = get_metadata(path)
        latitude, longitude = get_gps_coordinates(metadata)
        image_width, image_height = get_image_resolution(metadata)
        yaw_degree, pitch_degree, roll_degree = get_gimbal_euler_angles(metadata)
        relative_altitude = get_relative_altitude(metadata)
        GSD_horizontal, GSD_vertical = calcule_gsd_teorico(metadata)
        datetime = metadata.get("EXIF:DateTimeOriginal")
        basename = os.path.basename(path)
        
        # altituded sobre el nivel del mar
        over_sea_level = metadata.get("EXIF:GPSAltitude", None)
        # model de drone
        drone_model = metadata.get("XMP:DroneModel", 'M3M')
        

        # Parse Dewarp Data e.g. "YYYY-mm-dd; fx,fy,cx,cy,k1,k2,p1,p2,k3"

        dewarp = metadata.get('XMP:DewarpData', None)

        fx=fy=cx=cy=k1=k2=p1=p2=k3=None
        _, nums = dewarp.split(";", 1)
        vals = [float(x.strip()) for x in nums.replace("\n", " ").split(",") if x.strip()!=""]
        if len(vals) >= 9:
            fx, fy, cx, cy, k1, k2, p1, p2, k3 = vals[:9]

        # Vignetting coefficients k[0..5]
        vign = metadata.get('XMP:VignettingData', None)
        kpoly = None
        if isinstance(vign, str):
            kpoly = [float(x.strip()) for x in vign.split(",") if x.strip()!=""]
            if len(kpoly) < 6:
                kpoly = None

        # Calibrated HMatrix: 9 numbers
        hcal = metadata.get('XMP:CalibratedHMatrix', None)

        H_cal = None
        if isinstance(hcal, str):
            hvals = [float(x.strip()) for x in hcal.split(",") if x.strip()!=""]
            if len(hvals) == 9:
                H_cal = np.array(hvals, dtype=np.float64).reshape(3,3).tolist()


        h_dewarp = metadata.get('XMP:DewarpHMatrix', None)
        H_d = None 
        if isinstance(h_dewarp, str):
            hvals = [float(x.strip()) for x in h_dewarp.split(",") if x.strip()!=""]
            if len(hvals) == 9:
                H_d = np.array(hvals, dtype=np.float64).reshape(3,3).tolist()

        # Center for vignetting (designed optical center)
        # Note: guide says CenterX, CenterY from Calibrated Optical Center X/Y
        cx_design = metadata.get('XMP:CalibratedOpticalCenterX', 0.0)
        cy_design = metadata.get('XMP:CalibratedOpticalCenterY', 0.0)

        # Photometric fields
        bits = int(metadata.get('EXIF:BitsPerSample', 16))
        black = int(metadata.get('XMP:BlackLevel', 0))
        gain  = float(metadata.get("XMP:SensorGain", 1.0))
        exp_us  = float(metadata.get("XMP:ExposureTime", 10000))
        pCam = float(metadata.get("XMP:SensorGainAdjustment", 1.0))
        irradiance = float(metadata.get("XMP:Irradiance", 1.0))
        band = str(metadata.get("XMP:BandName", "")).upper()
        

        return dict(
        relative_path = path,
        name = basename,
        latitude = latitude,
        longitude = longitude,
        yaw_degree = yaw_degree,
        pitch_degree = pitch_degree,
        datetime_original = datetime,
        roll_degree = roll_degree,
        image_width = image_width,
        image_height = image_height,
        gsd_horizontal = GSD_horizontal,
        gsd_vertical = GSD_vertical,
        relative_altitude = relative_altitude,
        over_sea_level = over_sea_level,
        drone_model = drone_model,
        bits=bits, black=black, gain=gain, exp_us=exp_us, pCam=pCam,
        irradiance=irradiance, band=band,
        kpoly=kpoly, cx_design=cx_design, cy_design=cy_design,
        fx=fx, fy=fy, cx=cx, cy=cy, k1=k1, k2=k2, p1=p1, p2=p2, k3=k3,
        H_cal=H_cal, H_dewarp=H_d
    )

    except Exception as e:
        print(f"Error leyendo {path}: {e}")
        return None
    
class MetadataProcessWorker(QObject):
    progress_changed = Signal(int)         # Progreso %
    all_metadata_ready = Signal(list)      # Lista con todos los metadatos
    finished = Signal()

    def __init__(self, image_paths):
        super().__init__()
        self.image_paths = image_paths

    
    @Slot()
    def run(self):
        total = len(self.image_paths)
        results = []

        # Multiprocessing Pool
        print("Num Cpu:", os.cpu_count())
        with Pool(processes=4) as pool:
            for i, data in enumerate(pool.imap(read_metadata_worker, self.image_paths)):
                results.append(data)
                self.progress_changed.emit(int((i + 1) / total * 100))

        self.all_metadata_ready.emit(results)
        self.finished.emit()
    
class ImageSelectionScreen(QFrame):
    def __init__(self, 
                    parent = None, 
                    dialog_parent=None, 
                    first_page = False,
                    on_update_images_metadata = None,
                    on_next_page = None):
        
        super().__init__(parent)
        self.dialog_parent = dialog_parent  # Almacena la referencia a NewAnalysisDialog
        self.on_update_images_metadata = on_update_images_metadata
        self.on_next_page = on_next_page

        layout = QVBoxLayout()

        self.info_label = QLabel("\u274C Se requieren al menos 3 imágenes en formato JPG o TIFF.")
        self.info_label.setStyleSheet("color: red;")
        layout.addWidget(self.info_label)
        
        self.image_list = QListWidget()
        self.image_list.setSelectionMode(QListWidget.ExtendedSelection)

        self.image_list.setStyleSheet("""
    QListWidget::item:hover {
        background-color: rgba(100, 149, 237, 0.5);
    }
    QListWidget::item:selected {
        background-color: rgba(70, 130, 180, 0.8);
        color: white;
    }

    QScrollBar:vertical {
        background: #f0f0f0;
        width: 12px;
        margin: 0px 0px 0px 0px;
    }
    QScrollBar::handle:vertical {
        background: #999999;
        min-height: 20px;
        border-radius: 5px;
    }
    QScrollBar::handle:vertical:hover {
        background: #666666;
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        background: none;
        height: 0px;
    }
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
        background: none;
    }

    QScrollBar:horizontal {
        background: #f0f0f0;
        height: 12px;
        margin: 0px 0px 0px 0px;
    }
    QScrollBar::handle:horizontal {
        background: #999999;
        min-width: 20px;
        border-radius: 5px;
    }
    QScrollBar::handle:horizontal:hover {
        background: #666666;
    }
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
        background: none;
        width: 0px;
    }
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
        background: none;
    }
""")
        
        button_layout = QHBoxLayout()
        self.add_images_button = QPushButton("Añadir Imágenes...")
        self.add_images_button.clicked.connect(self.add_images)
        button_layout.addWidget(self.add_images_button)
        
        self.add_folder_button = QPushButton("Añadir Carpeta...")
        self.add_folder_button.clicked.connect(self.add_folder)
        button_layout.addWidget(self.add_folder_button)

        self.remove_selected_button = QPushButton("Eliminar Seleccionado")
        self.remove_selected_button.clicked.connect(self.remove_selected)
        button_layout.addWidget(self.remove_selected_button)
        
        layout.addLayout(button_layout)
        layout.addWidget(self.image_list)

        self.progress_bar = QProgressBar()
        self.progress_bar.setStyleSheet(""" QProgressBar { border: 2px solid grey; border-radius: 5px; text-align: center; }
                                           QProgressBar::chunk { background-color: #76e900; width: 20px; }""")

        self.progress_bar.setMinimumWidth(400)
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(20)
        self.progress_bar.setTextVisible(False)

        self.progress_bar.setFormat("Leyendo EXIF Metadata: %p%") 

        layout.addWidget(self.progress_bar)
        self.progress_bar.setVisible(False)

        button_layout = QHBoxLayout()
        if not first_page:
            self.back_button = QPushButton("< Atrás")
            self.back_button.clicked.connect(self.go_back_to_initial)
        else:
            self.back_button = QPushButton("Cancelar")
            self.back_button.clicked.connect(self.close_dialog)
        
        button_layout.addWidget(self.back_button)
        
        self.next_button = QPushButton("Siguiente >")
        self.next_button.clicked.connect(self.start_read_metadata)
        self.next_button.setEnabled(False)
        button_layout.addWidget(self.next_button)
        layout.addLayout(button_layout)
        self.setLayout(layout)

    def close_dialog(self):
        parent = self.dialog_parent
        if isinstance(parent, QDialog):
            parent.reject() 
        else:
            parent.close()

    def add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Seleccionr carpeta")
        if folder:
            files = [os.path.join(folder, f) for f in os.listdir(folder) if f.lower().endswith(('.jpg','.jpeg','.tiff','.tif'))]
            print("\nfiles:", len(files))
            print()
            self.image_list.addItems(files)
        
        self.validate_selection()
    
    def add_images(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Seleccionar imágenes", "", "Imágenes (*.jpg *.jpeg *.tiff *.tif)")
        if files:
            self.image_list.addItems(files)
        self.validate_selection()
    
    def add_path_images(self, files):
        if files:
            self.image_list.addItems(files)
        
        self.validate_selection()

    def validate_selection(self):
        if self.image_list.count() >= 3:
            self.info_label.setText("✔ Imágenes seleccionadas correctamente.")
            self.info_label.setStyleSheet("color: green;")
            self.next_button.setEnabled(True)
        else:
            self.info_label.setText("\u274C Se requieren al menos 3 imágenes en formato JPG o TIFF.")
            self.info_label.setStyleSheet("color: red;")
            self.next_button.setEnabled(False)

    def remove_selected(self):
        for item in self.image_list.selectedItems():
            self.image_list.takeItem(self.image_list.row(item))

    def start_read_metadata(self):
        print("Comenzando la lectura de metadatos..............")
        self.next_button.setEnabled(False)
        print()
        self.progress_bar.setVisible(True)
        self.progress_bar.setTextVisible(True)
        image_paths = [self.image_list.item(i).text() for i in range(self.image_list.count())]
        total_images = len(image_paths)
        print("\ntotal_images:", total_images)
        print()

        self.qthread = QThread()
        self.worker = MetadataProcessWorker(image_paths)
        self.worker.moveToThread(self.qthread)

        self.qthread.started.connect(self.worker.run)
        self.worker.progress_changed.connect(self.progress_bar.setValue)
        self.worker.all_metadata_ready.connect(self.on_all_metadata_ready)
        #self.worker.finished.connect(self.on_metadata_finished, Qt.QueuedConnection)
        self.worker.finished.connect(self.qthread.quit)
        #self.worker.finished.connect(self.worker.deleteLater)
        #self.worker.finished.connect(self.qthread.deleteLater)
        # Limpieza automática
        self.worker.finished.connect(self.worker.deleteLater)
        self.qthread.finished.connect(self.qthread.deleteLater)
        self.qthread.start()

        return None
    
    def on_all_metadata_ready(self, metadata_list):
        self.next_button.setEnabled(True)

        if self.on_update_images_metadata is not None:
            self.on_update_images_metadata(metadata_list)
        else:
            for idx, metadata in enumerate(metadata_list):
                if metadata:
                    self.dialog_parent.new_analysis_data_store.add_image_data(idx, metadata)

        # Ir a la siguiente pantalla
        print("self.on_next_page", self.on_next_page)
        if self.on_next_page is not None:
            self.on_next_page()
        else:
            self.dialog_parent.go_to_image_data_table()

    def on_metadata_loaded(self, index, metadata):
        self.dialog_parent.new_analysis_data_store.add_image_data(index, metadata)
    
    def on_metadata_finished(self):
        self.dialog_parent.go_to_image_data_table()

    def go_back_to_initial(self):
        self.dialog_parent.go_back_to_initial()

    def get_exif_data(self, image_path):
        metadata = get_metadata(image_path)
        latitude, longitude = get_gps_coordinates(metadata)
        print(f"Latitud: {latitude}, Longitud: {longitude}")
        image_width, image_height = get_image_resolution(metadata)

        yaw_degree, pitch_degree, roll_degree = get_gimbal_euler_angles(metadata)
        relative_altitude = get_relative_altitude(metadata)
        GSD_horizontal, GSD_vertical = calcule_gsd_teorico(metadata)

        datetime = metadata.get("EXIF:DateTimeOriginal")
        basename = os.path.basename(image_path)
        
        metadata_data = {
            "name": basename,
            "latitude": latitude,
            "longitude" : longitude,
            "yaw_degree": yaw_degree,
            "pitch_degree": pitch_degree,
            "roll_degree": roll_degree,
            "datetime_original": datetime,
            "image_width": image_width,
            "image_height": image_height,
            "gsd_horizontal": GSD_horizontal,
            "gsd_vertical": GSD_vertical,
            "relative_altitude": relative_altitude
        }
       
        return metadata_data

class ImageDataTableScreen(QFrame):
    finished_configure = Signal()
    def __init__(self, parent = None, 
                 dialog_parent = None,
                 on_next_page = None,
                 on_prev_page = None):
        super().__init__(parent)
        self.dialog_parent = dialog_parent  # Almacena la referencia a NewAnalysisDialog
        self.on_next_page = on_next_page
        self.on_prev_page = on_prev_page

        layout = QVBoxLayout()
   
        # Título de la pantalla
        self.title_label = QLabel("Propiedades de Imagen")
        self.title_label.setStyleSheet("font-weight: bold; font-size: 14px; margin-bottom: 4px;")

        self.title_label.setAlignment(Qt.AlignCenter)  # Centra el título
        layout.addWidget(self.title_label)

        # Crear la tabla
        self.table = QTableWidget()
        self.table.setRowCount(0)
        self.table.setColumnCount(9)
        self.table.setHorizontalHeaderLabels(["Nombre","Ancho","Alto", "Latitud", "Longitud", "Ángulo Yaw", "Ángulo Pitch", "Ángulo Roll", "Fecha"])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)

        header = self.table.horizontalHeader()

        header.setSectionResizeMode(QHeaderView.Interactive)  # todas manuales
        header.setStretchLastSection(True)

        #header.setSectionResizeMode(0, QHeaderView.Stretch)   # solo "Nombre" se adapta

        #self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setColumnWidth(0, 250)  # El primer parámetro es el índice (0), el segundo los píxeles
        #self.add_image_data()
        
        # Crear un área de desplazamiento para la tabla
        scroll_area = QScrollArea()
        scroll_area.setWidget(self.table)
        scroll_area.setWidgetResizable(True)  # Hacer que la tabla se ajuste al tamaño del área
        scroll_area.setAlignment(Qt.AlignCenter)
        scroll_area.setStyleSheet("""
            QScrollBar:vertical {
                background: #f0f0f0; /* fondo de la barra */
                width: 12px;
                margin: 0px 0px 0px 0px;
            }
            QScrollBar::handle:vertical {
                background: #999999; /* color del handle (barra que se mueve) */
                min-height: 20px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical:hover {
                background: #666666; /* más oscuro cuando el mouse pasa encima */
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                background: none;
                height: 0px;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }

            QScrollBar:horizontal {
                background: #f0f0f0;
                height: 12px;
                margin: 0px 0px 0px 0px;
            }
            QScrollBar::handle:horizontal {
                background: #999999;
                min-width: 20px;
                border-radius: 5px;
            }
            QScrollBar::handle:horizontal:hover {
                background: #666666;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                background: none;
                width: 0px;
            }
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
                background: none;
            }
        """)
        layout.addWidget(scroll_area)

        # Botones en la parte inferior
        button_layout = QHBoxLayout()
        self.back_button = QPushButton("< Atrás")
        self.back_button.clicked.connect(self.go_back_to_image_selection)
        button_layout.addWidget(self.back_button)

        self.finished_button = QPushButton('Siguiente >')
        self.finished_button.clicked.connect(self.finish_configure)
        button_layout.addWidget(self.finished_button)

        layout.addLayout(button_layout)

        self.setLayout(layout)

    def _convert_format_date(self, date_str):
        # Convertir a datetime
        if date_str is None:
            return ""
        date = datetime.strptime(date_str, "%Y:%m:%d %H:%M:%S")

        # Formato más entendible (día/mes/año hora)
        date_parsed = date.strftime("%d/%m/%Y %H:%M:%S")

        return date_parsed

    def update_data_table(self, images_data):
        table_data = [[ metadata["name"],
            metadata["image_width"],
            metadata["image_height"],
            metadata["latitude"],
            metadata["longitude"],
            metadata["yaw_degree"],
            metadata["pitch_degree"],
            metadata["roll_degree"],
            self._convert_format_date(metadata["datetime_original"]),
                ] for metadata in images_data.values()]

        self.table.setRowCount(0)
        for data in table_data:
            row_position = self.table.rowCount()
            self.table.insertRow(row_position)
            for column, value in enumerate(data):
                self.table.setItem(row_position, column, QTableWidgetItem(str(value)))

    def load_metadata(self, metadata_list):
        print("metadata_list:", metadata_list)
        self.table.setRowCount(0)
        for data in metadata_list:
            row_position = self.table.rowCount()
            self.table.insertRow(row_position)
            for column, value in enumerate(data):
                self.table.setItem(row_position, column, QTableWidgetItem(str(value)))
    
    def go_back_to_image_selection(self):
        if self.on_prev_page is not None:
            self.on_prev_page()
        else:
            self.dialog_parent.go_back_to_image_selection()
    
    # def add_image_data(self):
    #     image_data = [["Imagen1.jpg", "12.345", "-67.890", "139.5", "-90.0", "180.00" , "2025-01-28"],
    #         ["Imagen2.tiff", "45.678", "-123.456", "2025-01-27",  "-90.0", "180.00" , "2025-01-28"],
    #         ["Imagen3.jpg", "23.456", "-98.765", "2025-01-26",  "-90.0", "180.00" , "2025-01-28"]]
        
    #     for data in image_data:
    #         row_position = self.table.rowCount()
    #         self.table.insertRow(row_position)
    #         for column, value in enumerate(data):
    #             self.table.setItem(row_position, column, QTableWidgetItem(value))

    def finish_configure(self):
        if self.on_next_page is not None:
            self.on_next_page()
        else:
            self.dialog_parent.go_to_manager_multi_specs_bands()
        #self.finished_configure.emit()
        ## Aqui guardar datos en json
        ## self.new_analysis_data_store.images_data
        
        #base_dir = self.dialog_parent.new_analysis_data_store.base_dir
        #images_data = self.dialog_parent.new_analysis_data_store.images_data
        #name = self.dialog_parent.new_analysis_data_store.name
        
        #config = {
        #    "project_info": {
        #        "name": name,
        #        "creation_date": datetime.now().isoformat(),
        #        "num_images": len(images_data),
        #        "base_dir": base_dir
        #    },
        #    "image_metatada": images_data}
        
        #self.save_configure_analysis(base_dir, config)

        

        #if isinstance(self.dialog_parent, QDialog):
        #    self.dialog_parent.accept()  
        #else:
        #    self.dialog_parent.close()
    
    def save_configure_analysis(self, base_dir, data):
        import json
        with open(f"{base_dir}/config.json", "w") as f:
            json.dump(data, f, indent=4)    

class AnalysisData:
    def __init__(self, base_dir = ".", name = None, images_data = None, 
                 alt_avg = None, gsd_avg = None, identifier_id = None, adquisition_date = None):
        self.images_data = images_data
        self.base_dir = base_dir
        self.name = name
        self.field_info = dict(stage = "Cuajado", soil_type = None, irrigation_type = None)
        self.alt_avg = alt_avg
        self.gsd_avg = gsd_avg
        self.identifier_id = identifier_id
        self.adquisition_date = adquisition_date
        self.processing_config = dict(option_resolution = 0,
                                      target_resolution = None, 
                                      threshold_nitrogen = None)
        self.options_resolutions = []
        print("self.gsd_avg:", self.gsd_avg)

        if self.gsd_avg is not None:
            self.options_resolutions = [self.gsd_avg * 8 , self.gsd_avg * 6, self.gsd_avg * 4]
            self.set_target_resolution(self.processing_config["option_resolution"])
        
        print("self.options_resolutions:", self.options_resolutions)
        
        self.thresh_stages = THRESH_STAGES_DEFAULT
    
    def set_adquisition_date(self, fecha):
        self.adquisition_date = fecha
        
    def set_images_data(self, images_data):
        self.images_data = images_data

    def add_image_data(self, id_img, metadata):
        if self.images_data is None:
            self.images_data = {}
        self.images_data[id_img] = metadata

    def set_base_dir(self, base_dir):
        self.base_dir = base_dir

    def set_name(self, name):
        self.name = name

    def set_alt_avg(self, value):
        self.alt_avg = value
    
    def set_gsd_avg(self, value):
        self.gsd_avg = value
        self.options_resolutions = [value * 8 , value * 6, value * 4]
        self.set_target_resolution(self.processing_config["option_resolution"])
    
    def set_target_resolution(self, value):
        self.processing_config["option_resolution"] = value
        self.processing_config["target_resolution"] = self.options_resolutions[value]

    def set_thresh_stages(self, thresh_stages):
        self.thresh_stages = thresh_stages
        self.processing_config["threshold_nitrogen"] = self.thresh_stages[self.field_info["stage"]]
    
    def update_thresh_stage(self, stage, threshold_nitrogen):
        self.thresh_stages[stage] = threshold_nitrogen

    def update_stage(self, stage):
        if stage is not None:
            self.field_info["stage"] = stage
            self.processing_config["threshold_nitrogen"] = self.thresh_stages[stage]

    def update_field_info(self, stage = None, soil_type = None, irrigation_type = None):
        self.field_info.update({
            "stage": stage,
            "soil_type": soil_type,
            "irrigation_type": irrigation_type
        })
        
        if stage is not None:
            self.processing_config["threshold_nitrogen"] = self.thresh_stages[stage]
    
    def update_processing_config(self, option_resolution = 0, target_resolution = None, threshold_nitrogen = None):
        self.processing_config.update({
            "option_resolution": option_resolution,
            "target_resolution": target_resolution,
            "threshold_nitrogen": threshold_nitrogen
        })
        

# --- NUEVA CONFIGURACIÓN DE ANCHOS ---
# [Index, RGB, Roja, Verde, NIR, Red Edge, Eliminar]
COL_WIDTHS = [50, 195, 230, 230, 230, 230, 60]

class BandSelector(QComboBox):
    def __init__(self, w = 225):
        super().__init__()
        # Los hacemos un poco más anchos ahora que hay más espacio
        self.options = []
        self.setFixedWidth(w)
        self.addItem("Selección...")
        self.setStyleSheet("""
            QComboBox {
                border: 1px solid #D1D5DB;
                border-radius: 6px;
                padding: 6px;
                background-color: white;
            }
            QComboBox::drop-down { border: none; }
        """)
    def update_options(self, options):
        self.options = options
        self.clear()
        self.addItems(["Selección..."] + options)
    

class CaptureRow(QFrame):
    def __init__(self, index, parent_manager=None, is_new=False):
        super().__init__()
        self.setFixedHeight(70)
        self.parent_manager=parent_manager
        self.setObjectName("FilaCaptura")
        
        self.setStyleSheet("""
            #FilaCaptura {
                border-bottom: 1px solid #F3F4F6;
                background-color: white;
            }
            #FilaCaptura:hover {
                background-color: #F9FAFB;
            }
        """)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 0, 20, 0)
        layout.setSpacing(10)

        # 1. Índice
        #lbl_idx = QLabel("New" if is_new else str(index))
        #lbl_idx.setFixedWidth(COL_WIDTHS[0])
        #lbl_idx.setStyleSheet("color: #3B82F6; font-weight: bold; border: none;" if is_new else "color: #9CA3AF; border: none;")
        #layout.addWidget(lbl_idx)

        # 2. Columnas de Bandas (Empezando por RGB)
        # Creamos 5 selectores para: RGB, Roja, Verde, NIR, Red Edge
        
        self.rgb_band_cb = BandSelector(w=190)
        self.red_band_cb = BandSelector()
        self.green_band_cb = BandSelector()
        self.nir_band_cb = BandSelector()
        self.re_band_cb = BandSelector()
        
        layout.addWidget(self.rgb_band_cb)
        layout.addWidget(self.red_band_cb)
        layout.addWidget(self.green_band_cb)
        layout.addWidget(self.nir_band_cb)
        layout.addWidget(self.re_band_cb)
        #for _ in range(5):
        #    cb = BandSelector()
        #    layout.addWidget(cb)

        # 3. Icono de Eliminar (Tacho)
        self.btn_delete = QPushButton("🗑️")
        self.btn_delete.setFixedWidth(COL_WIDTHS[6])
        self.btn_delete.setCursor(Qt.PointingHandCursor)
        self.btn_delete.setStyleSheet("""
            QPushButton {
                color: #EF4444;
                border: none;
                background: transparent;
                font-size: 18px;
            }
            QPushButton:hover { color: #B91C1C; }
        """)

        for cb in [self.rgb_band_cb, self.red_band_cb, self.green_band_cb,
           self.nir_band_cb, self.re_band_cb]:
            cb.currentIndexChanged.connect(self.parent_manager.validate_all_rows)
    
        self.btn_delete.clicked.connect(self.deleteLater)
        layout.addWidget(self.btn_delete)
    
    def get_values_row(self):
        return [self.rgb_band_cb.currentText(),
                self.red_band_cb.currentText(),
                self.green_band_cb.currentText(),
                self.nir_band_cb.currentText(),
                self.re_band_cb.currentText(),
                ]

    def update_options(self, rgb_images, red_images, green_images, nir_images, re_images):
        self.rgb_band_cb.update_options(rgb_images)
        self.red_band_cb.update_options(red_images)
        self.green_band_cb.update_options(green_images)
        self.nir_band_cb.update_options(nir_images)
        self.re_band_cb.update_options(re_images)
        self.update()

class ManagerMultiSpecBanbScreen(QFrame):
    def __init__(self, 
                 dialog_parent = None,
                 on_prev_page = None,
                 on_finish_configure = None):
        super().__init__()
        self.dialog_parent = dialog_parent
        self.on_prev_page = on_prev_page
        self.on_finish_configure = on_finish_configure
        self.setWindowTitle("Gestor de Bandas")
        self.resize(1150, 700)
        self.setStyleSheet("background-color: white;")
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(30, 30, 30, 20)

        # --- HEADER (TÍTULO, SUBTÍTULO Y BOTÓN) ---
        header_layout = QHBoxLayout()
        title_vbox = QVBoxLayout()
        title = QLabel("Gestor de Capturas y Bandas")
        title.setStyleSheet("font-size: 22px; font-weight: bold; color: #111827; border: none;")
        subtitle = QLabel("*No fue posible identificar las bandas espectrales en las siguientes capturas. Por favor, realiza la asignación manual de las bandas para cada captura.")
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #FF0000; font-size: 14px; border: none;")
        title_vbox.addWidget(title)
        title_vbox.addWidget(subtitle)
        
        self.btn_new = QPushButton("+ Nueva Captura")
        self.btn_new.setCursor(Qt.PointingHandCursor)
        self.btn_new.setStyleSheet("""
            QPushButton {
                background-color: #3B82F6; color: white; border-radius: 8px;
                padding: 10px 20px; font-weight: bold; border: none;
            }
            QPushButton:hover { background-color: #2563EB; }
        """)
        self.btn_new.clicked.connect(self.add_empty_row)

        header_layout.addLayout(title_vbox, 1)
        #header_layout.addStretch()
        header_layout.addWidget(self.btn_new, 0)
        main_layout.addLayout(header_layout)

        # --- TABLA ---
        self.table_box = QFrame()
        self.table_box.setObjectName("ContenedorPrincipal")
        self.table_box.setStyleSheet("""
            #ContenedorPrincipal {
                border: 1px solid #E5E7EB;
                border-radius: 12px;
                background-color: white;
            }
        """)
        
        table_vbox = QVBoxLayout(self.table_box)
        table_vbox.setContentsMargins(0, 0, 0, 0)
        table_vbox.setSpacing(0)

        # Encabezado
        header_row = QFrame()
        header_row.setFixedHeight(50)
        header_row.setStyleSheet("""
            background-color: #F9FAFB; 
            border-bottom: 1px solid #E5E7EB; 
            border-top-left-radius: 12px; 
            border-top-right-radius: 12px;
        """)
        hr_layout = QHBoxLayout(header_row)
        hr_layout.setContentsMargins(20, 0, 20, 0)
        hr_layout.setSpacing(10)

        # Etiquetas de columna (Sin el identificador)
        cols = [
            #("#", COL_WIDTHS[0]), 
            ("<font color='#A855F7'>●</font> RGB", COL_WIDTHS[1]), 
            ("<font color='#EF4444'>●</font> Roja", COL_WIDTHS[2]), 
            ("<font color='#22C55E'>●</font> Verde", COL_WIDTHS[3]), 
            ("<font color='#6B7280'>●</font> NIR", COL_WIDTHS[4]), 
            ("<font color='#F97316'>●</font> Red Edge", COL_WIDTHS[5]), 
            ("", COL_WIDTHS[6])
        ]
        
        for text, w in cols:
            lbl = QLabel(text)
            lbl.setFixedWidth(w)
            lbl.setStyleSheet("font-weight: bold; color: #4B5563; font-size: 12px; border: none;")
            hr_layout.addWidget(lbl)
        
        table_vbox.addWidget(header_row)

        # Scroll
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("QScrollArea { border: none; background: white; border-bottom-left-radius: 12px; border-bottom-right-radius: 12px; }")
        
        self.scroll_content = QWidget()
        self.rows_layout = QVBoxLayout(self.scroll_content)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(0)
        self.rows_layout.setAlignment(Qt.AlignTop)
        self.scroll.setWidget(self.scroll_content)
        
        table_vbox.addWidget(self.scroll)
        main_layout.addWidget(self.table_box)
        self.rows_widgets = []
        
        # Filas iniciales
        #for i in range(1, 4):
        #    self.rows_layout.addWidget(CaptureRow(i))

        
        # Botones en la parte inferior
        button_layout = QHBoxLayout()
        self.back_button = QPushButton("< Atrás")
        self.back_button.clicked.connect(self.go_prev_page)
        button_layout.addWidget(self.back_button)

        self.finished_button = QPushButton('Finalizar')
        self.finished_button.clicked.connect(self.finish_configure)
        button_layout.addWidget(self.finished_button)
        self.finished_button.setEnabled(False)
        main_layout.addLayout(button_layout)

    @Slot()
    def add_empty_row(self):
        # Añade la fila nueva al principio
        self.rows_layout.insertWidget(0, CaptureRow(0, is_new=True))
    
    def go_prev_page(self):
        if self.on_prev_page is not None:
            self.on_prev_page()
        else:
            self.dialog_parent.go_to_image_data_table()
    
    def update_tables(self, rgb_names, red_names, green_names, nir_names, re_names):
        num_rows = len(rgb_names)
        
        if num_rows > 0:
            self.btn_new.setEnabled(True)
        else:
            self.btn_new.setEnabled(False)

        for i in range(num_rows):
            row_wb = CaptureRow(i, parent_manager=self)
            row_wb.update_options(rgb_names, red_names, green_names, nir_names, re_names)
            row_wb.rgb_band_cb.setCurrentIndex(i + 1)
            row_wb.red_band_cb.setCurrentIndex(i + 1)
            row_wb.green_band_cb.setCurrentIndex(i + 1)
            row_wb.nir_band_cb.setCurrentIndex(i + 1)
            row_wb.re_band_cb.setCurrentIndex(i + 1)
            self.rows_widgets.append(row_wb)
            self.rows_layout.addWidget(row_wb)
        
        self.validate_all_rows()

    
    def validate_all_rows(self):
        all_valid = True

        for row in self.rows_widgets:
            combos = [
                row.rgb_band_cb,
                row.red_band_cb,
                row.green_band_cb,
                row.nir_band_cb,
                row.re_band_cb
            ]

            for cb in combos:
                if cb.currentIndex() == 0:  # "Seleccionar"
                    all_valid = False
                    break

            if not all_valid:
                break

        self.finished_button.setEnabled(all_valid)

    def finish_configure(self):
        
        rows_bands = []
        for r_w in self.rows_widgets:
            bands = r_w.get_values_row()
            rows_bands.append(bands)

        if self.on_finish_configure is not None:
            self.on_finish_configure(rows_bands)
            return
        
        images_data = self.dialog_parent.new_analysis_data_store.images_data

        for r_w in self.rows_widgets:
            bands = r_w.get_values_row()
            rgb_band = bands[0]
            for _, im_d in images_data.items():
                if rgb_band in im_d['name']:
                    im_d["muitispec_bands"] = dict(r = bands[1],
                                                   g = bands[2],
                                                   nir = bands[3],
                                                   re = bands[4])

        avg_alt = None
        avg_gsd = None

        if images_data:
            num_images = len(images_data)
            alts = [im_data['relative_altitude'] for im_data in images_data.values()]
            avg_alt = sum(alts) / num_images
            print("avg_alt:", avg_alt)

            gsds = [im_data['gsd_horizontal'] for im_data in images_data.values() if "_D.JPG" not in im_data['relative_path']]
            avg_gsd = sum(gsds) / len(gsds) 

        self.dialog_parent.new_analysis_data_store.set_gsd_avg(avg_gsd)
        self.dialog_parent.new_analysis_data_store.set_alt_avg(avg_alt)
        
        #self.dialog_parent.new_analysis_data_store.update_processing_config(option_resolution = 0,
         #                                                                   target_resolution = avg_gsd * 8, 
        #                                                                   threshold_nitrogen = 2.0)

        self.dialog_parent.finished_configure.emit()
        if isinstance(self.dialog_parent, QDialog):
            self.dialog_parent.accept()  
        else:
            self.dialog_parent.close()

class ImageManagerDialog(QDialog):
    def __init__(self, parent=None, images_files = []):
        super().__init__(parent)
        self.setWindowTitle("Gestionar Imagenes")
        self.setFixedSize(1280, 650)
        self.stacked_widget = QStackedWidget(self)  # Contenedor principal de pantallas
        self.setLayout(QVBoxLayout())
        self.layout().addWidget(self.stacked_widget)
        
        self.images_data = dict()
        self.flight_info = dict(gsd_avg = None, alt_avg = None)
        self.image_selection_screen = ImageSelectionScreen(dialog_parent = self, 
                                                           first_page = True,
                                                           on_update_images_metadata = self.on_update_images_metadata,
                                                           on_next_page = self.go_image_data_table 
                                                           )
        
        self.image_data_screen = ImageDataTableScreen(dialog_parent = self,
                                                      on_prev_page = self.go_back_to_image_selection,
                                                      on_next_page = self.go_to_manager_multi_specs_bands)
        
        self.manager_multispect_banb = ManagerMultiSpecBanbScreen(dialog_parent = self,
                                                                  on_prev_page = self.go_back_to_image_data_table,
                                                                  on_finish_configure = self.on_finish_configure)

        self.image_selection_screen.add_path_images(images_files)
        self.stacked_widget.addWidget(self.image_selection_screen)
        self.stacked_widget.addWidget(self.image_data_screen)
        self.stacked_widget.addWidget(self.manager_multispect_banb)
        self.stacked_widget.setCurrentIndex(0)  # Mostrar la pantalla inicial
    
    def on_update_images_metadata(self, metadata_images):
        for idx, meta in enumerate(metadata_images):
            self.images_data[idx] = meta
        
    def go_image_data_table(self):
        self.image_data_screen.update_data_table(self.images_data)
        """Método para ir al paso de tabla de datos de imagen"""
        self.stacked_widget.setCurrentIndex(1)

    def go_back_to_image_selection(self):
        self.stacked_widget.setCurrentIndex(0)

    def go_back_to_image_data_table(self):
        self.stacked_widget.setCurrentIndex(1)
    
    def go_to_manager_multi_specs_bands(self):

        images_data = self.images_data

        ## Evaluar bandas completas
        rgb_images = []
        all_images_data_dict = dict()

        for _, im_data in images_data.items():
            relative_path = im_data["relative_path"]
            base_name = os.path.basename(relative_path)[:-4]
            if "_D" in relative_path:
                rgb_images.append(base_name)

            all_images_data_dict[base_name] = im_data
            
        
        images_incomplete_bands = []
        images_complete_bands = []
        suffixes = ["_MS_R", "_MS_G", "_MS_NIR", "_MS_RE"]

        for base_name in rgb_images:
            band_names = [
                base_name.replace("_D", suf) 
                for suf in suffixes
            ]

            if not all(name in all_images_data_dict for name in band_names):
                images_incomplete_bands.append(base_name)
            else:
                images_complete_bands.append(base_name)
        
        images_incomplete_green = []
        images_incomplete_red = []
        images_incomplete_nir = []
        images_incomplete_re = []

        for base_name_band in all_images_data_dict.keys():
            if "_MS_G" in base_name_band:
                band_name_rgb = base_name_band.replace("_MS_G","_D")
                if band_name_rgb not in images_complete_bands:
                    images_incomplete_green.append(all_images_data_dict[base_name_band]['name'])

            elif "_MS_R" in base_name_band and "_MS_RE" not in base_name_band:
                band_name_rgb = base_name_band.replace("_MS_R","_D")
                if band_name_rgb not in images_complete_bands:
                    images_incomplete_red.append(all_images_data_dict[base_name_band]['name'])
        
            elif "_MS_NIR" in base_name_band:
                band_name_rgb = base_name_band.replace("_MS_NIR","_D")
                if band_name_rgb not in images_complete_bands:
                    images_incomplete_nir.append(all_images_data_dict[base_name_band]['name'])
            
            elif "_MS_RE" in base_name_band:
                band_name_rgb = base_name_band.replace("_MS_RE","_D")
                if band_name_rgb not in images_complete_bands:
                    images_incomplete_re.append(all_images_data_dict[base_name_band]['name'])
            else:
                continue
            
        
        incomplete_bands = [images_incomplete_bands, images_incomplete_red, 
                                                   images_incomplete_green, images_incomplete_nir, images_incomplete_re]
        assert len(set(len(l) for l in incomplete_bands)) == 1, "Algunas capturas no tienen las bandas completas"

        # Ordenar segun matches de numeros y tiempo
        im_imcomplete_bands = images_incomplete_bands.copy()
        im_incomplete_red = []
        im_incomplete_green = []
        im_incomplete_nir = []
        im_incomplete_re = []

        for i in range(len(im_imcomplete_bands)):
            rgb_name = im_imcomplete_bands[i]
            print("rgb_name:", rgb_name)
            rgb_name = rgb_name.replace("_D", "")
            print("rgb_name:", rgb_name)
            parts = rgb_name.split("_")

            if len(parts) == 3:
                _, time_str, num_img = parts
            else:
                im_incomplete_red.append(images_incomplete_red[i])
                im_incomplete_green.append(images_incomplete_green[i])
                im_incomplete_nir.append(images_incomplete_nir[i])
                im_incomplete_re.append(images_incomplete_re[i])
                print("Formato inesperado:", rgb_name)

            #_, time_str, num_img = rgb_name.split("-")
            
            num_img = "_" + num_img + "_"
            print("time_str:", time_str)
            print("num_img:", num_img)
            print("time_str:", time_str[:-2])
            idx_red = [j for j, s in enumerate(images_incomplete_red) if num_img in s and time_str[:-2] in s]
            idx_green = [j for j, s in enumerate(images_incomplete_green) if num_img in s and time_str[:-2] in s]
            idx_nir = [j for j, s in enumerate(images_incomplete_nir) if num_img in s and time_str[:-2] in s]
            idx_re = [j for j, s in enumerate(images_incomplete_re) if num_img in s and time_str[:-2] in s]

            if len(idx_red) > 0:
                im_incomplete_red.append(images_incomplete_red[idx_red[0]])
            else:
                im_incomplete_red.append(images_incomplete_red[i])
                print("images_incomplete_red:", images_incomplete_red)

            if len(idx_green) > 0:
                im_incomplete_green.append(images_incomplete_green[idx_green[0]])
            else:
                im_incomplete_green.append(images_incomplete_green[i])

            if len(idx_nir) > 0:
                im_incomplete_nir.append(images_incomplete_nir[idx_nir[0]])
            else:
                im_incomplete_nir.append(images_incomplete_nir[i])

            if len(idx_re) > 0:
                im_incomplete_re.append(images_incomplete_re[idx_re[0]])
            else:
                im_incomplete_re.append(images_incomplete_re[i])

        self.manager_multispect_banb.update_tables(im_imcomplete_bands, im_incomplete_red, 
                                                   im_incomplete_green, im_incomplete_nir, im_incomplete_re)
        #self.image_data_screen.update_data_table(self.new_analysis_data_store.images_data)
        """Método para ir al paso de tabla de datos de imagen"""
        self.stacked_widget.setCurrentIndex(2)
    
    def get_data(self):
        return self.images_data, self.flight_info

    def on_finish_configure(self, rows_bands):

        for bands in rows_bands:
            rgb_band = bands[0]
            for _, im_d in self.images_data.items():
                if rgb_band in im_d['name']:
                    im_d["muitispec_bands"] = dict(r = bands[1],
                                                   g = bands[2],
                                                   nir = bands[3],
                                                   re = bands[4])

        avg_alt = None
        avg_gsd = None

        if len(self.images_data):
            num_images = len(self.images_data)
            alts = [im_data['relative_altitude'] for im_data in self.images_data.values()]
            avg_alt = sum(alts) / num_images
            print("avg_alt:", avg_alt)

            gsds = [im_data['gsd_horizontal'] for im_data in self.images_data.values() if "_D.JPG" not in im_data['relative_path']]
            avg_gsd = sum(gsds) / len(gsds)
            print("avg_gsd:", avg_gsd)

            self.flight_info["avg_alt"] = avg_alt
            self.flight_info["avg_gsd"] = avg_gsd

        #self.dialog_parent.new_analysis_data_store.set_gsd_avg(avg_gsd)
        #self.dialog_parent.new_analysis_data_store.set_alt_avg(avg_alt)
        
        #self.dialog_parent.new_analysis_data_store.update_processing_config(option_resolution = 0,
        #                                                                   target_resolution = avg_gsd * 8, 
        #                                                                    threshold_nitrogen = 2.0)

        #self.dialog_parent.finished_configure.emit()
        if isinstance(self, QDialog):
            self.accept()  
        else:
            self.close()


class NewAnalysisDialog(QDialog):
    finished_configure = Signal()
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Nuevo Análisis de Parcela")
        self.setFixedSize(1280, 650)

        self.stacked_widget = QStackedWidget(self)  # Contenedor principal de pantallas
        self.setLayout(QVBoxLayout())
        self.layout().addWidget(self.stacked_widget)

        self.new_analysis_data_store = AnalysisData()
        # Crear pantallas
        self.initial_screen = InitialConfigureScreen(dialog_parent = self)

        #self.create_initial_screen()
        self.image_selection_screen = ImageSelectionScreen(dialog_parent = self)

        self.image_data_screen = ImageDataTableScreen(dialog_parent = self)

        self.manager_multispect_banb = ManagerMultiSpecBanbScreen(dialog_parent = self)
        
        #ImageDataTableScreen
        self.stacked_widget.addWidget(self.initial_screen)
        self.stacked_widget.addWidget(self.image_selection_screen)
        self.stacked_widget.addWidget(self.image_data_screen)
        self.stacked_widget.addWidget(self.manager_multispect_banb)

        self.current_step = 0  # Variable para llevar el control de los pasos
        self.stacked_widget.setCurrentIndex(self.current_step)  # Mostrar la pantalla inicial
    
    def go_to_image_selection_screen(self):
        """Método para ir al paso de selección de imágenes"""
        if self.initial_screen.name_input.text().strip() and self.initial_screen.folder_input.text().strip():
            self.stacked_widget.setCurrentIndex(1)  # Ir al segundo paso
        else:
            # Validar los campos (puedes agregar lógica de validación aquí)
            self.initial_screen.name_input.setStyleSheet("border: 1px solid red;")
            self.initial_screen.folder_input.setStyleSheet("border: 1px solid red;")
    
    def go_back_to_initial(self):
        """Método para volver al primer paso"""
        self.stacked_widget.setCurrentIndex(0)

    def go_to_image_data_table(self):
        #print("self.new_analysis_data_store.images_data:", self.new_analysis_data_store.images_data)
        self.image_data_screen.update_data_table(self.new_analysis_data_store.images_data)
        """Método para ir al paso de tabla de datos de imagen"""
        self.stacked_widget.setCurrentIndex(2)
    
    def go_to_manager_multi_specs_bands(self):

        images_data = self.new_analysis_data_store.images_data

        ## Evaluar bandas completas
        rgb_images = []
        all_images_data_dict = dict()

        for _, im_data in images_data.items():
            relative_path = im_data["relative_path"]
            base_name = os.path.basename(relative_path)[:-4]
            if "_D" in relative_path:
                rgb_images.append(base_name)

            all_images_data_dict[base_name] = im_data
            
        
        images_incomplete_bands = []
        images_complete_bands = []
        suffixes = ["_MS_R", "_MS_G", "_MS_NIR", "_MS_RE"]

        for base_name in rgb_images:
            band_names = [
                base_name.replace("_D", suf) 
                for suf in suffixes
            ]

            if not all(name in all_images_data_dict for name in band_names):
                images_incomplete_bands.append(base_name)
            else:
                images_complete_bands.append(base_name)
        
        images_incomplete_green = []
        images_incomplete_red = []
        images_incomplete_nir = []
        images_incomplete_re = []

        for base_name_band in all_images_data_dict.keys():
            if "_MS_G" in base_name_band:
                band_name_rgb = base_name_band.replace("_MS_G","_D")
                if band_name_rgb not in images_complete_bands:
                    images_incomplete_green.append(all_images_data_dict[base_name_band]['name'])

            elif "_MS_R" in base_name_band and "_MS_RE" not in base_name_band:
                band_name_rgb = base_name_band.replace("_MS_R","_D")
                if band_name_rgb not in images_complete_bands:
                    images_incomplete_red.append(all_images_data_dict[base_name_band]['name'])
        
            elif "_MS_NIR" in base_name_band:
                band_name_rgb = base_name_band.replace("_MS_NIR","_D")
                if band_name_rgb not in images_complete_bands:
                    images_incomplete_nir.append(all_images_data_dict[base_name_band]['name'])
            
            elif "_MS_RE" in base_name_band:
                band_name_rgb = base_name_band.replace("_MS_RE","_D")
                if band_name_rgb not in images_complete_bands:
                    images_incomplete_re.append(all_images_data_dict[base_name_band]['name'])
            else:
                continue
            
        
        incomplete_bands = [images_incomplete_bands, images_incomplete_red, 
                                                   images_incomplete_green, images_incomplete_nir, images_incomplete_re]
        assert len(set(len(l) for l in incomplete_bands)) == 1, "Algunas capturas no tienen las bandas completas"

        # Ordenar segun matches de numeros y tiempo
        im_imcomplete_bands = images_incomplete_bands.copy()
        im_incomplete_red = []
        im_incomplete_green = []
        im_incomplete_nir = []
        im_incomplete_re = []

        for i in range(len(im_imcomplete_bands)):
            rgb_name = im_imcomplete_bands[i]
            print("rgb_name:", rgb_name)
            rgb_name = rgb_name.replace("_D", "")
            print("rgb_name:", rgb_name)
            parts = rgb_name.split("_")

            if len(parts) == 3:
                _, time_str, num_img = parts
            else:
                im_incomplete_red.append(images_incomplete_red[i])
                im_incomplete_green.append(images_incomplete_green[i])
                im_incomplete_nir.append(images_incomplete_nir[i])
                im_incomplete_re.append(images_incomplete_re[i])
                print("Formato inesperado:", rgb_name)

            #_, time_str, num_img = rgb_name.split("-")
            
            num_img = "_" + num_img + "_"
            print("time_str:", time_str)
            print("num_img:", num_img)
            print("time_str:", time_str[:-2])
            idx_red = [j for j, s in enumerate(images_incomplete_red) if num_img in s and time_str[:-2] in s]
            idx_green = [j for j, s in enumerate(images_incomplete_green) if num_img in s and time_str[:-2] in s]
            idx_nir = [j for j, s in enumerate(images_incomplete_nir) if num_img in s and time_str[:-2] in s]
            idx_re = [j for j, s in enumerate(images_incomplete_re) if num_img in s and time_str[:-2] in s]

            if len(idx_red) > 0:
                im_incomplete_red.append(images_incomplete_red[idx_red[0]])
            else:
                im_incomplete_red.append(images_incomplete_red[i])
                print("images_incomplete_red:", images_incomplete_red)

            if len(idx_green) > 0:
                im_incomplete_green.append(images_incomplete_green[idx_green[0]])
            else:
                im_incomplete_green.append(images_incomplete_green[i])

            if len(idx_nir) > 0:
                im_incomplete_nir.append(images_incomplete_nir[idx_nir[0]])
            else:
                im_incomplete_nir.append(images_incomplete_nir[i])

            if len(idx_re) > 0:
                im_incomplete_re.append(images_incomplete_re[idx_re[0]])
            else:
                im_incomplete_re.append(images_incomplete_re[i])

        self.manager_multispect_banb.update_tables(im_imcomplete_bands, im_incomplete_red, 
                                                   im_incomplete_green, im_incomplete_nir, im_incomplete_re)
        #self.image_data_screen.update_data_table(self.new_analysis_data_store.images_data)
        """Método para ir al paso de tabla de datos de imagen"""
        self.stacked_widget.setCurrentIndex(3)
