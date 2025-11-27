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
from enum import Enum
from tqdm import tqdm
from osgeo import gdal, osr
from scipy.sparse import coo_matrix
import numpy as np
from tqdm import tqdm
from scipy.sparse.linalg import lsqr
from datetime import datetime
import pandas as pd
import json

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

def direct_project_image_to_dom(image, H, dom_size, terrain_points_dom):

        imagen_proyectada = cv2.warpPerspective(
            image,
            H,
            (int(dom_size[1]), int(dom_size[0])),
            flags=cv2.INTER_LANCZOS4  # Interpolación de alta calidad
        )

        gray = cv2.cvtColor(imagen_proyectada, cv2.COLOR_BGR2GRAY)

        mask = np.where(gray > 0, 255, 0).astype(np.float32)
        # Crear mascara
        #mask = np.zeros((dom_size[0], dom_size[1]), dtype=np.float32)  # Invertir tamaño para (height, width)
        #cv2.fillConvexPoly(mask, terrain_points_dom.astype(np.int32), 1)
        
        return imagen_proyectada, mask

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
        imagen_proyectada, _ = direct_project_image_to_dom(img_undistorned, H_rtk, dom_size, terrain_points_dom)
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
    
    for (u,v,H,mask,pts_u,pts_v) in mst_edges:
        adj_map.setdefault(u, []).append((v,H))
        adj_map.setdefault(v, []).append((u, np.linalg.inv(H)))

    # BFS propagation
    queue = [0]
    while queue:
        u = queue.pop(0)
        for (v, H_uv) in adj_map.get(u, []):
            if H_abs[v] is None:
                H_abs[v] = H_abs[u].dot(H_uv)
                queue.append(v)

    
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

    mst = prim_mst(n_images, adj_graph)
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
            imagen_proyectada, _ = direct_project_image_to_dom(img_undistorned, H_rtk, dom_size, terrain_points_dom)
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
                image_distortion = distortion_correction(image)
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

    def run(self, 
            name_file = None, 
            prefix_name = None,
            detector_keypoints = "SIFT",
            type_align_matrix = "affine"):
        self.is_running = True
        all_images_data_list = self.images_data
        n_images = len(all_images_data_list)
        print("Comienza process_calculate_camera_pose")
        all_images_data_list = self.process_calculate_camera_pose(all_images_data_list)
        self.progress_update(2)
        
        if not self.check_continue_procress():
            return
        
        print("Comienza process_terrain_points")
        all_images_data_list = self.process_terrain_points(all_images_data_list)
        if not self.check_continue_procress():
                return
        
        self.progress_update(4)
        print("Comienza estimate_dom_parameters")
        dom_bounds, dom_resolution = self.estimate_dom_parameters(all_images_data_list, margin_extension = 0.1)
        if not self.check_continue_procress():
                return
        self.progress_update(6)

        width_m = dom_bounds[1] - dom_bounds[0]
        height_m = dom_bounds[3] - dom_bounds[2]
        width_px = int(width_m / dom_resolution)
        height_px = int(height_m / dom_resolution)
        dom_size = (height_px, width_px)
        print("Comienza process_project_corners_to_dom")
        all_images_data_list = self.process_project_corners_to_dom(all_images_data_list, dom_bounds, dom_resolution)
        if not self.check_continue_procress():
                return
        self.progress_update(8)
        
        print("Comienza process_detect_keypoint_descriptors_in_dom")
        all_images_data_list = self.process_detect_keypoint_descriptors_in_dom(all_images_data_list, dom_size, detector_keypoints)
        
        if not self.check_continue_procress():
                return
        
        self.progress_update(20)
        print("Comienza calculate_pairwase_matches")
        
        all_terrain_points_dom = [d['terrain_points_dom'] for d in all_images_data_list]

        # 2. Construir grafo de solapamiento
        overlap_graph  = build_overlap_graph(all_terrain_points_dom, min_overlap=0.45)
        # 5) Grafo y MST (Prim). Ruta de propacion
        edges = estimate_pairwase_homographies(overlap_graph, all_images_data_list, type_align_matrix)

        adj_graph = build_adjacency_graph_from_edges(n_images, edges)

        mst = prim_mst(n_images, adj_graph)
        # 6) Inicialización H absolute vía propagación en MST
        H_abs = initialize_homographies(n_images, mst)
        if not self.check_continue_procress():
            return
        self.progress_update(40)

        final_dom, trees_mask = self.create_mosaic_batch_seam_blending(
            all_images_data_list,
              H_abs, 
              dom_size=(height_px, width_px),
              save_dir_logs=f"{self.result_dir}/mosaic/blending")

        
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

        mosaic_path = f"{self.result_dir}/mosaic/{name_file}"
        print("--------------Dividiendo en tiles-----------------")
        self.save_as_geotiff(
                final_dom, 
                mosaic_path, 
                dom_bounds[0], dom_bounds[3],  # Esquina superior izquierda (X,Y)
                dom_resolution,
                ref_zone_lon
        )
        
        if not self.check_continue_procress():
            return

        self._generate_single_zoom_tiles(
            input_raster = mosaic_path, 
            output_dir = f"{self.result_dir}/mosaic/tiles_mosaic", 
            tile_size = 256)
        
        if not self.check_continue_procress():
                return
        
        final_dom_out = final_dom.copy()
        trees_mask_green = np.zeros_like(final_dom, dtype=np.uint8)
        trees_mask_green[trees_mask > 0] = [0, 255, 0]
        final_dom_out[trees_mask > 0] = [0, 255, 0]
        alpha = 0.45

        final_out = cv2.addWeighted(final_dom_out, alpha, final_dom, 1-alpha, 0)

        final_result_path = f"{self.result_dir}/mosaic/{name_file[:-4]}_TREES_RESULT.tif"

        self.save_as_geotiff(
            final_out,
            final_result_path,
            dom_bounds[0], dom_bounds[3],  # Esquina superior izquierda (X,Y)
            dom_resolution,
            ref_zone_lon
        )

        if not self.check_continue_procress():
            return

        self._generate_single_zoom_tiles(
            input_raster = final_result_path, 
            output_dir = f"{self.result_dir}/mosaic/tiles_result", 
            tile_size = 256)
        
        final_masks_trees = f"{self.result_dir}/mosaic/{name_file[:-4]}_MASK_TREES.tif"

        self.save_as_geotiff(
            trees_mask_green,#np.expand_dims(trees_mask, axis=-1),
            final_masks_trees,
            dom_bounds[0], dom_bounds[3],  # Esquina superior izquierda (X,Y)
            dom_resolution,
            ref_zone_lon,
            alpha=0.5
        )

        self._generate_single_zoom_tiles(
            input_raster = final_masks_trees, 
            output_dir = f"{self.result_dir}/mosaic/tiles_mask_trees", 
            tile_size = 256)
        
        
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
