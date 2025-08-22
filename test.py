from core.inference import TreeDetectorYolo
from core.processing import ImageSticher
import pandas as pd

if __name__ == "__main__":

    df_images = pd.read_csv("./df_images_metadata.csv")
    df_images_slice = df_images.iloc[:50,:]
    print(df_images_slice)
    
    images_path = df_images_slice['relative_path'].to_list()
    detector = TreeDetectorYolo().get_instance()
    predictions = detector.predict(images_path, save_dir = "./results")

    assert len(predictions) == len(df_images_slice), "El numero de predicciones deber ser igual a la cantidad de imaganes"

    df_images_data = pd.concat([df_images_slice, pd.DataFrame(predictions)], axis=1)
    print("df_images_data:", df_images_data.head())

    df_images_data.to_csv("./df_images_data.csv", index = False)
    #generate_mosaic(df_images.to_dict(orient='index'), type_align_matrix = "affine", signal_progress = None)
    image_sticher = ImageSticher(images_data= df_images_data.to_dict(orient='index'))

    image_sticher.run(save_dir = "./mosaic", 
                      prefix_name="Vuelo-Agosto-16-Campo2-Accopampa")