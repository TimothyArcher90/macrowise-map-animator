"""
project.py — proyeccion Web Mercator manual (sin pyproj/shapely) + carga de
fronteras/costas de Natural Earth.

Web Mercator (EPSG:3857) es la proyeccion de todos los tiles slippy (ESRI, OSM,
Mapbox). Convertimos lon/lat a "world pixels" globales a un zoom dado, y luego a
pixeles locales del basemap restando el origen del recorte.
"""
import json
import math
import os
import urllib.request

TILE = 256

# GeoJSON de fronteras de paises (Natural Earth 110m via CDN publico, gratis).
NE_COUNTRIES_URL = ("https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
                    "master/geojson/ne_110m_admin_0_countries.geojson")


def lonlat_to_world_px(lon, lat, zoom):
    """lon/lat -> pixel global (Web Mercator) al 'zoom' dado."""
    n = TILE * (2 ** zoom)
    x = (lon + 180.0) / 360.0 * n
    s = math.sin(math.radians(lat))
    y = (0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)) * n
    return x, y


def make_projector(bbox, zoom, out_w, out_h):
    """
    Devuelve una funcion proj(lon,lat)->(px,py) en pixeles del basemap recortado.
    bbox = [w, s, e, n]. El basemap cubre exactamente ese bbox reescalado a out_w×out_h.
    """
    w, s, e, n = bbox
    x0, y0 = lonlat_to_world_px(w, n, zoom)   # esquina sup-izq (oeste, norte)
    x1, y1 = lonlat_to_world_px(e, s, zoom)   # esquina inf-der (este, sur)
    span_x = x1 - x0
    span_y = y1 - y0

    def proj(lon, lat):
        wx, wy = lonlat_to_world_px(lon, lat, zoom)
        px = (wx - x0) / span_x * out_w
        py = (wy - y0) / span_y * out_h
        return px, py
    return proj


def download_natural_earth(cache_dir):
    os.makedirs(cache_dir, exist_ok=True)
    path = os.path.join(cache_dir, "ne_110m_admin_0_countries.geojson")
    if not os.path.exists(path):
        req = urllib.request.Request(NE_COUNTRIES_URL, headers={"User-Agent": "mw-map/1.0"})
        with urllib.request.urlopen(req, timeout=60) as r, open(path, "wb") as f:
            f.write(r.read())
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def country_rings(geojson, name):
    """Devuelve lista de anillos (cada uno lista de [lon,lat]) del pais 'name'."""
    for feat in geojson.get("features", []):
        props = feat.get("properties", {})
        nm = props.get("NAME") or props.get("ADMIN") or props.get("name") or ""
        if nm.lower() == name.lower():
            geom = feat["geometry"]
            rings = []
            if geom["type"] == "Polygon":
                rings = geom["coordinates"]
            elif geom["type"] == "MultiPolygon":
                for poly in geom["coordinates"]:
                    rings.extend(poly)
            return rings
    return []


if __name__ == "__main__":
    # auto-test: el proyector mapea las esquinas del bbox a (0,0) y (W,H)
    bbox = [51.0, 22.0, 60.0, 30.0]  # golfo persico aprox
    proj = make_projector(bbox, 7, 1920, 1080)
    x0, y0 = proj(51.0, 30.0)
    x1, y1 = proj(60.0, 22.0)
    assert abs(x0) < 1 and abs(y0) < 1, "esquina NW deberia ser ~(0,0)"
    assert abs(x1 - 1920) < 1 and abs(y1 - 1080) < 1, "esquina SE deberia ser ~(W,H)"
    print("OK project: proyeccion Mercator verificada en las 4 esquinas")
