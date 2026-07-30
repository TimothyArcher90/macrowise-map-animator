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


def _hex(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


# Rampa hipsometrica CLARA estilo Caspian (terreno de papel crema/tostado, suave).
# El color del pais va ENCIMA semi-transparente, asi que la base es tenue.
HYPSO = [
    (0,    (226, 220, 200)),   # tierras bajas crema
    (300,  (222, 212, 186)),   # llanura tostada clara
    (900,  (212, 196, 166)),   # tostado
    (1800, (196, 176, 148)),   # colina
    (3000, (182, 162, 140)),   # montaña
    (4200, (198, 186, 172)),   # roca clara
    (5500, (238, 234, 228)),   # nieve
]
# agua: azul Caspian plano (leve gradiente)
WATER_SHALLOW = (168, 200, 216)
WATER_DEEP = (120, 165, 190)


def _ramp(elev, stops=None):
    import numpy as np
    h, w = elev.shape
    out = np.zeros((h, w, 3), dtype="float64")
    stops = stops or HYPSO
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


# Tema OSCURO: tierra casi negra con relieve sutil + oceano azul brillante
HYPSO_DARK = [
    (0,    (26, 30, 34)),
    (400,  (30, 35, 40)),
    (1200, (38, 44, 50)),
    (2500, (48, 55, 62)),
    (4200, (64, 72, 80)),
    (5500, (96, 104, 112)),
]
WATER_DARK_SHALLOW = (58, 158, 224)
WATER_DARK_DEEP = (28, 118, 190)


def build_caspian(bbox, zoom, out_path, z_factor=2.6, tints=None, theme="light"):
    """Terreno claro estilo Caspian + tinte de pais semi-transparente ENCIMA
    (el terreno se ve a traves del color). tints: {pais: '#hex'} o {pais: ['#hex', alpha]}."""
    import numpy as np
    from PIL import Image, ImageFilter, ImageDraw
    dark = (theme == "dark")
    elev = _elevation(bbox, min(zoom, 10))
    land = _ramp(elev, HYPSO_DARK if dark else None) / 255.0
    lum = land.mean(axis=2, keepdims=True)
    land = land * 0.85 + lum * 0.15   # leve desaturacion

    # hillshade: en oscuro va mas marcado (la textura es lo unico que se ve)
    hs = hillshade(elev, az=315, alt=45, z_factor=z_factor)[:, :, None]
    shaded = np.clip(land * ((0.55 + 0.85 * hs) if dark else (0.74 + 0.42 * hs)), 0, 1)

    # agua con DEGRADADO DE PROFUNDIDAD marcado (claro en la costa -> azul intenso
    # mar adentro), como en la referencia. Curva gamma para que el cambio se note
    # en la plataforma continental, no solo en fosas abisales.
    ws = WATER_DARK_SHALLOW if dark else WATER_SHALLOW
    wd = WATER_DARK_DEEP if dark else WATER_DEEP
    depth = np.clip(-elev, 0, 2500) / 2500.0
    depth = np.power(depth, 0.45)[:, :, None]
    water = (np.array(ws) / 255.0)[None, None, :] * (1 - depth) + \
            (np.array(wd) / 255.0)[None, None, :] * depth
    is_water = (elev <= 0)[:, :, None]
    img = np.where(is_water, water, shaded)

    # --- TINTE DE PAIS semi-transparente (la firma de Caspian) ---
    if tints:
        from project import make_projector, download_natural_earth, country_rings
        H, Wc = img.shape[0], img.shape[1]
        proj = make_projector(bbox, 5, Wc, H)
        ge = download_natural_earth(os.path.join(HERE, "..", ".tmp"), res="50m")
        landmask = (~(elev <= 0))
        for name, spec in tints.items():
            if isinstance(spec, (list, tuple)):
                hexc, a = spec[0], float(spec[1])
            else:
                hexc, a = spec, 0.42
            col = np.array(_hex(hexc)) / 255.0
            m = Image.new("L", (Wc, H), 0)
            md = ImageDraw.Draw(m)
            for ring in country_rings(ge, name):
                if len(ring) > 2:
                    md.polygon([tuple(proj(lo, la)) for lo, la in ring], fill=255)
            k = (np.asarray(m).astype("float64") / 255.0)[:, :, None] * a
            k = k * landmask[:, :, None]      # el tinte NO pinta el mar
            # MULTIPLY (tecnica canonica GEOlayers/AE): preserva el relieve bajo el
            # color en vez de taparlo. Sobre terreno CLARO (desierto) el multiply
            # lava el color, asi que se compensa saturando segun la luminosidad.
            mult = img * col[None, None, :]
            mult = mult * 0.82 + (1 - (1 - img) * (1 - col[None, None, :] * 0.35)) * 0.18
            terrain_lum = img.mean(axis=2, keepdims=True)
            boost = np.clip((terrain_lum - 0.45) * 1.15, 0, 0.5)   # 0 en oscuro, ~.5 en claro
            mult = mult * (1 - boost) + col[None, None, :] * boost
            img = img * (1 - k) + mult * k

    out = Image.fromarray((np.clip(img, 0, 1) * 255).astype("uint8"))
    out = out.filter(ImageFilter.UnsharpMask(radius=2, percent=45))
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
