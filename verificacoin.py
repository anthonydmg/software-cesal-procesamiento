import torch, numpy, cv2, pandas, folium, osgeo, PySide6, ultralytics, dotenv

print("Torch:", torch.__version__, "CUDA disponible:", torch.cuda.is_available())
print("NumPy:", numpy.__version__)
print("Pandas:", pandas.__version__)
print("OpenCV:", cv2.__version__)
print("GDAL:", osgeo.gdal.VersionInfo())
print("PySide6:", PySide6.__version__)
print("Ultralytics:", ultralytics.__version__)
print("Dotenv:", dotenv.__version__)