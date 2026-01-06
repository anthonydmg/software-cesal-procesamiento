#from core.deficiency_classifier import NitrogenDefClassifer
from core.inference import TreeDetectorYolo
from core.processing import ImageSticher
import pandas as pd
import json
import cv2
import numpy as np

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
        
        
        mask = cv2.imread(r['mask_path'],cv2.IMREAD_GRAYSCALE)
        # 1. Asegurar que la máscara sea 2D
        if len(mask.shape) == 3:
            mask = mask.squeeze()

        h, w = mask.shape
        y_max = y_min + h
        x_max = xmin + w

        roi = mosaic_base[y_min:y_max, xmin:x_max]
        pixeles_base = roi[mask > 0, :3]
        color_mask = COLOR_DEFICIENCIA if r['class'].upper() == "DEFICIENCIA" else COLOR_SALUDABLE
        overlay_pixels = (pixeles_base * (1 - alpha_overlay)) + (color_mask * alpha_overlay)
        
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
    cv2.imwrite(path_map_trees, mosaic_base)
    return path_map_trees

# def create_map_trees_ids(mosaic_path = None, mosaic_image = None, base_dir = None):
#     if mosaic_image is not None:
#         mosaic_base = mosaic_image
#     elif mosaic_path is not None:
#         mosaic_base = cv2.imread(mosaic_path)

#     path_trees_results = f"{base_dir}/mosaic/trees/trees_results.json"

#     trees_results = []
    
#     print("mosaic_base:", mosaic_base.shape)
#     with open(path_trees_results, 'r') as f:
#         trees_results = json.load(f)

#     # Definimos colores en BGR
#     try:
#         num_canales = mosaic_base.shape[2]
#     except IndexError:
#         num_canales = 1 # Imagen en escala de grises

#     if num_canales == 4:
#         print("Imagen BGRA detectada. Usando colores con canal Alpha.")
#         # [Azul, Verde, Rojo, Alpha] -> Alpha 255 es opaco
#         COLOR_ROJO = (0, 0, 255, 255)
#         COLOR_BLANCO = (255, 255, 255, 255)
#     else:
#         print("Imagen BGR estándar detectada.")
#         COLOR_ROJO = (0, 0, 255)
#         COLOR_BLANCO = (255, 255, 255)

#     font = cv2.FONT_HERSHEY_SIMPLEX
#     scale_font = 2
#     thickness_font = 2
#     alpha_overlay = 0.5

#     COLOR_SALUDABLE = np.array([0, 255, 50], dtype=np.uint8)
#     COLOR_DEFICIENCIA = np.array([0, 247, 191],  dtype=np.uint8)

#     for r in trees_results:
#         xmin, y_min, x_max, y_max = r['bbox']
#         x_c = (xmin + x_max) // 2
#         y_c = (y_min + y_max) // 2
#         coord_center = (x_c, y_c)
#         tree_id = r["id"]
        
        
#         mask = cv2.imread(r['mask_path'],cv2.IMREAD_GRAYSCALE)
#         # 1. Asegurar que la máscara sea 2D
#         if len(mask.shape) == 3:
#             mask = mask.squeeze()

#         h, w = mask.shape
#         y_max = y_min + h
#         x_max = xmin + w

#         roi = mosaic_base[y_min:y_max, xmin:x_max]
#         pixeles_base = roi[mask > 0, :3]
#         color_mask = COLOR_DEFICIENCIA if r['class'].upper() == "DEFICIENCIA" else COLOR_SALUDABLE
#         overlay_pixels = (pixeles_base * (1 - alpha_overlay)) + (color_mask * alpha_overlay)
        
#         roi[mask > 0, :3] = overlay_pixels.astype(np.uint8)

#         #
#         #overlay = 
#         texto = str(tree_id)
        
#         (ancho_text, alto_text), linea_base = cv2.getTextSize(texto, font, scale_font, thickness_font)

#         # Calculamos la posición de la esquina inferior izquierda del texto para que quede centrado
#         x_text = coord_center[0] - (ancho_text // 2)
#         y_text = coord_center[1] + (alto_text // 2)
#         posicion_text = (x_text, y_text)
        

