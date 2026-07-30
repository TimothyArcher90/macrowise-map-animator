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
import hashlib
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
    """Smootherstep QUINTICO (Perlin): derivada Y aceleracion cero en los extremos.
    El cubico (smoothstep) arranca y frena con un tironcito perceptible; el
    quintico entra y sale sin que se sienta el keyframe = movimiento organico."""
    u = max(0.0, min(1.0, u))
    return u * u * u * (u * (u * 6 - 15) + 10)


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
            # ZOOM en escala LOGARITMICA: interpolar el span linealmente hace que
            # el zoom parezca acelerar al final (9->5 grados no es perceptualmente
            # uniforme). Geometrico = velocidad de zoom constante, como una lente.
            span = math.exp(math.log(a["span"]) * (1 - u) + math.log(b["span"]) * u)
            return (a["lon"] + (b["lon"] - a["lon"]) * u,
                    a["lat"] + (b["lat"] - a["lat"]) * u,
                    span)
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
def font(sz, bold=True, style=None):
    """style: None=sans | 'serif_italic'=serif cursiva (nombres de ciudad, ref.
    Caspian) | 'serif'=serif recta."""
    from PIL import ImageFont
    if style == "serif_italic":
        names = ["georgiai.ttf", "timesi.ttf", "GeorgiaItalic.ttf", "DejaVuSerif-Italic.ttf"]
    elif style == "serif":
        names = ["georgia.ttf", "times.ttf", "DejaVuSerif.ttf"]
    else:
        names = [("arialbd.ttf" if bold else "arial.ttf"), "Arial.ttf",
                 "DejaVuSans-Bold.ttf"]
    for name in names:
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


