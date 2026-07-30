"""
caspian_base.py — ingenieria inversa del look de Caspian Report: genera un basemap
de RELIEVE HIPSOMETRICO desde datos de elevacion gratis (AWS Terrarium) + numpy.

Capas (como las arma Caspian en AE, pero automatico):
  1. Tinte hipsometrico: color por altura (verde bajo -> tostado -> montaña oscura -> nieve).
  2. Hillshade fuerte: sombreado de relieve 3D (multiply) para dar volumen.
  3. Agua estilizada: teal con gradiente de profundidad (batimetria).
Resultado: la base tostada con montañas en 3D, identica en espiritu a su mapa de Iran.
"""
import math
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


def softlight(b, s):
    """Soft-light del W3C. A diferencia de MULTIPLY, preserva la luminancia:
    apilar hillshade x AO x color por multiplicacion oscurece ~39% (medido),
    porque cada capa tiene media <1 y las medias se multiplican."""
    import numpy as np
    d = np.where(b <= 0.25, ((16 * b - 12) * b + 4) * b, np.sqrt(np.clip(b, 0, 1)))
    return np.where(s <= 0.5, b - (1 - 2 * s) * b * (1 - b), b + (2 * s - 1) * (d - b))


def norm_mid(a, strength=1.0):
    """Re-centra una capa de sombra en 0.5 (el punto neutro de soft-light).
    SIN esto, una capa con media 0.35 actua como un multiply disfrazado y
    oscurece igual. Es la clave del apilado cartografico correcto."""
    import numpy as np
    a = (a - a.mean()) / (a.std() + 1e-9)
    return np.clip(0.5 + a * 0.18 * strength, 0, 1)


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


# Tema OSCURO CON VIDA: no negro plano — verdes profundos en tierras bajas,
# ocres en zonas secas, roca clara en la altura. El relieve se lee.
HYPSO_DARK = [
    (0,    (72, 104, 82)),    # verde vivo (llanura vegetada)
    (350,  (86, 112, 84)),
    (900,  (114, 118, 86)),   # vira a ocre
    (1800, (140, 126, 94)),
    (2800, (158, 144, 118)),  # roca
    (4000, (186, 178, 166)),
    (5500, (234, 236, 238)),  # nieve
]
# calibrados PRE-boost: el gamma/brillo final los levanta, asi que se parten
# mas oscuros para aterrizar en un azul solido (no cian electrico).
WATER_DARK_SHALLOW = (30, 108, 168)
WATER_DARK_DEEP = (14, 68, 118)


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

    # APILADO CARTOGRAFICO (orden Imhof/Suizo) en SOFT-LIGHT normalizado, no
    # multiply: el multiply oscurecia ~39%. Cada capa se re-centra en 0.5.
    #   1) multi-direccional (volumen, crestas en todas las orientaciones)
    #   2) luz clave a 315 grados (da la lectura y la direccion)
    shaded = land
    hs_multi = np.zeros_like(elev, dtype="float64")
    for az in (225.0, 270.0, 315.0, 360.0):          # las 4 del USGS OF 92-422
        hs_multi += hillshade(elev, az=az, alt=45, z_factor=z_factor)
    hs_multi /= 4.0
    shaded = softlight(shaded, norm_mid(hs_multi, 1.0)[:, :, None])
    hs_key = hillshade(elev, az=315, alt=42, z_factor=z_factor)
    shaded = softlight(shaded, norm_mid(hs_key, 1.5 if dark else 1.2)[:, :, None])
    shaded = np.clip(shaded, 0, 1)

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


def add_life(base_path, bbox, zoom, amount=0.45, sat=1.25, dark=False, out_path=None):
    """DA VIDA al terreno mezclando imagen SATELITAL real (vegetacion, desiertos,
    bosques) sobre la base estilizada. El satelite aporta color y micro-detalle;
    la base aporta el relieve y la paleta. Resultado: terreno vivo, no plano.

    amount: cuanto satelite se mezcla (0.3-0.6 suele ser lo bueno)
    sat:    saturacion final (>1 = mas vivo)
    """
    import numpy as np
    from PIL import Image, ImageEnhance
    from fetch_basemap import fetch

    sat_path = base_path.replace(".png", "_sat.png")
    if not os.path.exists(sat_path):
        fetch(bbox, min(zoom, 9), sat_path, source="esri")

    base = Image.open(base_path).convert("RGB")
    sky = Image.open(sat_path).convert("RGB").resize(base.size, Image.LANCZOS)
    b = np.asarray(base).astype("float64") / 255.0
    s = np.asarray(sky).astype("float64") / 255.0

    # el satelite entra en SOFT LIGHT: aporta textura y color sin tapar la paleta
    soft = np.where(s < 0.5, 2 * b * s + b * b * (1 - 2 * s),
                    2 * b * (1 - s) + np.sqrt(np.clip(b, 0, 1)) * (2 * s - 1))
    mixed = b * (1 - amount) + soft * amount
    # ademas un toque del color crudo del satelite (vegetacion real)
    mixed = mixed * 0.80 + s * 0.20
    mixed = np.clip(mixed, 0, 1)

    # EXPOSICION ADAPTATIVA: un terreno de nieve (Himalaya) o desierto (Sahel) ya
    # viene claro; aplicarle el mismo boost que a una selva oscura lo QUEMA. Se
    # mide la luminancia media y se ajusta el gamma para aterrizar en un target.
    lum = float(mixed.mean())
    target = 0.46
    gamma = math.log(max(target, 1e-3)) / math.log(max(lum, 1e-3))
    gamma = max(0.62, min(1.35, gamma))          # tope: no exagerar en ninguno
    mixed = np.power(mixed, gamma)
    mixed = 0.035 + mixed * 0.955                # lift suave de negros

    # ROLLOFF DE ALTAS LUCES (filmico): comprime por encima de 0.72 en vez de
    # clipear a blanco. Es lo que evita que la nieve y la arena se "quemen".
    knee = 0.72
    hi = mixed > knee
    mixed[hi] = knee + (1 - knee) * np.tanh((mixed[hi] - knee) / (1 - knee) * 1.6) / \
        np.tanh(1.6)
    mixed = np.clip(mixed, 0, 1)

    img = Image.fromarray((mixed * 255).astype("uint8"), "RGB")
    img = ImageEnhance.Color(img).enhance(sat)        # vida
    img = ImageEnhance.Contrast(img).enhance(1.05)
    out_path = out_path or base_path.replace(".png", "_life.png")
    img.save(out_path)
    return out_path


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
