import pandas as pd
import cv2
import numpy as np
import ast
import re
import json

from core.inference import distortion_correction
df_images_data = pd.read_csv("./image_date_mosaic.csv")

print(df_images_data.head())

def bbox(poly):
    x, y = poly[:,0], poly[:,1]
    return [x.min(), y.min(), x.max(), y.max()]

def draw_detections(image, segmentations, classes, bboxes = None, alpha=0.45):
        img_out = image.copy()
        print("segmentations:", segmentations)
        print("segmentations:", len(segmentations))
        for i, seg in enumerate(segmentations):
            pts = np.array(seg, dtype=np.int32).reshape(-1,1,2)
            
            # Color azul claro
            color = (255, 200, 0)  # BGR (azul cielo)

            # Relleno
            cv2.fillPoly(img_out, [pts], color)
            # Borde
            #cv2.polylines(img_out, [pts], isClosed=True, color=(0, 0, 255), thickness=4)

            # Texto
            # Etiqueta
            # Dibujar bounding box si existe
            
            if bboxes is not None:
                x1, y1, x2, y2 = map(int, bboxes[i])
                cv2.rectangle(img_out, (x1, y1), (x2, y2), (0, 0, 255), 10)
            else:
                x1, y1, x2, y2 = bbox(np.array(seg, dtype=np.int32))
                cv2.rectangle(img_out, (x1, y1), (x2, y2), (0, 0, 255), 10)

            cls = classes[i]
           
            label = f"{cls}"
            x, y = pts[0][0]
            
            # Fuente y escala
            font = cv2.FONT_HERSHEY_SIMPLEX
            scale = 2
            thickness = 8

            # Calcular tamaño del texto
            (text_w, text_h), baseline = cv2.getTextSize(label, font, scale, thickness)

            # Coordenadas del rectángulo (fondo rojo)
            cv2.rectangle(img_out, 
                        (x, y - text_h - baseline - 5),  # esquina superior izq
                        (x + text_w + 10, y + 5),        # esquina inferior der
                        (0, 0, 255),                    # rojo BGR
                        -1)                             # relleno

            cv2.putText(img_out, label, 
                (x + 5, y - baseline), 
                font, scale, 
                (255, 255, 255),  # blanco
                thickness)
            
        # Combinar con transparencia
        final = cv2.addWeighted(img_out, alpha, image, 1 - alpha, 0)

        return final

def str_to_arrays(seg_str):
    if not isinstance(seg_str, str) or seg_str.strip() in ["", "[]"]:
        return []
    
    # 1. Quitar "array(" y "dtype=..."
    s = re.sub(r'array\(', '(', seg_str)
    s = re.sub(r',?\s*dtype=[^)]+', '', s)

    # 2. Eliminar saltos de línea y espacios múltiples
    s = s.replace("\n", " ")
    s = re.sub(r"\s+", " ", s).strip()

    # 3. Reemplazar paréntesis por corchetes
    s = s.replace('(', '[').replace(')', ']')

    # 4. Intentar evaluar
    try:
        parsed = ast.literal_eval(s)
    except Exception as e:
        print("Error parseando:", e)
        print("Cadena problemática:", s[:200], "...")
        return []

    # --- CORRECCIÓN: quitar nivel extra si empieza con [[[[
    while isinstance(parsed, list) and len(parsed) == 1 and isinstance(parsed[0], list):
        parsed = parsed[0]

    # 5. Convertir cada polígono en np.array
    out = []
    for poly in parsed:
        arr = np.array(poly, dtype=float)
        if arr.ndim == 1 and arr.size % 2 == 0:
            arr = arr.reshape(-1, 2)
        out.append(arr)
    return out


# Reconstruir listas de arrays
df_images_data["segs_filtered"] = df_images_data["segs_filtered"].apply(
    lambda x: [np.array(sublist) for sublist in json.loads(x)]
)

import os
os.makedirs("./results/filtered", exist_ok=True)

for index, data in df_images_data.iterrows():
    image = cv2.imread(data['relative_path'])
    image = distortion_correction(image)
    segs_filtered = data['segs_filtered']
    print(type(segs_filtered))
    
    classes =['avocado'] * len(segs_filtered)
    output = draw_detections(image, segs_filtered, classes, bboxes = None, alpha=0.45)
    cv2.imwrite(f"./results/filtered/{data['basename']}_RESULT_FILTERED.png", output)
    