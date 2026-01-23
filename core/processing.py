## Guarda esto en una parte del xml
import numpy as np
import cv2
import matplotlib.pyplot as plt
import os
from PIL import Image
from pyproj import Proj, transform, CRS
from pyproj import Transformer
from scipy.spatial.transform import Rotation
import time
from enum import Enum
from tqdm import tqdm
from osgeo import gdal, osr
from scipy.sparse import coo_matrix
import numpy as np
from scipy.sparse.linalg import lsqr
from datetime import datetime
import pandas as pd
import json
import copy
import random

from core.deficiency_classifier import NitrogenDefClassifer

class FusionMethod(Enum):
    SIMPLE_AVERAGE = 1
    SEAM_BLENDING = 2
    WEIGHTED_DISTANCE = 3
    EXPOSURE_COMPENSATED = 4
    MULTIBAND_ADAPTIVE = 5
    ROBUST_DRONE = 6

MIN_MATCHES_FOR_EDGE = 30

RANSAC_THRESH  = 4.0

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

def crop_image(image, bbox):
    (x_min, y_min), (x_max, y_max) = bbox
    return image[y_min:y_max+1, x_min:x_max+1]

def distortion_correction(img, K = Camara_M3M.K, dist = Camara_M3M.dist):
    return cv2.undistort(img, K, dist, None, K)

def load_gray16(path):
    I = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    print("I:", I.shape)
    print("I.ndim:", I.ndim)
    if I is None:
        raise RuntimeError(f"Could not read {path}")
    if I.ndim == 3 and I.shape[-1] > 1:
        I = cv2.cvtColor(I, cv2.COLOR_BGR2GRAY)
    if I.shape[-1] == 1:
        I = I.squeeze()
    return I

def vignetting_correct(I, meta):
    """
    I_out = I * (k[5]*r^6 + k[4]*r^5 + ... + k[0]*r + 1.0)
    r = sqrt((x-CenterX)^2 + (y-CenterY)^2), Center from calibrated optical center.
    """
    k = meta["kpoly"]
    if k is None:
        return I
    h, w = I.shape[:2]
    # meshgrid in pixel coords (x to right, y down)
    xs = np.arange(w, dtype=np.float64)
    ys = np.arange(h, dtype=np.float64)
    X, Y = np.meshgrid(xs, ys)
    cx = meta["cx_design"]
    cy = meta["cy_design"]
    r = np.sqrt((X - cx)**2 + (Y - cy)**2)
    # Polynomial: k0..k5 with powers r^1..r^6 (per guide)
    r1 = r
    r2 = r1*r
    r3 = r2*r
    r4 = r3*r
    r5 = r4*r
    r6 = r5*r
    poly = 1.0 + k[0]*r1 + k[1]*r2 + k[2]*r3 + k[3]*r4 + k[4]*r5 + k[5]*r6
    return (I.astype(np.float64) * poly).astype(I.dtype)

def undistort_with_meta(I, meta):
    """
    OpenCV undistort using Dewarp Data.
    Camera matrix uses (fx, 0, CenterX+cx), (0, fy, CenterY+cy), (0,0,1) as per guide.
    """
    fx, fy, cx, cy = meta["fx"], meta["fy"], meta["cx"], meta["cy"]
    k1, k2, p1, p2, k3 = meta["k1"], meta["k2"], meta["p1"], meta["p2"], meta["k3"]
    if None in (fx, fy, cx, cy, k1, k2, p1, p2, k3):
        return I
    h, w = I.shape[:2]
    cx_vign = meta["cx_design"]
    cy_vign = meta["cy_design"]
    K = np.array([[fx, 0, cx_vign + cx],
                  [0,  fy, cy_vign + cy],
                  [0,   0,          1]], dtype=np.float64)
    D = np.array([k1, k2, p1, p2, k3], dtype=np.float64)
    # Per guide, avoid changing newcameramtx; use original K
    return cv2.undistort(I, K, D, None, K)

def apply_hmatrix(I, H, out_shape=None):
    if H is None:
        return I
    h, w = I.shape[:2]
    if out_shape is None:
        out_shape = (w, h)
    return cv2.warpPerspective(I, H, out_shape, flags=cv2.INTER_LINEAR)

def per_band_pipeline(path, metadata):
    """
    Load -> vignetting -> undistort -> HMatrix warp -> return corrected image and metadata.
    """
    I0 = load_gray16(path)

    I1 = vignetting_correct(I0, metadata)
    I2 = undistort_with_meta(I1, metadata)
    H_cal = np.array(metadata["H_cal"])
    I3 = apply_hmatrix(I2, H_cal, out_shape=(I2.shape[1], I2.shape[0]))
    return I3, metadata

def img_signal(I, bits, black, gain, exp_raw):
    # Normalize raw to [0,1], subtract normalized black, divide by gain * (exp/1e6)
    exp_us = None
    if exp_raw is None:
        exp_us = 1000.0  # fallback: 1000 us
    else:
        # Si es una fracción "1/1250"
        if isinstance(exp_raw, str) and "/" in exp_raw:
            try:
                a, b = exp_raw.split("/")
                seconds = float(a) / float(b)
                exp_us = seconds * 1e6
            except Exception:
                try:
                    exp_us = float(exp_raw) * 1e6
                except Exception:
                    exp_us = 1000.0
        else:
            # numérico o string que representa float
            try:
                val = float(exp_raw)
                # heurística: si val < 10 it's almost certainly seconds (e.g. 0.0008),
                # if val > 1000 probably already in microseconds, so leave
                if val < 10.0:
                    # treat as seconds -> convert to microseconds
                    exp_us = val * 1e6
                else:
                    # treat as microseconds already
                    exp_us = val
            except Exception:
                exp_us = 1000.0

    denom = float(2**bits)
    I_norm = I.astype(np.float64) / denom
    black_norm = float(black) / denom
    cam = (I_norm - black_norm)
    cam[cam < 0] = 0.0
    return cam / (gain * (exp_us / 1e6))

def compute_reflectance(Icorr, meta):
    cam = img_signal(Icorr, meta["bits"], meta["black"], meta["gain"], meta["exp_us"])   # Eq. 9
    #print(f"Meta values: pCam={meta['pCam']}, irradiance={meta['irradiance']}, gain={meta['gain']}, exp_us={meta['exp_us']}")
    # reflectance_X = (X_camera * pCam_X) / (Irradiance_X)
    irradiance = meta["irradiance"]
    ref = (cam * meta["pCam"]) / max(irradiance, 1e-12)

    #cam = img_signal(Icorr, meta["bits"], meta["black"], meta["gain"], meta["exp_us"])   # Eq. 9
    # reflectance_X = (X_camera * pCam_X) / (Irradiance_X)
    #ref = (cam * meta["pCam"]) / max(meta["irradiance"], 1e-12)
    return ref

def modern_ldp_ndvi_colormap(ndvi):
    """
    Robust, vectorized NDVI -> RGB colormap with smooth linear interpolation
    across defined color segments. Expects ndvi in [-1, 1].
    Returns uint8 RGB image (H, W, 3).
    """
    ndvi = np.asarray(ndvi, dtype=np.float32)
    ndvi = np.sign(ndvi) * np.abs(ndvi) ** 0.8  # boost higher values

    h, w = ndvi.shape
    colored = np.zeros((h, w, 3), dtype=np.uint8)

    # Define segments (low, high, color_low(RGB), color_high(RGB))
    segments = [
        (-1.0, 0.0, np.array([0, 0, 0], dtype=np.float32),   np.array([0, 0, 0], dtype=np.float32)),   # black -> blue
        (0.0, 0.3, np.array([0, 0, 0], dtype=np.float32),   np.array([0, 0, 251], dtype=np.float32)),   # black -> blue
        (0.3, 0.5, np.array([0, 0, 251], dtype=np.float32), np.array([220, 0, 251], dtype=np.float32)), # blue -> purple
        (0.5, 0.7, np.array([220, 0, 251], dtype=np.float32), np.array([220, 0, 120], dtype=np.float32)), # purple -> pink
        (0.7, 0.8, np.array([220, 0, 120], dtype=np.float32),  np.array([220, 100, 0], dtype=np.float32)),  # pink -> dark orange
        (0.8, 0.9, np.array([220, 100, 0], dtype=np.float32),  np.array([255, 255, 0], dtype=np.float32)),  # dark orange -> yellow
        (0.9, 0.999, np.array([255, 255, 0], dtype=np.float32),  np.array([20, 80, 0], dtype=np.float32)),    # yellow -> green
        (0.999, 1.0, np.array([0, 0, 0], dtype=np.float32),   np.array([0, 0, 0], dtype=np.float32)),   # black -> blue
    ]

    # Assign for each segment
    for low, high, c_low, c_high in segments:
        if high == low:
            continue
        mask = (ndvi >= low) & (ndvi < high)
        if not np.any(mask):
            continue
        t = (ndvi[mask] - low) / (high - low)
        # Interpolate per-channel
        cols = (c_low[None, :] * (1.0 - t[:, None]) + c_high[None, :] * (t[:, None])).astype(np.uint8)
        colored[mask] = cols

    # handle exact 1.0 (inclusive)
    mask_one = (ndvi >= 1.0)
    if np.any(mask_one):
        colored[mask_one] = segments[-1][3].astype(np.uint8)  # final color_high

    return colored

def ndvi_to_drgb(ndvi_dip, rgb_path, H_dewarp):
    """
    NDVI currently on 'designed image plane'.
    Apply Dewarp HMatrix (designed → designed RGB image plane).
    """
    rgb = cv2.imread(rgb_path, cv2.IMREAD_UNCHANGED)
    if rgb is None:
        raise RuntimeError("Cannot read RGB image")
    H_dewarp = np.array(H_dewarp)
    #m = exif_read(red_path)
    #H_dewarp = m["H_dewarp"]
    h_out, w_out =  rgb.shape[:2]
    ndvi_on_drgb = cv2.warpPerspective(ndvi_dip, H_dewarp, (w_out, h_out), flags=cv2.INTER_LINEAR)
    return ndvi_on_drgb


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
    roll_degree_gimbal = metadata["roll_degree"]
    yaw_degree_gimbal = metadata["yaw_degree"]
    pitch_degree_gimbal = metadata["pitch_degree"]
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
    min_gsd = np.min([m['gsd_horizontal'] for m in images_data])
    print("min_gsd:", min_gsd)
    dom_resolution = min_gsd * 5.1
    print("Dom resolution")
    all_coordinates = np.array([m['terrain_points'] for m in images_data]).reshape(-1,2)
    
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

def direct_project_image_to_dom(image, H, dom_size, get_valid_region = False):
        # Proyectar imagen
        imagen_proyectada = cv2.warpPerspective(
            image,
            H,
            (int(dom_size[1]), int(dom_size[0])),
            flags=cv2.INTER_LANCZOS4  # Interpolación de alta calidad
        )

        # Región válida: recorte del 12% en cada borde
        valid_region = np.zeros(image.shape[:2], dtype=np.uint8)
        percent_crop_w,  percent_crop_h = (12, 12)
        crop_h = (image.shape[0] * percent_crop_h) // 100
        crop_w = (image.shape[1] * percent_crop_w) // 100
        valid_region[crop_h:-crop_h,crop_w:-crop_w] = 255

        # Proyectar máscara válida
        valid_region_mask = cv2.warpPerspective(
            valid_region,
            H,
            (int(dom_size[1]), int(dom_size[0])),
            flags=cv2.INTER_LANCZOS4  # Interpolación de alta calidad
        )

        # Máscara de píxeles proyectados

        gray = cv2.cvtColor(imagen_proyectada, cv2.COLOR_BGR2GRAY)

        mask = np.where(gray > 0, 255, 0).astype(np.float32)
        # Crear mascara
        #mask = np.zeros((dom_size[0], dom_size[1]), dtype=np.float32)  # Invertir tamaño para (height, width)
        #cv2.fillConvexPoly(mask, terrain_points_dom.astype(np.int32), 1)
        if not get_valid_region:
            return imagen_proyectada, mask
        else:
            return imagen_proyectada, mask, valid_region_mask

def apply_clahe(img, clip_limit=2.0, grid_size=(8, 8)):
    """Preprocesamiento CLAHE para mejorar contraste"""
    if len(img.shape) == 3:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=grid_size)
    return clahe.apply(img)

def detect_keypoint_descriptors(img, detector_type="ORB", draw_keypoints = False, nfeatures = 10000):
    start_time = time.time()

    im_gray = apply_clahe(img)
    if detector_type == "ORB":
        detector = cv2.ORB_create(nfeatures=nfeatures, edgeThreshold=15, patchSize=31)
    elif detector_type == "AKZE":
        detector = cv2.AKAZE_create(threshold=0.0005)
    elif detector_type == "SIFT":
        detector = cv2.SIFT_create(nfeatures=nfeatures, contrastThreshold=0.02, edgeThreshold=15)
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

def process_detect_keypoint_descriptors_in_dom(images_data, dom_size, detector_keypoint = "SIFT"):
    for im_data in tqdm(images_data,"keypoints Detection:"):
        im_path = im_data['relative_im_path']
        H_rtk = im_data['H_rtk']
        terrain_points_dom = im_data['terrain_points_dom'].astype(np.int32)
        img = cv2.imread(im_path)
        img_undistorned = distortion_correction(img)
        imagen_proyectada, _ = direct_project_image_to_dom(img_undistorned, H_rtk, dom_size)
        kp, desc, _ = detect_keypoint_descriptors_in_dom(imagen_proyectada, terrain_points_dom, detector_type = detector_keypoint, draw_keypoints = False)
        im_data['kp_img_dom'] = kp
        im_data['desc_img_dom'] = desc
    return images_data


def build_overlap_graph(all_terrain_points, min_overlap = 0.4):
    """Construye un grafo de solapamiento entre imagenes"""
    n = len(all_terrain_points)
    graph = {i:[] for i in range(n)}
    for i in range(n):
        terrain_points_i = all_terrain_points[i]
        poly_i = cv2.convexHull(terrain_points_i.astype(np.float32))
        area_i = cv2.contourArea(poly_i)
        for j in range(i+1, n):
            terrain_points_j = all_terrain_points[j] 
            poly_j = cv2.convexHull(terrain_points_j.astype(np.float32))
            area_j = cv2.contourArea(poly_j)
            intersection = cv2.intersectConvexConvex(poly_i, poly_j)[0]
            overlap_ratio = intersection / min(area_i, area_j)
            if overlap_ratio >= min_overlap:
                graph[i].append((j, overlap_ratio))
                graph[j].append((i, overlap_ratio))
    
    return graph

def match_keypoints_with_flann(
    desc1: np.ndarray, 
    desc2: np.ndarray, 
    detector_type: str = "ORB"
) :
    """
    Empareja descriptores usando FLANN + Ratio Test de Lowe.
    - Para ORB/AKAZE: FLANN con LSH (Locality-Sensitive Hashing).
    - Para SIFT/SURF: FLANN con KD-Tree.
    """
    if detector_type in ["ORB", "AKAZE"]:
        # Configuración FLANN para descriptores binarios (ORB/AKAZE)
        flann_params = {
            "algorithm": 6,  # LSH (Local Sensitivity Hashing)
            "table_number": 6,
            "key_size": 12,
            "multi_probe_level": 1
        }
        flann = cv2.FlannBasedMatcher(flann_params, dict(checks=50))
        matches = flann.knnMatch(desc1, desc2, k=2)
        
        # Ratio Test de Lowe (filtra matches ambiguos)
        good_matches = []
        for m, n in matches:
            if m.distance < 0.6 * n.distance:  # Ratio típico para ORB/AKAZE
                good_matches.append(m)
        return good_matches
    
    elif detector_type in ["SIFT", "SURF"]:
        # Configuración FLANN para descriptores no binarios (SIFT/SURF)
        flann_params = dict(algorithm=1, trees=5)  # KD-Tree
        flann = cv2.FlannBasedMatcher(flann_params, dict(checks=50))
        matches = flann.knnMatch(desc1, desc2, k=2)
        
        # Ratio Test de Lowe
        good_matches = []
        for m, n in matches:
            if m.distance < 0.7 * n.distance:  # Ratio típico para SIFT/SURF
                good_matches.append(m)
        return good_matches
    
    else:
        raise ValueError(f"Detector no soportado: {detector_type}")
    
