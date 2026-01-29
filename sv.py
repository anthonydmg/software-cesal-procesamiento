from PIL import Image
import numpy as np

# Rutas
ruta_entrada = "./ejemplo/DJI_20251016105510_0140_D_MASK.JPG"
ruta_salida = "./ejemplo/mascara.png"

# Leer imagen y convertir a escala de grises
img = Image.open(ruta_entrada).convert("L")

# Convertir a numpy
img_np = np.array(img)

# Crear máscara: todo lo > 0 pasa a 1
mascara = (img_np > 0).astype(np.uint8)

# Opcional: escalar a 0 y 255 para visualización correcta
mascara = mascara * 255

# Guardar como PNG
mascara_img = Image.fromarray(mascara)
mascara_img.save(ruta_salida)

print("Máscara guardada en:", ruta_salida)