import os
import cv2
import matplotlib.pyplot as plt
import numpy as np
import exiftool
import numpy as np
import json
from glob import glob

def detection_trees_human_ann(im_path, show = False):
    image_uav = cv2.imread(im_path)
    mask_name = os.path.basename(im_path)[:-4]
    print("mask_name: ", mask_name)
    mask_path = f"./data/trees-avocado/m3m/campo2/masks/{mask_name}_MASK.JPG"
    print("mask_path:", mask_path)

    image_uav = cv2.GaussianBlur(image_uav, (5,5), 0)
    full_mask = cv2.imread(mask_path)
    print("mask:", full_mask.shape)
    full_mask = full_mask != 0
    full_mask = full_mask.astype(np.uint8)
    full_mask = cv2.cvtColor(full_mask, cv2.COLOR_BGR2GRAY)
    kernel = np.ones((5,5), np.uint8)
    full_mask = cv2.morphologyEx(full_mask, cv2.MORPH_OPEN, kernel, iterations = 2)
    #mask = cv2.erode(mask, kernel , iterations = 3)
    #mask = cv2.Canny(mask, 0, 500)
    countorus, _  = cv2.findContours(full_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)

    coordinates = []
    bboxes = []
    masks = []
    im_bboxes = image_uav.copy()

    for cn in countorus:
        area_cn = cv2.contourArea(cn)
        if area_cn > 65000:
            coordinates.append(cn)
            x, y, w, h = cv2.boundingRect(cn)
            bboxes.append([x,y,w,h])
            image_mask_tree = np.zeros_like(full_mask, dtype= full_mask.dtype)
            cv2.drawContours(image_mask_tree, [cn], -1, color = 255, thickness = cv2.FILLED)
            masks.append(image_mask_tree)
            #print("area:", area_cn)
            cv2.rectangle(im_bboxes, (x,y), (x + w, y + h), (255,0,0), 14)
    print("Numero de contornos:", len(coordinates))
    if show:
        mascara_filtrada = np.zeros_like(full_mask, np.uint8)
        cv2.drawContours(mascara_filtrada, coordinates, -1, color = 255, thickness = cv2.FILLED)
        fig, axis = plt.subplots(2,2 , figsize = (15,8))
        axis[0][0].imshow(image_uav)
        axis[0][1].imshow(cv2.imread(mask_path), cmap = 'gray')
        axis[1][0].imshow(im_bboxes)
        axis[1][1].imshow(mascara_filtrada, cmap = 'gray')
        plt.show()

    return full_mask, bboxes, coordinates



def get_metadata(im_path):
    with exiftool.ExifToolHelper() as et:
       metadata = et.get_metadata(im_path)
       return metadata[0]
        #print(metadata[0].get("EXIF:GPSLatitude"))

def position(self): 
        """get the WGS-84 latitude, longitude tuple as signed decimal degrees"""
        lat = self.get_item('EXIF:GPSLatitude')
        latref = self.get_item('EXIF:GPSLatitudeRef')
        if latref == 'S':
            lat *= -1.0
        lon = self.get_item('EXIF:GPSLongitude')
        lonref = self.get_item('EXIF:GPSLongitudeRef')
        if lonref == 'W':
            lon *= -1.0
        alt = self.get_item('EXIF:GPSAltitude')
        return lat, lon, alt

def get_gps_coordinates(metadata):

    latitude = metadata.get('EXIF:GPSLatitude')
    latref = metadata.get('EXIF:GPSLatitudeRef')
    if latref == 'S':
        latitude *= -1.0
    longitude = metadata.get('EXIF:GPSLongitude')
    lonref = metadata.get('EXIF:GPSLongitudeRef')
    if lonref == 'W':
        longitude *= -1.0

    #latitude = metadata.get("EXIF:GPSLatitude")
    #longitude = metadata.get("EXIF:GPSLongitude")
    return latitude, longitude

def get_image_resolution(metadata):
    image_width = metadata.get("EXIF:ExifImageWidth") or metadata.get( "EXIF:ImageWidth")
    image_heigth = metadata.get("EXIF:ExifImageHeight") or metadata.get( "EXIF:ImageHeight")

    return image_width, image_heigth

