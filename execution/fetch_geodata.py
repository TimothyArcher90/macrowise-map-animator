"""
fetch_geodata.py — descarga TODO el catalogo geografico que necesita el motor.
Natural Earth (dominio publico, gratis, sin token). Se cachea en .tmp del repo (D:).

Capas: paises, estados/provincias, costas, RIOS, lagos, ciudades (con poblacion),
areas urbanas, rutas, mares/oceanos con nombre, fronteras disputadas.
"""
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from workdir import TMP  # noqa

BASE = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/"

# (archivo, para que sirve)
LAYERS = [
    ("ne_10m_admin_0_countries.geojson",           "paises (alta resolucion)"),
    ("ne_50m_admin_0_countries.geojson",           "paises (media, bordes suaves)"),
    ("ne_110m_admin_0_countries.geojson",          "paises (baja, rapido)"),
    ("ne_10m_admin_1_states_provinces.geojson",    "estados / provincias"),
    ("ne_10m_coastline.geojson",                   "linea de costa"),
    ("ne_10m_rivers_lake_centerlines.geojson",     "RIOS"),
    ("ne_50m_rivers_lake_centerlines.geojson",     "rios (media)"),
    ("ne_10m_lakes.geojson",                       "lagos"),
    ("ne_10m_populated_places.geojson",            "CIUDADES con nombre y poblacion"),
    ("ne_50m_populated_places.geojson",            "ciudades (media)"),
    ("ne_10m_urban_areas.geojson",                 "areas urbanas (manchas de ciudad)"),
    ("ne_10m_roads.geojson",                       "rutas / carreteras"),
    ("ne_10m_geography_marine_polys.geojson",      "mares y oceanos con nombre"),
    ("ne_10m_admin_0_boundary_lines_land.geojson", "lineas de frontera terrestre"),
    ("ne_10m_geography_regions_points.geojson",    "puntos geograficos con nombre"),
    ("ne_10m_ports.geojson",                       "puertos"),
    ("ne_10m_airports.geojson",                    "aeropuertos"),
]


def fetch_all(force=False):
    ok, fail = [], []
    for fname, desc in LAYERS:
        path = os.path.join(TMP, fname)
        if os.path.exists(path) and not force and os.path.getsize(path) > 1000:
            ok.append((fname, desc, os.path.getsize(path), "cache"))
            continue
        try:
            req = urllib.request.Request(BASE + fname, headers={"User-Agent": "mw-map/1.0"})
            with urllib.request.urlopen(req, timeout=300) as r, open(path, "wb") as f:
                f.write(r.read())
            ok.append((fname, desc, os.path.getsize(path), "descargado"))
            print("  OK  %-46s %s" % (fname, desc))
        except Exception as ex:
            fail.append((fname, str(ex)[:80]))
            print("  --  %-46s FALLO: %s" % (fname, str(ex)[:60]))
    return ok, fail


def load(name):
    """Carga una capa ya descargada por nombre corto (ej. 'rivers', 'cities')."""
    alias = {
        "countries": "ne_10m_admin_0_countries.geojson",
        "countries50": "ne_50m_admin_0_countries.geojson",
        "states": "ne_10m_admin_1_states_provinces.geojson",
        "coastline": "ne_10m_coastline.geojson",
        "rivers": "ne_10m_rivers_lake_centerlines.geojson",
        "lakes": "ne_10m_lakes.geojson",
        "cities": "ne_10m_populated_places.geojson",
        "urban": "ne_10m_urban_areas.geojson",
        "roads": "ne_10m_roads.geojson",
        "marine": "ne_10m_geography_marine_polys.geojson",
        "borders": "ne_10m_admin_0_boundary_lines_land.geojson",
        "ports": "ne_10m_ports.geojson",
        "airports": "ne_10m_airports.geojson",
    }
    path = os.path.join(TMP, alias.get(name, name))
    if not os.path.exists(path):
        raise SystemExit("Falta la capa %s. Corre: python fetch_geodata.py" % name)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


if __name__ == "__main__":
    print("Descargando catalogo geografico a:", TMP)
    ok, fail = fetch_all("--force" in sys.argv)
    total = sum(s for _, _, s, _ in ok)
    print("\n%d capas OK (%.1f MB), %d fallos" % (len(ok), total / 1e6, len(fail)))
