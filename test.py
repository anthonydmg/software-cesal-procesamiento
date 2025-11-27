from core.inference import TreeDetectorYolo
from core.processing import ImageSticher
import pandas as pd
import json

if __name__ == "__main__":
    dir_analsis = "./analisis/prueba-biochumbi-150-oct-test"
    with open(f"{dir_analsis}/config.json", "r") as f:
        config = json.load(f)
    

    name = config["project_info"]['name']
    print("name:", name)
    images_data = config['image_metatada']
    images_data_list = list(images_data.values())

    print("Numero de Imagenes Orignales:", len(images_data_list))
    
    metadata_rgb_files = [img_m for img_m in images_data_list if "_D.JPG" in img_m['relative_path']]
    print("Numero de Imagenes RGB:", len(metadata_rgb_files))
    # Filtramos que no son perpendiculares
    metadata_rgb_files = [ im_data for im_data in metadata_rgb_files if im_data["pitch_degree"] < -89 and im_data['pitch_degree'] > -91]
                
    for row in metadata_rgb_files:
        row["detections_path"] = f"{dir_analsis}/results/detections/{row['name'][:-4]}_DETECTIONS.json"
        
    print("Numero de Imagenes Perpendiculares:", len(metadata_rgb_files))
    total = len(metadata_rgb_files)
    processed = 0
    batch_results = {}
    
    metadata_rgb_files = metadata_rgb_files[:30]


    image_sticher = ImageSticher(images_data = metadata_rgb_files, 
                                 result_dir=f"{dir_analsis}")
    
    image_sticher.run(prefix_name=name)