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