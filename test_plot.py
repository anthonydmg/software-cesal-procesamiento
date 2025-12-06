import matplotlib.pyplot as plt

# Datos
sizes = [65, 35]
labels = ["Healthy", "Deficient"]
colors = ["#22A529", "#FFC000"]  # verde y amarillo

# Crear figura
fig, ax = plt.subplots(figsize=(6, 6))

# Gráfico de dona
wedges, _ = ax.pie(
    sizes,
    colors=colors,
    startangle=90,
    wedgeprops={"width": 0.25, "edgecolor": "white"}  # ancho de dona
)

# Texto centrado
ax.text(
    0, 0.15, "Healthy", ha="center", va="center", fontsize=12, color="#22A529"
)
ax.text(
    0, 0.02, "65%", ha="center", va="center", fontsize=22, fontweight="bold"
)
ax.text(
    0, -0.10, "(130 Trees)", ha="center", va="center", fontsize=10, color="gray"
)

ax.text(
    0, -0.35, "Deficient", ha="center", va="center", fontsize=12, color="#FFC000"
)
ax.text(
    0, -0.48, "35%", ha="center", va="center", fontsize=22, fontweight="bold"
)
ax.text(
    0, -0.60, "(70 Trees)", ha="center", va="center", fontsize=10, color="gray"
)

# Quitar ejes
ax.set(aspect="equal")
plt.show()
