import matplotlib.pyplot as plt

# Nombres de categorías
labels = [
    "SALUDABLE",
    "DEFICIENCIA"
    #"DEFICIENCIA NITROGENO",
    #"DEFICIENCIA ZINC",
    #"DEFICIENCIA MAGNESIO",
    #"DEF. NITROGENO Y ZINC",
    #"DEF. NITROGENO Y MAGNESIO",
    #"DEF. ZINC Y MAGNESIO",
    #"DEF. NITROGENO ZINC Y MAGNESIO"
]

# Valores simulados (suma debe ser 100)
sizes = [85, 15]
#, 6, 6, 8, 10, 8, 5]

# Colores aproximados de la leyenda en la imagen
colors = [
    "#00FF00",  # SALUDABLE - verde fosforescente
    "#CCFF00",  # NITROGENO - verde limón
   # "#FF9900",  # ZINC - naranja
   # "#FFD700",  # MAGNESIO - amarillo dorado
   # "#CC6600",  # NITROGENO Y ZINC - marrón claro
   # "#FFCC00",  # NITROGENO Y MAGNESIO - amarillo fuerte
   # "#FF6600",  # ZINC Y MAGNESIO - naranja fuerte
   # "#CC5500"   # NITROGENO ZINC Y MAGNESIO - marrón oscuro
]

# Crear gráficoplt.figure(figsize=(8, 8), dpi=150)  # sube el dpi (150 o 200)
plt.figure(figsize=(8, 8), dpi=200)
plt.pie(sizes, labels=labels, colors=colors, autopct='%1.1f%%', startangle=140, textprops={'fontsize': 10})
plt.axis('equal')  # Circulo perfecto
plt.tight_layout()
# Guardar con fondo gris también
plt.savefig("diagrama_pastel_deficiencias_completo_fondo_gris.png", facecolor='lightgray', transparent=True)
plt.show()