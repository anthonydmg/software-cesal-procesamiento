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
