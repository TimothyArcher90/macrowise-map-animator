"""
workdir.py — directorio de trabajo/cache DENTRO del repo (.tmp).

Todo lo pesado (basemaps, tiles de elevacion, GeoJSON, secuencias de frames del
render) vive en el .tmp del repo. El repo entero debe vivir en el disco duro D:
(copia local) y espejarse en GitHub -> asi nada pesa en C: y todo queda en el repo.
.tmp esta en .gitignore (cache regenerable, no se sube).
"""
import os

TMP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".tmp")
os.makedirs(TMP, exist_ok=True)
