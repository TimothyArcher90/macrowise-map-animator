"""
geo_layers.py — capas geograficas que se HORNEAN en el basemap (antes de animar):
  · rios y lagos
  · costa / fronteras resaltadas en color
  · areas urbanas (relleno o trama rayada)
  · extrusion de pais (masa levantada con canto mas oscuro)
  · fronteras internas (estados/provincias)

Todo desde Natural Earth (gratis). Se dibuja con Pillow sobre el basemap ya generado.
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from fetch_geodata import load  # noqa
from project import make_projector  # noqa


def _hex(h):
    if isinstance(h, (list, tuple)):
        return tuple(h[:3])
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _geoms(feat):
    g = feat.get("geometry") or {}
    t = g.get("type")
    if t == "LineString":
        return [g["coordinates"]]
    if t == "MultiLineString":
        return g["coordinates"]
    if t == "Polygon":
        return g["coordinates"]
    if t == "MultiPolygon":
        out = []
        for poly in g["coordinates"]:
            out.extend(poly)
        return out
    if t == "Point":
        return [[g["coordinates"]]]
    return []


def _in_bbox(coords, bbox, pad=2.0):
    w, s, e, n = bbox
    for lo, la in coords[:: max(1, len(coords) // 24)]:
        if (w - pad) <= lo <= (e + pad) and (s - pad) <= la <= (n + pad):
            return True
    return False


def draw_rivers(img, bbox, color="#5FA8D3", width=2, alpha=170, res="10m", min_scale=None):
    """Rios (lineas azules finas)."""
    from PIL import Image, ImageDraw
    ge = load("rivers" if res == "10m" else "ne_50m_rivers_lake_centerlines.geojson")
    W, H = img.size
    proj = make_projector(bbox, 8, W, H)
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    col = _hex(color) + (alpha,)
    n = 0
    for f in ge.get("features", []):
        if min_scale is not None:
            sr = f.get("properties", {}).get("scalerank")
            if sr is not None and sr > min_scale:
                continue
        for line in _geoms(f):
            if len(line) < 2 or not _in_bbox(line, bbox):
                continue
            pts = [tuple(proj(lo, la)) for lo, la in line]
            d.line(pts, fill=col, width=width, joint="curve")
            n += 1
    img.alpha_composite(layer) if img.mode == "RGBA" else img.paste(
        Image.alpha_composite(img.convert("RGBA"), layer).convert(img.mode))
    return n


def draw_lakes(img, bbox, color="#7FBEE0", alpha=210):
    from PIL import Image, ImageDraw
    ge = load("lakes")
    W, H = img.size
    proj = make_projector(bbox, 8, W, H)
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    col = _hex(color) + (alpha,)
    n = 0
    for f in ge.get("features", []):
        for ring in _geoms(f):
            if len(ring) < 3 or not _in_bbox(ring, bbox):
                continue
            d.polygon([tuple(proj(lo, la)) for lo, la in ring], fill=col)
            n += 1
    img.alpha_composite(layer)
    return n


def draw_coast_highlight(img, bbox, countries, color="#F08A24", width=8, glow=True,
                         min_ring_px=None, segments=None, alpha=245):
    """Costa/frontera resaltada. Parametros para que NO quede como un borde gordo:
      · min_ring_px: descarta islas chicas (perimetro en px menor al umbral)
      · segments: [[lon,lat],...] tramos concretos a resaltar (playas puntuales)
      · glow: halo suave alrededor (apagable)"""
    from PIL import Image, ImageDraw, ImageFilter
    W, H = img.size
    proj = make_projector(bbox, 8, W, H)
    col = _hex(color)
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    n = 0

    if segments:
        # tramos explicitos: solo esas playas/costas, como en la referencia
        for seg in segments:
            pts = [tuple(proj(lo, la)) for lo, la in seg]
            if len(pts) > 1:
                d.line(pts, fill=col + (alpha,), width=width, joint="curve")
                n += 1
    else:
        ge = load("countries")
        names = set(countries)
        for f in ge.get("features", []):
            p = f.get("properties", {})
            nm = p.get("NAME") or p.get("ADMIN") or ""
            if nm not in names:
                continue
            for ring in _geoms(f):
                if len(ring) < 3:
                    continue
                pts = [tuple(proj(lo, la)) for lo, la in ring]
                if min_ring_px:
                    per = sum(math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
                              for i in range(len(pts) - 1))
                    if per < min_ring_px:
                        continue     # isla demasiado chica -> no la resalta
                d.line(pts + [pts[0]], fill=col + (alpha,), width=width, joint="curve")
                n += 1
    if glow:
        g = layer.filter(ImageFilter.GaussianBlur(max(2, width)))
        img.alpha_composite(g)
    img.alpha_composite(layer)
    return n


def draw_urban(img, bbox, color="#6E6A64", alpha=120, hatch=False, hatch_gap=9):
    """Areas urbanas: relleno translucido o TRAMA RAYADA (zonas disputadas/urbanas)."""
    from PIL import Image, ImageDraw
    ge = load("urban")
    W, H = img.size
    proj = make_projector(bbox, 8, W, H)
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    col = _hex(color)
    n = 0
    if hatch:
        # patron de rayas diagonales recortado por las areas urbanas
        mask = Image.new("L", (W, H), 0)
        md = ImageDraw.Draw(mask)
        for f in ge.get("features", []):
            for ring in _geoms(f):
                if len(ring) < 3 or not _in_bbox(ring, bbox):
                    continue
                md.polygon([tuple(proj(lo, la)) for lo, la in ring], fill=255)
                n += 1
        # rayas + un velo de base: la trama sola se lee como ruido a poco zoom
        stripes = Image.new("RGBA", (W, H), col + (int(alpha * 0.35),))
        sd = ImageDraw.Draw(stripes)
        lw = max(2, hatch_gap // 3)
        for x in range(-H, W + H, hatch_gap):
            sd.line([x, 0, x + H, H], fill=col + (min(255, int(alpha * 1.8)),), width=lw)
        layer = Image.composite(stripes, Image.new("RGBA", (W, H), (0, 0, 0, 0)), mask)
        # contorno de la zona: la delimita y evita que parezca suciedad del mapa
        od = ImageDraw.Draw(layer)
        for f in ge.get("features", []):
            for ring in _geoms(f):
                if len(ring) < 3 or not _in_bbox(ring, bbox):
                    continue
                pts = [tuple(proj(lo, la)) for lo, la in ring]
                od.line(pts + [pts[0]], fill=col + (min(255, int(alpha * 1.5)),), width=2)
    else:
        for f in ge.get("features", []):
            for ring in _geoms(f):
                if len(ring) < 3 or not _in_bbox(ring, bbox):
                    continue
                d.polygon([tuple(proj(lo, la)) for lo, la in ring], fill=col + (alpha,))
                n += 1
    img.alpha_composite(layer)
    return n


def draw_borders(img, bbox, color="#2A2A32", width=3, alpha=190, internal=False):
    """Fronteras: entre paises (borders) o internas de estados/provincias."""
    from PIL import Image, ImageDraw
    ge = load("states" if internal else "borders")
    W, H = img.size
    proj = make_projector(bbox, 8, W, H)
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    col = _hex(color) + (alpha,)
    n = 0
    for f in ge.get("features", []):
        for line in _geoms(f):
            if len(line) < 2 or not _in_bbox(line, bbox):
                continue
            pts = [tuple(proj(lo, la)) for lo, la in line]
            if internal:
                d.line(pts + [pts[0]], fill=col, width=width)
            else:
                d.line(pts, fill=col, width=width, joint="curve")
            n += 1
    img.alpha_composite(layer)
    return n


def extrude_country(img, bbox, countries, depth=14, angle_deg=90, darken=0.62):
    """EXTRUSION 2.5D: 'levanta' el pais dibujando su canto desplazado y mas oscuro."""
    from PIL import Image, ImageDraw
    import numpy as np
    ge = load("countries")
    W, H = img.size
    proj = make_projector(bbox, 8, W, H)
    names = set(countries)
    rings_px = []
    for f in ge.get("features", []):
        p = f.get("properties", {})
        nm = p.get("NAME") or p.get("ADMIN") or ""
        if nm in names:
            for ring in _geoms(f):
                if len(ring) >= 3:
                    rings_px.append([tuple(proj(lo, la)) for lo, la in ring])
    if not rings_px:
        return 0
    dx = math.cos(math.radians(angle_deg)) * depth
    dy = math.sin(math.radians(angle_deg)) * depth

    # mascara del pais y del pais desplazado -> el canto es la diferencia
    m_top = Image.new("L", (W, H), 0)
    m_bot = Image.new("L", (W, H), 0)
    dt, db = ImageDraw.Draw(m_top), ImageDraw.Draw(m_bot)
    for r in rings_px:
        dt.polygon(r, fill=255)
        db.polygon([(x + dx, y + dy) for x, y in r], fill=255)
    side = np.clip(np.asarray(m_bot).astype(int) - np.asarray(m_top).astype(int), 0, 255)
    side_mask = Image.fromarray(side.astype("uint8"), "L")

    base = np.asarray(img.convert("RGB")).astype("float64") / 255.0
    dark = np.clip(base * darken, 0, 1)
    darkimg = Image.fromarray((dark * 255).astype("uint8"), "RGB").convert("RGBA")
    img.paste(darkimg, (0, 0), side_mask)
    return len(rings_px)


def apply_layers(basemap_path, bbox, cfg, out_path=None):
    """Aplica el set de capas indicado en cfg sobre el basemap. Devuelve la ruta."""
    from PIL import Image
    img = Image.open(basemap_path).convert("RGBA")
    log = {}
    if cfg.get("extrude"):
        e = cfg["extrude"]
        log["extrude"] = extrude_country(img, bbox, e.get("countries", []),
                                         depth=e.get("depth", 14),
                                         darken=e.get("darken", 0.62))
    if cfg.get("urban"):
        u = cfg["urban"]
        log["urban"] = draw_urban(img, bbox, u.get("color", "#6E6A64"),
                                  u.get("alpha", 120), u.get("hatch", False))
    if cfg.get("lakes"):
        l = cfg["lakes"] if isinstance(cfg["lakes"], dict) else {}
        log["lakes"] = draw_lakes(img, bbox, l.get("color", "#7FBEE0"), l.get("alpha", 210))
    if cfg.get("rivers"):
        r = cfg["rivers"] if isinstance(cfg["rivers"], dict) else {}
        log["rivers"] = draw_rivers(img, bbox, r.get("color", "#5FA8D3"),
                                    r.get("width", 2), r.get("alpha", 170),
                                    min_scale=r.get("min_scale"))
    if cfg.get("borders"):
        b = cfg["borders"] if isinstance(cfg["borders"], dict) else {}
        log["borders"] = draw_borders(img, bbox, b.get("color", "#2A2A32"),
                                      b.get("width", 3), b.get("alpha", 190))
    if cfg.get("internal_borders"):
        b = cfg["internal_borders"] if isinstance(cfg["internal_borders"], dict) else {}
        log["internal"] = draw_borders(img, bbox, b.get("color", "#8A8A94"),
                                       b.get("width", 1), b.get("alpha", 120), internal=True)
    if cfg.get("coast_highlight"):
        c = cfg["coast_highlight"]
        log["coast"] = draw_coast_highlight(img, bbox, c.get("countries", []),
                                            c.get("color", "#F08A24"),
                                            c.get("width", 8), c.get("glow", True),
                                            min_ring_px=c.get("min_ring_px"),
                                            segments=c.get("segments"),
                                            alpha=c.get("alpha", 245))
    out_path = out_path or basemap_path.replace(".png", "_geo.png")
    img.convert("RGB").save(out_path)
    return out_path, log