def _hexc(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


_DOF_MASK = {"k": None, "wh": None}   # mascara de profundidad de campo (cacheada)


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
    # inclinacion: 'tilt_deg' en GRADOS (0-60, como el rig de AE) o 'tilt' 0-1 (legacy)
    if "tilt_deg" in story:
        tilt = max(0.0, min(60.0, float(story["tilt_deg"]))) / 60.0
    else:
        tilt = float(story.get("tilt", 0))
    sky_top = tuple(story.get("sky_top", [22, 28, 38]))
    sky_bot = tuple(story.get("sky_bot", [58, 70, 86]))
    dof = float(story.get("dof", 0))     # 0 = sin desenfoque, ~0.5 = documental suave
    dof_mode = story.get("dof_mode", "radial")   # 'tiltshift' = banda horizontal nitida
    dof_band = float(story.get("dof_band", 0.20))   # alto de la franja en foco (0-1)
    dof_focus = float(story.get("dof_focus", 0.55)) # posicion vertical del foco (0-1)

    # el nombre del cache incluye bbox + tintes: si cambian, se regenera
    _sig = hashlib.md5(json.dumps([bbox, story.get("country_colors")],
                                  sort_keys=True).encode()).hexdigest()[:8]
    bpath = os.path.join(TMP, "basemap_%s_z%d_%s.png" % (source, zoom, _sig))
    if source == "caspian":
        # terreno claro Caspian + tinte de pais semi-transparente (country_colors)
        if not os.path.exists(bpath):
            from caspian_base import build_caspian
            print("generando base Caspian (terreno claro + tintes de pais)...")
            build_caspian(bbox, zoom, bpath, tints=story.get("country_colors"),
                          theme=theme)
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

    # VIDA: mezcla de imagen satelital real (vegetacion/desiertos) sobre la base
    # estilizada. Sin esto el terreno queda plano y apagado.
    if story.get("life"):
        _l = story["life"] if isinstance(story["life"], dict) else {}
        amount = _l.get("amount", 0.45) if isinstance(story["life"], dict) else float(story["life"])
        lsig = hashlib.md5(("%s|%s" % (amount, _l.get("sat", 1.25))).encode()).hexdigest()[:6]
        lpath = bpath.replace(".png", "_life%s.png" % lsig)
        if not os.path.exists(lpath):
            from caspian_base import add_life
            print("dando vida al terreno (mezcla satelital)...")
            lpath = add_life(bpath, bbox, zoom, amount=amount,
                             sat=_l.get("sat", 1.25), dark=(theme == "dark"),
                             out_path=lpath)
        bpath = lpath

    # CAPAS GEOGRAFICAS horneadas: rios, lagos, urbano, fronteras, costa, extrusion
    _geo_cfg = {k: story[k] for k in
                ("rivers", "lakes", "urban", "borders", "internal_borders",
                 "coast_highlight", "extrude") if story.get(k)}
    if _geo_cfg:
        _gsig = hashlib.md5(json.dumps(_geo_cfg, sort_keys=True).encode()).hexdigest()[:8]
        gpath = bpath.replace(".png", "_geo%s.png" % _gsig)
        if not os.path.exists(gpath):
            from geo_layers import apply_layers
            print("horneando capas geograficas: %s" % ", ".join(_geo_cfg))
            gpath, glog = apply_layers(bpath, bbox, _geo_cfg, gpath)
            print("   ->", glog)
        bpath = gpath

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

    # carpeta de frames UNICA por render: dos renders en paralelo no se pisan
    _rid = hashlib.md5(("%s|%s|%d" % (out_mp4, fmt, os.getpid())).encode()).hexdigest()[:10]
    frames_dir = os.path.join(TMP, "frames_%s_%s" % (fmt, _rid))
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
        # Con TILT se recorta MAS area: lo lejano (arriba) se comprime en
        # perspectiva, asi que hace falta mas mapa del que se ve. Sin esto la
        # inclinacion no se nota (el mapa queda "plano" o se ve su borde).
        if tilt > 0:
            crop_w *= (1.0 + 0.85 * tilt)
            crop_h *= (1.0 + 0.55 * tilt)
        ccx, ccy = proj(clon, clat)
        left = ccx - crop_w / 2
        top = ccy - crop_h / 2
        left = max(0, min(bw - crop_w, left))
        top = max(0, min(bh - crop_h, top))
        box = (int(left), int(top), int(left + crop_w), int(top + crop_h))
        frame = annotated.crop(box).resize((W, H), Image.LANCZOS).convert("RGBA")

        # PROFUNDIDAD DE CAMPO falsa ("Blur it Out"): desenfoca los bordes del cuadro
        # y deja nitido el centro. Da el aire cinematografico de documental.
        if dof > 0:
            from PIL import ImageFilter as _IF
            import numpy as _np
            blurred = frame.filter(_IF.GaussianBlur(dof * 9.0))
            _key = (W, H, dof_mode, round(dof_band, 3), round(dof_focus, 3))
            if _DOF_MASK.get("key") != _key:
                yy, xx = _np.mgrid[0:H, 0:W]
                if dof_mode == "tiltshift":
                    # BANDA horizontal nitida (mira el look de mapas 3D inclinados):
                    # arriba y abajo desenfocados, franja del medio en foco.
                    ny = (yy / H - dof_focus) / max(0.02, dof_band)
                    k = _np.clip(_np.abs(ny) - 1.0, 0, 1)
                    k = _np.clip(k / 1.2, 0, 1) ** 1.3
                else:
                    nx = (xx - W / 2) / (W / 2)
                    ny2 = (yy - H / 2) / (H / 2)
                    rad = _np.sqrt(nx * nx + ny2 * ny2) / 1.414
                    k = _np.clip((rad - 0.42) / 0.5, 0, 1) ** 1.6
                _DOF_MASK["k"] = Image.fromarray((k * 255).astype("uint8"), "L")
                _DOF_MASK["key"] = _key
            frame = Image.composite(blurred, frame, _DOF_MASK["k"])

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

        def under_ui(sx, sy):
            """True si el punto cae bajo el chip de fecha o el logo (no dibujar ahi)."""
            if story.get("dates") and sx < W * 0.30 and sy < H * 0.17:
                return True
            if logo_img is not None and sx > W * 0.68 and sy > H * 0.86:
                return True
            return False

        # labels (caja): tamaño CONSTANTE, siempre rectos, encima del mapa inclinado
        for lb in labels:
            appear = lb.get("t", 5)
            alpha = max(0.0, min(1.0, (t - appear) / 0.5))
            if alpha <= 0:
                continue
            sx, sy = screen(lb["lon"], lb["lat"])
            if -50 < sx < W + 50 and -50 < sy < H + 50:
                draw_label(d, sx, sy, lb["text"].upper(), alpha, W)

        # etiquetas de PAIS: tamaño constante. Con keep=true la etiqueta se queda
        # pegada al borde cuando el pais sale de cuadro (no desaparece en el zoom).
        for ml in story.get("map_labels", []):
            sx, sy = screen(ml["lon"], ml["lat"])
            if ml.get("keep", True):
                mgx = W * 0.13 * ml.get("size", 1.0)
                mgy = H * 0.10
                onscreen = (-mgx < sx < W + mgx) and (-mgy < sy < H + mgy)
                sx = max(mgx, min(W - mgx, sx))
                sy = max(mgy, min(H - mgy, sy))
                # ZONAS DE UI reservadas: chip de fecha (sup-izq) y logo (inf-der).
                # Una etiqueta pegada al borde no debe caer encima de ellas.
                if story.get("dates") and sx < W * 0.34 and sy < H * 0.20:
                    sy = H * 0.22
                if logo_img is not None and sx > W * 0.66 and sy > H * 0.84:
                    sy = H * 0.80
                # si el pais quedo MUY lejos del cuadro, se atenua en vez de gritar
                fade = 1.0 if onscreen else 0.55
            else:
                fade = 1.0
                if not (-100 < sx < W + 100 and -100 < sy < H + 100):
                    continue
            _draw_country(d, sx, sy, ml["text"], ml.get("size", 1.0), W,
                          ml.get("alpha", 0.82) * fade, dark=(theme == "dark"))

        # marcador de FOCO pulsante
        if focus:
            fa = max(0.0, min(1.0, (t - focus.get("t", 3)) / 0.5))
            if fa > 0:
                sx, sy = screen(focus["lon"], focus["lat"])
                if -80 < sx < W + 80 and -80 < sy < H + 80:
                    _draw_focus(d, sx, sy, t, fa)

        # ---- KIT CASPIAN: flechas dasheadas / arcos / ciudades / pins ----
        import overlays as OV
        # FLECHAS: se dibujan progresivamente entre t0 y t1, con punta triangular
        for ar in story.get("arrows", []):
            t0, t1 = ar.get("t", [3, 6])
            if t < t0:
                continue
            prog = 1.0 if t >= t1 else (t - t0) / max(0.01, t1 - t0)
            pth = ar.get("path") or [ar["from"], ar["to"]]
            spts = [screen(lo, la) for lo, la in pth]
            if ar.get("curve"):
                spts = OV.bezier(spts[0], spts[-1], curve=float(ar["curve"]))
            col = _hexc(ar.get("color", "#1A1A22"))
            wdt = int(ar.get("width", max(5, W // 320)))
            tip = OV.dashed_line(d, spts, col, width=wdt,
                                 dash=ar.get("dash", 20), gap=ar.get("gap", 14),
                                 progress=prog)
            if prog >= 0.99 and ar.get("head", True) and len(spts) > 1:
                OV.arrow_head(d, spts[-1], spts[-2], col, size=int(wdt * 4.2))
            elif tip and ar.get("head", True):
                OV.arrow_head(d, tip, spts[0], col, size=int(wdt * 3.6))

        # CIUDADES: dot amarillo + nombre
        for c in story.get("cities", []):
            ca = max(0.0, min(1.0, (t - c.get("t", 0)) / 0.5)) if c.get("t") else 1.0
            if ca <= 0:
                continue
            sx, sy = screen(c["lon"], c["lat"])
            if -60 < sx < W + 60 and -60 < sy < H + 60 and not under_ui(sx, sy):
                # si hay un icono en esta misma coordenada, corre el nombre para no pisarlo
                off = 0
                for ic in story.get("icons", []):
                    if abs(ic.get("lon", 1e9) - c["lon"]) < 1e-4 and \
                       abs(ic.get("lat", 1e9) - c["lat"]) < 1e-4:
                        off = int(W * ic.get("size", 0.012) * 1.6)
                        break
                OV.city_dot(d, sx, sy, c.get("name", ""),
                            font(int(W / 56), style=story.get("city_font", "serif_italic")),
                            alpha=ca, r=int(W / 200), offset=off,
                            side=c.get("side", "right"),
                            ink=_hexc(c.get("ink", "#28241E")) if theme != "dark" else (245, 246, 248),
                            halo=(255, 255, 255) if theme != "dark" else (10, 12, 16),
                            fill=_hexc(c.get("dot", "#FFD63D")))

        # ICONOS en coordenadas (ancla, barco, avion, alerta, base)
        for ic in story.get("icons", []):
            ia = max(0.0, min(1.0, (t - ic.get("t", 0)) / 0.4)) if ic.get("t") else 1.0
            if ia <= 0:
                continue
            sx, sy = screen(ic["lon"], ic["lat"])
            if -60 < sx < W + 60 and -60 < sy < H + 60 and not under_ui(sx, sy):
                OV.icon(d, sx, sy, ic.get("kind", "dot"),
                        size=int(W * ic.get("size", 0.012)),
                        color=_hexc(ic.get("color", "#1A1A22")),
                        bg=_hexc(ic.get("bg", "#FFFFFF")), alpha=ia,
                        invert=ic.get("invert", story.get("icons_invert", True)))

        # CAJAS DE CALL-OUT blancas con linea lider (referencia "Mountains/Urban areas")
        for co in story.get("callouts", []):
            # aparicion TRANQUILA: 1.1s con easing suave (antes 0.5s lineal = golpe)
            oa = ease(max(0.0, min(1.0, (t - co.get("t", 0)) / 1.1))) if co.get("t") else 1.0
            if oa <= 0:
                continue
            ax, ay = screen(co["lon"], co["lat"])
            bx = ax + co.get("dx", 0.10) * W
            by = ay + co.get("dy", -0.12) * H
            mgx, mgy = W * 0.13, H * 0.10
            bx = max(mgx, min(W - mgx, bx))
            by = max(mgy, min(H - mgy, by))
            OV.callout_box(d, bx, by, co["text"], font(int(W / co.get("fs", 52))),
                           anchor=(ax, ay), alpha=oa,
                           bg=_hexc(co.get("bg", "#FFFFFF")),
                           ink=_hexc(co.get("ink", "#18181C")),
                           lead=_hexc(co.get("lead", "#FFFFFF")))

        # PINS CON FOTO DE LIDER: recorte circular + aro + linea al punto del mapa
        for lp in story.get("leaders", []):
            la2 = max(0.0, min(1.0, (t - lp.get("t", 0)) / 0.5)) if lp.get("t") else 1.0
            if la2 <= 0:
                continue
            ax, ay = screen(lp["lon"], lp["lat"])
            # el pin flota desplazado del punto (offset en fraccion de pantalla)
            ox = lp.get("dx", 0.10) * W
            oy = lp.get("dy", -0.14) * H
            px, py = ax + ox, ay + oy
            # clamp: el pin nunca se sale del cuadro (con margen para aro + etiqueta)
            _r = int(W * lp.get("size", 0.045))
            m = _r + int(W * 0.02)
            px = max(m, min(W - m, px))
            py = max(m, min(H - m - int(H * 0.06), py))
            if True:
                OV.photo_pin(frame, d, px, py, lp["photo"],
                             r=int(W * lp.get("size", 0.045)), alpha=la2,
                             anchor=(ax, ay), font_obj=font(int(W / 72)),
                             label=lp.get("label"))

        # PINS: circulo de faccion con etiqueta
        for p in story.get("pins", []):
            pa = max(0.0, min(1.0, (t - p.get("t", 0)) / 0.5)) if p.get("t") else 1.0
            if pa <= 0:
                continue
            sx, sy = screen(p["lon"], p["lat"])
            if -100 < sx < W + 100 and -100 < sy < H + 100:
                OV.pin(d, sx, sy, _hexc(p.get("color", "#C9A84C")),
                       font(int(W / 70)), p.get("label"), r=int(W / 58), alpha=pa)

        # BANNER de titulo (marcador amarillo) + CHIP de fecha — en pantalla
        for bn in story.get("banners", []):
            ba = _fade_window(t, bn.get("in", 1.0), bn.get("out", 6.0), 0.45)
            if ba > 0:
                import overlays as OV2
                OV2.title_banner(d, W, H, bn["text"].upper(),
                                 font(int(W / (bn.get("scale") and 16 / bn["scale"] or 16))),
                                 y_frac=bn.get("y", 0.42), alpha=ba)
        for dc in story.get("dates", []):
            da = _fade_window(t, dc.get("in", 0.5), dc.get("out", 99), 0.4)
            if da > 0:
                import overlays as OV3
                OV3.date_chip(d, W, H, dc["text"], font(int(W / 34)), alpha=da)

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
    """Inclina el mapa en 2.5D (rig rotation_x) SIN mostrar el borde del mapa.

    Clave: el mapa recortado abarca MAS area de la que se ve, asi que al inclinar
    el cuadro sigue lleno de mapa (nada de 'mesa' flotando con cielo alrededor).
    La perspectiva se aplica mapeando el cuadro completo a un trapecio que se
    EXTIENDE por fuera del lienzo — el horizonte queda fuera de cuadro."""
    from PIL import Image
    # el trapecio se abre por fuera del lienzo: arriba mas angosto pero aun asi
    # mas ancho que W, y los lados de abajo se salen -> nunca se ve el borde.
    # El frame que entra ya trae MAS area de mapa (crop expandido). Su borde
    # superior completo se mapea al ancho del cuadro (lo lejano, comprimido) y su
    # borde inferior se abre POR FUERA del lienzo (lo cercano, ampliado).
    # Perspectiva fuerte: el borde inferior se abre MUCHO por fuera del lienzo y
    # el superior se levanta por encima -> compresion progresiva hacia el fondo
    # (lo lejano se apelmaza arriba), que es lo que hace legible la inclinacion.
    # CALIBRADO: 1.9 deformaba el pais ("derretido"); 0.85 no se notaba.
    # 1.15 da perspectiva legible sin romper la forma. tilt_deg util: 20-35.
    bulge = 1.15 * tilt
    rise = 0.20 * tilt
    dst = [(0, -H * rise), (W, -H * rise),
           (W * (1 + bulge), H), (-W * bulge, H)]
    src = [(0, 0), (W, 0), (W, H), (0, H)]
    coeffs = _find_coeffs(dst, src)
    warped = frame_rgba.transform((W, H), Image.PERSPECTIVE, coeffs, Image.BICUBIC)
    fwd = _find_coeffs(src, dst)   # directa: punto del mapa plano -> mapa inclinado
    return warped, fwd


def _draw_country(d, x, y, text, size, W, alpha, dark=False):
    """Etiqueta de pais con tracking amplio. En tema OSCURO el texto va claro
    (sobre tierra negra el marron es ilegible) con sombra negra de contraste."""
    txt = " ".join(list(text.upper()))   # letter-spacing manual
    fs = int(W / 34 * size)
    f = font(fs, bold=True)
    tw = d.textlength(txt, font=f)
    px, py = x - tw / 2, y - fs / 2
    # BISELADO 3D (como el "TAIWAN" gris de la referencia): sombra proyectada en
    # diagonal + realce claro arriba-izquierda + cuerpo del texto encima.
    depth = max(3, int(fs * 0.055))
    if dark:
        body, hi, sh = (176, 180, 186), (232, 236, 240), (8, 10, 14)
    else:
        body, hi, sh = (86, 78, 66), (232, 226, 214), (24, 20, 14)
    for k in range(depth, 0, -1):
        d.text((px + k, py + k), txt, fill=_a(sh, 0.42 * alpha), font=f)
    d.text((px - 1.5, py - 1.5), txt, fill=_a(hi, 0.55 * alpha), font=f)
    d.text((px, py), txt, fill=_a(body, alpha), font=f)


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
    # sin vignette: oscurecia los bordes y era parte del look "apagado".
    # gamma>1 y brightness levantan el conjunto; saturacion para vida.
    vf = ("eq=contrast=1.02:saturation=1.08:gamma=1.0,"
          "unsharp=5:5:0.4:5:5:0.0,"
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
    # nombres de lugar -> coordenadas ("place": "Fuzhou")
    try:
        from places import resolve_story
        story = resolve_story(story)
    except Exception as ex:
        print("[places] aviso:", ex)
    # marca: rellena lo que el story no defina explicitamente
    bpath_brand = os.path.join(HERE, "..", "brand.json")
    if os.path.exists(bpath_brand):
        with open(bpath_brand, encoding="utf-8") as f:
            brand = json.load(f)
        story.setdefault("_brand", brand)
        if "logo" not in story:
            story["logo"] = brand.get("logo", {}).get("dark")
        story.setdefault("logo_opacity", brand.get("logo", {}).get("opacity", 0.5))
    render(story, a.format, a.out)


if __name__ == "__main__":
    main()