def calculate_gsd(metadata):
    relative_altitude_text = metadata["XMP:RelativeAltitude"]
    print("relative_altitude_text:", relative_altitude_text)
    signo, numero = (relative_altitude_text[0], relative_altitude_text[1:]) if relative_altitude_text[0] in '+-' else ("+", relative_altitude_text[0])
    altitude_drone = float(numero) if signo == '+' else -float(numero)
    altitude_drone = altitude_drone * 100 # cm/pixel
    #print("altitude_drone:", altitude_drone)
    image_width, image_heigth = get_image_resolution(metadata)

    fov_metadata = metadata.get('Composite:FOV')
    if  isinstance(fov_metadata, str):
    # Extraer el FOV angular (primer número)
        fov_metadata = fov_metadata.split()[0]
        fov_metadata = float(fov_metadata)
    
    fov = float(fov_metadata)

    #print("fov:", fov)
    fov_rad = np.radians(fov)
    rel_asp = image_width / image_heigth
    fov_h = 2 * np.arctan((rel_asp / (np.sqrt(rel_asp ** 2 + 1))) * np.tan(fov_rad / 2))
    fov_v = 2 * np.arctan((1 / (np.sqrt(rel_asp ** 2 + 1))) * np.tan(fov_rad / 2))

    GSD_horizontal = (2 * altitude_drone * np.tan(fov_h)/ 2) / image_width #  cm/pixel
    GSD_vertical = (2 * altitude_drone * np.tan(fov_v / 2)) / image_heigth 
    
    return GSD_horizontal, GSD_vertical

def get_drone_model(metadata):
    if metadata["EXIF:Make"] == "DJI":
        return metadata["EXIF:Model"]
    return None

def calculate_gps_for_pixel(pixel_coord ,gps_image, gsd_horizontal, gsd_vertical, resolution, yaw_degree):
    latitud_image, longitude_image = gps_image
    height_image, width_image = resolution
    pixel_x, pixel_y = pixel_coord
    #print("pixel_coord:", pixel_coord)
    degree_rad = np.radians(yaw_degree)
    #print("desp pix:", "x:", pixel_x - width_image / 2, "y:", pixel_x - height_image / 2)
    ## Calculate desplazamiento en centimetros de pixel
    desp_x = (pixel_x - width_image / 2) * gsd_horizontal / 100
    desp_y = (pixel_y - height_image / 2) * gsd_vertical / 100

    #print("desp meters:", "x:", desp_x, "y:", desp_y)

    # ajustar desplazamiento segun angulo yaw
    desp_lat = (-desp_y * np.cos(degree_rad) - desp_x * np.sin(degree_rad)) / 111320
    #desp_long = (desp_x * np.cos(degree_rad) - desp_y * np.sin(degree_rad)) / (111320 * np.cos(np.radians(latitud_image)))
    desp_long = (desp_x * np.cos(degree_rad) - desp_y * np.sin(degree_rad)) / (111320 * np.cos(np.radians(latitud_image)))

    #print("desp gps:", "desp_lat:", desp_lat, "desp_long:", desp_long)
    # nuevas coordenadas
    latitud_pixel = latitud_image + desp_lat
    longitude_pixel = longitude_image + desp_long
    #print("latitud_pixel:", latitud_pixel, ", longitude_pixel:", longitude_pixel)
    return latitud_pixel, longitude_pixel

