"""
preview_frame.py — render ESTATICO (Pillow) de un frame del mapa, para validar el
look SIN After Effects. Compone basemap satelital + fronteras con glow + ruta +
marcador del estrecho + labels, y recorta al formato pedido (horizontal|vertical).

Uso: python preview_frame.py stories/estrecho_ormuz.json --format horizontal --out prev.png
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from project import make_projector, download_natural_earth, country_rings  # noqa

FORMATS = {"horizontal": (1920, 1080), "vertical": (1080, 1920)}
TMP = os.path.join(HERE, "..", ".tmp")
COL = {"Iran": (224, 83, 61), "Oman": (78, 201, 176),
       "United Arab Emirates": (232, 185, 58)}


def glow_line(base, pts, color, width):
    from PIL import Image, ImageDraw, ImageFilter
    if len(pts) < 2:
        return
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.line(pts, fill=color + (230,), width=width, joint="curve")
    glow = Image.new("RGBA", base.size, (0, 0, 0, 0))
    dg = ImageDraw.Draw(glow)
    dg.line(pts, fill=color + (120,), width=width + 8, joint="curve")
    glow = glow.filter(ImageFilter.GaussianBlur(6))
    base.alpha_composite(glow)
    base.alpha_composite(layer)


def render(story, fmt, out):
    from PIL import Image, ImageDraw, ImageFont
    W, H = FORMATS[fmt]
    bbox = story["bbox"]
    zoom = story.get("basemap_zoom", 8)

    # basemap (usa el cache del build)
    tag = "%.2f_%.2f_%.2f_%.2f_z%d" % (bbox[0], bbox[1], bbox[2], bbox[3], zoom)
    bpath = os.path.join(TMP, "basemap_%s.png" % tag)
    if not os.path.exists(bpath):
        import subprocess
        subprocess.run([sys.executable, os.path.join(HERE, "fetch_basemap.py"),
                        "--bbox", *[str(x) for x in bbox], "--zoom", str(zoom),
                        "--out", bpath], check=True)
    base = Image.open(bpath).convert("RGBA")
    bw, bh = base.size
    proj = make_projector(bbox, zoom, bw, bh)
    ge = download_natural_earth(TMP)

    # fronteras con glow
    for reg in story.get("regions", []):
        col = COL.get(reg["query"], (224, 83, 61))
        for ring in country_rings(ge, reg["query"]):
            pts = [proj(lon, lat) for lon, lat in ring]
            glow_line(base, pts, col, 4)

    # ruta
    for ro in story.get("routes", []):
        path = ro.get("path") or [ro["from"], ro["to"]]
        pts = [proj(lon, lat) for lon, lat in path]
        glow_line(base, pts, (232, 185, 58), 5)

    d = ImageDraw.Draw(base)
    # marcador del estrecho + labels
    def font(sz):
        try:
            return ImageFont.truetype("arialbd.ttf", sz)
        except Exception:
            return ImageFont.load_default()
    for lb in story.get("labels", []):
        x, y = proj(lb["lon"], lb["lat"])
        d.ellipse([x - 7, y - 7, x + 7, y + 7], outline=(255, 236, 120), width=3)
        txt = lb["text"].upper()
        fs = max(14, int(bw / 55))
        tb = d.textbbox((0, 0), txt, font=font(fs))
        tw = tb[2] - tb[0]
        bx, by = x + 14, y - fs - 6
        d.rectangle([bx - 6, by - 4, bx + tw + 10, by + fs + 8], fill=(15, 20, 27, 235),
                    outline=(232, 185, 58), width=2)
        d.text((bx, by), txt, fill=(242, 239, 233), font=font(fs))

    # recorte al formato (cover, centrado)
    target = W / H
    src = bw / bh
    if src > target:  # basemap mas ancho -> recortar lados
        nw = int(bh * target)
        left = (bw - nw) // 2
        base = base.crop((left, 0, left + nw, bh))
    else:             # mas alto -> recortar arriba/abajo
        nh = int(bw / target)
        top = (bh - nh) // 2
        base = base.crop((0, top, bw, top + nh))
    base = base.convert("RGB").resize((W, H), Image.LANCZOS)
    base.save(out, "PNG")
    print("OK preview:", out, base.size)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("story")
    ap.add_argument("--format", choices=list(FORMATS), default="horizontal")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    with open(a.story, encoding="utf-8") as f:
        story = json.load(f)
    render(story, a.format, a.out)


if __name__ == "__main__":
    main()
