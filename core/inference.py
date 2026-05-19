from PySide6.QtCore import QMutex
from datetime import datetime
import traceback
import os
import gc
import numpy as np
import cv2
import json
from tqdm import tqdm
import onnxruntime as ort


from core.utils import resource_path

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

IM_SIZE = 1280#640

class TreeDetectorYolo:
    _instance = None
    _mutex = QMutex()
    
    # Define tus clases aquí (ONNX pierde el diccionario de nombres)
    CLASS_NAMES = {0: "Arbol"} 
    
    def __init__(self):
        if TreeDetectorYolo._instance is not None:
            raise Exception("Esta clase es un singleton. Usa get_instance()")
        
        self.providers = self._select_providers()
        print("Providers seleccionados:", self.providers)
        self.session = self._load_model()
        
        # Obtener nombres de los nodos de entrada y salida del grafo ONNX
        self.input_name = self.session.get_inputs()[0].name
        self.output_names = [out.name for out in self.session.get_outputs()]
        
    @classmethod
    def get_instance(cls):
        cls._mutex.lock()
        try:
            if cls._instance is None:
                cls._instance = TreeDetectorYolo()
            return cls._instance
        finally:
            cls._mutex.unlock()
    
    def _select_providers(self):
        available = ort.get_available_providers()
        if 'CUDAExecutionProvider' in available:
            return ['CUDAExecutionProvider', 'CPUExecutionProvider']
        return ['CPUExecutionProvider']
    
    def _load_model(self):
        # CAMBIAR EXTENSIÓN A .onnx
        model_path = resource_path(os.path.join("assets", "models", "yolo11s-seg-finituned-2-split-1280.onnx"))
        return ort.InferenceSession(model_path, providers=self.providers)
    
    def _preprocess(self, image):
        # cv2.dnn.blobFromImage es súper eficiente en C++ para preprocesar
        blob = cv2.dnn.blobFromImage(
            image, 1/255.0, (IM_SIZE, IM_SIZE), 
            swapRB=True, crop=False
        )
        return blob

    def _postprocess(self, outputs, scale_factor, conf_thresh, img_shape):
        """
        Matemática cruda para decodificar YOLO Segmentation sin PyTorch.
        """
        predictions = dict(
            bboxes=[], 
            segmentations=[],
            classes=[], 
            scores=[], 
            timestamp=datetime.now().isoformat()
        )
        orig_h, orig_w = img_shape

        
        # Salida 0: Coordenadas, Scores y Coeficientes de Máscara
        # Shape esperado: (1, 4 + num_clases + 32_mascaras, 8400)
        preds = outputs[0][0].T  # Transponemos a (8400, N) para iterar filas
        
        # Salida 1: Prototipos de máscaras
        # Shape esperado: (1, 32, 160, 160) u otra resolución según el IM_SIZE
        protos = outputs[1][0]   # (32, H_proto, W_proto)
        num_masks = protos.shape[0]
        num_classes = preds.shape[1] - 4 - num_masks
        
        # 1. Separar los tensores
        boxes_cxcywh = preds[:, :4]
        scores_matrix = preds[:, 4:4+num_classes]
        mask_coefs = preds[:, 4+num_classes:]
        
        # 2. Convertir cajas (Centro X, Centro Y, W, H) a (X1, Y1, X2, Y2)
        boxes_xyxy = np.empty_like(boxes_cxcywh)
        boxes_xyxy[:, 0] = boxes_cxcywh[:, 0] - boxes_cxcywh[:, 2] / 2
        boxes_xyxy[:, 1] = boxes_cxcywh[:, 1] - boxes_cxcywh[:, 3] / 2
        boxes_xyxy[:, 2] = boxes_cxcywh[:, 0] + boxes_cxcywh[:, 2] / 2
        boxes_xyxy[:, 3] = boxes_cxcywh[:, 1] + boxes_cxcywh[:, 3] / 2
        
        # 3. Obtener el score máximo y su clase
        class_ids = np.argmax(scores_matrix, axis=1)
        confidences = scores_matrix[np.arange(len(class_ids)), class_ids]
        
        # 4. Filtrar por confianza mínima para optimizar memoria antes del NMS
        valid_idx = confidences > conf_thresh
        boxes_xyxy = boxes_xyxy[valid_idx]
        confidences = confidences[valid_idx]
        class_ids = class_ids[valid_idx]
        mask_coefs = mask_coefs[valid_idx]
        
        # 5. Non-Maximum Suppression (NMS)
        iou_thresh = 0.45
        indices = cv2.dnn.NMSBoxes(boxes_xyxy.tolist(), confidences.tolist(), conf_thresh, iou_thresh)
        
        if len(indices) > 0:
            indices = indices.flatten()
            
            for i in indices:
                # Datos de esta detección
                box = boxes_xyxy[i]
                conf = confidences[i]
                cls_id = class_ids[i]
                coef = mask_coefs[i]
                
                # --- PROCESAMIENTO DE LA MÁSCARA ---
                # Multiplicación matricial: (1, 32) @ (32, H*W) -> (1, H*W)
                proto_flat = protos.reshape(num_masks, -1)
                mask = np.dot(coef, proto_flat).reshape(protos.shape[1], protos.shape[2])
                
                # Función Sigmoide para obtener probabilidades entre 0 y 1
                # (np.clip evita overflow de exp)
                mask = 1.0 / (1.0 + np.exp(np.clip(-mask, -500, 500)))
                
                # Redimensionar la máscara al tamaño de la imagen de entrada (IM_SIZE x IM_SIZE)
                mask_resized = cv2.resize(mask, (IM_SIZE, IM_SIZE), interpolation=cv2.INTER_LINEAR)
                
                # Delimitar la máscara dentro del Bounding Box (cortar ruido de fondo)
                x1, y1, x2, y2 = map(int, box)
                # Limitar coords a la imagen
                x1, y1 = max(0, x1), max(0, y1)
                x2, y2 = min(IM_SIZE, x2), min(IM_SIZE, y2)
                
                bbox_mask = np.zeros_like(mask_resized)
                bbox_mask[y1:y2, x1:x2] = 1
                
                # Binarización y aplicación de límite del BBox
                mask_bin = ((mask_resized > 0.5) * bbox_mask).astype(np.uint8) * 255
                
                # Extracción de contornos (Polígonos)
                contours, _ = cv2.findContours(mask_bin, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                
                cnt_largest = max(contours, key=cv2.contourArea)
                #for cnt in contours:
                if len(cnt_largest) >= 3: # descartar ruido
                    poly = cnt_largest.squeeze(1).astype(np.float32) * scale_factor
                    poly[:, 0] = poly[:, 0] / float(orig_w) #np.clip(poly[:, 0] / orig_w, 0, 1)
                    poly[:, 1] = poly[:, 1] / float(orig_h) #np.clip(poly[:, 1] / orig_h, 0, 1)
                    
                    predictions["segmentations"].append(poly.tolist())
                        
                # Escalar el BBox y guardarlo

                
                bbox = box * scale_factor
                bbox[0] = np.clip(bbox[0] / orig_w, 0, 1)
                bbox[1] = np.clip(bbox[1] / orig_h, 0, 1)
                bbox[2] = np.clip(bbox[2] / orig_w, 0, 1)
                bbox[3] = np.clip(bbox[3] / orig_h, 0, 1)
                #bbox[:, 1] = np.clip(bbox[:, 1] / orig_h, 0, 1)
                
                bbox = bbox.tolist()
                #scaled_box = (box * scale_factor).tolist()
                cls_name = self.CLASS_NAMES.get(int(cls_id), f"Class_{int(cls_id)}")
                
                predictions['bboxes'].append(bbox)
                predictions['scores'].append(float(conf))
                predictions['classes'].append(cls_name)

        return predictions
    
    def predict(self, image_paths, save_dir="./results", conf_thresh=0.5):
        all_results = []
        os.makedirs(save_dir, exist_ok=True)
        #os.makedirs(f"{save_dir}/visualizations", exist_ok=True)
        os.makedirs(f"{save_dir}/detections", exist_ok=True)

        for image_path in image_paths: #tqdm(image_paths, desc="Trees Deteccion"):
            try:
                if not os.path.exists(image_path):
                    raise FileNotFoundError(f"Imagen no encontrada: {image_path}")
                
                self._clean_memory()
                image = cv2.imread(image_path)
                height, width = image.shape[:2]
                
                image_undistort = distortion_correction(image)
                im_padded = padding_to_square_image(image_undistort)
                h_im_pad, w_im_pad = im_padded.shape[:2]
                
                # 1. Preprocesamiento ONNX (Blob)
                input_tensor = self._preprocess(im_padded)
                
                # 2. Inferencia pura ONNX
                outputs = self.session.run(self.output_names, {self.input_name: input_tensor})
                
                # 3. Decodificación
                scale_factor = w_im_pad / IM_SIZE
                #scale_factor = 1 / IM_SIZE
                
                #w_pad = w_im_pad - width
                #h_pad = h_im_pad - height

                #predictions = self._postprocess(outputs, scale_factor, conf_thresh, (height, width))
                predictions = self._postprocess(outputs, scale_factor, conf_thresh, (height, width))
                
                all_results.append(predictions)
                
                # 4. Dibujar Resultados
                # im_result = self.draw_detections(
                #     image_undistort,  # Dibujamos sobre la no-paddeada (undistorted)
                #     predictions['segmentations'], 
                #     predictions["classes"], 
                #     predictions["scores"],
                #     predictions['bboxes'],
                #     im_shape=(height, width)
                # )
                
                filename = os.path.basename(image_path)[:-4]
                #cv2.imwrite(f"{save_dir}/visualizations/{filename}_RESULT.png", im_result)
                
                with open(f"{save_dir}/detections/{filename}_DETECTIONS.json", "w", encoding="utf-8") as f:
                    json.dump({"image_path": image_path, "detecctions": predictions}, f, indent=4, ensure_ascii=True)
               
            except Exception as e:
                print(f"Error en predicción: {str(e)}")
                traceback.print_exc()
                all_results.append(None)
            finally:
                self._clean_memory()
                
        return all_results
    
    def _clean_memory(self):
        gc.collect()

    def draw_detections(self, image, segmentations, classes, scores, bboxes=None, alpha=0.45, im_shape = None):
        img_out = image.copy()
        h, w = im_shape
        
        
        for i, seg in enumerate(segmentations):
            if len(seg) == 0: continue
            #print("seg:", seg)
            pts = np.array(seg)
            pts[:, 0] = np.clip(pts[:, 0] * w, 0, w)
            pts[:, 1] = np.clip(pts[:, 1] * h, 0, h)
            #print("pts:", pts)
            pts = np.array(pts, dtype=np.int32).reshape(-1, 1, 2)
            
            
            color = (255, 200, 0)
            cv2.fillPoly(img_out, [pts], color)
            
            # Se usa una validación simple de índices por si hay múltiples polígonos por caja
            # (En YOLO seg, es 1 caja -> N polígonos si el objeto está dividido visualmente)
            box_idx = i if i < len(bboxes) else 0 
            
            if bboxes is not None and box_idx < len(bboxes):
                bbox = bboxes[box_idx].copy()
                
                bbox[0] = np.clip(bbox[0] * w, 0, w)
                bbox[1] = np.clip(bbox[1] * h, 0, h)
                bbox[2] = np.clip(bbox[2] * w, 0, w)
                bbox[3] = np.clip(bbox[3] * h, 0, h)

                x1, y1, x2, y2 = map(int, bbox)
                cv2.rectangle(img_out, (x1, y1), (x2, y2), (0, 0, 255), 10)

                cls = classes[box_idx]
                score = scores[box_idx]
                label = f"{cls} {score:.2f}"
                x, y = pts[0][0]
                
                font = cv2.FONT_HERSHEY_SIMPLEX
                scale = 2
                thickness = 8
                (text_w, text_h), baseline = cv2.getTextSize(label, font, scale, thickness)

                cv2.rectangle(img_out, 
                            (x, y - text_h - baseline - 5), 
                            (x + text_w + 10, y + 5),       
                            (0, 0, 255),                    
                            -1)                             

                cv2.putText(img_out, label, 
                    (x + 5, y - baseline), 
                    font, scale, 
                    (255, 255, 255), 
                    thickness)
            
        final = cv2.addWeighted(img_out, alpha, image, 1 - alpha, 0)
        return final
    
if __name__ == "__main__":
    detector = TreeDetectorYolo().get_instance()
    from glob import glob
    
    images_path = glob("./data/trees-avocado/m3m/campo2/images/*.JPG")
    predictions = detector.predict(images_path, save_dir = "./results")