def select_good_trees(bboxes, im_shape):
    '''Selecciona las detecciones que el centro no supere un limite definido, y el cuadrado delimitador no supero un segundo limite'''
    h, w = im_shape
    # Limete para los centros de las detecciones
    bbox_limit_centers = [3 * w//20, 3 * h//20, 14 * w // 20, 14 * h // 20]
    x_min_limit_centers = bbox_limit_centers[0]
    x_max_limit_centers = bbox_limit_centers[0] + bbox_limit_centers[2]
    y_min_limit_centers = bbox_limit_centers[1]
    y_max_limit_centers = bbox_limit_centers[1] + bbox_limit_centers[3]
    # Limete para las cajas de las detecciones
    bbox_limit_sides = [w//20, h//20, 18 * w // 20, 18 * h // 20]
    x_min_limit_sides = bbox_limit_sides[0]
    x_max_limit_sides = bbox_limit_sides[0] + bbox_limit_sides[2]
    y_min_limit_sides = bbox_limit_sides[1]
    y_max_limit_sides = bbox_limit_sides[1] + bbox_limit_sides[3]

    good_bboxes = []
    good_trees_idx = []
    for i , bbox in enumerate(bboxes):
        c_x = bbox[0] + bbox[2]//2
        c_y = bbox[1] + bbox[3]//2
        x_min = bbox[0]
        x_max = bbox[0] + bbox[2]
        y_min = bbox[1]
        y_max = bbox[1] + bbox[3]
        # Si el centro esta dentro del limite defino
        if (c_x > x_min_limit_centers and c_x < x_max_limit_centers) and (c_y > y_min_limit_centers and c_y < y_max_limit_centers):
            # Si la deteccion esta dentro del limite defino
            if (x_min > x_min_limit_sides and x_max < x_max_limit_sides) and (y_min > y_min_limit_sides and y_max < y_max_limit_sides):
                good_bboxes.append(bbox)
                good_trees_idx.append(i)

    return good_trees_idx


from glob import glob
import os
import pandas as pd
#dir_images = "./mavic3m/campo2/Viaje3-27-Nov/DJI_202411281538_002_acco2-campo2/DJI_202411281538_002_acco2-campo2"
#folder_path = "mavic3m/campo2/Viaje3-27-Nov/DJI_202411281538_002_acco2-campo2/"
folder_path = "./data/trees-avocado/m3m/campo2/images/"

tif_files = glob(f"{folder_path}/*.TIF")

jpg_files = glob(f"{folder_path}/*.JPG")


images_names = tif_files + jpg_files
print(f"{len(jpg_files)} imagenes encontradas")

im_basenames = ["_".join(os.path.basename(im_file).split("_")[:3]) for im_file in jpg_files]

latitudes = []
longitudes  = []
yaw_degrees  = []
pitch_degrees  = []
roll_degrees = []
images_w = []
images_h = []
images_GSDH = []
images_GSDV = [] 
datetimes = []

camera_features = {
    "M3M": {
        "bands_features": {
                "RGB": { 
                    "suffix": "_D",
                    "file": "jpg"
                },
                "GREEN": { 
                "suffix": "_MS_G",
                "file": "tif"
                },
                'RED': { 
                "suffix": "_MS_R",
                "file": "tif"
                } ,
                "NIR": { 
                "suffix": "_MS_NIR",
                "file": "tif"
                },
                'RED_EDGE': { 
                "suffix": "_MS_RE",
                "file": "tif"
                }}
    }
}

bands_features = camera_features["M3M"]["bands_features"]
bands_features

for im_name in im_basenames:
    ## solo usamos el RGB por ahora
    im_path = f"{folder_path}/{im_name}{bands_features['RGB']['suffix']}.JPG"
    metadata = get_metadata(im_path)
    latitude, longitude = get_gps_coordinates(metadata)
    print(f"Latitud: {latitude}, Longitud: {longitude}")
    image_width, image_height = get_image_resolution(metadata)
    yaw_degree = metadata.get("XMP:GimbalYawDegree")
    pitch_degree = metadata.get("XMP:GimbalPitchDegree")
    roll_degree = metadata.get("XMP:GimbalRollDegree")
    if not isinstance(yaw_degree, float):
        signo, yaw_degree = (yaw_degree[0], yaw_degree[1:]) if yaw_degree[0] in '+-' else ("+", yaw_degree[0])
        yaw_degree =  float(yaw_degree) if signo == '+' else -float(yaw_degree)

    GSD_horizontal, GSD_vertical = calculate_gsd(metadata)
    
    latitudes.append(latitude)
    longitudes.append(longitude)
    yaw_degrees.append(yaw_degree)
    pitch_degrees.append(pitch_degree)
    roll_degrees.append(roll_degree)
    images_w.append(image_width)
    images_h.append(image_height)
    images_GSDH.append(GSD_horizontal)
    images_GSDV.append(GSD_vertical)
    datetimes.append(metadata.get("EXIF:DateTimeOriginal"))

df_images_metadata =  pd.DataFrame({"basename": im_basenames,
                                    "latitude": latitudes,
                                    "longitude" : longitudes,
                                    "yaw_degree": yaw_degrees,
                                    "pitch_degree": pitch_degrees,
                                    "roll_degree": roll_degrees,
                                    "image_w": images_w,
                                    "image_h": images_h,
                                    "GSDH": images_GSDH,
                                    'GSDV': images_GSDV,
                                    "DateTimeOriginal": datetimes,
                                    })
df_images_metadata["Timestamp_ms"] = pd.to_datetime(df_images_metadata["DateTimeOriginal"], format="%Y:%m:%d %H:%M:%S").astype(int) // 10**6

def filter_oblique_images(df_images):
    return df_images[(df_images['pitch_degree'] < -89) & (df_images['pitch_degree'] > -91)]

df_images_filtered = filter_oblique_images(df_images_metadata)

df_images_filtered.to_csv("./df_images_metadata.csv", index= False)
df_images_filtered = df_images_filtered.sort_values(by="Timestamp_ms", ascending=True)
print(df_images_filtered.head(10))

geojson_data = {
    "type": "FeatureCollection",  # Indica que es una colección de características
    "features": []
}

for i in range(min(60, len(df_images_filtered))):
    basename = df_images_filtered["basename"].iloc[i]
    im_path = folder_path + f"{basename}_D.JPG"

    metadata = get_metadata(im_path)
    latitude, longitude = get_gps_coordinates(metadata)
    image_width, image_heigth = get_image_resolution(metadata)
    yaw_degree = metadata.get("XMP:GimbalYawDegree")
    pitch_degree = metadata.get("XMP:GimbalPitchDegree")
    roll_degree = metadata.get("XMP:GimbalRollDegree")

    if not isinstance(yaw_degree, float):
        signo, yaw_degree = (yaw_degree[0], yaw_degree[1:]) if yaw_degree[0] in '+-' else ("+", yaw_degree[0])
        yaw_degree =  float(yaw_degree) if signo == '+' else -float(yaw_degree)

    GSD_horizontal, GSD_vertical = calculate_gsd(metadata)

    model_drone = get_drone_model(metadata)
    #GSD = 0.78
    print(f"Latitud: {latitude}, Longitud: {longitude}")
    print(f"image_width: {image_width}, image_heigth: {image_heigth}")
    print(f"GSD_horizontal: {GSD_horizontal}, GSD_vertical: {GSD_vertical}")
    print(f"yaw_degree: {yaw_degree}")
    print(f"model_drone: {model_drone}")



    im = cv2.imread(im_path)
    full_mask, bboxes, coordinates = detection_trees_human_ann(im_path , show = False)

    good_trees_idx = select_good_trees(bboxes, im.shape[:2])
    print("good_trees_idx:", good_trees_idx)
    if len(good_trees_idx) == 0:
        continue
    coordinates = [ coordinates[idx] for idx in good_trees_idx]
    coordinates_aprox = []
    # Iterar sobre cada contorno
    for contorno in coordinates:
        # Aproximar el contorno a un polígono con menos puntos
        epsilon = 0.0010 * cv2.arcLength(contorno, True)  # Parámetro para ajustar la cantidad de puntos
        coordinates_aprox.append(cv2.approxPolyDP(contorno, epsilon, True))
        
    print(coordinates[0][0])
    coordinates_geo = [[calculate_gps_for_pixel(pt[0], (latitude, longitude), GSD_horizontal, GSD_vertical, (image_heigth, image_width), yaw_degree) for pt in tree_coordinates] for tree_coordinates in coordinates_aprox ]
    coordinates_geo = [[(pt[1], pt[0]) for pt in tree_coordinates] for tree_coordinates in coordinates_geo]
    print("coordinates_geo:", len(coordinates_geo[0]))


    for j in range(len(coordinates_geo)):
        tree_coordinates = coordinates_geo[j]
        geojson_data["features"].append({
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",  # Definir que es un polsígono
                    "coordinates": [tree_coordinates + [tree_coordinates[0]]]
                },
                "properties": {
                    "treeID": i,
                    "tree_type": "avocado",  # Tipo de árbol en esta área
                    "description": "Arboles de Palta HASS"
                }
            
        })

# Guardar el archivo GeoJSON
with open('mascara_arboles.geojson', 'w') as f:
    json.dump(geojson_data, f, indent=4)

print("Archivo GeoJSON guardado con éxito como 'mascara_arboles.geojson'")