def find_pairwise_correction(i,j, all_images_data, type = "affine"):
    desc_i = all_images_data[i]['desc_img_dom']
    kp_img_dom_i = all_images_data[i]['kp_img_dom']
    desc_j = all_images_data[j]['desc_img_dom']
    kp_img_dom_j = all_images_data[j]['kp_img_dom']

    matches = match_keypoints_with_flann(desc_i, desc_j)
    print("matches:",len(matches))
    if len(matches) < 10:
        return None
    
    src_pts = np.float32([kp_img_dom_i[m.queryIdx].pt for m in matches])
    dst_pts = np.float32([kp_img_dom_j[m.trainIdx].pt for m in matches])
    
     # Estimar transformación de corrección
    #M, inliers = cv2.estimateAffinePartial2D(
    #    src_pts, dst_pts, 
    #    method=cv2.RANSAC, 
    #    ransacReprojThreshold=5.0
    #)
    if type == "affine":
        M, inliers = cv2.estimateAffinePartial2D(#cv2.estimateAffine2D(
            src_pts, dst_pts, 
            method=cv2.RANSAC, 
            ransacReprojThreshold=5.0
        )
    else:
        M, inliers = cv2.findHomography(
            src_pts, dst_pts, 
            method=cv2.RANSAC, 
            ransacReprojThreshold=5.0
        )

    if M is not None and np.sum(inliers) > 10:
        return {
            'type': type, #'homography',
            'matrix': M,
            'num_matches': len(matches),
            'inliers': np.sum(inliers),
            'source_idx': i,
            'target_idx': j
        }
    return None

def correction_to_matrix(correction):
    """Convierte una corrección a matriz de transformación homogénea"""
    if correction['type'] == 'affine':
        M = np.vstack([correction['matrix'], [0, 0, 1]])
        return M
    elif correction['type'] == 'homography':
        return correction['matrix']
    return np.eye(3)

def calculate_pairwase_matches(all_images_data):
    corrected = set()
    all_terrain_points_dom = [im_data['terrain_points_dom'] for im_data in all_images_data]
    overlap_graph  = build_overlap_graph(all_terrain_points_dom, min_overlap=0.45)
    matches =  {}
    for i, nbrs in tqdm(overlap_graph.items(), desc= "Image"):
        for j, _ in nbrs:
            desc_i = all_images_data[i]['desc_img_dom']
            #kp_img_dom_i = all_images_data[i]['kp_img_dom']
            desc_j = all_images_data[j]['desc_img_dom']
            #kp_img_dom_j = all_images_data[j]['kp_img_dom']
            good_matches = match_keypoints_with_flann(desc_i, desc_j)
            if len(good_matches) >= 4:  # Mínimo para estimar transformación
                    matches[(i, j)] = good_matches
    
    return matches

def estimate_translation_ransac(src_pts, dst_pts, max_iters=1000, threshold=1.0):
    """Estimación eficiente de traslación con RANSAC"""
    best_tx, best_ty, best_inliers = 0, 0, np.zeros(len(src_pts), dtype=bool)
    for _ in range(max_iters):
        idx = np.random.randint(len(src_pts))
        tx = dst_pts[idx,0,0] - src_pts[idx,0,0]
        ty = dst_pts[idx,0,1] - src_pts[idx,0,1]
        diff = dst_pts - src_pts - np.array([[[tx, ty]]])
        current_inliers = np.linalg.norm(diff, axis=2) < threshold
        if np.sum(current_inliers) > np.sum(best_inliers):
            best_inliers, best_tx, best_ty = current_inliers, tx, ty
    M = np.eye(3)
    M[0,2], M[1,2] = best_tx, best_ty
    return M, best_inliers

def estimate_pairwase_homographies(overlap_graph, all_images_data, transform_type = "homography", ransac_thresh = RANSAC_THRESH, min_matches_per_edges = MIN_MATCHES_FOR_EDGE):
    edges = []
    n = len(all_images_data)
    for i, neighboards in tqdm(overlap_graph.items(),"Pairwase Edges"):
        neighboards_ids = [neigh[0] for neigh in neighboards]
        for j in range(i+1, n):
            if j not in neighboards_ids:
                continue
            desc_i = all_images_data[i]['desc_img_dom']
            kp_img_dom_i = all_images_data[i]['kp_img_dom']
            #print("kp_img_dom_i", kp_img_dom_i)
            desc_j = all_images_data[j]['desc_img_dom']
            kp_img_dom_j = all_images_data[j]['kp_img_dom']
            good_matches = match_keypoints_with_flann(desc_i, desc_j, detector_type="SIFT")

            if len(good_matches) < 8:
                 continue
            
            pts_i = np.array([kp_img_dom_i[m.queryIdx].pt for m in good_matches], dtype=np.float32)
            pts_j = np.array([kp_img_dom_j[m.trainIdx].pt for m in good_matches], dtype=np.float32)
            
            if transform_type == 'homography': # 8 grados de libertad
                H, mask = cv2.findHomography(pts_j, pts_i, cv2.RANSAC, ransac_thresh)
            elif transform_type == 'similarity': # 4 grados de libertad
                H, mask = cv2.estimateAffinePartial2D(pts_j, pts_i, method=cv2.RANSAC, ransacReprojThreshold= RANSAC_THRESH)
                H = np.vstack([H, [0, 0, 1]])
            elif transform_type == 'affine':    # 6 grados de libertad
                H, mask = cv2.estimateAffine2D(pts_j, pts_i, method=cv2.RANSAC, ransacReprojThreshold= RANSAC_THRESH)
                if H is None or H.shape != (2, 3):
                    print(f"⚠️ Transformación inválida entre imágenes {i} y {j}, se salta")
                    continue
                    #H = np.eye(3, dtype=np.float32) 
                H = np.vstack([H, [0, 0, 1]])
            else:
                H, mask = cv2.findHomography(pts_j, pts_i, cv2.RANSAC, RANSAC_THRESH) 
            
            if H is None:
                 continue
            
            mask = mask.ravel().astype(bool)
            #print("Mask:", mask)
            inliers = mask.sum()
            print(f"inliers ({i}, {j}):", inliers)

            if inliers >= min_matches_per_edges:  # Mínimo para estimar transformación
                edges.append((i, j, H, mask, inliers, pts_i, pts_j))
    
    return edges

def estimate_pairwise_transforms(all_images_data, matches, transform_type='similarity'):
    """Estima transformaciones entre pares de imágenes"""
    transforms = {}
    inliers = {}
    
    for (i, j), match_list in matches.items():
        #desc_i = all_images_data[i]['desc_img_dom']
        kp_img_dom_i = all_images_data[i]['kp_img_dom']
        #desc_j = all_images_data[j]['desc_img_dom']
        kp_img_dom_j = all_images_data[j]['kp_img_dom']
        src_pts = np.float32([kp_img_dom_i[m.queryIdx].pt for m in match_list]).reshape(-1, 1, 2)
        dst_pts = np.float32([kp_img_dom_j[m.trainIdx].pt for m in match_list]).reshape(-1, 1, 2)
        
        if transform_type == 'translation':
            M, mask = estimate_translation_ransac(src_pts, dst_pts)
        elif transform_type == 'similarity':
            M, mask = cv2.estimateAffinePartial2D(src_pts, dst_pts, method=cv2.RANSAC)
            M = np.vstack([M, [0, 0, 1]])
        elif transform_type == 'affine':
            M, mask = cv2.estimateAffine2D(src_pts, dst_pts, method=cv2.RANSAC)
            M = np.vstack([M, [0, 0, 1]])
        elif transform_type == 'homography':
            M, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC)
        
        if mask is not None and np.sum(mask) >= 4:
            transforms[(i, j)] = M
            inliers[(i, j)] = [match_list[k] for k in range(len(match_list)) if mask[k]]
    
    return transforms, inliers

def propagate_pairwise_correction(all_images_data, type_align_matrix = "affine"):
#all_images_data = df_images_filtered_slice.reset_index().to_dict(orient='index')
    transforms = {i: np.eye(3) for i in range(len(all_images_data))}
    corrected = set()
    all_terrain_points_dom = [im_data['terrain_points_dom'] for im_data in all_images_data]
    overlap_graph  = build_overlap_graph(all_terrain_points_dom, min_overlap=0.45)
    first_img_idx = list(overlap_graph.keys())[0]
    queue = [first_img_idx]
    corrected.add(first_img_idx)
    #type_align_matrix = "affine"# "affine"
    while len(queue) >0:
        img_idx = queue.pop(0)
        neighbors = sorted([x[0] for x in overlap_graph[img_idx]], 
                        key=lambda x: -overlap_graph[img_idx][[y[0] for y in overlap_graph[img_idx]].index(x)][1])
        print("img_idx:", img_idx)
        for neighbor_idx in neighbors[:3]:
            if neighbor_idx not in corrected:
                print("neighbor_idx:", neighbor_idx)
                #print("neighbor_idx:", neighbor_idx)
                #print("corrected:", corrected)
                correction = find_pairwise_correction(neighbor_idx, img_idx, all_images_data, type = type_align_matrix)
                if correction:
                    M = correction_to_matrix(correction)
                    transforms[neighbor_idx] = transforms[img_idx] @ M @ transforms[neighbor_idx]
                    corrected.add(neighbor_idx)
                    queue.append(neighbor_idx)
                else:
                    print(f"No encontrado match suficiente images idx :{img_idx}, neighbor_idx: {neighbor_idx}")
    print("corrected:", len(corrected))
    return transforms


def calculate_weights(mask, image=None, method=FusionMethod.ROBUST_DRONE):
    #print("method:", method)
    """Calcula pesos según el método seleccionado"""
    if method == FusionMethod.SIMPLE_AVERAGE:
        return mask.astype(np.float32)
    
    elif method in [FusionMethod.WEIGHTED_DISTANCE, FusionMethod.ROBUST_DRONE]:
        return cv2.distanceTransform(
            mask.astype(np.uint8), 
            cv2.DIST_L2, 
            3
        ) * mask
    
    elif method == FusionMethod.EXPOSURE_COMPENSATED:
        # Implementación simplificada - en producción calcular ganancias reales
        return cv2.distanceTransform(
            mask.astype(np.uint8), 
            cv2.DIST_L2, 
            3
        ) * mask
    
    else:
        return mask.astype(np.float32)
    
    
