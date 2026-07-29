"""
vector_base.py — estilo VECTOR PLANO geopolitico (colores precisos por pais + borde),
como el manual GeoLayers. Cada pais = color solido exacto, borde negro, oceano solido.

A diferencia del relieve hipsometrico (color por altura = "sucio"), esto da colores
limpios y precisos por pais. Usa poligonos de Natural Earth.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from project import make_projector, download_natural_earth, lonlat_to_world_px  # noqa


def _hex(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


# Paleta MacroWise para rellenos geopoliticos (limpios, distintos, sobrios)
DEFAULT_FILL = "#CBC6BC"      # Stone
OCEAN = "#DCE3E8"            # azul-gris claro
BORDER = "#1A1A26"          # Ink
HIGHLIGHT = "#C9A84C"        # oro MacroWise
MUTED_SET = ["#CBC6BC", "#B8B3A9", "#D6D1C8", "#B8B8C4", "#A0A0B4", "#C9C4CE"]


def build_vector(bbox, out_path, W=2600, country_colors=None, highlight=None,
                 ocean=OCEAN, border=BORDER, default_fill=DEFAULT_FILL,
                 highlight_fill=HIGHLIGHT, border_px=3):
    from PIL import Image, ImageDraw
    country_colors = country_colors or {}
    highlight = set(highlight or [])

    # aspecto Mercator del bbox
    w, s, e, n = bbox
    x0, y0 = lonlat_to_world_px(w, n, 8)
    x1, y1 = lonlat_to_world_px(e, s, 8)
    H = int(W * (y1 - y0) / (x1 - x0))
    proj = make_projector(bbox, 8, W, H)
    ge = download_natural_earth(os.path.join(HERE, "..", ".tmp"), res="50m")  # bordes suaves

    img = Image.new("RGB", (W, H), _hex(ocean))
    d = ImageDraw.Draw(img)
    bcol = _hex(border)

    idx = 0
    for feat in ge.get("features", []):
        props = feat.get("properties", {})
        name = props.get("NAME") or props.get("ADMIN") or ""
        geom = feat.get("geometry", {})
        polys = []
        if geom.get("type") == "Polygon":
            polys = [geom["coordinates"]]
        elif geom.get("type") == "MultiPolygon":
            polys = geom["coordinates"]
        else:
            continue
        # color del pais
        if name in country_colors:
            fill = _hex(country_colors[name])
        elif name in highlight:
            fill = _hex(highlight_fill)
        else:
            fill = _hex(default_fill)

        drew = False
        for poly in polys:
            for ri, ring in enumerate(poly):
                pts = [tuple(proj(lo, la)) for lo, la in ring]
                # descartar poligonos totalmente fuera del lienzo
                xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
                if max(xs) < -50 or min(xs) > W + 50 or max(ys) < -50 or min(ys) > H + 50:
                    continue
                if len(pts) < 3:
                    continue
                if ri == 0:
                    d.polygon(pts, fill=fill)
                else:
                    d.polygon(pts, fill=_hex(ocean))   # agujeros (lagos/huecos)
                # borde grueso
                d.line(pts + [pts[0]], fill=bcol, width=border_px, joint="curve")
                drew = True
        idx += drew

    img.save(out_path)
    return out_path, (W, H)


if __name__ == "__main__":
    import json
    bbox = [float(x) for x in sys.argv[1:5]]
    out = sys.argv[5]
    hl = sys.argv[6].split(",") if len(sys.argv) > 6 else []
    p, sz = build_vector(bbox, out, highlight=hl)
    print("OK vector base:", p, sz)
