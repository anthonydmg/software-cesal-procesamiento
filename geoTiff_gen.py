import numpy as np
import rasterio
from rasterio.transform import from_origin
import exiftool
from PIL import Image

# Función para obtener metadatos de la imagen
def get_metadata(im_path):
    with exiftool.ExifToolHelper() as et:
        metadata = et.get_metadata(im_path)
    return metadata[0]

# Función para obtener las coordenadas GPS y altitud de los metadatos
def get_gps_coordinates(metadata):
    latitude = metadata.get('EXIF:GPSLatitude')
    latref = metadata.get('EXIF:GPSLatitudeRef')
    if latref == 'S':
        latitude *= -1.0
    longitude = metadata.get('EXIF:GPSLongitude')
    lonref = metadata.get('EXIF:GPSLongitudeRef')
    if lonref == 'W':
        longitude *= -1.0
    return latitude, longitude

# Función para obtener la altitud del dron
def get_drone_altitude(metadata):
    relative_altitude_text = metadata.get("XMP:RelativeAltitude")
    if relative_altitude_text is not None:
        print("relative_altitude_text:", relative_altitude_text)
        signo, numero = (relative_altitude_text[0], relative_altitude_text[1:]) if relative_altitude_text[0] in '+-' else ("+", relative_altitude_text[0])
        altitude_drone = float(numero) if signo == '+' else -float(numero)
        return altitude_drone
    else:
        print("Altitud relativa no encontrada.")
        return None

# Cargar la imagen y obtener los metadatos
imagen_jpg = "./data/trees-avocado/m3m/campo2/images/DJI_20241128154239_0001_D.JPG"
img = Image.open(imagen_jpg)

# Obtener los metadatos de la imagen
metadata = get_metadata(imagen_jpg)

# Obtener las coordenadas GPS de los metadatos
lat, lon = get_gps_coordinates(metadata)
print(f"Coordenadas de la imagen: Latitud {lat}, Longitud {lon}")

# Obtener la altitud del dron
alt = get_drone_altitude(metadata)
if alt is not None:
    print(f"Altitud del dron: {alt} metros")

# Parámetros de la cámara (ajustados con metadatos reales)
sensor_width_mm = 17.3  # Ancho del sensor en mm
sensor_height_mm = 13.0  # Alto del sensor en mm
focal_length = 12.29  # Distancia focal en mm (ajustado con metadatos reales)

# Cargar imagen para obtener su resolución en píxeles
width, height = img.size  # Resolución de la imagen en píxeles

# Calcular el tamaño del píxel en el suelo (GSD - Ground Sample Distance)
gsd_x = (alt * sensor_width_mm) / (focal_length * width)   # Tamaño del píxel en el eje X (m/píxel)
gsd_y = (alt * sensor_height_mm) / (focal_length * height)  # Tamaño del píxel en el eje Y (m/píxel)

print(f"GSD calculado: {gsd_x:.4f} m/píxel (X), {gsd_y:.4f} m/píxel (Y)")

# Crear la transformación geoespacial con las coordenadas obtenidas
transform = from_origin(lon, lat, gsd_x/100000, gsd_y/100000)

# Convertir la imagen a un arreglo numpy
img_array = np.array(img)

# Guardar la imagen como un archivo GeoTIFF
output_tiff = "imagen_georreferenciada_con_metadatos_y_altitud8.tif"
with rasterio.open(output_tiff, 'w', driver='GTiff', height=height, width=width,
                   count=3, dtype=img_array.dtype, crs='EPSG:4326', transform=transform) as dst:
    dst.write(img_array[:, :, 0], 1)  # Canal R
    dst.write(img_array[:, :, 1], 2)  # Canal G
    dst.write(img_array[:, :, 2], 3)  # Canal B

print(f"Imagen georreferenciada guardada como: {output_tiff}")