def save_as_geotiff(image, filename, origin_x, origin_y, resolution, ref_zone_lon, transparent_bg = True, alpha = 1.0):
    """Guarda una imagen numpy como GeoTIFF georreferenciado"""
    driver = gdal.GetDriverByName('GTiff')
    rows, cols, bands = image.shape
    
    out_ds = driver.Create(
        filename, 
        cols, 
        rows, 
        bands + 1 if transparent_bg else bands, 
        gdal.GDT_Byte)
    # Establecer georreferenciación
    out_ds.SetGeoTransform((
        origin_x,    # Coordenada X del píxel superior izquierdo
        resolution,   # Tamaño de píxel en X (resolución)
        0,           # Rotación (0 si el norte está arriba)
        origin_y,    # Coordenada Y del píxel superior izquierdo
        0,           # Rotación (0 si el norte está arriba)
        -resolution  # Tamaño de píxel en Y (negativo porque el origen es la esquina superior)
    ))

    # Establecer sistema de referencia espacial (WGS84 UTM por ejemplo)
        # Sistema de coordenadas (ej: UTM zona 18S para Perú)
    srs = osr.SpatialReference()
    zone = int((ref_zone_lon + 180) // 6 + 1)  # Corregido para usar coordenada x (origin[0])
    epsg = 32700 + zone #if origin_y < 0 else 32600 + zone  # 326XX para norte, 327XX para sur
    print("epsg:", epsg)
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(epsg)  # Cambiar al EPSG adecuado para tu zona UTM
    out_ds.SetProjection(srs.ExportToWkt())

    for b in range(bands):
        out_band = out_ds.GetRasterBand(b+1)
        out_band.WriteArray(image[:, :, 2-b])
        out_band.FlushCache()
        
    if transparent_bg:
        #Crear y escribir banda Alpha (0 donde la imagen es cero)
        alpha_band = np.ones((image.shape[0], image.shape[1]), dtype=np.uint8) * 255
        # Verificar si todos los canales son cero (píxel transparente)
        zero_mask = np.all(image == 0, axis=2)
        alpha_band[zero_mask] = 0
        if alpha < 1.0:
            alpha_band = (alpha_band * alpha).astype(np.uint8)

        out_ds.GetRasterBand(4).WriteArray(alpha_band)
        # Configurar la banda 4 como canal alpha
        out_ds.GetRasterBand(4).SetColorInterpretation(gdal.GCI_AlphaBand)
   
    out_ds.FlushCache()
    out_ds = None  # Cerrar el archivo

def build_adjacency_graph_from_edges(n, edges):
    """Construye lista de adyacencia con peso = -num_inliers (queremos MST con mayor inliers)."""
    adj_graph = { i: [] for i in range(n)}
    for (i,j,H,mask,inliers,pts_i,pts_j) in edges:
        w = -inliers
        adj_graph[i].append((j, w, H, mask, pts_i, pts_j))
        adj_graph[j].append((i, w, np.linalg.inv(H), mask, pts_j, pts_i))
    return adj_graph

def prim_mst(n, adj_graph):
    """
    Prim simple que retorna aristas del MST en forma (u,v,H_uv,mask,pts_u,pts_v).
    Es el camino a recoorrer en la propagacion de correciones.
    """

    visited = [False] * n
    visited[0] = True
    mst_edges = []
    
    import heapq
    heap = []

    for (v, w, H, mask, pts_u, pts_v) in adj_graph[0]:
        heapq.heappush(heap, (w, 0, v, H, mask, pts_u, pts_v))
    
    while heap:
        w,u,v,H,mask,pts_u,pts_v = heapq.heappop(heap)
        if visited[v]:
            continue

        visited[v] = True
        mst_edges.append((u,v, H, mask, pts_u, pts_v))

        for (to, w2, H2, mask2, pts_a, pts_b) in adj_graph[v]:
            if not visited[to]:
                heapq.heappush(heap, (w2, v, to, H2, mask2, pts_a, pts_b))
    
    return mst_edges


def prim_mst_2(n, adj_graph):
    """
    Prim simple que retorna aristas del MST en forma (u,v,H_uv,mask,pts_u,pts_v).
    Es el camino a recoorrer en la propagacion de correciones.
    """

    visited = np.full((n,n), False, dtype=bool)
    #visited = [False] * n
    visited[0,0] = True
    mst_edges = []
    
    import heapq
    heap = []

    for (v, w, H, mask, pts_u, pts_v) in adj_graph[0]:
        heapq.heappush(heap, (w, 0, v, H, mask, pts_u, pts_v))
    
    while heap:
        w,u,v,H,mask,pts_u,pts_v = heapq.heappop(heap)
        print(f"visited[{u},{v}]:", visited[u,v])
        if visited[u,v]:
            continue

        visited[u,v] = True
        visited[v,u] = True

        mst_edges.append((u,v, H, mask, pts_u, pts_v))

        for (to, w2, H2, mask2, pts_a, pts_b) in adj_graph[v]:
            if not visited[v,to]:
                heapq.heappush(heap, (w2, v, to, H2, mask2, pts_a, pts_b))
    
    return mst_edges

def build_lineal_system(all_images_data, inliers, scale_factor):
    # Inicialización de listas para COO
    weight = 5
    row_data = []
    row_indices = []
    col_indices = []
    b_list = []
    row_counter = 0
    # 1. Restricciones de referencia (para imagen 0)
    ref_values = [1, 0, 0, 0, 1, 0]  # a, b, tx, c, d, ty
    for col_idx, val in enumerate(ref_values):
        row_data.append(weight)
        row_indices.append(row_counter)
        col_indices.append(col_idx)
        b_list.append(weight * val)
        row_counter += 1
    n = len(all_images_data)
    num_params = 6 * n
    # 2. Restricciones de similitud: a ≈ d, b ≈ -c
    for i in range(n):
        # T₁₁ = T₂₂
        row_data.extend([1.0, -1.0])
        row_indices.extend([row_counter] * 2)
        col_indices.extend([6 * i, 6 * i + 4])
        b_list.append(0)
        row_counter += 1

        # T₁₂ = -T₂₁  → T₁₂ + T₂₁ = 0
        row_data.extend([1.0, 1.0])
        row_indices.extend([row_counter] * 2)
        col_indices.extend([6 * i + 1, 6 * i + 3])
        b_list.append(0)
        row_counter += 1


    # 4. Restricciones de reproyección
    for (i, j), match_list in tqdm(inliers.items(), desc="Matches"):
        kp_i = all_images_data[i]['kp_img_dom']
        kp_j = all_images_data[j]['kp_img_dom']
        selected_matches = match_list[:60]

        for m in selected_matches:
            src_pt = np.array([*kp_i[m.queryIdx].pt, 1.0])
            dst_pt = np.array([*kp_j[m.trainIdx].pt, 1.0])

            # Escalar para evitar magnitudes grandes
            src_pt_scaled = src_pt * scale_factor
            dst_pt_scaled = dst_pt * scale_factor

            # Ecuación para coordenada X
            for k in range(3):
                row_data.extend([src_pt_scaled[k], -dst_pt_scaled[k]])
                row_indices.extend([row_counter, row_counter])
                col_indices.extend([6 * i + k, 6 * j + k])
            b_list.append(0)
            row_counter += 1

            # Ecuación para coordenada Y
            for k in range(3):
                row_data.extend([src_pt_scaled[k], -dst_pt_scaled[k]])
                row_indices.extend([row_counter, row_counter])
                col_indices.extend([6 * i + 3 + k, 6 * j + 3 + k])
            b_list.append(0)
            row_counter += 1

    # Construcción del sistema disperso
    A = coo_matrix((row_data, (row_indices, col_indices)), shape=(row_counter, num_params)).tocsr()
    b = np.array(b_list)
    return A, b


def solve_global_transforms(A, b, n_images, scale_factor):
    solution = lsqr(A, b, atol=1e-6, btol=1e-6)[0]
    # Reorganizar las transformaciones
    global_transforms = []
    for i in tqdm(range(n_images), desc="Images"):
        T1 = solution[6*i:6*i+3]
        T1[2] = T1[2] / scale_factor
        T2 = solution[6*i+3:6*i+6]
        T2[2] = T2[2] / scale_factor
        M = np.vstack([T1, T2, [0, 0, 1]])
        global_transforms.append(M)
    
    return global_transforms

def create_mosaic(all_images_data, global_transforms, dom_shape):
    blended = np.zeros((dom_shape[0], dom_shape[1], 3), dtype=np.float32)
    total_weights = np.zeros((dom_shape[0], dom_shape[1]), dtype=np.float32)

    n_images = len(all_images_data)
    for index, row in tqdm(all_images_data.items(), total= n_images, desc = "Build Mosaic"):
        image = cv2.imread(row['relative_im_path'])
        image_distortion = distortion_correction(image)
        H_rtk = row['H_rtk']
        terrain_points_dom = row['terrain_points_dom']
        imagen_proyectada, mask = direct_project_image_to_dom(image_distortion, H_rtk, dom_shape, terrain_points_dom)


        projected_corrected = cv2.warpPerspective(imagen_proyectada, global_transforms[index], (int(dom_shape[1]), int(dom_shape[0])))
        mask = cv2.warpPerspective(mask, global_transforms[index], (int(dom_shape[1]), int(dom_shape[0])))
        weights = calculate_weights(mask, None, FusionMethod.ROBUST_DRONE)
        max_weight = np.max(weights)
        if max_weight > 0:
            weights = weights / max_weight
        update_mask = weights > total_weights
        blended[update_mask] = projected_corrected[update_mask]
        total_weights = np.maximum(total_weights, weights)


    final_dom = blended.astype(np.uint8).copy()
    
    return final_dom

def initialize_homographies(n, mst_edges):
    """Inicializa H_i con H_root = I, propaga por MST."""
    H_abs = [None] * n
    H_abs[0] = np.eye(3)

    # Construir lista de hijos por propagacion
    added = {0}
    adj_map = {}

    np.full((n,n), False, dtype=bool)

    inliers_masks_abs = [None] * n
    for (u,v,H,mask,pts_u,pts_v) in mst_edges:
        print("initialize_homographies mask:", len(mask))
        print("pts_u mask:", len(pts_u))
        print("pts_v mask:", len(pts_v))
        adj_map.setdefault(u, []).append((v,H))
        adj_map.setdefault(v, []).append((u, np.linalg.inv(H)))
        inliers_masks_abs[u] = [False] * len(pts_u)
        inliers_masks_abs[v] = [False] * len(pts_v)


    # BFS propagation
    queue = [0]
    while queue:
        u = queue.pop(0)
        for (v, H_uv) in adj_map.get(u, []):
            if H_abs[v] is None:
                H_abs[v] = H_abs[u].dot(H_uv)
                queue.append(v)
        ## Aca es el cambio si es que hay un H_abs aplicar la mascara a los puntos de la imagen luego hacer en homografie con los puntos pero manteniendo los inlieres que habia antes
    
    # src_pts = pts_i.reshape(-1, 1, 2)

    # 3. Aplicar la transformación
    # Esto calcula: P_dst = H * P_src
    #dst_pts = cv2.perspectiveTransform(src_pts, H)

    # For any disconnected images, set identity
    for i in range(n):
        if H_abs[i] is None:
            print("Desconectado:", i)
            H_abs[i] = np.eye(3)

    
    return H_abs


def initialize_homographies2(n, mst_edges):
    """Inicializa H_i con H_root = I, propaga por MST."""
    H_abs = [None] * n
    H_abs[0] = np.eye(3)

    # Construir lista de hijos por propagacion
    added = {0}
    adj_map = {}

    #inliers_masks_abs = np.full((n,n), None, dtype=bool)

    inliers_masks_abs = [[None] * n for _ in range(n)]
    for (u,v,H,mask,pts_u,pts_v) in mst_edges:
        print("initialize_homographies mask:", len(mask))
        print("pts_u mask:", len(pts_u))
        print("pts_v mask:", len(pts_v))
        adj_map.setdefault(u, []).append((v,H,mask,pts_u,pts_v))
        adj_map.setdefault(v, []).append((u, np.linalg.inv(H), mask,pts_v,pts_u))
        inliers_masks_abs[u][v] = [False] * len(pts_u)
        inliers_masks_abs[v][u] = [False] * len(pts_v)


    # BFS propagation
    queue = [0]
    while queue:
        u = queue.pop(0)
        for (v, H_uv, mask,pts_u,pts_v) in adj_map.get(u, []):
            if H_abs[v] is None:
                H_abs[v] = H_abs[u].dot(H_uv)
                print("inliers_masks_abs[u,v]:",inliers_masks_abs[u][v])
                print("mask:",mask)
                inliers_masks_abs[u][v] = mask.copy()
                inliers_masks_abs[v][u] = mask.copy()
                queue.append(v)
            else:
                src_pts_v = pts_v.reshape(-1, 1, 2)
                dst_pts_v = cv2.perspectiveTransform(src_pts_v, H_abs[v])
                dst_pts_u = copy.deepcopy(pts_u.reshape(-1, 1, 2))
                print("[inliers_masks_abs[v]:", len(inliers_masks_abs[u][v]))
                print("dst_pts_u:", len(dst_pts_u))
                print("dst_pts_v:", len(dst_pts_v))
                dst_pts_u = np.array(dst_pts_u)
                dst_pts_v = np.array(dst_pts_v)
                dst_pts_u[inliers_masks_abs[u][v]] = dst_pts_v[inliers_masks_abs[v][u]]
                H, mask = cv2.estimateAffine2D(dst_pts_v, dst_pts_u, method=cv2.RANSAC, ransacReprojThreshold= RANSAC_THRESH)
                H = np.vstack([H, [0, 0, 1]])
                mask = mask.ravel().astype(bool)
                H_abs[v] = H_abs[v].dot(H)
                inliers_masks_abs[u][v] = [a or b for a, b in zip(inliers_masks_abs[u][v], mask)]
                inliers_masks_abs[v][u] = [a or b for a, b in zip(inliers_masks_abs[v][u], mask)]
                
        ## Aca es el cambio si es que hay un H_abs aplicar la mascara a los puntos de la imagen luego hacer en homografie con los puntos pero manteniendo los inlieres que habia antes
    
    # src_pts = pts_i.reshape(-1, 1, 2)

    # 3. Aplicar la transformación
    # Esto calcula: P_dst = H * P_src
    #dst_pts = cv2.perspectiveTransform(src_pts, H)

    # For any disconnected images, set identity
    for i in range(n):
        if H_abs[i] is None:
            print("Desconectado:", i)
            H_abs[i] = np.eye(3)

    
    return H_abs

def generate_mosaic(all_images_data, type_align_matrix = "affine", detector_keypoint = "SIFT", signal_progress = None):
    all_images_data_list = list(all_images_data.values())
    n_images = len(all_images_data)
    print("Comienza process_calculate_camera_pose")
    all_images_data_list = process_calculate_camera_pose(all_images_data_list)
    if signal_progress is not None:
        signal_progress.emit(55)
    print("Comienza process_terrain_points")
    all_images_data_list = process_terrain_points(all_images_data_list)
    if signal_progress is not None:
        signal_progress.emit(60)
    print("Comienza estimate_dom_parameters")
    dom_bounds, dom_resolution = estimate_dom_parameters(all_images_data_list, margin_extension = 0.1)
    width_m = dom_bounds[1] - dom_bounds[0]
    height_m = dom_bounds[3] - dom_bounds[2]
    width_px = int(width_m / dom_resolution)
    height_px = int(height_m / dom_resolution)
    dom_size = (height_px, width_px)

    if signal_progress is not None:
        signal_progress.emit(65)
    print("Comienza process_project_corners_to_dom")
    all_images_data_list = process_project_corners_to_dom(all_images_data_list, dom_bounds, dom_resolution)
    if signal_progress is not None:
        signal_progress.emit(70)
    print("Comienza process_detect_keypoint_descriptors_in_dom")

    all_images_data_list = process_detect_keypoint_descriptors_in_dom(all_images_data_list, dom_size, detector_keypoint)
    
    if signal_progress is not None:
        signal_progress.emit(75)
    
    print("Comienza propagate_pairwise_correction")
    all_terrain_points_dom = [d['terrain_points_dom'] for d in all_images_data_list]

    # 2. Construir grafo de solapamiento
    overlap_graph  = build_overlap_graph(all_terrain_points_dom, min_overlap=0.45)
    # 5) Grafo y MST (Prim). Ruta de propacion
    edges = estimate_pairwase_homographies(overlap_graph, all_images_data_list, type_align_matrix)

    adj_graph = build_adjacency_graph_from_edges(n_images, edges)

    mst = prim_mst_2(n_images, adj_graph)
    # 6) Inicialización H absolute vía propagación en MST
    #H_abs = initialize_homographies(n, mst)
    #matches = calculate_pairwase_matches(all_images_data_list)
    #transforms, inliers = estimate_pairwise_transforms(all_images_data_list, matches, transform_type='affine')
    #scale_factor = 1.0 / dom_size[0]
    #A, b = build_lineal_system(all_images_data, inliers, scale_factor = scale_factor)
    #global_transforms = solve_global_transforms(A.tocsr(), b, len(all_images_data), scale_factor = scale_factor)
    #print("global_transforms:", global_transforms)
    #if signal_progress is not None:
    #    signal_progress.emit(85)
    #print("Comienza transformations")
    #print("Comienza propagate_pairwise_correction")
    
    #final_dom = create_mosaic(all_images_data, global_transforms, dom_shape = (height_px, width_px))
    #ref_zone_lon = all_images_data[0]['longitude']
    #save_as_geotiff(
    #        final_dom, f"campo2_mosaico_graph_queue_refine_{type_align_matrix}_{len(all_images_data)}_images.tif", 
    #        dom_bounds[0], dom_bounds[3],  # Esquina superior izquierda (X,Y)
    #        dom_resolution,
    #        ref_zone_lon
    #    )
    if signal_progress is not None:
        signal_progress.emit(100)

def crop_valid_region(img, mask, tree_mask):
    ys, xs = np.where(mask > 0)
    y_min, y_max = ys.min(), ys.max()
    x_min, x_max = xs.min(), xs.max()
    cropped_img = img[y_min:y_max+1, x_min:x_max+1]
    cropped_mask = mask[y_min:y_max+1, x_min:x_max+1]
    cropped_tree_mask = tree_mask[y_min:y_max+1, x_min:x_max+1]
    corner = (x_min, y_min)
    return cropped_img, cropped_mask, cropped_tree_mask, corner

def crop_valid_region_mask(mask):
    ys, xs = np.where(mask > 0)
    y_min, y_max = ys.min(), ys.max()
    x_min, x_max = xs.min(), xs.max()
    cropped_mask = mask[y_min:y_max+1, x_min:x_max+1]
    corner = (x_min, y_min)
    return cropped_mask, corner

def centroide_poligono(polygon):
        """
        polygon: np.array de shape (N,2) con vértices (x,y).
        """
        M = cv2.moments(np.array(polygon, dtype=np.int32))
        if M["m00"] == 0:
            # Si área = 0 (ej. polígono degenerado), devolvemos promedio de puntos
            cx, cy = polygon[:,0].mean(), polygon[:,1].mean()
        else:
            cx = M["m10"] / M["m00"]
            cy = M["m01"] / M["m00"]
        return np.array([cx, cy])


def distancia_centroide_imagen( polygon, img_shape):
    """
    polygon: np.array de (N,2)
    img_shape: (alto, ancho) de la imagen
    """
    h, w = img_shape[:2]
    centro_img = np.array([w/2, h/2])
    centro_poly = centroide_poligono(polygon)
    dist = np.linalg.norm(centro_poly - centro_img)
    return dist

def bbox(poly):
    x, y = poly[:,0], poly[:,1]
    return [x.min(), y.min(), x.max(), y.max()]

def iou_polygons_mask(pts_a, pts_b, img_shape, show_intersection = False):
    """
    pts_*: array-like (N,2) en coordenadas de imagen (x,y). Pueden ser float.
    img_shape: (alto, ancho) de la máscara.
    """
    h, w = img_shape
    m1 = np.zeros((h, w), dtype=np.uint8)
    m2 = np.zeros((h, w), dtype=np.uint8)

    # OpenCV espera int32 y coordenadas como (x,y)
    pa = np.round(np.array(pts_a)).astype(np.int32)
    pb = np.round(np.array(pts_b)).astype(np.int32)

    # Bounding boxes
    bx1, by1, bx2, by2 = bbox(pa)
    cx1, cy1, cx2, cy2 = bbox(pb)

    # ROI común
    x1, y1 = max(bx1, cx1), max(by1, cy1)
    x2, y2 = min(bx2, cx2), min(by2, cy2)
    
    #if x2 <= x1 or y2 <= y1:
    #    return 0.0  # no hay intersección posible


    if x2 <= x1 or y2 <= y1:
        return 0.0  # no hay intersección posible
    
    cv2.fillPoly(m1, [pa], 1)
    cv2.fillPoly(m2, [pb], 1)

     # 3. Cálculo de áreas
    area1 = m1.sum()
    area2 = m2.sum()

    if show_intersection:
        print("Mostrar interseccion:")
        # Imagen en color
        img_vis = np.zeros((h, w, 3), dtype=np.uint8)
        img_vis[m1 == 1] = [255, 0, 0]     # Polígono A en rojo
        img_vis[m2 == 1] = [0, 255, 0]     # Polígono B en verde
        img_vis[np.logical_and(m1 == 1, m2 == 1)] = [0, 0, 255]  # Intersección en azul

        plt.imshow(img_vis)
        plt.title(f"IoU")
        #plt.axis("off")
        plt.show()

    inter = np.logical_and(m1, m2).sum()
    union = np.logical_or(m1, m2).sum()
    
    iou = 0.0 if union == 0 else inter / union

    # 4. Intersección normalizada por el polígono más grande
    max_area = max(area1, area2)
    inter_over_max = inter / max_area if max_area > 0 else 0.0

    return inter_over_max


def filter_valid_region_contours(contours, im_shape, percent_crop_h = 10, percent_crop_w = 10):
    h, w = im_shape
    crop_h = (h * percent_crop_h) // 100
    crop_w = (w * percent_crop_w) // 100

    x_min, x_max = crop_w, w - crop_w
    y_min, y_max = crop_h, h - crop_h
    filtered_contours = []
    for cnt in contours:
        pts = cnt.reshape(-1, 2)
        # Verificar si algún punto está dentro del área válida
        inside  = np.logical_and.reduce((
            pts[:, 0] >= x_min,
            pts[:, 0] <= x_max,
            pts[:, 1] >= y_min,
            pts[:, 1] <= y_max
        ))
         # Si TODOS los puntos están dentro, mantenemos el contorno
        if np.all(inside):
            filtered_contours.append(cnt)
        # Se puede agregar un else para recortar los que no, o tal solo si tenen mas de las 3 cuartas partes dentro
    
    return filtered_contours


def contour_hu_moments(contour):
    moments = cv2.moments(contour)
    hu_moments = cv2.HuMoments(moments)

    hu_moments = -np.sign(hu_moments) * np.log10(np.abs(hu_moments) + 1e-10)

    hu_1 = hu_moments[0][0]
    hu_2 = hu_moments[1][0]

    return hu_1, hu_2

def filter_disconnected_region(contour, im_size):
    contours = [contour]  # el que enviaste
    # 1. Dibujar el contorno en una máscara vacía
    mask = np.zeros(im_size, dtype=np.uint8)
    cv2.drawContours(mask, contours, -1, 255, -1)
    # 2. Encontrar regiones separadas

    # --- A) Cierre: une regiones próximas ---
    kernel = np.ones((7, 7), np.uint8)
    #closed = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    # --- B) Apertura: elimina fragmentos pequeños ---
    opened = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, 1)
    closed = cv2.morphologyEx(opened, cv2.MORPH_CLOSE, kernel,1)

    contours_new, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # 3. Elegir el contorno más grande por área
    largest = max(contours_new, key=cv2.contourArea)
    return largest

