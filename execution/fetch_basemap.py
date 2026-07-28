"""
fetch_basemap.py — arma un PNG satelital de un bbox cosiendo tiles de ESRI World
Imagery (XYZ publico, sin token, gratis).

Uso:
  python fetch_basemap.py --bbox 51 22 60 30 --zoom 7 --out basemap.png
Devuelve por stdout la metadata (bbox, zoom, tamano px) que consume build_map_native.py.
"""
import argparse
import io
import json
import math
import os
import sys
import time
import urllib.request

TILE = 256
SOURCES = {
    # satelite (Johnny Harris look)
    "esri": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    # claro politico tipo Google Maps (gratis, sin token) — "linea grafica" clara
    "carto": "https://basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png",
    "carto_light": "https://basemaps.cartocdn.com/rastertiles/light_all/{z}/{x}/{y}.png",
    # oscuro estilo Caspian (gratis, sin token)
    "carto_dark": "https://basemaps.cartocdn.com/rastertiles/dark_all/{z}/{x}/{y}.png",
}
ESRI = SOURCES["esri"]


def lonlat_to_tile(lon, lat, z):
    n = 2 ** z
    xt = (lon + 180.0) / 360.0 * n
    s = math.sin(math.radians(lat))
    yt = (0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)) * n
    return xt, yt


def fetch(bbox, zoom, out_path, source="esri"):
    from PIL import Image
    tpl = SOURCES.get(source, ESRI)
    w, s, e, n = bbox
    x0f, y0f = lonlat_to_tile(w, n, zoom)   # NW
    x1f, y1f = lonlat_to_tile(e, s, zoom)   # SE
    x0, y0 = int(math.floor(x0f)), int(math.floor(y0f))
    x1, y1 = int(math.floor(x1f)), int(math.floor(y1f))
    cols, rows = (x1 - x0 + 1), (y1 - y0 + 1)
    if cols * rows > 400:
        raise SystemExit("bbox/zoom demasiado grande (%d tiles). Bajá el zoom." % (cols * rows))

    canvas = Image.new("RGB", (cols * TILE, rows * TILE))
    for iy in range(rows):
        for ix in range(cols):
            xt, yt = x0 + ix, y0 + iy
            url = tpl.format(z=zoom, x=xt, y=yt)
            data = _get(url)
            tile = Image.open(io.BytesIO(data)).convert("RGB")
            canvas.paste(tile, (ix * TILE, iy * TILE))

    # recortar el canvas de tiles al bbox exacto (en pixeles globales)
    gx0, gy0 = x0f * TILE, y0f * TILE
    gx1, gy1 = x1f * TILE, y1f * TILE
    ox = x0 * TILE
    oy = y0 * TILE
    crop = (int(gx0 - ox), int(gy0 - oy), int(gx1 - ox), int(gy1 - oy))
    img = canvas.crop(crop)
    img.save(out_path, "PNG")
    return {"bbox": bbox, "zoom": zoom, "w": img.width, "h": img.height, "path": out_path}


def _get(url, tries=3):
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "mw-map/1.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except Exception as ex:
            if k == tries - 1:
                raise
            time.sleep(1.0 + k)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bbox", nargs=4, type=float, required=True, metavar=("W", "S", "E", "N"))
    ap.add_argument("--zoom", type=int, default=7)
    ap.add_argument("--source", default="esri", choices=list(SOURCES))
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    meta = fetch(a.bbox, a.zoom, a.out, a.source)
    print(json.dumps(meta))


if __name__ == "__main__":
    main()
