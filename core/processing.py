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

class FusionMethod(Enum):
    SIMPLE_AVERAGE = 1
    SEAM_BLENDING = 2
    WEIGHTED_DISTANCE = 3
    EXPOSURE_COMPENSATED = 4
    MULTIBAND_ADAPTIVE = 5
    ROBUST_DRONE = 6

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


def generate_mosaic(all_images_data, type_align_matrix = "affine", signal_progress = None):
    all_images_data_list = all_images_data.values()
    print("Comienza process_calculate_camera_pose")
    all_images_data_list = process_calculate_camera_pose(all_images_data_list)
    signal_progress.emit(55)
    print("Comienza process_terrain_points")
    all_images_data_list = process_terrain_points(all_images_data_list)
    signal_progress.emit(60)
    print("Comienza estimate_dom_parameters")
    dom_bounds, dom_resolution = estimate_dom_parameters(all_images_data_list, margin_extension = 0.1)
    signal_progress.emit(65)
    print("Comienza process_project_corners_to_dom")
    all_images_data_list = process_project_corners_to_dom(all_images_data_list, dom_bounds, dom_resolution)
    signal_progress.emit(70)
    print("Comienza process_detect_keypoint_descriptors_in_dom")
    all_images_data_list = process_detect_keypoint_descriptors_in_dom(all_images_data_list, dom_size)
    signal_progress.emit(75)
    print("Comienza propagate_pairwise_correction")
    transforms = propagate_pairwise_correction(all_images_data_list, type_align_matrix)
    signal_progress.emit(85)
    print("Comienza transformations")
    #print("Comienza propagate_pairwise_correction")
    width_m = dom_bounds[1] - dom_bounds[0]
    height_m = dom_bounds[3] - dom_bounds[2]
    width_px = int(width_m / dom_resolution)
    height_px = int(height_m / dom_resolution)
    dom_size = (height_px, width_px)

    blended = np.zeros((height_px, width_px, 3), dtype=np.float32)
    total_weights = np.zeros((height_px, width_px), dtype=np.float32)
    detector_type = "SIFT"
    ref_zone_lon = all_images_data[0]['longitude']

    for index, row in enumerate(tqdm(all_images_data, desc = "Build Mosaic")):
        image = cv2.imread(row['relative_im_path'])
        image_distortion = distortion_correction(image)
        #image_distortion = cv2.putText(image_distortion, f"{index}", (image_distortion.shape[1]//2, image_distortion.shape[0]//2), cv2.FONT_HERSHEY_COMPLEX, 8, (0,0,255), thickness= 5)
        H_rtk = row['H_rtk']
        terrain_points_dom = row['terrain_points_dom']
        imagen_proyectada, mask = direct_project_image_to_dom(image_distortion, H_rtk, dom_size, terrain_points_dom)

        projected_corrected = cv2.warpPerspective(imagen_proyectada, transforms[index], (int(dom_size[1]), int(dom_size[0])))
        mask = cv2.warpPerspective(mask, transforms[index], (int(dom_size[1]), int(dom_size[0])))
        weights = calculate_weights(mask, None, FusionMethod.ROBUST_DRONE)
        max_weight = np.max(weights)
        if max_weight > 0:
            weights = weights / max_weight
        #weights = cv2.GaussianBlur(weights, (9, 9), 0)
        update_mask = weights > total_weights
        blended[update_mask] = projected_corrected[update_mask]
        total_weights = np.maximum(total_weights, weights)
    
        progress = int((85 +  15 * index/ len(all_images_data)) * 100)
        signal_progress.emit(progress)
    final_dom = blended.astype(np.uint8).copy()

    plt.figure(figsize=(10,10))
    plt.imshow(cv2.cvtColor(final_dom, cv2.COLOR_BGR2RGB))
    plt.show()
    save_as_geotiff(
            final_dom, f"campo2_mosaico_graph_queue_refine_{type_align_matrix}_{detector_type}_{len(all_images_data)}_images.tif", 
            dom_bounds[0], dom_bounds[3],  # Esquina superior izquierda (X,Y)
            dom_resolution,
            ref_zone_lon
        )
    signal_progress.emit(100)
if __name__ == "__main__":
    print()
    #generate_mosaic(all_images_data, type_align_matrix = "affine")
#type_align_matrix = "affine"
#transforms = propagate_pairwise_correction(df_images_filtered_slice.reset_index().to_dict(orient='index'), type_align_matrix)

#overlap_graph  = build_overlap_graph(all_terrain_points_dom, min_overlap=0.45)