def posprocessing_segmentations(segmentations, im_shape, hu1_threshold = 0.75):
    ## eliminar regiones separadas en deteccion

    contours = [np.array(seg, dtype=np.int32).reshape((-1,1,2)) for seg in segmentations]
    contours = filter_valid_region_contours(contours, im_shape)
    ## Filtar por redondes
    hu_moments = [contour_hu_moments(contour=contours[i]) for i in range(len(contours))]
    for i in range(len(hu_moments)):
        if hu_moments[i][0] < 77:
            #print("AQUI ENTRO: i=", i,", hu1=", hu_moments[i][0])
            conts = [contours[i]]  # el que enviaste
            # 1. Dibujar el contorno en una máscara vacía
            mask = np.zeros(im_shape, dtype=np.uint8)
            cv2.drawContours(mask, conts, -1, 255, -1)
            # 2. Encontrar regiones separadas

            # --- A) Cierre: une regiones próximas ---
            kernel = np.ones((7, 7), np.uint8)
            #closed = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

            # --- B) Apertura: elimina fragmentos pequeños ---
            opened = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, 1)
            closed = cv2.morphologyEx(opened, cv2.MORPH_CLOSE, kernel,1)

            contours_new, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
              # 3. Elegir el contorno más grande por área
            largest = max(contours_new, key=cv2.contourArea)
            contours[i] = largest
            hu_moments[i]= contour_hu_moments(largest)

    filtered_contours = [contours[i] for i in range(len(contours)) if hu_moments[i][0] >= hu1_threshold]
    filtered_contours = [filter_disconnected_region(contour, im_shape) for contour in filtered_contours]
    
    return filtered_contours

def read_trees_mask(detect_path, im_shape):
    with open(detect_path, "r") as f:
        detecctions = json.load(f)
    
    detecctions = detecctions['detecctions']

    segmentations = detecctions['segmentations']
    mask_trees = np.zeros(im_shape, dtype=np.uint8)
    contours = [np.array(seg, dtype=np.int32).reshape((-1,1,2)) for seg in segmentations]
    mask_trees = cv2.drawContours(mask_trees, contours, -1, 255, -1)
    return mask_trees, segmentations

def seg_pts_to_dom(segs, H):
    #print("len(segs):", len(segs))
    segs_warped = []
    for poly in segs:
        pts = np.array(poly, dtype=np.float32).reshape(-1, 1, 2)
        pts_warped = cv2.perspectiveTransform(pts, H)
        pts_warped = pts_warped.reshape(-1, 2)

        area = cv2.contourArea(pts_warped)
        if area < 1:
            print("⚠️ Contorno degenerado o autointersectado")
            pts_warped = cv2.convexHull(pts_warped)
        # 2. Verificar si está cerrado
        
        #if not np.allclose(pts_warped[0], pts_warped[-1], atol=1e-3):
        #    pts_warped = np.vstack([pts_warped, pts_warped[0]])
        #    print("--------------------contorno abierto---------------------")


        segs_warped.append(pts_warped)
    return segs_warped

def match_sames_detects(adj_graph, metadata_images, dom_size):
    all_filtered_segmentations = []
    all_dist_to_centers = []
    for i in tqdm(range(len(metadata_images)), desc="Filtered Detects"):
        meta = metadata_images[i]
        detect_path = meta['detections_path']
        im_shape = (meta["image_height"], meta["image_width"])
        mask_trees, segmentations = read_trees_mask(detect_path, im_shape)
        filtered_segmentations = posprocessing_segmentations(segmentations, im_shape, hu1_threshold = 0.70)
        all_filtered_segmentations.append(filtered_segmentations)
        dist_to_centers = [distancia_centroide_imagen(poly, img_shape = im_shape) for poly in filtered_segmentations]
        all_dist_to_centers.append(dist_to_centers)

    same_detects_graph = {}
    for i, neighbords in tqdm(adj_graph.items(), desc="Trees Matches", total=len(adj_graph)):
        filtered_segmentations_i = all_filtered_segmentations[i]
        meta_i = metadata_images[i]
        if len(filtered_segmentations_i) == 0:
            continue
        H_rtk_i = meta_i['H_rtk']
        segs_im_dom_i = seg_pts_to_dom(filtered_segmentations_i, H_rtk_i) #[seg_pts_to_dom(seg, H_global) for seg in segmentations]
        dist_to_centers_i = all_dist_to_centers[i] # [distancia_centroide_imagen(poly, img_shape = im_shape) for poly in filtered_segmentations_i] #[[distancia_centroide_imagen(poly, img_shape = im_shape) for poly in seg] for seg in segmentations]
        
        for u, seg_u in enumerate(segs_im_dom_i):
                key_id = f"I{i}-T{u}"
                #print("key_id:", key_id)
                if key_id not in same_detects_graph:
                    same_detects_graph[key_id] = [[(i,u), dist_to_centers_i[u], 1.0, seg_u, filtered_segmentations_i[u]]]
                    

        for neigh_i in range(len(neighbords)):
            j, _, H, _, _, _ = neighbords[neigh_i]
            meta_j = metadata_images[j]
            filtered_segmentations_j = all_filtered_segmentations[j]
            meta_j = metadata_images[j]
            
            H_rtk_j = meta_j['H_rtk']
            H_g = H @ H_rtk_j
            segs_im_dom_j = seg_pts_to_dom(filtered_segmentations_j, H_g) #[seg_pts_to_dom(seg, H_global) for seg in segmentations]
            dist_to_centers_j = all_dist_to_centers[j] #[distancia_centroide_imagen(poly, img_shape = im_shape) for poly in filtered_segmentations_j] #[[distancia_centroide_imagen(poly, img_shape = im_shape) for poly in seg] for seg in segmentations]

            for u, seg_u in enumerate(segs_im_dom_i):
                key_id = f"I{i}-T{u}"
                if key_id not in same_detects_graph:
                    same_detects_graph[key_id] = []
                poly_i_u = seg_u
                
                if len(segs_im_dom_j) == 0:
                    continue
                for v, poly_j_v in enumerate(segs_im_dom_j):
                    iou = iou_polygons_mask(poly_i_u, poly_j_v, dom_size, show_intersection = False)

                    if iou > 0.40:
                        if key_id in same_detects_graph:
                            same_detects_graph[key_id].append([(j,v), dist_to_centers_j[v], iou, poly_j_v, filtered_segmentations_j[v]])
                        else:
                            same_detects_graph[key_id] = [[(j,v), dist_to_centers_j[v], iou, poly_j_v, filtered_segmentations_j[v]]]

    
    return same_detects_graph

def reduce_unique_detections(same_detects_graph):
    visited = {key: False for key in same_detects_graph.keys()}

    unique_detects_trees = []

    for key, trees_matches in same_detects_graph.items():
        im_code, tree_code = key.split("-")
        im_id, tree_id = int(im_code[1:]), int(tree_code[1:])
        key_iv = f"I{im_id}-T{tree_id}"

        if visited[key_iv]:
            continue

        if len(trees_matches) > 1:
            full_matches = trees_matches.copy()
            for match in trees_matches[1:]:
                im_j, tree_u = match[0]
                key_ju = f"I{im_j}-T{tree_u}"
                full_matches.extend(same_detects_graph[key_ju])
            
            best_tree = min(full_matches, key= lambda x: x[1])
            best_tree_index = best_tree[0] # im_index, poly_index
            key_best_tree = f"I{best_tree_index[0]}-T{best_tree_index[1]}"

            if not visited[key_best_tree]:
                unique_detects_trees.append([best_tree_index, best_tree[-2], best_tree[-1]])

            for match in full_matches:
                im_j, tree_u = match[0]
                key_ju = f"I{im_j}-T{tree_u}"
                visited[key_ju] = True

        else:
            best_tree = trees_matches[0]
            im_j, tree_u = best_tree[0]
            unique_detects_trees.append([[im_j, tree_u], best_tree[-2], best_tree[-1]])

            key_ju = f"I{im_j}-T{tree_u}"
            visited[key_ju] = True

    return unique_detects_trees

def apply_unique_detecs(images_metadata, unique_detects_trees):
    for i in range(len(images_metadata)):
        images_metadata[i]['unique_detects'] = [] 
    
    for unique_detect in unique_detects_trees:
        images_metadata[unique_detect[0][0]]['unique_detects'].append(unique_detect[-1])

    return images_metadata


