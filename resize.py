import cv2
from PIL import Image

# Ruta de la imagen original
ruta_imagen = "./20250910_143246.jpg"

# Tamaños recomendados para EfficientNetV2
tamanios = {
    "EfficientNetV2-S": (384, 384),
    "EfficientNetV2-M": (480, 480),
    "EfficientNetV2-L": (480, 480),
    "EfficientNetV2-XL": (512, 512)
}

# --- Usando OpenCV ---
img_cv = cv2.imread(ruta_imagen)

for modelo, size in tamanios.items():
    resized = cv2.resize(img_cv, size)  # size = (width, height)
    cv2.imwrite(f"{modelo}_cv2.jpg", resized)
    print(f"Imagen guardada con OpenCV: {modelo}_cv2.jpg - {resized.shape}")

# --- Usando PIL ---
img_pil = Image.open(ruta_imagen)

for modelo, size in tamanios.items():
    resized = img_pil.resize(size, Image.Resampling.LANCZOS)
    resized.save(f"{modelo}_pil.jpg")
    print(f"Imagen guardada con PIL: {modelo}_pil.jpg - {resized.size}")