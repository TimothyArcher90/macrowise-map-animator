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

FORMATS = {"horizontal": (1920, 1080), "vertical": (1080, 1920)}
TMP = os.path.join(HERE, "..", ".tmp")
FPS = 30

COL = {"Iran": (224, 83, 61), "Oman": (78, 201, 176),
       "United Arab Emirates": (232, 185, 58)}
GOLD = (232, 185, 58)
INK = (243, 240, 233)
PANEL = (12, 17, 24)


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

    bpath = os.path.join(TMP, "basemap_z%d.png" % zoom)
    if not os.path.exists(bpath):
        subprocess.run([sys.executable, os.path.join(HERE, "fetch_basemap.py"),
                        "--bbox", *[str(x) for x in bbox], "--zoom", str(zoom),
                        "--out", bpath], check=True)
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
        d = ImageDraw.Draw(frame)

        # labels anclados al mapa (siguen la camara), fade-in en su t
        for lb in labels:
            appear = lb.get("t", 5)
            alpha = max(0.0, min(1.0, (t - appear) / 0.5))
            if alpha <= 0:
                continue
            lx, ly = proj(lb["lon"], lb["lat"])
            sx = (lx - box[0]) / (box[2] - box[0]) * W
            sy = (ly - box[1]) / (box[3] - box[1]) * H
            if -50 < sx < W + 50 and -50 < sy < H + 50:
                draw_label(d, sx, sy, lb["text"].upper(), alpha, W)

        # lower-third de apertura (titulo + subtitulo), estilo MacroWise
        if lower:
            la = _fade_window(t, lower.get("in", 1.0), lower.get("out", 7.0), 0.6)
            if la > 0:
                _draw_lower_third(d, W, H, lower, la)

        frame.convert("RGB").save(os.path.join(frames_dir, "f%05d.jpg" % fi), quality=92)
        if fi % 60 == 0:
            print("  frame %d/%d" % (fi, n))

    print("frames listos, encodeando con grado cinematografico...")
    _encode(frames_dir, out_mp4, W, H)
    shutil.rmtree(frames_dir, ignore_errors=True)
    print("OK video:", out_mp4)


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
    # barra de acento
    d.rectangle([x - 18, y, x - 8, y + int(W / 26) + 34], fill=_a(GOLD, alpha))
    d.text((x, y), title, fill=_a(INK, alpha), font=fT)
    d.text((x, y + int(W / 26) + 8), sub, fill=_a((210, 205, 195), alpha), font=fS)


def _encode(frames_dir, out_mp4, W, H):
    # grado cinematografico: contraste/saturacion suave + sharpen + viñeta + grain fino
    vf = ("eq=contrast=1.07:saturation=1.14:gamma=0.98,"
          "unsharp=5:5:0.5:5:5:0.0,"
          "vignette=PI/5,"
          "noise=alls=4:allf=t")
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
