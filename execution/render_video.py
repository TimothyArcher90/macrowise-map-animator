"""
render_video.py — renderiza un MAPA ANIMADO estilo Johnny Harris a MP4, 100% en
Python + ffmpeg (SIN After Effects). Camara cinematografica (zoom/pan sobre satelite
con micro-pausas), fronteras con glow, ruta que se dibuja, labels que siguen el mapa,
y grado de color + film grain + viñeta via ffmpeg.

Esta es la ruta autonoma: no depende de AE ni de -r. El mismo motor sirve para
"pasame una imagen de un lugar y te la animo": cambias el basemap + los waypoints.

Uso:
  python render_video.py stories/estrecho_ormuz.json --format horizontal --out mapa.mp4
"""
import argparse
import json
import math
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from project import make_projector, download_natural_earth, country_rings  # noqa

from workdir import TMP  # cache/frames en D:, no en C:

FORMATS = {"horizontal": (1920, 1080), "vertical": (1080, 1920)}
FPS = 30

COL = {"Iran": (224, 83, 61), "Oman": (78, 201, 176),
       "United Arab Emirates": (232, 185, 58)}
# Marca MacroWise
GOLD = (201, 168, 76)      # #C9A84C
TEAL = (80, 181, 162)      # #50b5a2
PURPLE = (115, 36, 125)    # #73247d
INK = (243, 240, 233)      # texto claro sobre caja oscura
PANEL = (26, 26, 38)       # #1A1A26 Ink (caja de label)


# ---------- easing + camara con micro-pausas ----------
def ease(u):
    return 3 * u * u - 2 * u * u * u


def cam_at(wps, t):
    wps = sorted(wps, key=lambda w: w["t"])
    for w in wps:
        w.setdefault("dwell", 0.0)
        w.setdefault("span", 6.0)
    if t <= wps[0]["t"]:
        a = wps[0]
        return a["lon"], a["lat"], a["span"]
    if t >= wps[-1]["t"]:
        a = wps[-1]
        return a["lon"], a["lat"], a["span"]
    for i in range(len(wps) - 1):
        a, b = wps[i], wps[i + 1]
        if a["t"] <= t <= b["t"]:
            if a["dwell"] > 0 and t <= a["t"] + a["dwell"]:
                return a["lon"], a["lat"], a["span"]
            t0 = a["t"] + a["dwell"]
            u = 0.0 if b["t"] - t0 <= 0 else ease((t - t0) / (b["t"] - t0))
            return (a["lon"] + (b["lon"] - a["lon"]) * u,
                    a["lat"] + (b["lat"] - a["lat"]) * u,
                    a["span"] + (b["span"] - a["span"]) * u)
    a = wps[-1]
    return a["lon"], a["lat"], a["span"]


# ---------- baked annotated basemap (fronteras glow + ruta) ----------
def bake_annotated(story, bpath, bbox, zoom):
    from PIL import Image, ImageDraw, ImageFilter
    base = Image.open(bpath).convert("RGBA")
    bw, bh = base.size
    proj = make_projector(bbox, zoom, bw, bh)
    ge = download_natural_earth(TMP)

    def glow(pts, color, w, aglow=110):
        if len(pts) < 2:
            return
        gl = Image.new("RGBA", base.size, (0, 0, 0, 0))
        dg = ImageDraw.Draw(gl)
        dg.line(pts, fill=color + (aglow,), width=w + 10, joint="curve")
        gl = gl.filter(ImageFilter.GaussianBlur(7))
        base.alpha_composite(gl)
        ln = Image.new("RGBA", base.size, (0, 0, 0, 0))
        dl = ImageDraw.Draw(ln)
        dl.line(pts, fill=color + (235,), width=w, joint="curve")
        base.alpha_composite(ln)

    for reg in story.get("regions", []):
        c = COL.get(reg["query"], (224, 83, 61))
        for ring in country_rings(ge, reg["query"]):
            glow([proj(lo, la) for lo, la in ring], c, 3)
    for ro in story.get("routes", []):
        path = ro.get("path") or [ro["from"], ro["to"]]
        glow([proj(lo, la) for lo, la in path], GOLD, 4, aglow=150)
    return base, proj, bw, bh


