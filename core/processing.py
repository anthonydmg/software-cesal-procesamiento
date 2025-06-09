## Guarda esto en una parte del xml
import numpy as np
import cv2
import matplotlib.pyplot as plt
import os
from PIL import Image
from tqdm import tqdm
from pyproj import Proj, transform, CRS
from pyproj import Transformer
from scipy.spatial.transform import Rotation
import time

class Camara_M3M:
    fx = fy = 3713.29  # Distancia focal en píxeles
    cx = 7.02          # Centro óptico X (en píxeles, origen en el centro de la imagen)
    cy = -8.72         # Centro óptico Y (en píxeles, origen en el centro de la imagen)
    width_px = 5280 
    high_px = 3956
    # Convertir centro óptico a origen OpenCV (esquina superior izquierda)
    cx_opencv = (width_px / 2) + cx
    cy_opencv = (high_px / 2) + cy  
    # Matriz intrínseca final K
    K = np.array([
        [fx,    0,  cx_opencv],
        [0,     fy, cy_opencv],
        [0,      0,      1   ]
    ], dtype=np.float32)
    # Parámetros de distorsión (k1, k2, p1, p2, k3)
    k1 = -0.11257524     # Distorsión radial (término cuadrático)
    k2 = 0.01487443      # Distorsión radial (término cuártico)
    p1 = -0.00008572     # Distorsión tangencial (x)
    p2 = 0.00000010      # Distorsión tangencial (y)
    k3 = -0.02706411     # Distorsión radial (término sextico, opcional)

    dist = np.array([
        k1,   
        k2,    
        p1,   
        p2,   
        k3   
    ], dtype=np.float32)

    width_sensor = 17.4
    high_sensor = 13.0
    pixel_size_w = width_sensor / width_px  # ej: 13.2 mm / 5472 px = 2.4 µm/px
    pixel_size_h = high_sensor / high_px  # ej: 13.2 mm / 5472 px = 2.4 µm/px
    focal_length = 12.29

def distortion_correction(img, K = Camara_M3M.K, dist = Camara_M3M.dist):
    return cv2.undistort(img, K, dist, None, K)

