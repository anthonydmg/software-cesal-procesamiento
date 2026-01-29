import cv2
import numpy as np
import json

def load_gray16(path):
    I = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    print("I:", I.shape)
    print("I.ndim:", I.ndim)
    if I is None:
        raise RuntimeError(f"Could not read {path}")
    if I.ndim == 3 and I.shape[-1] > 1:
        I = cv2.cvtColor(I, cv2.COLOR_BGR2GRAY)
    if I.shape[-1] == 1:
        I = I.squeeze()
    return I

def ndvi_to_drgb(band_path, rgb_path, H_dewarp):
    """
    NDVI currently on 'designed image plane'.
    Apply Dewarp HMatrix (designed → designed RGB image plane).
    """
    band_image = load_gray16(band_path)
    rgb = cv2.imread(rgb_path, cv2.IMREAD_UNCHANGED)
    if rgb is None:
        raise RuntimeError("Cannot read RGB image")
    H_dewarp = np.array(H_dewarp)
    #m = exif_read(red_path)
    #H_dewarp = m["H_dewarp"]
    h_out, w_out =  rgb.shape[:2]
    ndvi_on_drgb = cv2.warpPerspective(band_image, H_dewarp, (w_out, h_out), flags=cv2.INTER_LINEAR)
    return ndvi_on_drgb


if __name__ == "__main__":
    with open("./analisis\prueba-biochumbi-150-oct\config.json", "r") as f:
        data = json.load(f)
    image_metatada = data['image_metatada']
    im_meta = image_metatada['699']
    H_dewarp = im_meta['H_dewarp']
    band_relative_path = im_meta['relative_path']
    rgb_path = "C:/Users/antho/Local/cesal-proyecto/software-cesal-procesamiento/data/trees-avocado/m3m/biochumbi/prueba-octubre-150\\DJI_20251016105510_0140_D.JPG"
    band_aligned = ndvi_to_drgb(band_relative_path, rgb_path, H_dewarp)
    
    cv2.imwrite("./band_REDEDGE.png", band_aligned)
    #print(image_metatada['696'])