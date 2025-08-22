from PySide6.QtCore import QMutex
import torch
from datetime import datetime
import traceback
import os
import gc
from ultralytics import YOLO
import numpy as np
import cv2
import json
from tqdm import tqdm

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


def padding_to_square_image(image):
    h, w =  image.shape[:2]
    max_side = max(h, w)

    top = 0
    bottom = max_side - h
    left = 0
    right = max_side - w

    img_squared = cv2.copyMakeBorder(
        image,
        top,
        bottom,
        left,
        right,
        borderType=cv2.BORDER_CONSTANT,
        value= [0,0,0] if len(image.shape) == 3 and image.shape[2] > 1 else 0
    )

    return img_squared

class TreeDetectorYolo:
    _instance = None
    _mutex = QMutex()
    
    def __init__(self):
        if TreeDetectorYolo._instance is not None:
            raise Exception("Esta clase es un singleton. Usa get_instance()")
        
        self.device = self._select_device()
        print("self.device:", self.device)
        self.model = self._load_model()
        
    @classmethod
    def get_instance(cls):
        cls._mutex.lock()
        try:
            if cls._instance is None:
                cls._instance = TreeDetectorYolo()
            return cls._instance
        finally:
            cls._mutex.unlock()
    
    def _select_device(self):
        if torch.cuda.is_available():
            torch.backends.cudnn.benchmark = True
            return "cuda"
        return "cpu"
    
    def _load_model(self):
        model = YOLO("./yolo11m-seg-finituned-2-split.pt", task= 'segment')

        #AutoDetectionModel.from_pretrained(
        #    model_type='yolo11',
        #    model_path='C:/Users/Anthony/Local/cesal-proyecto/avocado-trees-identication/yolo11s-seg-finituned.pt',
        #    confidence_threshold=0.5,
        #    device=self.device,
        #)
        
        #if hasattr(model, 'model'):
        #    for param in model.model.parameters():
        #        param.requires_grad = False
        return model
    
    def resize_and_unpad_mask(self, mask, original_shape, pad_shape):
        mask_resized = cv2.resize(mask, pad_shape, interpolation=cv2.INTER_LANCZOS4)
        height, width = original_shape
        binary_mask = np.maximum(binary_mask, mask_resized[:height, :width])  # Unión lógica (OR)
        return binary_mask

    def mask_to_polygons(self, mask_bin):
        # Asegurar binaria tipo 0/255
        mask_bin = (mask_bin > 0).astype(np.uint8) * 255
        contours, _ = cv2.findContours(mask_bin, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        polygons = []
        for cnt in contours:
            if len(cnt) >= 3:  # descartar degenerados
                poly = cnt.squeeze(1).tolist()  # [[x1,y1], [x2,y2], ...]
                polygons.append(poly)
        return polygons
    
    def predict(self, 
                image_paths, 
                save_dir =  "./results"):
        
        all_results = []
        for image_path in tqdm(image_paths, desc= "Trees Deteccion"):
            try:
                if not os.path.exists(image_path):
                    raise FileNotFoundError(f"Imagen no encontrada: {image_path}")
                os.makedirs(save_dir, exist_ok=True)
                self._clean_memory()
                print("image_path:", image_path)
                image = cv2.imread(image_path)
                height, width = image.shape[:2]
                image = distortion_correction(image)
                im_padded = padding_to_square_image(image)
                h_im_pad, w_im_pad = im_padded.shape[:2]
                im_resized = cv2.resize(im_padded, (640, 640), interpolation=cv2.INTER_LANCZOS4)
                results = self.model.predict(im_resized, imgsz = (640, 640), conf=0.5)
                predictions = dict(
                    bboxes= [], 
                    #masks= [], 
                    segmentations= [],
                    classes= [], 
                    scores= [], 
                    timestamp= datetime.now().isoformat()
                )
                scale_factor = w_im_pad / 640
                for r in results:
                    if r.boxes is not None:
                        boxes = r.boxes.xyxy.cpu().numpy()
                        scores = r.boxes.conf.cpu().numpy()
                        classes = r.boxes.cls.cpu().numpy()
                        for box, score, cls in zip(boxes, scores, classes):
                            predictions['bboxes'].append((box * scale_factor).tolist())
                            predictions['scores'].append(float(score))
                            predictions['classes'].append(r.names[cls])
                    
                    print("r.names",r.names)
                    if r.masks is not None:
                        #print(r.masks)
                        
                        

                        for seg in r.masks.xy:
                            poly = seg * scale_factor
                            poly[:, 0] = np.clip(poly[:, 0], 0, width)  # eje x limitado al ancho original
                            poly[:, 1] = np.clip(poly[:, 1], 0, height)
                            poly = poly.astype(np.int32)
                            predictions["segmentations"].append(poly.tolist())

                all_results.append(predictions)
                im_result = self.draw_detections(image, 
                                        predictions['segmentations'], 
                                        predictions["classes"], 
                                        predictions["scores"],
                                        predictions['bboxes'])
                filename = os.path.basename(image_path)[:-4]
                os.makedirs(f"./{save_dir}/visualizations", exist_ok=True)
                cv2.imwrite(f"./{save_dir}/visualizations/{filename}_RESULT.png", im_result)
                
                os.makedirs(f"./{save_dir}/detections", exist_ok=True)
                with open(f"./{save_dir}/detections/{filename}_DETECTIONS.json", "w", encoding="utf-8") as f:
                    json.dump({"image_path": image_path, "detecctions": predictions}, f, indent= 4, ensure_ascii= True)
               
            except Exception as e:
                print(f"Error en predicción: {str(e)}")
                traceback.print_exc()
                all_results.append(None)
            finally:
                self._clean_memory()
        return all_results
    
    def _process_segmentation(self, segmentation):
        if isinstance(segmentation, list):
            if all(isinstance(v, (int, float)) for v in segmentation):
                return np.array(segmentation, dtype=np.int32).reshape((-1, 2)).tolist()
            elif all(isinstance(v, list) for v in segmentation):
                return [np.array(s, dtype=np.int32).reshape((-1, 2)).tolist() for s in segmentation]
        return segmentation
    
    def _clean_memory(self):
        gc.collect()
        if self.device.startswith('cuda'):
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()

    def draw_detections(self, image, segmentations, classes, scores, bboxes = None, alpha=0.45):
        img_out = image.copy()
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

            cls = classes[i]
            score = scores[i]
            label = f"{cls} {score:.2f}"
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

if __name__ == "__main__":
    detector = TreeDetectorYolo().get_instance()
    from glob import glob
    
    images_path = glob("./data/trees-avocado/m3m/campo2/images/*.JPG")
    predictions = detector.predict(images_path, save_dir = "./results")