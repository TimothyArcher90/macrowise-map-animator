"""
relief.py — agrega RELIEVE 3D (hillshade) a un basemap, desde datos de elevacion
gratis (AWS Terrarium, sin token) + numpy. Liviano, sin Blender.

add_relief(basemap_path, bbox, zoom, strength) -> escribe un PNG con el mapa
texturizado con sombreado de montañas (soft-light) y lo devuelve.
"""
import io
import math
import os
import sys
import urllib.request

TILE = 256
TERR = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from workdir import TMP  # noqa: cache en D:


def _ll2tile(lon, lat, z):
    n = 2 ** z
    xt = (lon + 180) / 360 * n
    s = math.sin(math.radians(lat))
    yt = (0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)) * n
    return xt, yt


def _get(url, tries=3):
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "mw-relief/1.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except Exception:
            if k == tries - 1:
                raise


def _elevation(bbox, zoom):
    import numpy as np
    from PIL import Image
    w, s, e, n = bbox
    x0f, y0f = _ll2tile(w, n, zoom)
    x1f, y1f = _ll2tile(e, s, zoom)
    x0, y0 = int(math.floor(x0f)), int(math.floor(y0f))
    x1, y1 = int(math.floor(x1f)), int(math.floor(y1f))
    cols, rows = x1 - x0 + 1, y1 - y0 + 1
    canvas = Image.new("RGB", (cols * TILE, rows * TILE))
    for iy in range(rows):
        for ix in range(cols):
            data = _get(TERR.format(z=zoom, x=x0 + ix, y=y0 + iy))
            canvas.paste(Image.open(io.BytesIO(data)).convert("RGB"), (ix * TILE, iy * TILE))
    # recortar al bbox exacto
    gx0, gy0 = x0f * TILE, y0f * TILE
    gx1, gy1 = x1f * TILE, y1f * TILE
    ox, oy = x0 * TILE, y0 * TILE
    canvas = canvas.crop((int(gx0 - ox), int(gy0 - oy), int(gx1 - ox), int(gy1 - oy)))
    arr = np.asarray(canvas).astype("float64")
    return (arr[:, :, 0] * 256 + arr[:, :, 1] + arr[:, :, 2] / 256) - 32768


def hillshade(elev, az=315.0, alt=45.0, z_factor=2.0):
    import numpy as np
    azr = math.radians(360 - az + 90)
    altr = math.radians(alt)
    dy, dx = np.gradient(elev * z_factor, 30.0)
    slope = np.arctan(np.sqrt(dx * dx + dy * dy))
    aspect = np.arctan2(-dx, dy)
    hs = np.sin(altr) * np.cos(slope) + np.cos(altr) * np.sin(slope) * np.cos(azr - aspect)
    return np.clip(hs, 0, 1)


def add_relief(basemap_path, bbox, zoom, strength=0.6, terr_zoom=None):
    import numpy as np
    from PIL import Image
    if terr_zoom is None:
        terr_zoom = min(zoom, 10)   # terreno hasta z10 basta y limita tiles
    elev = _elevation(bbox, terr_zoom)
    hs = hillshade(elev)
    base = Image.open(basemap_path).convert("RGB")
    hs_img = Image.fromarray((hs * 255).astype("uint8")).resize(base.size, Image.LANCZOS)
    m = np.asarray(base).astype("float64") / 255
    h = (np.asarray(hs_img).astype("float64") / 255)[:, :, None]
    # soft-light: realza relieve sin ensuciar el color del mapa
    blend = np.where(h < 0.5, 2 * m * h + m * m * (1 - 2 * h),
                     2 * m * (1 - h) + np.sqrt(np.clip(m, 0, 1)) * (2 * h - 1))
    out = m * (1 - strength) + blend * strength
    out_path = basemap_path.replace(".png", "_relief.png")
    Image.fromarray((np.clip(out, 0, 1) * 255).astype("uint8")).save(out_path)
    return out_path


if __name__ == "__main__":
    import sys
    bpath = sys.argv[1]
    bbox = [float(x) for x in sys.argv[2:6]]
    zoom = int(sys.argv[6])
    print(add_relief(bpath, bbox, zoom))
