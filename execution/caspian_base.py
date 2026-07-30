"""
caspian_base.py — ingenieria inversa del look de Caspian Report: genera un basemap
de RELIEVE HIPSOMETRICO desde datos de elevacion gratis (AWS Terrarium) + numpy.

Capas (como las arma Caspian en AE, pero automatico):
  1. Tinte hipsometrico: color por altura (verde bajo -> tostado -> montaña oscura -> nieve).
  2. Hillshade fuerte: sombreado de relieve 3D (multiply) para dar volumen.
  3. Agua estilizada: teal con gradiente de profundidad (batimetria).
Resultado: la base tostada con montañas en 3D, identica en espiritu a su mapa de Iran.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from relief import _elevation, hillshade  # noqa


# Rampa hipsometrica (elevacion m -> RGB), calibrada al look Caspian (tierra calida).
# puntos: (altura, color)
HYPSO = [
    (0,    (196, 214, 178)),   # costa / tierras bajas verdosas
    (200,  (206, 208, 160)),   # llanura
    (600,  (216, 200, 150)),   # tostado
    (1200, (206, 178, 128)),   # tostado medio
    (2000, (170, 140, 100)),   # montaña
    (3000, (135, 110, 85)),    # montaña alta
    (4000, (170, 155, 140)),   # roca gris
    (5500, (235, 232, 226)),   # nieve
]
# agua: teal con profundidad
WATER_SHALLOW = (108, 165, 178)
WATER_DEEP = (70, 120, 140)


def _ramp(elev):
    import numpy as np
    h, w = elev.shape
    out = np.zeros((h, w, 3), dtype="float64")
    stops = HYPSO
    e = np.clip(elev, 0, 6000)
    for i in range(len(stops) - 1):
        a_h, a_c = stops[i]
        b_h, b_c = stops[i + 1]
        mask = (e >= a_h) & (e < b_h)
        if not mask.any():
            continue
        t = ((e[mask] - a_h) / (b_h - a_h))[:, None]
        out[mask] = np.array(a_c) * (1 - t) + np.array(b_c) * t
    out[e >= stops[-1][0]] = stops[-1][1]
    return out


def build_caspian(bbox, zoom, out_path, z_factor=2.9):
    import numpy as np
    from PIL import Image, ImageFilter
    elev = _elevation(bbox, min(zoom, 10))
    land = _ramp(elev) / 255.0
    # desaturar ~18% -> tonos tierra naturales (no ultrasaturado), estilo Caspian/JH
    lum = land.mean(axis=2, keepdims=True)
    land = land * 0.82 + lum * 0.18

    # hillshade para volumen 3D (mas suave, menos duro)
    hs = hillshade(elev, az=315, alt=42, z_factor=z_factor)[:, :, None]
    shaded = land * (0.62 + 0.74 * hs)
    shaded = np.clip(shaded, 0, 1)

    # agua: batimetria teal donde elev <= 0
    depth = np.clip(-elev, 0, 4000) / 4000.0
    water = (np.array(WATER_SHALLOW) / 255.0)[None, None, :] * (1 - depth[:, :, None]) + \
            (np.array(WATER_DEEP) / 255.0)[None, None, :] * depth[:, :, None]
    is_water = (elev <= 0)[:, :, None]
    img = np.where(is_water, water, shaded)

    out = Image.fromarray((np.clip(img, 0, 1) * 255).astype("uint8"))
    # microcontraste + leve suavizado para look editorial
    out = out.filter(ImageFilter.UnsharpMask(radius=2, percent=60))
    out.save(out_path)
    return out_path, out.size


def apply_highlight(basemap_path, bbox, names, out_path=None):
    """Mascara por pais (look Caspian): el/los pais(es) 'names' quedan a todo color;
    el resto se desatura y oscurece. Usa polígonos de Natural Earth."""
    import numpy as np
    from PIL import Image, ImageDraw, ImageFilter
    from project import make_projector, download_natural_earth, country_rings
    base = Image.open(basemap_path).convert("RGB")
    bw, bh = base.size
    proj = make_projector(bbox, 5, bw, bh)   # el zoom se cancela en make_projector
    ge = download_natural_earth(os.path.join(HERE, "..", ".tmp"))
    mask = Image.new("L", (bw, bh), 0)
    md = ImageDraw.Draw(mask)
    for nm in names:
        for ring in country_rings(ge, nm):
            if len(ring) > 2:
                md.polygon([tuple(proj(lo, la)) for lo, la in ring], fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(3))
    m = np.asarray(base).astype("float64") / 255
    k = (np.asarray(mask).astype("float64") / 255)[:, :, None]
    # afuera: NO a gris — solo atenuar sutil (mantiene relieve y color natural).
    # el pais protagonista destaca por CONTRASTE, no por apagar a los vecinos.
    lum = (m[:, :, 0] * 0.299 + m[:, :, 1] * 0.587 + m[:, :, 2] * 0.114)[:, :, None]
    dim = (m * 0.72 + lum * 0.28) * 0.90   # 28% desaturado + 10% mas oscuro
    out = m * k + dim * (1 - k)
    out_path = out_path or basemap_path.replace(".png", "_hl.png")
    Image.fromarray((np.clip(out, 0, 1) * 255).astype("uint8")).save(out_path)
    return out_path


if __name__ == "__main__":
    bbox = [float(x) for x in sys.argv[1:5]]
    zoom = int(sys.argv[5])
    out = sys.argv[6]
    p, sz = build_caspian(bbox, zoom, out)
    print("OK caspian base:", p, sz)