#         cv2.circle(
#             mosaic_base,
#             coord_center,
#             15,
#             COLOR_ROJO,
#             thickness=-1
#         )

#         # Dibujamos el texto
#         cv2.putText(
#             mosaic_base,
#             texto,
#             posicion_text,
#             font,
#             scale_font,
#             COLOR_BLANCO,
#             thickness_font,
#             lineType=cv2.LINE_AA # LINE_AA hace que los bordes del texto se vean suaves
#         )

#     path_map_trees = f"{base_dir}/mosaic/rgb/map_trees_ids.png"

#     print("path_map_trees:", path_map_trees)
#     cv2.imwrite(path_map_trees, mosaic_base)

if __name__ == "__main__":
    # NitrogenDefClassifer.configure("./best_resnet18_6ch.pth")

    # #NitrogenDefClassifer.build_cube_and_predict()

    # detections = []
    # with open("./analisis\prueba-biochumbi-60/results/unique_trees_detections/unique_detections.json", 'r') as f:
    #     detections = json.load(f)

    # detect = detections[0]
    # img_path = detect["img_path"]
    # corner = detect["corner"]
    # mask_cropped_path = detect['mask_cropped_path']
    # mask = cv2.imread(mask_cropped_path,cv2.IMREAD_GRAYSCALE)
    # # 1. Asegurar que la máscara sea 2D
    # if len(mask.shape) == 3:
    #     mask = mask.squeeze()
    
    # dir_analsis = "./analisis/prueba-biochumbi-60"
    # with open(f"{dir_analsis}/config.json", "r") as f:
    #     config = json.load(f)
    

    # name = config["project_info"]['name']
    # print("name:", name)
    # images_data = config['image_metatada']
    # all_images_data_metadata = list(images_data.values())
    # all_images_metadada_dict = {img_m['name']:img_m for img_m in all_images_data_metadata}
    # prediction, hypercube = NitrogenDefClassifer.build_cube_and_predict(img_path, mask, corner, all_images_metadada_dict)
    # print("prediction:", prediction)
    # print("hypercube:", hypercube.shape)
    # ndvi = hypercube[4,:,:]
    # print("ndvi:", ndvi.max())
    # avg_ndvi = ndvi[ndvi > 0.5].mean()
    # print("avg_ndvi:", avg_ndvi)
    # create_map_trees_ids(mosaic_image= None, 
    #                      mosaic_path = "C:/Users/antho/Local/cesal-proyecto/software-cesal-procesamiento/analisis\\prueba-60-bio/mosaic/rgb/mosaic_prueba-60-bio.tif", 
    #                      base_dir = "C:/Users/antho/Local/cesal-proyecto/software-cesal-procesamiento/analisis\\prueba-60-bio")
    
    dir_analsis = "./analisis/prueba-biochumbi-150-oct-test"
    with open(f"{dir_analsis}/config.json", "r") as f:
        config = json.load(f)
    

    name = config["project_info"]['name']
    print("name:", name)
    images_data = config['image_metatada']
    all_images_data_metadata = list(images_data.values())

    print("Numero de Imagenes Orignales:", len(all_images_data_metadata))
    # Filtramos que no son perpendiculares
    all_images_data_metadata = [ im_data for im_data in all_images_data_metadata if im_data["pitch_degree"] < -89 and im_data['pitch_degree'] > -91]

    print("Numero de Imagenes Perpendiculares:", len(all_images_data_metadata))

    metadata_rgb_files = [img_m for img_m in all_images_data_metadata if "_D.JPG" in img_m['relative_path']]

                
    for row in metadata_rgb_files:
        row["detections_path"] = f"{dir_analsis}/results/detections/{row['name'][:-4]}_DETECTIONS.json"
        
    print("Numero de Imagenes Perpendiculares:", len(metadata_rgb_files))
    total = len(metadata_rgb_files)
    processed = 0
    batch_results = {}
    
    #metadata_rgb_files = metadata_rgb_files[:30]


    image_sticher = ImageSticher(images_data = all_images_data_metadata, 
                                 result_dir=f"{dir_analsis}")
    
    image_sticher.run(prefix_name=name)

 