def latlon_to_utm(lat, lon):
    # Calculo automatico de la zona para el hemisferio sur
    zone = int((lon + 180) // + 6 + 1)
    epsg = 32700 + zone
    utm = CRS(f"EPSG:{epsg}") # UTM para peru
    wgs84 = CRS("EPSG:4326")
    transformer = Transformer.from_crs(wgs84, utm, always_xy=True)
    x, y = transformer.transform(lon, lat)
    return x, y

def camera_position(lat, lon, alt):
    # Posición fisica de la cámara
    x_dron, y_dron = latlon_to_utm(lat, lon)
    # offset fisico de la camara
    dx, dy, dz = 0.1, 0.0, 0.0
    x_cam = x_dron + dx
    y_cam = y_dron + dy
    z_cam = alt + dz
    return x_cam, y_cam, z_cam

def angles_euler_gimbal_fix_orientation(yaw_degree_gimbal, pitch_degree_gimbal, roll_degree_gimbal):

    if roll_degree_gimbal > 90:
        roll_degree_gimbal += 180
        roll_degree_gimbal = roll_degree_gimbal % 360
        yaw_degree_gimbal = yaw_degree_gimbal - 180

    if pitch_degree_gimbal < 0.0:
        pitch_degree_gimbal += 90.0

    return yaw_degree_gimbal, pitch_degree_gimbal, roll_degree_gimbal

def rotation_matrix_cam(yaw_degree_gimbal, pitch_degree_gimbal, roll_degree_gimbal):
    rot = Rotation.from_euler('ZYX', [yaw_degree_gimbal, pitch_degree_gimbal, roll_degree_gimbal], degrees=True)
    R_cam = rot.as_matrix()
    return R_cam

def calculate_camera_pose(metadata):
    relative_altitude = metadata["relative_altitude"]
    lat = metadata["latitude"]
    lon = metadata["longitude"]
    x_cam, y_cam, z_cam = camera_position(lat, lon, relative_altitude)
    roll_degree_gimbal = metadata["roll_degree_gimbal"]
    yaw_degree_gimbal = metadata["yaw_degree_gimbal"]
    pitch_degree_gimbal = metadata["pitch_degree_gimbal"]
    yaw_degree_gimbal, pitch_degree_gimbal, roll_degree_gimbal = angles_euler_gimbal_fix_orientation(yaw_degree_gimbal, pitch_degree_gimbal, roll_degree_gimbal)
    R_cam = rotation_matrix_cam(yaw_degree_gimbal, pitch_degree_gimbal, roll_degree_gimbal)
    camera_pose = np.hstack((R_cam, np.array([x_cam, y_cam, z_cam]).reshape(3, 1)))  # Matriz de pose [R | t]
    return camera_pose

def project_img_points_to_ground(img_points, K, pose):
    fx, fy = K[0, 0], K[1, 1]
    cx, cy = K[0, 2], K[1, 2]
    z_cam = pose[2, 3]
    # 1. Convertir esquinas a metros (vectorizado)
    x_img, y_img = img_points[:, 0], img_points[:, 1]
    x_m = ((x_img - cx) / fx) * z_cam  # (x_img / fx) * z_cam
    y_m = ((y_img - cy) / fy) * z_cam
    rays_cam = np.vstack((x_m, y_m, np.full_like(x_m, pose[2, 3]))).T

    # 2. Rotación y proyección (vectorizado)
    R_cam = pose[:, :3]#.astype(np.float64)
    rays_global = (R_cam @ rays_cam.T).T

    # 3. Intersección con z=0 (evitando divisiones por ~0)
    threshold = 1e-6
    valid = np.abs(rays_global[:, 2]) > threshold
    lambda_ = np.where(valid, pose[2, 3] / rays_global[:, 2], np.nan) # pose[2, 3] - (parte a restar o sumar) aqui restar o sumar las elevaciones

    terrain_points = np.vstack((
        pose[0, 3] + lambda_ * rays_global[:, 0],
        pose[1, 3] + lambda_ * rays_global[:, 1]
    )).T

    #print("Footprint (UTM, float64):\n", terrain_points)
    return terrain_points

def corners_to_terrain_points(metadata):
    camera_pose = metadata["camera_pose"]
    img_points = np.array([
        [0, 0],    # Esquina superior izquierda
        [Camara_M3M.width_px, 0],     # Esquina superior derecha
        [Camara_M3M.width_px, Camara_M3M.high_px],     # Esquina inferior derecha
        [0, Camara_M3M.high_px]      # Esquina inferior izquierda
    ], dtype=np.float32)

    terrain_points = project_img_points_to_ground(img_points, Camara_M3M.K, camera_pose)
    return terrain_points

def process_calculate_camera_pose(images_data):
    for im_data in images_data:
        im_data['camera_pose'] = calculate_camera_pose(im_data)
    return images_data

def process_terrain_points(images_data):
    for im_data in images_data:
        im_data['terrain_points'] = corners_to_terrain_points(im_data)
    return images_data

def estimate_dom_parameters(images_data, margin_extension = 0.1):
    min_gsd = np.min([m['gsd_horizontal']] for m in images_data)
    dom_resolution = min_gsd * 5.1
    all_coordinates = np.array([m['terrain_points']] for m in images_data)
    min_x, min_y = np.min(all_coordinates, axis=0)
    max_x, max_y = np.max(all_coordinates, axis=0)
    ancho = max_x - min_x # creo que seria al reves
    alto = max_y - min_y

    min_x -= ancho * margin_extension
    max_x += ancho * margin_extension
    min_y -= alto * margin_extension
    max_y += alto * margin_extension
    return (min_x, max_x, min_y, max_y), dom_resolution

def project_corners_to_dom(im_size, dom_bounds, resolution, terrain_points):
    h, w = im_size
    x_min, y_min = np.min(terrain_points, axis=0)
    x_max, y_max = np.max(terrain_points, axis=0)
    terrain_points_dom = np.round((terrain_points - [dom_bounds[0], y_min + y_max -dom_bounds[3]]) // resolution)
    img_points = np.array([
            [0 , 0 ],     # Esquina superior izquierda
            [w , 0 ],     # Esquina superior derecha
            [w , h ],     # Esquina inferior derecha
            [0 , h ]      # Esquina inferior izquierda
        ], dtype=np.float32)
    # Calcular homografía
    H, _ = cv2.findHomography(img_points, terrain_points_dom, method=cv2.RANSAC)
    return terrain_points_dom, H

def process_project_corners_to_dom(images_data, dom_bounds, dom_resolution):
    for im_data in images_data:
        terrain_points_dom, H = project_corners_to_dom((im_data["image_h"], im_data["image_w"]), dom_bounds, dom_resolution, im_data['terrain_points'])
        im_data['terrain_points_dom'] = terrain_points_dom
        im_data['H_rtk'] = H

    return images_data

def direct_project_image_to_dom(image, H, dom_size, terrain_points_dom):

        imagen_proyectada = cv2.warpPerspective(
            image,
            H,
            (int(dom_size[1]), int(dom_size[0])),
            flags=cv2.INTER_LANCZOS4  # Interpolación de alta calidad
        )
        # Crear mascara
        mask = np.zeros((dom_size[0], dom_size[1]), dtype=np.float32)  # Invertir tamaño para (height, width)
        cv2.fillConvexPoly(mask, terrain_points_dom.astype(np.int32), 1)
        
        return imagen_proyectada, mask

def apply_clahe(img, clip_limit=2.0, grid_size=(8, 8)):
    """Preprocesamiento CLAHE para mejorar contraste"""
    if len(img.shape) == 3:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=grid_size)
    return clahe.apply(img)

def detect_keypoint_descriptors(img, detector_type="ORB", draw_keypoints = False):
    start_time = time.time()

    im_gray = apply_clahe(img)
    if detector_type == "ORB":
        detector = cv2.ORB_create(nfeatures=10000, edgeThreshold=15, patchSize=31)
    elif detector_type == "AKZE":
        detector = cv2.AKAZE_create(threshold=0.0005)
    elif detector_type == "SIFT":
        detector = cv2.SIFT_create(nfeatures=10000, contrastThreshold=0.02, edgeThreshold=15)
    kp, desc = detector.detectAndCompute(im_gray, None)
    ## Codigp para visualizar los keypoints detectados
    if draw_keypoints:
        ## aqui completar el codigo:
        img_display = im_gray.copy()
        img_display = cv2.drawKeypoints(img_display, kp, None, color=(0,255,0), flags = cv2.DRAW_MATCHES_FLAGS_DRAW_RICH_KEYPOINTS)

        # Mostrar con Matplotlib
        plt.figure(figsize=(10, 10))
        plt.imshow(img_display)
        plt.title(f'Keypoints detectados ({detector_type}) - Total: {len(kp)}')
        plt.axis('off')
        plt.show()
    
    elapsed_time = time.time() - start_time

    return kp, desc, elapsed_time

def detect_keypoint_descriptors_in_dom(img_dom, corners_img, detector_type = "ORB", draw_keypoints = False):
    start_time = time.time()
    x_min, y_min = corners_img.min(axis = 0)
    x_max, y_max = corners_img.max(axis = 0)
    img_dom_cuted = img_dom[y_min:y_max, x_min:x_max, :]
    kp_img, desc_img, _ = detect_keypoint_descriptors(img_dom_cuted, detector_type, draw_keypoints = False)

    kp_img_dom = [
        cv2.KeyPoint(x=kp.pt[0] + x_min, y=kp.pt[1] + y_min, size=kp.size, angle=kp.angle, 
                        response=kp.response, octave=kp.octave, class_id=kp.class_id)
        for kp in kp_img
    ]
    elapsed_time = time.time() - start_time
    if draw_keypoints:
        im_gray = apply_clahe(img_dom)
        ## aqui completar el codigo:
        img_display = im_gray.copy()
        img_display = cv2.drawKeypoints(img_display, kp_img_dom, None, color=(0,255,0), flags = cv2.DRAW_MATCHES_FLAGS_DRAW_RICH_KEYPOINTS)

        # Mostrar con Matplotlib
        plt.figure(figsize=(10, 10))
        plt.imshow(img_display)
        plt.title(f'Keypoints detectados ({detector_type}) - Total: {len(kp_img)}')
        plt.axis('off')
        plt.show()

    return kp_img_dom, desc_img, elapsed_time

def process_detect_keypoint_descriptors_in_dom(images_data, dom_size):
    for im_data in images_data:
        im_path = im_data['relative_im_path']
        H_rtk = im_data['H_rtk']
        terrain_points_dom = im_data['terrain_points_dom'].astype(np.int32)
        img = cv2.imread(im_path)
        img_undistorned = distortion_correction(img)
        imagen_proyectada, _ = direct_project_image_to_dom(img_undistorned, H_rtk, dom_size, terrain_points_dom)
        kp, desc, _ = detect_keypoint_descriptors_in_dom(imagen_proyectada, terrain_points_dom, detector_type = "ORB", draw_keypoints = False)
        im_data['kp_img_dom'] = kp
        im_data['desc_img_dom'] = desc
    return images_data