# ---------- helpers de dibujo ----------
def font(sz, bold=True):
    from PIL import ImageFont
    for name in (("arialbd.ttf" if bold else "arial.ttf"), "Arial.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, sz)
        except Exception:
            continue
    return ImageFont.load_default()


def draw_label(d, x, y, text, alpha, W):
    from PIL import Image, ImageDraw
    if alpha <= 0:
        return
    fs = max(20, int(W / 48))
    f = font(fs)
    tb = d.textbbox((0, 0), text, font=f)
    tw, th = tb[2] - tb[0], tb[3] - tb[1]
    # dot
    _rgba_dot(d, x, y, GOLD, alpha)
    bx, by = x + 16, y - th - 16
    pad = 10
    _rgba_box(d, [bx - pad, by - pad, bx + tw + pad, by + th + pad], PANEL, GOLD, alpha)
    _rgba_text(d, bx, by - tb[1], text, INK, alpha, f)


def _a(c, alpha):
    return (c[0], c[1], c[2], int(max(0, min(1, alpha)) * 255))


def _rgba_dot(d, x, y, c, alpha):
    d.ellipse([x - 7, y - 7, x + 7, y + 7], outline=_a((255, 236, 120), alpha), width=3)
    d.ellipse([x - 2, y - 2, x + 2, y + 2], fill=_a(c, alpha))


def _rgba_box(d, box, fill, outline, alpha):
    d.rectangle(box, fill=_a(fill, 0.88 * alpha), outline=_a(outline, alpha), width=2)


def _rgba_text(d, x, y, t, c, alpha, f):
    d.text((x, y), t, fill=_a(c, alpha), font=f)


# ---------- render principal ----------
def render(story, fmt, out_mp4):
    from PIL import Image, ImageDraw
    W, H = FORMATS[fmt]
    bbox = story["bbox"]
    zoom = story.get("video_zoom", 9)
    dur = story.get("duration", 20)
    source = story.get("basemap_source", "esri")
    theme = story.get("theme", "dark")   # 'light' para mapas claros
    tilt = float(story.get("tilt", 0))   # 0 = plano, ~0.6 = 2.5D inclinado
    sky_top = tuple(story.get("sky_top", [22, 28, 38]))
    sky_bot = tuple(story.get("sky_bot", [58, 70, 86]))

    bpath = os.path.join(TMP, "basemap_%s_z%d.png" % (source, zoom))
    if source == "caspian":
        # terreno claro Caspian + tinte de pais semi-transparente (country_colors)
        if not os.path.exists(bpath):
            from caspian_base import build_caspian
            print("generando base Caspian (terreno claro + tintes de pais)...")
            build_caspian(bbox, zoom, bpath, tints=story.get("country_colors"))
    elif source == "vector":
        # estilo vector plano: colores precisos por pais + borde (look manual GeoLayers)
        if not os.path.exists(bpath):
            from vector_base import build_vector
            print("generando base vector (colores precisos por pais)...")
            build_vector(bbox, bpath, country_colors=story.get("country_colors"),
                         highlight=story.get("highlight"),
                         ocean=story.get("ocean", "#DCE3E8"))
    elif not os.path.exists(bpath):
        subprocess.run([sys.executable, os.path.join(HERE, "fetch_basemap.py"),
                        "--bbox", *[str(x) for x in bbox], "--zoom", str(zoom),
                        "--source", source, "--out", bpath], check=True)

    # MASCARA POR PAIS (opcional, off por defecto): el tinte de pais ya resalta.
    if story.get("highlight_mask") and source == "caspian":
        hl_path = bpath.replace(".png", "_hl.png")
        if not os.path.exists(hl_path):
            from caspian_base import apply_highlight
            print("aplicando mascara por pais...")
            hl_path = apply_highlight(bpath, bbox, story["highlight"])
        bpath = hl_path

    # RELIEVE 3D opcional (hillshade desde elevacion gratis)
    if story.get("relief"):
        relief_path = bpath.replace(".png", "_relief.png")
        if not os.path.exists(relief_path):
            from relief import add_relief
            strength = story["relief"] if isinstance(story["relief"], (int, float)) else 0.6
            print("agregando relieve 3D (hillshade)...")
            relief_path = add_relief(bpath, bbox, zoom, strength)
        bpath = relief_path

    # logo de marca (watermark) opcional
    logo_img = None
    if story.get("logo") and os.path.exists(story["logo"]):
        logo_img = Image.open(story["logo"]).convert("RGBA")
        lw = int(W * 0.105)   # marca de agua discreta
        logo_img = logo_img.resize((lw, int(lw * logo_img.height / logo_img.width)), Image.LANCZOS)
        # opacidad reducida (watermark profesional, no sticker)
        op = story.get("logo_opacity", 0.5)
        a = logo_img.split()[3].point(lambda v: int(v * op))
        logo_img.putalpha(a)
    focus = story.get("focus")   # {lon,lat,t} punto a resaltar con anillo pulsante
    annotated, proj, bw, bh = bake_annotated(story, bpath, bbox, zoom)
    lon_span = bbox[2] - bbox[0]

    cam_wps = story.get("camera", story.get("waypoints"))
    labels = story.get("labels", [])
    lower = story.get("lower_third")

    frames_dir = os.path.join(TMP, "frames_%s" % fmt)
    if os.path.isdir(frames_dir):
        shutil.rmtree(frames_dir)
    os.makedirs(frames_dir)

    n = int(dur * FPS)
    for fi in range(n):
        t = fi / FPS
        clon, clat, span = cam_at(cam_wps, t)
        # ventana de recorte en px del basemap
        crop_w = span / lon_span * bw
        crop_h = crop_w * H / W
        ccx, ccy = proj(clon, clat)
        left = ccx - crop_w / 2
        top = ccy - crop_h / 2
        left = max(0, min(bw - crop_w, left))
        top = max(0, min(bh - crop_h, top))
        box = (int(left), int(top), int(left + crop_w), int(top + crop_h))
        frame = annotated.crop(box).resize((W, H), Image.LANCZOS).convert("RGBA")

        # INCLINACION 2.5D del MAPA primero; las letras van ENCIMA (no se deforman)
        fwd = None
        if tilt > 0:
            frame, fwd = apply_tilt(frame, W, H, tilt, sky_top, sky_bot)
        d = ImageDraw.Draw(frame)

        def screen(lon, lat):
            lx, ly = proj(lon, lat)
            sx = (lx - box[0]) / (box[2] - box[0]) * W
            sy = (ly - box[1]) / (box[3] - box[1]) * H
            if fwd is not None:
                sx, sy = _project_point(fwd, sx, sy)
            return sx, sy

        # labels (caja): tamaño CONSTANTE, siempre rectos, encima del mapa inclinado
        for lb in labels:
            appear = lb.get("t", 5)
            alpha = max(0.0, min(1.0, (t - appear) / 0.5))
            if alpha <= 0:
                continue
            sx, sy = screen(lb["lon"], lb["lat"])
            if -50 < sx < W + 50 and -50 < sy < H + 50:
                draw_label(d, sx, sy, lb["text"].upper(), alpha, W)

        # etiquetas de PAIS: tamaño constante (no encogen con el zoom/tilt)
        for ml in story.get("map_labels", []):
            sx, sy = screen(ml["lon"], ml["lat"])
            if -100 < sx < W + 100 and -100 < sy < H + 100:
                _draw_country(d, sx, sy, ml["text"], ml.get("size", 1.0), W, ml.get("alpha", 0.82))

        # marcador de FOCO pulsante
        if focus:
            fa = max(0.0, min(1.0, (t - focus.get("t", 3)) / 0.5))
            if fa > 0:
                sx, sy = screen(focus["lon"], focus["lat"])
                if -80 < sx < W + 80 and -80 < sy < H + 80:
                    _draw_focus(d, sx, sy, t, fa)

        # lower-third de apertura (titulo + subtitulo), estilo MacroWise
        if lower:
            la = _fade_window(t, lower.get("in", 1.0), lower.get("out", 7.0), 0.6)
            if la > 0:
                _draw_lower_third(d, W, H, lower, la)

        # logo de marca de agua (esquina inferior derecha, con padding generoso)
        if logo_img is not None:
            lx = W - logo_img.width - int(W * 0.035)
            ly = H - logo_img.height - int(H * 0.05)
            frame.alpha_composite(logo_img, (lx, ly))

        frame.convert("RGB").save(os.path.join(frames_dir, "f%05d.jpg" % fi), quality=96)
        if fi % 60 == 0:
            print("  frame %d/%d" % (fi, n))

    print("frames listos, encodeando con grado cinematografico...")
    _encode(frames_dir, out_mp4, W, H)
    shutil.rmtree(frames_dir, ignore_errors=True)
    print("OK video:", out_mp4)


def _find_coeffs(dst, src):
    # coeffs de homografia que mapean un punto de 'dst' a 'src'
    import numpy as np
    A = []
    for (xd, yd), (xs, ys) in zip(dst, src):
        A.append([xd, yd, 1, 0, 0, 0, -xs * xd, -xs * yd])
        A.append([0, 0, 0, xd, yd, 1, -ys * xd, -ys * yd])
    A = np.array(A, dtype="float64")
    B = np.array(src, dtype="float64").reshape(8)
    return np.linalg.solve(A, B)


def _project_point(coeffs, x, y):
    a, b, c, d, e, f, g, h = coeffs
    den = g * x + h * y + 1.0
    return ((a * x + b * y + c) / den, (d * x + e * y + f) / den)


def apply_tilt(frame_rgba, W, H, tilt, sky_top, sky_bot):
    """Inclina el mapa en 2.5D (rig rotation_x) + cielo/atmosfera arriba."""
    from PIL import Image
    inset = 0.06 + 0.22 * tilt        # convergencia de perspectiva arriba
    horizon = 0.10 + 0.22 * tilt      # el mapa arranca mas abajo (cielo arriba)
    hy = H * horizon
    dst = [(W * inset, hy), (W * (1 - inset), hy), (W, H), (0, H)]
    src = [(0, 0), (W, 0), (W, H), (0, H)]
    coeffs = _find_coeffs(dst, src)
    warped = frame_rgba.transform((W, H), Image.PERSPECTIVE, coeffs, Image.BICUBIC)
    fwd = _find_coeffs(src, dst)   # directa: punto del mapa plano -> mapa inclinado
    # cielo: gradiente vertical
    import numpy as np
    grad = np.zeros((H, W, 3), dtype="uint8")
    tcol = np.array(sky_top); bcol = np.array(sky_bot)
    for yy in range(H):
        f = yy / max(1, H - 1)
        grad[yy, :, :] = (tcol * (1 - f) + bcol * f).astype("uint8")
    sky = Image.fromarray(grad, "RGB").convert("RGBA")
    sky.alpha_composite(warped)
    return sky, fwd


def _draw_country(d, x, y, text, size, W, alpha):
    # texto de pais grande con tracking amplio, sombra suave, sin caja (look Caspian)
    txt = " ".join(list(text.upper()))   # letter-spacing manual
    fs = int(W / 34 * size)
    f = font(fs, bold=True)
    tw = d.textlength(txt, font=f)
    px, py = x - tw / 2, y - fs / 2
    d.text((px + 2, py + 2), txt, fill=_a((30, 26, 20), 0.35 * alpha), font=f)   # sombra
    d.text((px, py), txt, fill=_a((60, 50, 38), alpha), font=f)                  # tinta calida


def _draw_focus(d, x, y, t, alpha):
    # anillo doble pulsante en oro (senala el punto) + crosshair sutil
    import math as _m
    pulse = 1.0 + 0.18 * _m.sin(t * 3.2)
    r = int(46 * pulse)
    d.ellipse([x - r, y - r, x + r, y + r], outline=_a(GOLD, alpha), width=4)
    d.ellipse([x - r - 10, y - r - 10, x + r + 10, y + r + 10], outline=_a(GOLD, 0.45 * alpha), width=2)
    d.ellipse([x - 5, y - 5, x + 5, y + 5], fill=_a(GOLD, alpha))
    for a in (0, 90, 180, 270):
        dx, dy = int(_m.cos(_m.radians(a)) * (r + 16)), int(_m.sin(_m.radians(a)) * (r + 16))
        dx2, dy2 = int(_m.cos(_m.radians(a)) * (r + 4)), int(_m.sin(_m.radians(a)) * (r + 4))
        d.line([x + dx2, y + dy2, x + dx, y + dy], fill=_a(GOLD, alpha), width=3)


def _fade_window(t, tin, tout, dur):
    if t < tin - dur or t > tout + dur:
        return 0.0
    if t < tin:
        return (t - (tin - dur)) / dur
    if t > tout:
        return max(0.0, 1 - (t - tout) / dur)
    return 1.0


def _draw_lower_third(d, W, H, lower, alpha):
    title = lower.get("title", "").upper()
    sub = lower.get("sub", "")
    fT = font(int(W / 26))
    fS = font(int(W / 60), bold=False)
    x = int(W * 0.06)
    y = int(H * 0.74)
    # panel de respaldo tenue (Ink MacroWise) para leer sobre cualquier mapa
    tw = max(d.textlength(title, font=fT), d.textlength(sub, font=fS))
    d.rectangle([x - 34, y - 20, x + tw + 40, y + int(W / 26) + 44], fill=_a(PANEL, 0.72 * alpha))
    # barra de acento oro (marca MacroWise)
    d.rectangle([x - 18, y, x - 8, y + int(W / 26) + 34], fill=_a(GOLD, alpha))
    d.text((x, y), title, fill=_a(INK, alpha), font=fT)
    d.text((x, y + int(W / 26) + 8), sub, fill=_a((214, 209, 200), alpha), font=fS)


def _encode(frames_dir, out_mp4, W, H):
    # grado cinematografico: contraste/saturacion suave + sharpen + viñeta + grain fino
    # grano ESTATICO (sin allf=t) para que no titile al moverse; viñeta suave; grado leve
    vf = ("eq=contrast=1.03:saturation=1.00:gamma=0.995,"
          "unsharp=5:5:0.35:5:5:0.0,"
          "vignette=PI/8,"
          "noise=alls=2")
    os.makedirs(os.path.dirname(out_mp4), exist_ok=True)
    cmd = ["ffmpeg", "-y", "-framerate", str(FPS),
           "-i", os.path.join(frames_dir, "f%05d.jpg"),
           "-vf", vf, "-c:v", "libx264", "-pix_fmt", "yuv420p",
           "-crf", "21", "-preset", "medium", out_mp4]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


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