def create_map_trees_ids(mosaic_path = None, mosaic_image = None, base_dir = None):
    if mosaic_image is not None:
        mosaic_base = mosaic_image
    elif mosaic_path is not None:
        mosaic_base = cv2.imread(mosaic_path)

    path_trees_results = f"{base_dir}/mosaic/trees/trees_results.json"

    trees_results = []
    
    print("mosaic_base:", mosaic_base.shape)
    with open(path_trees_results, 'r') as f:
        trees_results = json.load(f)

    # Definimos colores en BGR
    try:
        num_canales = mosaic_base.shape[2]
    except IndexError:
        num_canales = 1 # Imagen en escala de grises

    if num_canales == 4:
        print("Imagen BGRA detectada. Usando colores con canal Alpha.")
        # [Azul, Verde, Rojo, Alpha] -> Alpha 255 es opaco
        COLOR_ROJO = (0, 0, 255, 255)
        COLOR_BLANCO = (255, 255, 255, 255)
    else:
        print("Imagen BGR estándar detectada.")
        COLOR_ROJO = (0, 0, 255)
        COLOR_BLANCO = (255, 255, 255)

    font = cv2.FONT_HERSHEY_SIMPLEX
    scale_font = 2
    thickness_font = 2
    alpha_overlay = 0.5

    COLOR_SALUDABLE = np.array([0, 255, 50], dtype=np.uint8)
    COLOR_DEFICIENCIA = np.array([0, 247, 191],  dtype=np.uint8)

    for r in trees_results:
        xmin, y_min, x_max, y_max = r['bbox']
        x_c = (xmin + x_max) // 2
        y_c = (y_min + y_max) // 2
        coord_center = (x_c, y_c)
        tree_id = r["id"]
        
        
        print("r['mask_path']:", r['mask_path'])
        mask = cv2.imread(r['mask_path'],cv2.IMREAD_GRAYSCALE)
        
        if mask is None:
            print("Mascara No encontrada")
            continue
        
        print("mask.shape", mask.shape)
        # 1. Asegurar que la máscara sea 2D
        if len(mask.shape) == 3:
            mask = mask.squeeze()
        print("mask.shape")
        h, w = mask.shape
        y_max = y_min + h
        x_max = xmin + w

        roi = mosaic_base[y_min:y_max, xmin:x_max]
        pixeles_base = roi[mask > 0, :3]
        color_mask = COLOR_DEFICIENCIA if r['class'].upper() == "DEFICIENCIA" else COLOR_SALUDABLE
        overlay_pixels = (pixeles_base * (1 - alpha_overlay)) + (color_mask * alpha_overlay)
        
        print("overlay_pixels:",  overlay_pixels.shape)
        roi[mask > 0, :3] = overlay_pixels.astype(np.uint8)

        #
        #overlay = 
        texto = str(tree_id)
        
        (ancho_text, alto_text), linea_base = cv2.getTextSize(texto, font, scale_font, thickness_font)

        # Calculamos la posición de la esquina inferior izquierda del texto para que quede centrado
        x_text = coord_center[0] - (ancho_text // 2)
        y_text = coord_center[1] + (alto_text // 2)
        posicion_text = (x_text, y_text)
        

        cv2.circle(
            mosaic_base,
            coord_center,
            15,
            COLOR_ROJO,
            thickness=-1
        )

        # Dibujamos el texto
        cv2.putText(
            mosaic_base,
            texto,
            posicion_text,
            font,
            scale_font,
            COLOR_BLANCO,
            thickness_font,
            lineType=cv2.LINE_AA # LINE_AA hace que los bordes del texto se vean suaves
        )

    path_map_trees = f"{base_dir}/mosaic/rgb/map_trees_ids.png"

    print("path_map_trees:", path_map_trees)
    mask_region = np.any(mosaic_base != 0, axis=2)
    # Coordenadas donde hay datos
    ys, xs = np.where(mask_region == 1)

    if len(xs) == 0:
        print("No hay ningún píxel válido en la imagen.")
    else:
        x_min, x_max = xs.min(), xs.max()
        y_min, y_max = ys.min(), ys.max()

    mosaic_base = mosaic_base[y_min: y_max + 1, x_min: x_max + 1, :]
    cv2.imwrite(path_map_trees, mosaic_base)

    path_card_map = f"{base_dir}/mosaic/rgb/card_map.png"
    cv2.imwrite(path_card_map, mosaic_base[:,:,:3])
    return path_map_trees

class ImageSticher():
    def __init__(self, images_data, on_progress_change = None, on_cancel = None, result_dir = "./"):
        self.images_data = images_data
        self.on_progress_change = on_progress_change
        self.result_dir = result_dir
        self.is_running = True
        self.on_cancel = on_cancel
    
    def process_calculate_camera_pose(self, images_data):
        for im_data in images_data:
            im_data['camera_pose'] = calculate_camera_pose(im_data)
        return images_data
    
    def process_terrain_points(self, images_data):
        for im_data in images_data:
            im_data['terrain_points'] = corners_to_terrain_points(im_data)
            if not self.check_continue_procress():
                return
        return images_data
    
    def stop(self):
        self.is_running = False
    
    def check_continue_procress(self):
        if not self.is_running:
            self.on_cancel()
            return False
        return True

    def estimate_dom_parameters(self, images_data, margin_extension = 0.1, target_resolution = None, scale_factor = 4.1):
        min_gsd = np.min([m['gsd_horizontal'] for m in images_data])
        print("min_gsd:", min_gsd)
        
        if target_resolution is None:
            dom_resolution = min_gsd * scale_factor
        else:
            dom_resolution = target_resolution

        print("Dom resolution:", dom_resolution)
        all_coordinates = np.array([m['terrain_points'] for m in images_data]).reshape(-1,2)
        
        min_x, min_y = np.min(all_coordinates, axis=0)
        max_x, max_y = np.max(all_coordinates, axis=0)
        ancho = max_x - min_x # creo que seria al reves
        alto = max_y - min_y

        min_x -= ancho * margin_extension
        max_x += ancho * margin_extension
        min_y -= alto * margin_extension
        max_y += alto * margin_extension
        return (min_x, max_x, min_y, max_y), dom_resolution

    def process_project_corners_to_dom(self, images_data, dom_bounds, dom_resolution):
        for im_data in images_data:
            terrain_points_dom, H = project_corners_to_dom((im_data["image_height"], im_data["image_width"]), dom_bounds, dom_resolution, im_data['terrain_points'])
            im_data['terrain_points_dom'] = terrain_points_dom
            im_data['H_rtk'] = H

        return images_data

    def process_detect_keypoint_descriptors_in_dom(self, images_data, dom_size, detector_keypoint = "SIFT"):
        for i, im_data in enumerate(tqdm(images_data, desc="Keypoints Detection")):
            #print("im_data:", im_data)
            im_path = im_data['relative_path']
            H_rtk = im_data['H_rtk']
            terrain_points_dom = im_data['terrain_points_dom'].astype(np.int32)
            img = cv2.imread(im_path)
            img_undistorned = distortion_correction(img)
            imagen_proyectada, _ = direct_project_image_to_dom(img_undistorned, H_rtk, dom_size)
            kp, desc, _ = detect_keypoint_descriptors_in_dom(imagen_proyectada, terrain_points_dom, detector_type = detector_keypoint, draw_keypoints = False)
            im_data['kp_img_dom'] = kp
            im_data['desc_img_dom'] = desc
            self.progress_update(8 + ((i * 20)// len(images_data)))

            if not self.check_continue_procress():
                return
        return images_data
    
    def calculate_pairwase_matches(self, all_images_data):
        all_terrain_points_dom = [im_data['terrain_points_dom'] for im_data in all_images_data]
        overlap_graph  = build_overlap_graph(all_terrain_points_dom, min_overlap=0.45)
        matches =  {}
        for i, nbrs in tqdm(overlap_graph.items(), desc= "Matches"):
            for j, _ in nbrs:
                desc_i = all_images_data[i]['desc_img_dom']
                #kp_img_dom_i = all_images_data[i]['kp_img_dom']
                desc_j = all_images_data[j]['desc_img_dom']
                #kp_img_dom_j = all_images_data[j]['kp_img_dom']
                good_matches = match_keypoints_with_flann(desc_i, desc_j)
                if len(good_matches) >= 4:  # Mínimo para estimar transformación
                        matches[(i, j)] = good_matches
            self.progress_update(20 + ((i * 30)// len(all_images_data)))
            
            if not self.check_continue_procress():
                return
        return matches

    def build_linear_system(self, all_images_data, inliers, scale_factor):
    # Inicialización de listas para COO
        weight = 20
        row_data = []
        row_indices = []
        col_indices = []
        b_list = []
        row_counter = 0
        # 1. Restricciones de referencia (para imagen 0)
        ref_values = [1, 0, 0, 0, 1, 0]  # a, b, tx, c, d, ty
        for col_idx, val in enumerate(ref_values):
            row_data.append(weight)
            row_indices.append(row_counter)
            col_indices.append(col_idx)
            b_list.append(weight * val)
            row_counter += 1
        n = len(all_images_data)
        num_params = 6 * n
        # 2. Restricciones de similitud: a ≈ d, b ≈ -c
        for i in range(n):
            # T₁₁ = T₂₂
            row_data.extend([1.0, -1.0])
            row_indices.extend([row_counter] * 2)
            col_indices.extend([6 * i, 6 * i + 4])
            b_list.append(0)
            row_counter += 1

            # T₁₂ = -T₂₁  → T₁₂ + T₂₁ = 0
            row_data.extend([1.0, 1.0])
            row_indices.extend([row_counter] * 2)
            col_indices.extend([6 * i + 1, 6 * i + 3])
            b_list.append(0)
            row_counter += 1


        # 3. Restricciones de regularización de traslaciones
        translation_weight = 0.1  # puedes ajustar este valor

        for i in range(n):
            # Penalizar traslación X cerca de 0
            row_data.append(translation_weight)
            row_indices.append(row_counter)
            col_indices.append(6 * i + 2)  # tx
            b_list.append(0)
            row_counter += 1

            # Penalizar traslación Y cerca de 0
            row_data.append(translation_weight)
            row_indices.append(row_counter)
            col_indices.append(6 * i + 5)  # ty
            b_list.append(0)
            row_counter += 1

        # 4. Restricciones de reproyección
        for (i, j), match_list in tqdm(inliers.items(), desc="Matches"):
            kp_i = all_images_data[i]['kp_img_dom']
            kp_j = all_images_data[j]['kp_img_dom']
            selected_matches = match_list[:60]

            for m in selected_matches:
                src_pt = np.array([*kp_i[m.queryIdx].pt, 1.0])
                dst_pt = np.array([*kp_j[m.trainIdx].pt, 1.0])

                # Escalar para evitar magnitudes grandes
                src_pt_scaled = src_pt * scale_factor
                dst_pt_scaled = dst_pt * scale_factor

                # Ecuación para coordenada X
                for k in range(3):
                    row_data.extend([src_pt_scaled[k], -dst_pt_scaled[k]])
                    row_indices.extend([row_counter, row_counter])
                    col_indices.extend([6 * i + k, 6 * j + k])
                b_list.append(0)
                row_counter += 1

                # Ecuación para coordenada Y
                for k in range(3):
                    row_data.extend([src_pt_scaled[k], -dst_pt_scaled[k]])
                    row_indices.extend([row_counter, row_counter])
                    col_indices.extend([6 * i + 3 + k, 6 * j + 3 + k])
                b_list.append(0)
                row_counter += 1

        # Construcción del sistema disperso
        A = coo_matrix((row_data, (row_indices, col_indices)), shape=(row_counter, num_params)).tocsr()
        b = np.array(b_list)
        return A, b

    def solve_global_transforms(self, A, b, n_images, scale_factor):
        solution = lsqr(A, b, atol=1e-6, btol=1e-6)[0]
        # Reorganizar las transformaciones
        global_transforms = []
        for i in tqdm(range(n_images), desc="Images"):
            T1 = solution[6*i:6*i+3]
            T1[2] = T1[2] / scale_factor
            T2 = solution[6*i+3:6*i+6]
            T2[2] = T2[2] / scale_factor
            M = np.vstack([T1, T2, [0, 0, 1]])
            global_transforms.append(M)
        
        return global_transforms

    def seg_pts_transform(self, segs, H):
        print("len(segs):", len(segs))
        segs_warped = []
        for poly in segs:
            pts = np.array(poly, dtype=np.float32).reshape(-1, 1, 2)
            pts_warped = cv2.perspectiveTransform(pts, H)
            pts_warped = pts_warped.reshape(-1, 2)
            segs_warped.append(pts_warped)
        return segs_warped

    def centroide_poligono(self, polygon):
        """
        polygon: np.array de shape (N,2) con vértices (x,y).
        """
        M = cv2.moments(np.array(polygon, dtype=np.int32))
        if M["m00"] == 0:
            # Si área = 0 (ej. polígono degenerado), devolvemos promedio de puntos
            cx, cy = polygon[:,0].mean(), polygon[:,1].mean()
        else:
            cx = M["m10"] / M["m00"]
            cy = M["m01"] / M["m00"]
        return np.array([cx, cy])

    def distancia_centroide_imagen(self, polygon, img_shape):
        """
        polygon: np.array de (N,2)
        img_shape: (alto, ancho) de la imagen
        """
        h, w = img_shape[:2]
        centro_img = np.array([w/2, h/2])
        centro_poly = self.centroide_poligono(polygon)
        dist = np.linalg.norm(centro_poly - centro_img)
        return dist
    def bbox(self, poly):
        x, y = poly[:,0], poly[:,1]
        return [x.min(), y.min(), x.max(), y.max()]

    def iou_polygons_mask(self, pts_a, pts_b, img_shape):
        """
        pts_*: array-like (N,2) en coordenadas de imagen (x,y). Pueden ser float.
        img_shape: (alto, ancho) de la máscara.
        """
        h, w = img_shape
        m1 = np.zeros((h, w), dtype=np.uint8)
        m2 = np.zeros((h, w), dtype=np.uint8)

        # OpenCV espera int32 y coordenadas como (x,y)
        pa = np.round(np.array(pts_a)).astype(np.int32)
        pb = np.round(np.array(pts_b)).astype(np.int32)

        # Bounding boxes
        bx1, by1, bx2, by2 = self.bbox(pa)
        cx1, cy1, cx2, cy2 = self.bbox(pb)

        # ROI común
        x1, y1 = max(bx1, cx1), max(by1, cy1)
        x2, y2 = min(bx2, cx2), min(by2, cy2)

        if x2 <= x1 or y2 <= y1:
            return 0.0  # no hay intersección posible
    
        cv2.fillPoly(m1, [pa], 1)
        cv2.fillPoly(m2, [pb], 1)

        inter = np.logical_and(m1, m2).sum()
        union = np.logical_or(m1, m2).sum()
        iou = 0.0 if union == 0 else inter / union
        return iou

    def filter_same_trees(self, all_images_data, dom_shape):
        all_terrain_points_dom = [im_data['terrain_points_dom'] for im_data in all_images_data]

        segs_dom = [self.seg_pts_transform(data['segmentations'], data['H_rtk'])  
                        for data in all_images_data]
        
        dist_polys = [[self.distancia_centroide_imagen(poly, img_shape = (data['image_height'],data['image_width'])) for poly in data['segmentations']]
                        for data in all_images_data]
        
        overlap_graph = build_overlap_graph(all_terrain_points_dom, min_overlap = 0.45)
        
        revised = [[] for i in range(len(all_images_data))]
        segs_filtered = [[] for i in range(len(all_images_data))]
        
        sames = []
        for i, nbrs in tqdm(overlap_graph.items(), desc= "Filter Trees"):
            segs_dom_i = segs_dom[i]
            
            for k, poly_i_k in enumerate(segs_dom_i):
                
                if k in revised[i]:
                    print("Ya revisado:", (i,k))
                    continue

                same_detecs = [[(i,k), dist_polys[i][k], 1.0]]
                for j, _ in nbrs:
                    segs_dom_j = segs_dom[j]
                    for l, poly_j_l in enumerate(segs_dom_j):
                        iou = self.iou_polygons_mask(poly_i_k, poly_j_l, dom_shape)
                        if iou > 0.5:
                            same_detecs.append( [(j,l), dist_polys[j][l], iou])
                
                best_tree = min(same_detecs, key= lambda x: x[1])
                print("(i,k):", (i,k))
                print("same_detecs:", same_detecs)
                print("best_tree:", best_tree)
                best_tree_index = best_tree[0]
                segs_filtered[best_tree_index[0]].append(best_tree_index[1])
                for indexes, _, _ in same_detecs:
                    revised[indexes[0]].append(indexes[1])

                sames.append()
        
        for i, filtered_segs_i in enumerate(segs_filtered):
            all_images_data[i]['segs_filtered_dom'] = [seg for k, seg in enumerate(segs_dom[i]) if k in filtered_segs_i]
            all_images_data[i]['segs_filtered'] = [seg for k, seg in enumerate(all_images_data[i]["segmentations"]) if k in filtered_segs_i]
            
        return segs_filtered


    def create_mosaic(self, all_images_data, global_transforms, dom_shape):
        blended = np.zeros((dom_shape[0], dom_shape[1], 3), dtype=np.float32)
        total_weights = np.zeros((dom_shape[0], dom_shape[1]), dtype=np.float32)
        
        trees_mask = np.zeros((dom_shape[0], dom_shape[1]), dtype=np.uint8)
        n_images = len(all_images_data)
        
        debug_path = f"{self.result_dir}/mosiac/debug"
        os.makedirs(debug_path, exist_ok = True)

        os.makedirs(f"{debug_path}/proyectada", exist_ok = True)

        os.makedirs(f"{debug_path}/alineada", exist_ok = True)
        
        for index, row in tqdm(all_images_data.items(), total= n_images, desc = "Build Mosaic"):
            print("index:", index)
            # Image Projection to Dom
            image = cv2.imread(row['relative_path'])
            image_distortion = distortion_correction(image)
            H_rtk = row['H_rtk']
            terrain_points_dom = row['terrain_points_dom']
            imagen_proyectada, mask = direct_project_image_to_dom(image_distortion, H_rtk, dom_shape, terrain_points_dom)
            
            cv2.imwrite(f"{debug_path}/proyectada/{os.path.basename(row['relative_path'])[:-4]}_proyectada.png", imagen_proyectada.astype(np.uint8))
            
            # Correction
            projected_corrected = cv2.warpPerspective(imagen_proyectada, global_transforms[int(index)], (int(dom_shape[1]), int(dom_shape[0])))
            
            cv2.imwrite(f"{debug_path}/alineada/{os.path.basename(row['relative_path'])[:-4]}_proyectada_alineada.png", projected_corrected.astype(np.uint8))

            # Trees Masks
            #segs_dom = self.seg_pts_transform(row['segs_filtered'], H_rtk)
            #segs_dom = self.seg_pts_transform(row['segs_filtered_dom'], global_transforms[index])
            #segs_dom_int = [np.array(poly, dtype=np.int32) for poly in segs_dom]
            
            trees_mask_image = np.zeros((dom_shape[0], dom_shape[1]), dtype=np.uint8)
            #cv2.fillPoly(trees_mask_image, segs_dom_int, 255)

            #segs_dom = cv2.perspectiveTransform(segs_dom.reshape(-1, 1, 2), global_transforms[index]).reshape(-1, 2)

            # Blended
            mask = cv2.warpPerspective(mask, global_transforms[int(index)], (int(dom_shape[1]), int(dom_shape[0])))
            weights = calculate_weights(mask, None, FusionMethod.ROBUST_DRONE)
            
            max_weight = np.max(weights)
            if max_weight > 0:
                weights = weights / max_weight

            #for poly in segs_dom_int:
            #    mask_poly = np.zeros((dom_shape[0], dom_shape[1]), dtype=np.uint8)
            #    cv2.fillPoly(mask_poly, [poly], 1)
            #    val_weights = weights[mask_poly == 1]
            #    weights[mask_poly == 1] = val_weights.max()

            
            update_mask = weights > total_weights
            blended[update_mask] = projected_corrected[update_mask]
            total_weights = np.maximum(total_weights, weights)
          
            trees_mask[update_mask] = trees_mask_image[update_mask]
            
            self.progress_update(40 + ((int(index) * 50)// n_images))

            if not self.check_continue_procress():
                return

        final_dom = blended.astype(np.uint8).copy()
        
        return final_dom, trees_mask

    def save_as_geotiff(self, image, filename, origin_x, origin_y, resolution, ref_zone_lon, transparent_bg = True, alpha = 1.0):
        """Guarda una imagen numpy como GeoTIFF georreferenciado"""
        driver = gdal.GetDriverByName('GTiff')
        rows, cols, bands = image.shape
        
        out_ds = driver.Create(
            filename, 
            cols, 
            rows, 
            4 if transparent_bg else 3, 
            gdal.GDT_Byte)
        # Establecer georreferenciación
        out_ds.SetGeoTransform((
            origin_x,    # Coordenada X del píxel superior izquierdo
            resolution,   # Tamaño de píxel en X (resolución)
            0,           # Rotación (0 si el norte está arriba)
            origin_y,    # Coordenada Y del píxel superior izquierdo
            0,           # Rotación (0 si el norte está arriba)
            -resolution  # Tamaño de píxel en Y (negativo porque el origen es la esquina superior)
        ))

        # Establecer sistema de referencia espacial (WGS84 UTM por ejemplo)
            # Sistema de coordenadas (ej: UTM zona 18S para Perú)
        srs = osr.SpatialReference()
        zone = int((ref_zone_lon + 180) // 6 + 1)  # Corregido para usar coordenada x (origin[0])
        epsg = 32700 + zone #if origin_y < 0 else 32600 + zone  # 326XX para norte, 327XX para sur
        print("epsg:", epsg)
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(epsg)  # Cambiar al EPSG adecuado para tu zona UTM
        out_ds.SetProjection(srs.ExportToWkt())

        for b in range(3):
            out_band = out_ds.GetRasterBand(b+1)
            if bands > 1:
                out_band.WriteArray(image[:, :, 2-b])
            else:
                out_band.WriteArray(image[:, :, 0])
            out_band.FlushCache()
            
        if transparent_bg:
            #Crear y escribir banda Alpha (0 donde la imagen es cero)
            alpha_band = np.ones((image.shape[0], image.shape[1]), dtype=np.uint8) * 255
            # Verificar si todos los canales son cero (píxel transparente)
            zero_mask = np.all(image == 0, axis=2)
            alpha_band[zero_mask] = 0
            if alpha < 1.0:
                alpha_band = (alpha_band * alpha).astype(np.uint8)

            out_ds.GetRasterBand(4).WriteArray(alpha_band)
            # Configurar la banda 4 como canal alpha
            out_ds.GetRasterBand(4).SetColorInterpretation(gdal.GCI_AlphaBand)
    
        out_ds.FlushCache()
        out_ds = None  # Cerrar el archivo

    def progress_update(self, percentaje):
        print("update progress:", percentaje)
        if self.on_progress_change is not None:
            print("update progress 2:", percentaje)
            self.on_progress_change(percentaje)

    def mask_to_polygons(self, mask, offset_x=0, offset_y=0):
        # Asegurar binaria tipo 0/255
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        polygons = []
        for cnt in contours:
            if len(cnt) >= 3:  # descartar degenerados
                 # aplicar offset a cada punto
                poly = [[int(x + offset_x), int(y + offset_y)] for [x, y] in cnt.squeeze(1).tolist()]
                polygons.append(poly)
        return polygons
    
    def crop_valid_region_by_mask(self, img, valid_region):
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        mask = np.where(gray > 0, 255, 0).astype(np.uint8)
        ys, xs = np.where(mask > 0)
        y_min, y_max = ys.min(), ys.max()
        x_min, x_max = xs.min(), xs.max()
        cropped_img = img[y_min:y_max+1, x_min:x_max+1]
        cropped_valid_region = valid_region[y_min:y_max+1, x_min:x_max+1]
        corner = (x_min, y_min)
        bbox_valid_region = [(x_min, y_min),(x_max, y_max)]
        return cropped_img, cropped_valid_region, corner, bbox_valid_region

    def find_seam_bleanding(self, images, valid_region_masks):
        images_cropped = []
        valid_region_masks_cropped = []
        corners = []
        bboxes_valid_regions = []
        # Recorte de imagen 
        for img, valid_region_mask in zip(images, valid_region_masks):
            cropped_img, cropped_valid_region_mask, corner, bbox_valid_region = self.crop_valid_region_by_mask(img, valid_region_mask)
            images_cropped.append(cropped_img)
            valid_region_masks_cropped.append(cropped_valid_region_mask)
            corners.append(corner)
            bboxes_valid_regions.append(bbox_valid_region)

        print("--- Exposure compensation ---")
        # Entrenamiento de la compensación
        compensator = cv2.detail.ExposureCompensator_createDefault(
            cv2.detail.ExposureCompensator_GAIN
        )

        compensator.feed(corners, images_cropped, valid_region_masks_cropped)

        # --- Aplicación de la compensación  ---
        for i in range(len(images_cropped)):
            # Se aplica la corrección directamente sobre la imagen original
            # 'i' es el índice, 'corners[i]' es la esquina
            # 'images_cropped[i]' es la imagen a corregir (se modifica in-place)
            # 'valid_region_masks_cropped[i]' es la máscara
            compensator.apply(i, corners[i], images_cropped[i], valid_region_masks_cropped[i])
            
        print("--- Seam finding ---")
        # --- Seam finding ---
        # Búsqueda de costuras
        seam_finder = cv2.detail_DpSeamFinder("COLOR")
        bleanding_masks = seam_finder.find(images_cropped, corners, valid_region_masks_cropped)

        return images_cropped, bleanding_masks, bboxes_valid_regions, corners

    

    def simple_bleanding(self, images_cropped, bleanding_masks, corners, dom_size):
        print("--- Simple blending ---")
        
        im0_shape = images_cropped[0].shape

        if len(im0_shape) == 3 and im0_shape[-1] == 3:
            result = np.zeros((dom_size[0], dom_size[1], 3), np.float32)
        else:
            result = np.zeros((dom_size[0], dom_size[1]), np.uint8)

        blend_mask_accum = np.zeros((dom_size[0], dom_size[1]), np.float32)
        #i=0

        for i, blend_mask in tqdm(enumerate(bleanding_masks ), "Sub Blending", total = len(bleanding_masks)):
            
            img = images_cropped[i] #img.get() if isinstance(img, cv2.UMat) else img
            blend_mask = blend_mask.get() if isinstance(blend_mask, cv2.UMat) else blend_mask
            h,w = img.shape[:2]
            corner = corners[i]

            blend_mask_f = blend_mask.astype(np.float32) / 255.0

            if result.dtype ==  np.float32:
                result[corner[1]: corner[1] + h, corner[0]: corner[0] + w, :] += img.astype(np.float32) * blend_mask_f[..., None]
            elif result.dtype ==  np.uint8:
                mask = cv2.bitwise_and(img, blend_mask_f.astype(np.uint8))
                result[corner[1]: corner[1] + h, corner[0]: corner[0] + w] += mask

            blend_mask_accum[corner[1]: corner[1] + h, corner[0]: corner[0] + w] += blend_mask_f
            
            #i+=1
        blend_mask_accum[blend_mask_accum == 0] = 1

        if result.dtype ==  np.float32:
            result /= blend_mask_accum[..., None]

        result = np.clip(result, 0, 255).astype(np.uint8)

        final_dom = result.astype(np.uint8)

        return final_dom, blend_mask_accum

    def seam_bleanding_process(self, images, valid_region_masks, dom_size):
        images_cropped, bleanding_masks, bboxes_val_regions, corners = self.find_seam_bleanding(images, valid_region_masks)
        mosaic, _ = self.simple_bleanding(images_cropped, bleanding_masks, corners, dom_size)
        return mosaic, bleanding_masks, bboxes_val_regions, corners
    
    

    def seam_blending_batch(self, subset_images, subset_masks, dom_size, subset_trees_mask = None, save_steps_dir = None):
        print("--- Exposure compensation ---")
        subset_images_warped = []
        #cv2.UMat(img) for img in subset_images]
        subset_masks_warped = []

        subset_trees_warped = []
        #cv2.UMat(mask) for mask in subset_masks]
        corners = []
        #corners = [(0, 0)] * len(subset_images_warped)

        for img, mask, trees in zip(subset_images, subset_masks, subset_trees_mask):
            cropped_img, cropped_mask, cropped_tree_mask, corner = crop_valid_region(img, mask, trees)
            subset_images_warped.append(cropped_img)
            subset_masks_warped.append(cropped_mask)
            subset_trees_warped.append(cropped_tree_mask)
            corners.append(corner)
            
        compensator = cv2.detail.ExposureCompensator_createDefault(
            cv2.detail.ExposureCompensator_GAIN
        )

        compensator.feed(corners, subset_images_warped, subset_masks_warped)
        print("--- Seam finding ---")
        # --- Seam finding ---
        seam_finder = cv2.detail_DpSeamFinder("COLOR")
        masks = seam_finder.find(subset_images_warped, corners, subset_masks_warped)
        print("--- Simple blending ---")

        if save_steps_dir is not None: 
            os.makedirs(save_steps_dir, exist_ok=True)
            os.makedirs(f"{save_steps_dir}/detections", exist_ok=True)
            os.makedirs(f"{save_steps_dir}/blend", exist_ok=True)

        result = np.zeros((dom_size[0], dom_size[1], 3), np.float32)
        mask_accum = np.zeros((dom_size[0], dom_size[1]), np.float32)
        mask_trees_accum = np.zeros((dom_size[0], dom_size[1]), np.uint8)
        
        i=0
        
        for img, mask, corner, t_mask in tqdm(zip(subset_images_warped, masks, corners, subset_trees_warped), "Sub Blending", total = len(subset_images_warped)):
            img = img.get() if isinstance(img, cv2.UMat) else img
            mask = mask.get() if isinstance(mask, cv2.UMat) else mask
            h,w = img.shape[:2]

            mask_f = mask.astype(np.float32)# / 255.0
            result[corner[1]: corner[1] + h, corner[0]: corner[0] + w, :] += img.astype(np.float32) * mask_f[..., None]
            mask_accum[corner[1]: corner[1] + h, corner[0]: corner[0] + w] += mask_f
            
            trees_blended = cv2.bitwise_and(t_mask, t_mask, mask = mask_f.astype(np.uint8))
            mask_trees_accum[corner[1]: corner[1] + h, corner[0]: corner[0] + w] += trees_blended
            #trees_m = trees_bin.astype(np.uint8) * 255
            poly_trees = self.mask_to_polygons(trees_blended, offset_x=corner[0], offset_y=corner[1])
            print("mask:", mask.max())
            if save_steps_dir:
                cv2.imwrite(f"{save_steps_dir}/blend/im_{i+1}.jpg", img)
                cv2.imwrite(f"{save_steps_dir}/blend/mask_blend_{i+1}.jpg", mask.astype(np.uint8) * 255)
                cv2.imwrite(f"{save_steps_dir}/detections/trees_mask{i+1}.jpg", t_mask)
                cv2.imwrite(f"{save_steps_dir}/detections/trees_mask_blended_{i+1}.jpg", trees_blended)
            
                with open(f"{save_steps_dir}/blend/corners_{i+1}.json", "w") as f:
                    json.dump([[int(corner[0]), int(corner[1])], [w, h]],f, indent=4)

                with open(f"{save_steps_dir}/detections/poly_trees_{i+1}.json", "w") as f:
                    json.dump(poly_trees,f, indent=4)
            i+=1

        mask_trees_accum[mask_trees_accum > 0] = 255

        mask_accum[mask_accum == 0] = 1
        result /= mask_accum[..., None]
        result = np.clip(result, 0, 255).astype(np.uint8)

        final_dom = result.astype(np.uint8)

        return final_dom, mask_accum, mask_trees_accum



    def averge_images(self, images_warped):
        accum = np.zeros_like(images_warped[0], dtype=np.float32)
        count = np.zeros_like(images_warped[0], dtype=np.float32)

        for img in images_warped:
            mask = (img > 0)    # o un threshold más fino
            accum += img * mask
            count += mask

        im_average = accum / np.maximum(count, 1)
        im_average = im_average.astype(np.uint8)

        return im_average

    def generate_mosaic_rgb_batch(self, images_data, global_transforms, dom_size, batch_id = 0):
        
        valid_region_masks = []
        images_warped = []
        
        for metadata, H_init in zip(images_data, global_transforms):
            image = cv2.imread(metadata['relative_path'])
            image_distortion = undistort_with_meta(image, metadata)
            H_rtk = metadata['H_rtk']
            H_global = H_init @ H_rtk
            img_warped, _, valid_region_mask = direct_project_image_to_dom(image_distortion, H_global, dom_size, get_valid_region=True)
            img_warped = img_warped.astype(np.uint8)
            valid_region_mask = valid_region_mask.astype(np.uint8)
            images_warped.append(img_warped)
            valid_region_masks.append(valid_region_mask)
        
          

        print("Save Averege")
        im_average = self.averge_images(images_warped) #np.mean(images_warped, axis=0).astype(np.uint8)
        os.makedirs(f"{self.result_dir}/mosaic/rgb", exist_ok=True)
        cv2.imwrite(f"{self.result_dir}/mosaic/rgb/averge_path_img_{batch_id}.png",im_average)

        mosaic, bleanding_masks, bboxes_val_regions, corners = self.seam_bleanding_process(images_warped, valid_region_masks, dom_size)
        
        cv2.imwrite(f"{self.result_dir}/mosaic/rgb/blending/bleanding_patch_img_{batch_id}.png", mosaic)

        return mosaic, bleanding_masks, bboxes_val_regions, corners

    def generate_ndvi_image(self, red_file_metadata, nir_file_metadata):
        red_path = red_file_metadata['relative_path']
        red_basename = os.path.basename(red_path)
        nir_path = nir_file_metadata['relative_path']
        rgb_path = red_path.replace("_MS_R.TIF", "_D.JPG")

        print("nir_path:", nir_path)
        print("red_path:", red_path)
        print("rgb_path:", rgb_path)

        nir_corr, mn = per_band_pipeline(nir_path, nir_file_metadata)
        red_corr, mr = per_band_pipeline(red_path, red_file_metadata)

        if red_corr is None or nir_corr is None:
                print(f"Error al cargar imagenes: {red_path} o {nir_path}")

        if red_corr.shape != nir_corr.shape:
                    print(f"Las imagenes tienen dimensione distintas {red_basename}: rojo {red_corr.shape}, nir {nir_corr.shape}. Saltando al siguiente.")
                    
        # Convert each band to reflectance (Eq. 4–6 use Irradiance already as LS*pLS)
        nir_ref = compute_reflectance(nir_corr, mn)
        red_ref = compute_reflectance(red_corr, mr)

        # NDVI (Eq. 6)
        eps = 1e-12
        ndvi = (nir_ref - red_ref) / (nir_ref + red_ref + eps)
        ndvi = np.clip(ndvi, -1.0, 1.0).astype(np.float32)
        colored_ndvi = modern_ldp_ndvi_colormap(ndvi)
        # Aligned to RGB designed plane
        aligned_ndvi = ndvi_to_drgb(colored_ndvi, rgb_path, red_file_metadata['H_dewarp'])
        return aligned_ndvi

    def calculate_average_ndvi(self, corner, tree_mask, img_path, all_files_metadata):

        nir_basename = os.path.basename(img_path.replace("_D.JPG", "_MS_NIR.TIF"))
        red_basename = os.path.basename(img_path.replace("_D.JPG", "_MS_R.TIF"))
        nir_file_metadata = all_files_metadata.get(nir_basename, None)
        red_file_metadata = all_files_metadata.get(red_basename, None)
        
        red_path = red_file_metadata['relative_path']
        red_basename = os.path.basename(red_path)
        nir_path = nir_file_metadata['relative_path']

        nir_corr, mn = per_band_pipeline(nir_path, nir_file_metadata)
        red_corr, mr = per_band_pipeline(red_path, red_file_metadata)

        if red_corr is None or nir_corr is None:
                print(f"Error al cargar imagenes: {red_path} o {nir_path}")

        if red_corr.shape != nir_corr.shape:
                    print(f"Las imagenes tienen dimensione distintas {red_basename}: rojo {red_corr.shape}, nir {nir_corr.shape}. Saltando al siguiente.")
                    
        # Convert each band to reflectance (Eq. 4–6 use Irradiance already as LS*pLS)
        nir_ref = compute_reflectance(nir_corr, mn)
        red_ref = compute_reflectance(red_corr, mr)

        # NDVI (Eq. 6)
        eps = 1e-12
        ndvi = (nir_ref - red_ref) / (nir_ref + red_ref + eps)
        ndvi = np.clip(ndvi, -1.0, 1.0).astype(np.float32)
        colored_ndvi = modern_ldp_ndvi_colormap(ndvi)
        aligned_ndvi = ndvi_to_drgb(ndvi, img_path, red_file_metadata['H_dewarp'])

        x_min, y_min = corner
        h, w = tree_mask.shape
        x_max = x_min + w + 1
        y_max = y_min + h + 1
        tree_ndvi = aligned_ndvi[y_min: y_max, x_min: x_max]

        return float(tree_ndvi[tree_ndvi > 0.50].mean())


    def generate_mosaic_ndvi_batch(self, metadata_rgb_images, global_transforms, bboxes_val_regions, bleanding_masks, corners, all_metadata, dom_size):
        ndvi_warped = []
        
        for metadata_rgb, H_init in zip(metadata_rgb_images, global_transforms):
            img_path = metadata_rgb['relative_path']
            H_rtk = metadata_rgb['H_rtk']
            H_global = H_init @ H_rtk
            ## Calcule ndvi
            nir_basename = os.path.basename(img_path.replace("_D.JPG", "_MS_NIR.TIF"))
            red_basename = os.path.basename(img_path.replace("_D.JPG", "_MS_R.TIF"))
            print("red_basename:", red_basename)
            print("nir_basename:", nir_basename)
            nir_file_metadata = all_metadata.get(nir_basename, None)
            red_file_metadata = all_metadata.get(red_basename, None)
            aligned_ndvi = self.generate_ndvi_image(red_file_metadata, nir_file_metadata)

            aligned_ndvi_warped = cv2.warpPerspective(
                        aligned_ndvi,
                        H_global,
                        (int(dom_size[1]), int(dom_size[0])),
                        flags=cv2.INTER_LANCZOS4  # Interpolación de alta calidad
            )

            ndvi_warped.append(aligned_ndvi_warped)

        
        ## Bleanding Ndvi images
        ndvi_cropped = [crop_image(ndvi, bbox) for ndvi, bbox in zip(ndvi_warped, bboxes_val_regions)]
        ndvi_dom, _ = self.simple_bleanding(ndvi_cropped, bleanding_masks, corners, dom_size)
        return ndvi_dom
    
    def create_mosaic_rgb_and_layers(self, metadata_rgb_images, global_transforms, all_files_metadata, dom_size, save_dir_logs = "./blending"):
        n_images = len(metadata_rgb_images)
        print("n_images:", n_images)
        batch_size = 30
        n_batches = n_images // batch_size + (1 if n_images % batch_size > 0 else 0)
        
        images_warped = []
        ndvi_images_warped = []
        valid_region_masks_warped = []

        first_level_bleanding_masks = []
        first_level_bboxes_val_regions = []
        first_level_corners = []

        for i in range(n_batches):
            start, end = batch_size * i, min(batch_size* (i+1), n_images)
            mosaic_patch, bleanding_masks, bboxes_val_regions, corners = self.generate_mosaic_rgb_batch(metadata_rgb_images[start:end], 
                                                                                                        global_transforms[start:end], 
                                                                                                        dom_size,
                                                                                                        i)
            
            valid_region = (mosaic_patch.sum(axis=2) > 0).astype(np.uint8) * 255
            valid_region = valid_region.astype(np.uint8)

            ndvi_patch = self.generate_mosaic_ndvi_batch(metadata_rgb_images[start:end], 
                                                         global_transforms, 
                                                         bboxes_val_regions, 
                                                         bleanding_masks, 
                                                         corners, 
                                                         all_files_metadata, 
                                                         dom_size)
            images_warped.append(mosaic_patch)
            ndvi_images_warped.append(ndvi_patch)
            valid_region_masks_warped.append(valid_region)

            first_level_bleanding_masks.extend(bleanding_masks)
            first_level_bboxes_val_regions.extend(bboxes_val_regions)
            first_level_corners.extend(corners)

        if len(images_warped) > 1:
            #im_average = np.mean(images_warped, axis=0).astype(np.uint8)
            im_average = self.averge_images(images_warped)
            cv2.imwrite(f"{self.result_dir}/mosaic/rgb/averge_path_img_second_level.png",im_average)
            final_mosaic, bleanding_masks, bboxes_val_regions, corners = self.seam_bleanding_process(images_warped, valid_region_masks_warped, dom_size)

            ## Bleanding Ndvi images
            ndvi_cropped = [crop_image(ndvi, bbox) for ndvi, bbox in zip(ndvi_images_warped, bboxes_val_regions)]
            final_ndvi, _ = self.simple_bleanding(ndvi_cropped, bleanding_masks, corners, dom_size)

            if not self.check_continue_procress():
                return
        else:
            final_mosaic = images_warped[0]
            final_ndvi = ndvi_images_warped[0]

        
        return final_mosaic, final_ndvi, first_level_bleanding_masks, first_level_bboxes_val_regions, first_level_corners


    def create_mosaic_batch_seam_blending(self, all_list_images_data, global_transforms, dom_size, save_dir_logs = "./blending"):
        n_images = len(all_list_images_data)
        print("n_images:", n_images)
        images_warped = []
        masks_warped = []
        trees_warped = []
        batch_size = 30
        n_batches = n_images // batch_size + (1 if n_images % batch_size > 0 else 0)

        print("n_batches:",n_batches)
        for i in range(n_batches):
            subset_images = []
            subset_masks = []
            subset_trees_mask = []
            save_steps_dir = f"{save_dir_logs}/seam_batch_{i+1}"

            for j in range(batch_size * i, min(batch_size* (i+1), n_images)):
                row = all_list_images_data[j]
                image = cv2.imread(row['relative_path'])
                image_distortion = undistort_with_meta(image, row)
                H_rtk = row['H_rtk']
                H_global = global_transforms[j] @ H_rtk
                terrain_points_dom = row['terrain_points_dom']
                imagen_proyectada, mask = direct_project_image_to_dom(image_distortion, H_global, dom_size, terrain_points_dom)
                
                imagen_proyectada = imagen_proyectada.astype(np.uint8)
                mask = mask.astype(np.uint8)
                detect_path = row['detections_path']
                mask_trees = self.read_trees_mask(detect_path, (image_distortion.shape[0],image_distortion.shape[1]))
                
                mask_trees_proyectada = cv2.warpPerspective(
                            mask_trees,
                            H_global,
                            (int(dom_size[1]), int(dom_size[0])),
                            flags=cv2.INTER_LANCZOS4  # Interpolación de alta calidad
                )

                subset_images.append(imagen_proyectada)
                subset_masks.append(mask)
                subset_trees_mask.append(mask_trees_proyectada)

            patch_dom, patch_mask, patch_mask_trees = self.seam_blending_batch(subset_images, subset_masks, dom_size, subset_trees_mask, save_steps_dir)
            patch_mask = (patch_dom.sum(axis=2) > 0).astype(np.uint8) * 255
            patch_mask = patch_mask.astype(np.uint8)

            images_warped.append(patch_dom)
            masks_warped.append(patch_mask)
            trees_warped.append(patch_mask_trees)
            if not self.check_continue_procress():
                return
            self.progress_update(40 + (50 * i) // (batch_size + 1))
        
        save_steps_dir = f"{save_dir_logs}/seam_batch_final"

        if len(images_warped) > 1:
            final_dom, final_mask, final_trees = self.seam_blending_batch(images_warped, masks_warped, dom_size, trees_warped, save_steps_dir)
            if not self.check_continue_procress():
                return
        else:
            final_dom = images_warped[0]
            final_mask = masks_warped[0]
            final_trees = trees_warped[0]
        
        return final_dom, final_trees

    def read_trees_mask(self, detect_path, im_shape):
        with open(detect_path, "r") as f:
            detecctions = json.load(f)
        
        detecctions = detecctions['detecctions']

        segmentations = detecctions['segmentations']
        mask_trees = np.zeros(im_shape, dtype=np.uint8)
        contours = [np.array(seg, dtype=np.int32).reshape((-1,1,2)) for seg in segmentations]
        mask_trees = cv2.drawContours(mask_trees, contours, -1, 255, -1)
        return mask_trees
    
    def _generate_single_zoom_tiles(self, input_raster, output_dir, tile_size):
        """
        Función interna para generar tiles de un solo nivel de zoom con transparencia.
        """
        os.makedirs(output_dir, exist_ok=True)
        ds = gdal.Open(input_raster)
        if ds is None:
            raise ValueError(f"No se pudo abrir el archivo: {input_raster}")

        # Obtener metadatos
        geotransform = ds.GetGeoTransform()
        projection = ds.GetProjection()
        width = ds.RasterXSize
        height = ds.RasterYSize
        bands = ds.RasterCount
        data_type = ds.GetRasterBand(1).DataType

        driver = gdal.GetDriverByName('GTiff')
        
        for y in range(0, height, tile_size):
            for x in range(0, width, tile_size):
                tile_width = min(tile_size, width - x)
                tile_height = min(tile_size, height - y)
                
                # Calcular nueva geotransform
                new_geotransform = (
                    geotransform[0] + x * geotransform[1],
                    geotransform[1],
                    geotransform[2],
                    geotransform[3] + y * geotransform[5],
                    geotransform[4],
                    geotransform[5]
                )
                
                output_path = os.path.join(output_dir, f"tile_{x}_{y}.tif")
                
                # Crear archivo de salida con opciones para transparencia
                creation_options = []
                if bands == 4:
                    creation_options = ['PHOTOMETRIC=RGB', 'ALPHA=YES']
                
                out_ds = driver.Create(
                    output_path,
                    tile_width,
                    tile_height,
                    bands,
                    data_type,
                    options=creation_options
                )
                
                if out_ds is None:
                    print(f"Error al crear: {output_path}")
                    continue
                
                out_ds.SetGeoTransform(new_geotransform)
                out_ds.SetProjection(projection)
                
                # Copiar todas las bandas
                for b in range(1, bands + 1):
                    band_data = ds.GetRasterBand(b).ReadAsArray(x, y, tile_width, tile_height)
                    out_band = out_ds.GetRasterBand(b)
                    out_band.WriteArray(band_data)
                    
                    # Configurar banda alpha si es la cuarta banda
                    if bands == 4 and b == 4:
                        out_band.SetColorInterpretation(gdal.GCI_AlphaBand)
                
                out_ds.FlushCache()
                out_ds = None

        ds = None

    def init_global_transforms(self, H_abs, metadata_rgb_images):
        H_abs_global = [H_i @ meta['H_rtk'] for H_i, meta in zip(H_abs, metadata_rgb_images)]
        return H_abs_global

    
    def save_unique_detections(self, unique_detects_trees, metadata_rgb_images, dir_base):
        dir_results_detections = f"{dir_base}/results/unique_trees_detections/masks"
        
        os.makedirs(dir_results_detections, exist_ok=True)
        unique_trees_results = []
        
        for i in range(len(unique_detects_trees)):
            # Obtener Mascara
            (im_idx, tree_id), _, poly = unique_detects_trees[i]
            contour = np.array(poly, dtype=np.int32).reshape(-1,2)    
            print("contour:", contour.shape)
            x_min, y_min, x_max, y_max = bbox(contour)
            x_min, y_min = np.floor(x_min), np.floor(y_min)
            x_max, y_max = np.ceil(x_max), np.ceil(y_max)
            x_min, y_min, x_max, y_max = int(x_min), int(y_min), int(x_max), int(y_max)

            # tamaño de la máscara final
            w = int(x_max - x_min) + 1
            h = int(y_max - y_min) + 1

            # Trasladar contorno para que empiece en (0,0)
            
            contour_translated = contour - np.array([x_min, y_min])
            contour_translated = np.clip(contour_translated, 0, None)
            contour_translated = np.array(contour_translated, dtype=np.int32).reshape(-1, 1, 2)

            print()
            image_metadata = metadata_rgb_images[im_idx]
            img_path = image_metadata['relative_path']
            basename = os.path.basename(img_path)[:-4]
            mask_path = f"{dir_base}/results/unique_trees_detections/masks/{basename}_tree_{x_min}_{y_min}.png"
            unique_trees_results.append({
                "id_img": im_idx,
                "tree_idx": tree_id,
                "img_path": img_path,
                "segmentation": poly,
                "corner": [x_min, y_min],
                "mask_cropped_path": mask_path
            })

            mask = np.zeros((h, w), dtype=np.uint8)

            cv2.drawContours(mask, [contour_translated], -1, 255, -1)
            cv2.imwrite(mask_path, mask)

        
        unique_trees_info = [dict(img_path = r['img_path'], corner = r['corner'], mask_cropped_path = r['mask_cropped_path']) for r in unique_trees_results]
        
        with open(f"{dir_base}/results/unique_trees_detections/unique_detections.json", 'w') as f:
            json.dump(unique_trees_info, f, indent=2)

        return unique_trees_results

    def apply_diagnosis_process(self, trees_detections, all_images_metadada_dict):
        clases = ["saludable","deficiencia"]
        # calculate_average_ndvi(self, corner, tree_mask, img_path, all_files_metadata)
        # magic_function = lambda mask, corner, img_path: (random.choices([0, 1], weights=[0.7, 0.3])[0], self.calculate_average_ndvi(corner, mask, img_path, all_images_metadada_dict))
        trees_diagnosis_results = copy.deepcopy(trees_detections)
        
        for i in range(len(trees_detections)):
            detection_result = trees_detections[i]
            img_path = detection_result["img_path"]
            mask_cropped_path = detection_result["mask_cropped_path"]
            mask = cv2.imread(mask_cropped_path)
            mask = mask.astype(np.uint8)
            
            if mask.ndim == 3 and mask.shape[-1] > 1:
                mask = cv2.cvtColor(mask, cv2.COLOR_BGR2GRAY)

            if mask.shape[-1] == 1:
                mask = mask.squeeze()

            corner = detection_result["corner"]
            #class_id, avg_ndvi = magic_function(mask, corner, img_path)

            prediction, hypercube = NitrogenDefClassifer.build_cube_and_predict(
                rgb_path=img_path,
                mask_tree= mask,
                corner = corner,
                all_metadata_images=all_images_metadada_dict
            )
            print("prediction:", prediction)
            print("hypercube:", hypercube.shape)
            ndvi = hypercube[4,:,:]
            avg_ndvi = ndvi[ndvi >= 0.3].mean()
            mcari_avg = hypercube[-1,:,:][ndvi >= 0.3].mean()

            print("avg_ndvi:", avg_ndvi)
            print("mcari_avg:", mcari_avg)
            class_name = clases[prediction]

            trees_diagnosis_results[i]["diagnosis_class"] = class_name
            trees_diagnosis_results[i]["avg_ndvi"] = float(avg_ndvi)
            trees_diagnosis_results[i]["mcari_avg"] = float(mcari_avg)
        
        return trees_diagnosis_results

    def save_trees_masks_mosaic(self, 
                                H_abs_global, 
                                unique_trees_results, 
                                same_detects_graph,
                                first_level_bleanding_masks, first_level_bboxes_val_regions, first_level_corners,
                                dom_size,
                                dir_base):
        
        dir_trees = f"{dir_base}/mosaic/trees/masks"
        os.makedirs(dir_trees, exist_ok=True)
        
        
        trees_results = []

        for i in range(len(unique_trees_results)):
            detection_result = unique_trees_results[i]
            poly = detection_result["segmentation"]
            im_idx = detection_result["id_img"]
            tree_idx = detection_result['tree_idx']
            key_id = f"I{im_idx}-T{tree_idx}"

            same_detects = same_detects_graph[key_id]

            masks_cropped = []
            bleanding_masks = []
            corners = []
            for detect in same_detects:
                (im_j, _),_,_,_, seg = detect
                poly_img_j = seg_pts_to_dom([seg], H_abs_global[im_j])[0]
                poly_img_j = poly_img_j.reshape(-1, 1, 2)
                poly_img_j = np.array(poly_img_j, dtype=np.int32)
                print("poly_img_j:", poly_img_j.shape)
                mask_j = np.zeros(dom_size, dtype=np.uint8)
                cv2.drawContours(mask_j, [poly_img_j], -1, 255, -1)

                # plt.imshow(mask_j)
                # plt.title(f"Tree - im - {i} - {im_j}")
                # plt.show()
                bbox_val = first_level_bboxes_val_regions[im_j]
                corner_j = first_level_corners[im_j]
                bleanding_mask_j = first_level_bleanding_masks[im_j]
                mask_j_cropped = crop_image(mask_j, bbox_val)

              

                masks_cropped.append(mask_j_cropped)
                bleanding_masks.append(bleanding_mask_j)
                corners.append(corner_j)
                
                #ndvi_cropped = [crop_image(ndvi, bbox) for ndvi, bbox in zip(ndvi_images_warped, bboxes_val_regions)]
            #[(j,v), dist_to_centers_j[v], iou, poly_j_v, filtered_segmentations_j[v]]

            
            mask_tree_blended, _ = self.simple_bleanding(masks_cropped, bleanding_masks, corners, dom_size)
            
            print("mask_tree_blended.max()", mask_tree_blended.max())
            # plt.imshow(mask_tree_blended)
            # plt.title(f"mask_tree_blended Tree - im - {i} ")
            # plt.show()

            if mask_tree_blended.max() > 0:
                mask_tree_cropped, corner = crop_valid_region_mask(mask_tree_blended)
                #mask_tree_cropped = mask_tree_cropped * 255
                mask_tree_cropped = mask_tree_cropped.astype(np.uint8)

                      # --- A) Cierre: une regiones próximas ---
                kernel = np.ones((7, 7), np.uint8)
                #closed = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

                # --- B) Apertura: elimina fragmentos pequeños ---
                opened = cv2.morphologyEx(mask_tree_cropped, cv2.MORPH_OPEN, kernel, 1)
                closed = cv2.morphologyEx(opened, cv2.MORPH_CLOSE, kernel,1)

                contours_new, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

                if contours_new and len(contours_new) > 0:
                    # 3. Elegir el contorno más grande por área
                    contours_new = max(contours_new, key=cv2.contourArea)

                    
                    mask_tree_cropped = np.zeros(mask_tree_cropped.shape, dtype=np.uint8)
                    cv2.drawContours(mask_tree_cropped, [contours_new], -1, 255, -1)

                    print("mask_tree_cropped.max()", mask_tree_cropped.max())
                    print("mask_tree_cropped,type:", mask_tree_cropped.dtype)
                    # plt.imshow(mask_tree_cropped)
                    # plt.title(f"mask_tree_cropped Tree - im - {i} ")
                    # plt.show()
                    
                    x_min, y_min = corner
                    h, w = mask_tree_cropped.shape
                    x_max, y_max = x_min + w, y_min + h
                    
                    tree_bbox = [int(x_min), int(y_min), int(x_max), int(y_max)]
                else:
                    print("contours_new:", contours_new)
                    continue
            else:
                poly_dom = seg_pts_to_dom([poly], H_abs_global[im_idx])[0]
                x_min, y_min, x_max, y_max = bbox(poly_dom)
                x_min, y_min = np.floor(x_min), np.floor(y_min)
                x_max, y_max = np.ceil(x_max), np.ceil(y_max)
                print("x_min, y_min, x_max, y_max", (x_min, y_min, x_max, y_max))
                contour = np.array(poly_dom, dtype=np.int32)
                print("contour:", contour.shape)
                # Trasladar contorno para que empiece en (0,0)
                contour_translated = contour - np.array([x_min, y_min])
                contour_translated = np.clip(contour_translated, 0, None)
                contour_translated = np.array(contour_translated, dtype=np.int32).reshape(-1, 1, 2)
                
                # tamaño de la máscara final
                w = int(x_max - x_min) + 1
                h = int(y_max - y_min) + 1
                print("(h, w):", (h, w))
                # Crear máscara binaria vacía
            
                # Dibujar el contorno en coordenadas normalizadas
            
                x_min, y_min, x_max, y_max = int(x_min), int(y_min), int(x_max), int(y_max)
                mask_tree_cropped = np.zeros((h, w), dtype=np.uint8)
                cv2.drawContours(mask_tree_cropped, [contour_translated], -1, 255, -1)
                corner = [x_min, y_min]
                tree_bbox = [x_min, y_min, x_max, y_max]

            
            #np.save(f"{dir_trees}/tree_{x_min}_{y_min}.npy", contour_translated)
           
            x_min_f = corner[0]
            y_min_f = corner[1]

            path_mask = f"{dir_trees}/tree_{x_min_f}_{y_min_f}.png"
            print("mosaic trees path_mask:", path_mask)
            cv2.imwrite(path_mask, mask_tree_cropped)

            diagnosis_class = detection_result["diagnosis_class"]
            avg_ndvi = detection_result["avg_ndvi"]
            mcari_avg = detection_result["mcari_avg"]
            
            trees_results.append({
                "id": i,
                "bbox": tree_bbox,
                "mask_path": path_mask,
                "seg_path": f"{dir_trees}/tree_{x_min}_{y_min}.npy",
                "class": diagnosis_class,
                "avg_ndvi": avg_ndvi,
                "mcari_avg" : mcari_avg
            })

        ## Ordenar y creaar ids
        final_trees_results = []
        sorted_trees_resultas = sorted(trees_results, key = lambda x: x["bbox"][0] + x["bbox"][1])
        
        first_tree = sorted_trees_resultas.pop(0)
        i = 1
        first_tree['id'] = i
        first_tree["name"] = f"ARBOL-{i:03d}"
        final_trees_results.append(first_tree)
        
        trees_results_temp = copy.deepcopy(sorted_trees_resultas)
        current_tree_x = first_tree["bbox"][0]
        i = 2
        
        while len(trees_results_temp) > 0:
            sorted_trees_results_temp = sorted(trees_results_temp, key = lambda x: abs(x["bbox"][0] - current_tree_x) + 2* x["bbox"][1])
            next_tree = sorted_trees_results_temp.pop(0)
            trees_results_temp = sorted_trees_results_temp
            current_tree_x = next_tree["bbox"][0]
            next_tree['id'] = i
            next_tree["name"] = f"ARBOL-{i:03d}"
            final_trees_results.append(next_tree)
            i+=1
       
        ## guardar info

        with open(f"{dir_base}/mosaic/trees/trees_results.json", "w") as fp:
            json.dump(final_trees_results, fp, indent=4)


    def save_unique_trees_masks(self, H_abs_global, unique_detects_trees, dir_base):
        
        dir_trees = f"{dir_base}/mosaic/trees/masks"
        os.makedirs(dir_trees, exist_ok=True)
        
        clases = ["saludable", "deficiencia"]
        trees_results = []

        for i in range(len(unique_detects_trees)):
            (im_idx, tree_id), _, poly = unique_detects_trees[i]
            print()
            poly_dom = seg_pts_to_dom([poly], H_abs_global[im_idx])[0]
            x_min, y_min, x_max, y_max = bbox(poly_dom)
            x_min, y_min = np.floor(x_min), np.floor(y_min)
            x_max, y_max = np.ceil(x_max), np.ceil(y_max)
            print("x_min, y_min, x_max, y_max", (x_min, y_min, x_max, y_max))
            contour = np.array(poly_dom, dtype=np.int32)
            print("contour:", contour.shape)
            # Trasladar contorno para que empiece en (0,0)
            contour_translated = contour - np.array([x_min, y_min])
            contour_translated = np.clip(contour_translated, 0, None)
            contour_translated = np.array(contour_translated, dtype=np.int32).reshape(-1, 1, 2)
            
            print("contour_translated:", contour_translated)
            # tamaño de la máscara final
            w = int(x_max - x_min) + 1
            h = int(y_max - y_min) + 1
            print("(h, w):", (h, w))
            # Crear máscara binaria vacía
           
            # Dibujar el contorno en coordenadas normalizadas
           
            x_min, y_min, x_max, y_max = int(x_min), int(y_min), int(x_max), int(y_max)
            np.save(f"{dir_trees}/tree_{x_min}_{y_min}.npy", contour_translated)

            mask = np.zeros((h, w), dtype=np.uint8)
            cv2.drawContours(mask, [contour_translated], -1, 255, -1)
            path_mask = f"{dir_trees}/tree_{x_min}_{y_min}.png"
            cv2.imwrite(path_mask, mask)

            tree_bbox = [x_min, y_min, x_max, y_max]

            trees_results.append({
                "id": i,
                "bbox": tree_bbox,
                "mask_path": f"{dir_trees}/tree_{x_min}_{y_min}.png",
                "seg_path": f"{dir_trees}/tree_{x_min}_{y_min}.npy",
                "class": clases[random.choices([0,1], weights=[0.7, 0.3])[0]],
                "avg_ndvi": random.uniform(0.75, 1.0)
            })

        ## Ordenar y creaar ids
        final_trees_results = []
        sorted_trees_resultas = sorted(trees_results, key = lambda x: x["bbox"][0] + x["bbox"][1])
        
        first_tree = sorted_trees_resultas.pop(0)
        i = 1
        first_tree['id'] = i
        first_tree["name"] = f"ARBOL-{i:03d}"
        final_trees_results.append(first_tree)
        
        trees_results_temp = copy.deepcopy(sorted_trees_resultas)
        current_tree_x = first_tree["bbox"][0]
        i = 2
        while len(trees_results_temp) > 0:
            sorted_trees_results_temp = sorted(trees_results_temp, key = lambda x: abs(x["bbox"][0] - current_tree_x) + 2* x["bbox"][1])
            next_tree = sorted_trees_results_temp.pop(0)
            trees_results_temp = sorted_trees_results_temp
            current_tree_x = next_tree["bbox"][0]
            next_tree['id'] = i
            next_tree["name"] = f"ARBOL-{i:03d}"
            final_trees_results.append(next_tree)
            i+=1
       
        ## guardar info


        with open(f"{dir_base}/mosaic/trees/trees_results.json", "w") as fp:
            json.dump(final_trees_results, fp, indent=4) 
        

    def run(self, 
            name_file = None, 
            prefix_name = None,
            detector_keypoints = "SIFT",
            type_align_matrix = "affine"):
        
        self.is_running = True
        
        metadata_rgb_images = [img_m for img_m in self.images_data if "_D.JPG" in img_m['relative_path']]
        
        metadata_rgb_images = metadata_rgb_images

        all_images_metadada_dict = {img_m['name']:img_m for img_m in self.images_data}

        n_images = len(metadata_rgb_images)
        print("Comienza process_calculate_camera_pose")
        metadata_rgb_images = self.process_calculate_camera_pose(metadata_rgb_images)
        self.progress_update(2)
        
        if not self.check_continue_procress():
            return
        
        print("Comienza process_terrain_points")
        metadata_rgb_images = self.process_terrain_points(metadata_rgb_images)
        if not self.check_continue_procress():
                return
        
        self.progress_update(4)
        print("Comienza estimate_dom_parameters")
        dom_bounds, dom_resolution = self.estimate_dom_parameters(metadata_rgb_images, margin_extension = 0.1)
        if not self.check_continue_procress():
                return
        self.progress_update(6)

        width_m = dom_bounds[1] - dom_bounds[0]
        height_m = dom_bounds[3] - dom_bounds[2]
        width_px = int(width_m / dom_resolution)
        height_px = int(height_m / dom_resolution)
        dom_size = (height_px, width_px)
        print("Comienza process_project_corners_to_dom")
        metadata_rgb_images = self.process_project_corners_to_dom(metadata_rgb_images, dom_bounds, dom_resolution)
        if not self.check_continue_procress():
                return
        self.progress_update(8)
        
        print("Comienza process_detect_keypoint_descriptors_in_dom")
        metadata_rgb_images = self.process_detect_keypoint_descriptors_in_dom(metadata_rgb_images, dom_size, detector_keypoints)
        
        if not self.check_continue_procress():
                return
        
        self.progress_update(20)
        print("Comienza calculate_pairwase_matches")
        
        all_terrain_points_dom = [d['terrain_points_dom'] for d in metadata_rgb_images]

        # 2. Construir grafo de solapamiento
        overlap_graph  = build_overlap_graph(all_terrain_points_dom, min_overlap=0.45)
        # 5) Grafo y MST (Prim). Ruta de propacion
        edges = estimate_pairwase_homographies(overlap_graph, metadata_rgb_images, type_align_matrix)

        adj_graph = build_adjacency_graph_from_edges(n_images, edges)

        mst = prim_mst(n_images, adj_graph)
        # 6) Inicialización H absolute vía propagación en MST
        H_abs = initialize_homographies(n_images, mst)
        if not self.check_continue_procress():
            return
        self.progress_update(40)
        
        final_mosaic, final_ndvi, first_level_bleanding_masks, first_level_bboxes_val_regions, first_level_corners = self.create_mosaic_rgb_and_layers(
            metadata_rgb_images,
            H_abs,
            all_images_metadada_dict,
            dom_size=(height_px, width_px),
            save_dir_logs=f"{self.result_dir}/mosaic/blending")

        #final_dom, trees_mask = self.create_mosaic_batch_seam_blending(
        #    metadata_rgb_images,
        #      H_abs, 
        #      dom_size=(height_px, width_px),
        #      save_dir_logs=f"{self.result_dir}/mosaic/blending")

        
        print("Comienza transformations")
        
        if not self.check_continue_procress():
                return
        
        self.progress_update(90)
        ref_zone_lon = self.images_data[0]['longitude']
        
        if name_file is None:
            name_file = datetime.now().strftime("%Y%m%d_%H%M%S") + ".tif"
            if prefix_name is not None:
                name_file = prefix_name + ".tif"
            else:
                name_file = prefix_name + "_" + name_file if prefix_name else name_file
        
        os.makedirs(f"{self.result_dir}/mosaic", exist_ok=True)

        
        print("--------------Guardar Mosaic RGB-----------------")
        print("--------------Dividiendo en tiles-----------------")
        os.makedirs(f"{self.result_dir}/mosaic/rgb", exist_ok=True)
        mosaic_path = f"{self.result_dir}/mosaic/rgb/mosaic_{name_file}"
        self.save_as_geotiff(
                final_mosaic, 
                mosaic_path, 
                dom_bounds[0], dom_bounds[3],  # Esquina superior izquierda (X,Y)
                dom_resolution,
                ref_zone_lon
        )
        
        if not self.check_continue_procress():
            return

        self._generate_single_zoom_tiles(
            input_raster = mosaic_path, 
            output_dir = f"{self.result_dir}/mosaic/rgb/tiles", 
            tile_size = 256)
        
        print("--------------Guardar NDVI Mosaic-----------------")
        print("--------------Dividiendo en tiles-----------------")

        os.makedirs(f"{self.result_dir}/mosaic/ndvi", exist_ok=True)
        ndvi_path = f"{self.result_dir}/mosaic/ndvi/ndvi_{name_file}"

        self.save_as_geotiff(
                cv2.cvtColor(final_ndvi, cv2.COLOR_BGR2RGB), 
                ndvi_path, 
                dom_bounds[0], dom_bounds[3],  # Esquina superior izquierda (X,Y)
                dom_resolution,
                ref_zone_lon
        )

        if not self.check_continue_procress():
            return

        self._generate_single_zoom_tiles(
            input_raster = ndvi_path, 
            output_dir = f"{self.result_dir}/mosaic/ndvi/tiles", 
            tile_size = 256)
        

        print("--------------Detectando Arboles Individiales-----------------")

        H_abs_global = self.init_global_transforms(H_abs, metadata_rgb_images)
        same_detects_graph = match_sames_detects(adj_graph, metadata_rgb_images, dom_size=(height_px, width_px))
        unique_detects_trees = reduce_unique_detections(same_detects_graph)
        print("Arboles detectados:", len(unique_detects_trees))
        # 

        unique_trees_results = self.save_unique_detections(unique_detects_trees, metadata_rgb_images, self.result_dir)
        print("--------------Procesando Diagnostico por imagenes-----------------")
        
        #NitrogenDefClassifer.configure("./best_resnet18_6ch.pth")
        
        trees_diagnosis_results = self.apply_diagnosis_process(unique_trees_results, all_images_metadada_dict)
        print("--------------Guardando Arboles en Mosaico-----------------")
        self.save_trees_masks_mosaic(H_abs_global, 
                                     trees_diagnosis_results,
                                     same_detects_graph,
                                     first_level_bleanding_masks, first_level_bboxes_val_regions, first_level_corners,
                                     (height_px, width_px),
                                     self.result_dir)
        

        # NDVI mean distribution
        
        healthy_count_ndvi = 0
        warning_count_ndvi = 0
        possible_problem_count_ndvi = 0
        critical_problem_count_ndvi = 0

        for tree_result in trees_diagnosis_results:
            if tree_result["avg_ndvi"] > 0.70:
                healthy_count_ndvi += 1
            elif tree_result["avg_ndvi"] > 0.55:
                warning_count_ndvi += 1
            elif tree_result["avg_ndvi"] > 0.40:
                possible_problem_count_ndvi += 1
            else:
                critical_problem_count_ndvi += 1


        # MACARI mean distribution
        
        healthy_count_mcari = 0
        warning_count_mcari = 0
        critical_problem_count_mcari = 0

        for tree_result in trees_diagnosis_results:
            if tree_result["mcari_avg"] > 0.1:
                healthy_count_mcari += 1
            elif tree_result["mcari_avg"] > 0.07:
                warning_count_mcari += 1
            else:
                critical_problem_count_mcari += 1

        # Crear una máscara: True donde algún canal NO es cero
        mask_region = np.any(final_mosaic != 0, axis=2)

        # Crear canal alfa: 255 donde hay imagen, 0 donde está vacío
        alpha = (mask_region.astype(np.uint8) * 255)

        # Convertir a BGRA
        mosaic_image = cv2.cvtColor(final_mosaic, cv2.COLOR_BGR2BGRA)

        # Reemplazar canal alfa
        mosaic_image[:, :, 3] = alpha

        path_map_trees = create_map_trees_ids(mosaic_image = mosaic_image, base_dir = self.result_dir)

        num_images = len(metadata_rgb_images)
        alts = [im_data['relative_altitude'] for im_data in metadata_rgb_images]
        avg_alt = sum(alts) / num_images
        print("avg_alt:", avg_alt)

        metadata_multispec_images = [img_m for img_m in self.images_data if "_D.JPG" not in img_m['relative_path']]
        
        multispec_gsd = [im_data['gsd_horizontal'] * 100 for im_data in metadata_multispec_images]
        avg_gsd_multispec = sum(multispec_gsd) / len(multispec_gsd)

        rgb_gsd = [im_data['gsd_horizontal'] * 100 for im_data in metadata_rgb_images]
        avg_gsd_rgb = sum(rgb_gsd) / num_images
        
        
        count_pixles = np.sum(np.any(final_mosaic > 0, axis=-1))
        area_mosaic = (count_pixles * dom_resolution) / 1000000
        
        fecha_formateada = ""
        if len(self.images_data) > 0:
            exif_str = self.images_data[0]['datetime_original']
            dt = datetime.strptime(exif_str, "%Y:%m:%d %H:%M:%S")

            # Formatear al formato deseado
            fecha_formateada = dt.strftime("%d/%m/%Y")

        path_card_map = f"{self.result_dir}/mosaic/rgb/card_map.png"

        processing_sumary = dict(
            mosaic_rgb = mosaic_path,
            mosaic_ndvi = ndvi_path,
            trees_count = len(unique_detects_trees),
            total_images = len(all_images_metadada_dict),
            avg_alt = avg_alt,
            avg_gsd_rgb = avg_gsd_rgb,
            avg_gsd_multispec = avg_gsd_multispec,
            area_mosaic = area_mosaic,
            map_trees = path_map_trees,
            card_map = path_card_map,
            adquisition_date = fecha_formateada,
            healthy_count_ndvi = healthy_count_ndvi,
            warning_count_ndvi = warning_count_ndvi,
            possible_problem_count_ndvi = possible_problem_count_ndvi,
            critical_problem_count_ndvi = critical_problem_count_ndvi,
            healthy_count_mcari = healthy_count_mcari,
            warning_count_mcari = warning_count_mcari,
            critical_problem_count_mcari = critical_problem_count_mcari
        )

        with open(f"{self.result_dir}/processing_sumary.json", "w") as f:
            json.dump(processing_sumary, f, indent =2)
        
        
        # if not self.check_continue_procress():
        #         return
        
        # final_dom_out = final_dom.copy()
        # trees_mask_green = np.zeros_like(final_dom, dtype=np.uint8)
        # trees_mask_green[trees_mask > 0] = [0, 255, 0]
        # final_dom_out[trees_mask > 0] = [0, 255, 0]
        # alpha = 0.45

        # final_out = cv2.addWeighted(final_dom_out, alpha, final_dom, 1-alpha, 0)

        # final_result_path = f"{self.result_dir}/mosaic/{name_file[:-4]}_TREES_RESULT.tif"

        # self.save_as_geotiff(
        #     final_out,
        #     final_result_path,
        #     dom_bounds[0], dom_bounds[3],  # Esquina superior izquierda (X,Y)
        #     dom_resolution,
        #     ref_zone_lon
        # )

        # if not self.check_continue_procress():
        #     return

        # self._generate_single_zoom_tiles(
        #     input_raster = final_result_path, 
        #     output_dir = f"{self.result_dir}/mosaic/tiles_result", 
        #     tile_size = 256)
        
        # final_masks_trees = f"{self.result_dir}/mosaic/{name_file[:-4]}_MASK_TREES.tif"

        # self.save_as_geotiff(
        #     trees_mask_green,#np.expand_dims(trees_mask, axis=-1),
        #     final_masks_trees,
        #     dom_bounds[0], dom_bounds[3],  # Esquina superior izquierda (X,Y)
        #     dom_resolution,
        #     ref_zone_lon,
        #     alpha=0.5
        # )

        # self._generate_single_zoom_tiles(
        #     input_raster = final_masks_trees, 
        #     output_dir = f"{self.result_dir}/mosaic/tiles_mask_trees", 
        #     tile_size = 256)
        
        
        self.progress_update(100)

if __name__ == "__main__":
    import pandas as pd
    df_images = pd.read_csv("./df_images_metadata.csv")
    df_images_slice = df_images.iloc[0,:50]
    print(df_images_slice)
    #generate_mosaic(df_images.to_dict(orient='index'), type_align_matrix = "affine", signal_progress = None)
    image_sticher = ImageSticher(images_data =  df_images_slice.to_dict(orient='index'))

    image_sticher.run(save_dir = "./", 
                      prefix_name="Vuelo-Agosto-15-Campo2-Accopampa")
    #generate_mosaic(all_images_data, type_align_matrix = "affine")
#type_align_matrix = "affine"
#transforms = propagate_pairwise_correction(df_images_filtered_slice.reset_index().to_dict(orient='index'), type_align_matrix)

#overlap_graph  = build_overlap_graph(all_terrain_points_dom, min_overlap=0.45)
