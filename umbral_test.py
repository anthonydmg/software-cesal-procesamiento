import cv2
import json
import matplotlib.pyplot as plt
import numpy as np
from core.processing import distortion_correction
from skimage import graph
from skimage.segmentation import slic, mark_boundaries


with open("./results/detections/DJI_20241128154239_0001_D_DETECTIONS.json", "r") as f:
    detecctions = json.load(f)

image_path = detecctions['image_path']
segmentations = detecctions["detecctions"]['segmentations']
boxes = detecctions["detecctions"]['bboxes']

image = cv2.imread(image_path)

image = distortion_correction(image)

tree_id = 0

seg = segmentations[tree_id]
bbox = boxes[tree_id]

output = image.copy()

cv2.fillPoly(output, [np.array(seg).reshape(-1,1,2)], color=[0,255,0])

output = cv2.addWeighted(image, 0.5, output, 0.5, 0)

x_min, y_min, x_max, y_max = np.array(bbox).astype(np.int32)
tree = image[ y_min:y_max, x_min:x_max, :]

# 1. Generar superpíxeles
# Esta bueno asi
#segments = slic(tree, n_segments=500, compactness=30, start_label=1)

segments = slic(tree, n_segments=700, compactness=30, start_label=1)

# 2. Convertir a HSV
hsv = cv2.cvtColor(tree, cv2.COLOR_BGR2HSV)

# 2. Funcion Dummy

def nothing(x):
    pass

cv2.namedWindow("Segmentacion HSV")
cv2.createTrackbar("H_min", "Segmentacion HSV", 33, 179, nothing)
cv2.createTrackbar("H_max", "Segmentacion HSV", 179, 179, nothing)
cv2.createTrackbar("S_min", "Segmentacion HSV", 50, 255, nothing)
cv2.createTrackbar("S_max", "Segmentacion HSV", 255, 255, nothing)
cv2.createTrackbar("V_min", "Segmentacion HSV", 66, 255, nothing)
cv2.createTrackbar("V_max", "Segmentacion HSV", 255, 255, nothing)

while True:
    # Leer valores de los trackbars
    h_min = cv2.getTrackbarPos("H_min", "Segmentacion HSV")
    h_max = cv2.getTrackbarPos("H_max", "Segmentacion HSV")
    s_min = cv2.getTrackbarPos("S_min", "Segmentacion HSV")
    s_max = cv2.getTrackbarPos("S_max", "Segmentacion HSV")
    v_min = cv2.getTrackbarPos("V_min", "Segmentacion HSV")
    v_max = cv2.getTrackbarPos("V_max", "Segmentacion HSV")

    # Crear máscara con los valores actuales
    lower = np.array([h_min, s_min, v_min])
    upper = np.array([h_max, s_max, v_max])
    # 3. Crear mascara inicial
    mask = np.zeros(shape = tree.shape[:2], dtype = np.uint8)

    # 4. Analizar cada superpixel
    for seg_val in np.unique(segments):
        # Crear mascara temporal para el superpixel
        mask_sp = (segments == seg_val)
        
        # Promedio de valores HSV
        mean_hue = np.mean(hsv[...,0][mask_sp])
        mean_sat = np.mean(hsv[...,1][mask_sp])
        mean_val = np.mean(hsv[...,2][mask_sp])

        if h_max >= mean_hue and h_min < mean_hue \
            and mean_sat < s_max and mean_sat > s_min and mean_val > v_min and mean_val < v_max:
            mask[mask_sp] = 255

    # Mostrar resultados
    cv2.imshow("Imagen Original", tree)
    cv2.imshow("Resultado", mark_boundaries(tree, segments))
    cv2.imshow("Mascara", mark_boundaries(mask, segments))

     # Salir con 'q'
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break