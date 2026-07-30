"""
overlays.py — kit de elementos estilo Caspian Report sobre el mapa:
  · flechas DASHEADAS (dasharray 6/4) con punta triangular, que se dibujan en el tiempo
  · arcos Bezier entre dos puntos (rutas de vuelo/comercio)
  · puntos de ciudad (dot amarillo + nombre en serif)
  · pins circulares (bandera/color) con etiqueta
  · banner de titulo (marcador amarillo estilo highlighter)
  · timeline / fecha en pantalla

Todo se dibuja en coordenadas de PANTALLA (ya proyectadas), asi que funciona con
cualquier mapa del mundo y con la camara en movimiento.
"""
import math


def _a(c, alpha):
    return (c[0], c[1], c[2], int(max(0.0, min(1.0, alpha)) * 255))


def dashed_line(d, pts, color, width=6, dash=18, gap=12, progress=1.0, alpha=1.0):
    """Linea dasheada que se dibuja progresivamente (progress 0..1)."""
    if len(pts) < 2 or progress <= 0:
        return None
    # longitud acumulada
    segs = []
    total = 0.0
    for i in range(len(pts) - 1):
        (x0, y0), (x1, y1) = pts[i], pts[i + 1]
        L = math.hypot(x1 - x0, y1 - y0)
        segs.append((x0, y0, x1, y1, L))
        total += L
    target = total * progress
    drawn = 0.0
    pos = 0.0
    last = pts[0]
    for (x0, y0, x1, y1, L) in segs:
        if L <= 0:
            continue
        t = 0.0
        while t < L:
            if drawn + t >= target:
                return last
            seg_len = min(dash, L - t, target - (drawn + t))
            if seg_len <= 0:
                break
            f0, f1 = t / L, (t + seg_len) / L
            ax, ay = x0 + (x1 - x0) * f0, y0 + (y1 - y0) * f0
            bx, by = x0 + (x1 - x0) * f1, y0 + (y1 - y0) * f1
            d.line([ax, ay, bx, by], fill=_a(color, alpha), width=width)
            last = (bx, by)
            t += dash + gap
        drawn += L
    return last


def arrow_head(d, tip, from_pt, color, size=26, alpha=1.0):
    """Punta triangular solida (estilo Caspian) apuntando desde from_pt hacia tip."""
    ang = math.atan2(tip[1] - from_pt[1], tip[0] - from_pt[0])
    a1, a2 = ang + 2.5, ang - 2.5
    p1 = (tip[0] + size * math.cos(a1), tip[1] + size * math.sin(a1))
    p2 = (tip[0] + size * math.cos(a2), tip[1] + size * math.sin(a2))
    d.polygon([tip, p1, p2], fill=_a(color, alpha))


def bezier(p0, p1, curve=0.28, steps=60):
    """Arco Bezier cuadratico entre dos puntos (ruta de vuelo/comercio)."""
    mx, my = (p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    # punto de control perpendicular al segmento
    cx, cy = mx - dy * curve, my + dx * curve
    pts = []
    for i in range(steps + 1):
        t = i / steps
        x = (1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * cx + t * t * p1[0]
        y = (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * cy + t * t * p1[1]
        pts.append((x, y))
    return pts


def city_dot(d, x, y, name, font_obj, alpha=1.0, r=9,
             fill=(255, 214, 61), ink=(40, 36, 30), halo=(255, 255, 255),
             offset=0, side="right"):
    """Punto de ciudad + nombre con halo. 'offset' separa el texto cuando hay un
    icono en el mismo punto (evita que se pisen); 'side' lo pone a izq/der."""
    d.ellipse([x - r, y - r, x + r, y + r], fill=_a(fill, alpha),
              outline=_a((60, 54, 44), alpha), width=2)
    if name:
        gap = r + 8 + offset
        if side == "left":
            tw = d.textlength(name, font=font_obj)
            tx = x - gap - tw
        else:
            tx = x + gap
        ty = y - r - 2
        for ox, oy in ((-2, 0), (2, 0), (0, -2), (0, 2), (-2, -2), (2, 2)):
            d.text((tx + ox, ty + oy), name, fill=_a(halo, 0.9 * alpha), font=font_obj)
        d.text((tx, ty), name, fill=_a(ink, alpha), font=font_obj)


def pin(d, x, y, color, font_obj=None, label=None, r=34, alpha=1.0):
    """Pin circular (color/faccion) con aro blanco y etiqueta opcional."""
    d.ellipse([x - r - 4, y - r - 4, x + r + 4, y + r + 4], fill=_a((255, 255, 255), alpha))
    d.ellipse([x - r, y - r, x + r, y + r], fill=_a(color, alpha),
              outline=_a((30, 28, 24), alpha), width=3)
    if label and font_obj:
        tw = d.textlength(label, font=font_obj)
        d.text((x - tw / 2, y + r + 8), label, fill=_a((30, 28, 24), alpha), font=font_obj)


def callout_box(d, x, y, text, font_obj, anchor=None, alpha=1.0,
                bg=(255, 255, 255), ink=(24, 24, 28), pad=16, radius=10,
                shadow=True, lead=(255, 255, 255), lead_w=3):
    """Caja blanca de call-out con linea lider curvada al punto del mapa.
    Es el elemento de 'Mountains / Urban areas / Rough seas' de la referencia."""
    lines = text.split("\n")
    fs = getattr(font_obj, "size", 30)
    tw = max(d.textlength(ln, font=font_obj) for ln in lines)
    th = fs * len(lines) + (len(lines) - 1) * 6
    x0, y0 = x - tw / 2 - pad, y - th / 2 - pad * 0.7
    x1, y1 = x + tw / 2 + pad, y + th / 2 + pad * 0.7

    # linea lider: sale del borde mas cercano de la caja hacia el punto
    if anchor is not None:
        ax, ay = anchor
        ex = min(max(ax, x0 + 8), x1 - 8)
        ey = y1 if ay > y1 else (y0 if ay < y0 else y)
        d.line([ex, ey, ax, ay], fill=_a(lead, 0.95 * alpha), width=lead_w)
        d.ellipse([ax - 5, ay - 5, ax + 5, ay + 5], fill=_a(lead, alpha))

    if shadow:
        d.rounded_rectangle([x0 + 5, y0 + 6, x1 + 5, y1 + 6], radius=radius,
                            fill=_a((0, 0, 0), 0.22 * alpha))
    d.rounded_rectangle([x0, y0, x1, y1], radius=radius, fill=_a(bg, 0.97 * alpha))
    cy = y0 + pad * 0.7
    for ln in lines:
        lw = d.textlength(ln, font=font_obj)
        d.text((x - lw / 2, cy), ln, fill=_a(ink, alpha), font=font_obj)
        cy += fs + 6


# --- ICONOS vectoriales (sin archivos externos): ancla, barco, avion, alerta, base
def icon(d, x, y, kind, size=22, color=(24, 24, 28), bg=(255, 255, 255), alpha=1.0):
    """Icono en coordenada: 'anchor' | 'ship' | 'plane' | 'alert' | 'base' | 'dot'."""
    s = size
    if kind != "none":
        d.ellipse([x - s * 1.25, y - s * 1.25, x + s * 1.25, y + s * 1.25],
                  fill=_a(bg, alpha), outline=_a(color, alpha), width=max(2, s // 9))
    c = _a(color, alpha)
    if kind == "anchor":
        d.line([x, y - s * 0.75, x, y + s * 0.7], fill=c, width=max(3, s // 6))
        d.line([x - s * 0.42, y - s * 0.34, x + s * 0.42, y - s * 0.34], fill=c, width=max(3, s // 7))
        d.arc([x - s * 0.62, y - s * 0.1, x + s * 0.62, y + s * 0.85], 20, 160, fill=c, width=max(3, s // 6))
        d.ellipse([x - s * 0.16, y - s * 0.96, x + s * 0.16, y - s * 0.64], outline=c, width=max(2, s // 8))
    elif kind == "ship":
        d.polygon([(x - s * 0.7, y + s * 0.1), (x + s * 0.7, y + s * 0.1),
                   (x + s * 0.42, y + s * 0.55), (x - s * 0.42, y + s * 0.55)], fill=c)
        d.rectangle([x - s * 0.34, y - s * 0.45, x + s * 0.18, y + s * 0.06], fill=c)
        d.line([x + s * 0.4, y - s * 0.6, x + s * 0.4, y + s * 0.08], fill=c, width=max(2, s // 9))
    elif kind == "plane":
        d.polygon([(x, y - s * 0.8), (x + s * 0.18, y - s * 0.1), (x + s * 0.8, y + s * 0.28),
                   (x + s * 0.8, y + s * 0.46), (x + s * 0.14, y + s * 0.3),
                   (x + s * 0.1, y + s * 0.62), (x + s * 0.36, y + s * 0.82),
                   (x + s * 0.36, y + s * 0.94), (x, y + s * 0.78),
                   (x - s * 0.36, y + s * 0.94), (x - s * 0.36, y + s * 0.82),
                   (x - s * 0.1, y + s * 0.62), (x - s * 0.14, y + s * 0.3),
                   (x - s * 0.8, y + s * 0.46), (x - s * 0.8, y + s * 0.28),
                   (x - s * 0.18, y - s * 0.1)], fill=c)
    elif kind == "alert":
        d.polygon([(x, y - s * 0.78), (x + s * 0.78, y + s * 0.6), (x - s * 0.78, y + s * 0.6)],
                  fill=c)
        d.line([x, y - s * 0.24, x, y + s * 0.2], fill=_a(bg, alpha), width=max(3, s // 6))
        d.ellipse([x - s * 0.09, y + s * 0.3, x + s * 0.09, y + s * 0.46], fill=_a(bg, alpha))
    elif kind == "base":
        d.rectangle([x - s * 0.6, y - s * 0.45, x + s * 0.6, y + s * 0.5], fill=c)
        d.polygon([(x - s * 0.75, y - s * 0.45), (x, y - s * 0.95), (x + s * 0.75, y - s * 0.45)],
                  fill=c)
    elif kind == "dot":
        d.ellipse([x - s * 0.45, y - s * 0.45, x + s * 0.45, y + s * 0.45], fill=c)


_PHOTO_CACHE = {}


def photo_pin(frame, d, x, y, img_path, r=70, alpha=1.0, ring=(255, 255, 255),
              ring_w=6, anchor=None, font_obj=None, label=None,
              ink=(28, 26, 22), lead=(28, 26, 22)):
    """Pin circular con FOTO de lider (recorte redondo + aro + linea al punto).
    frame: imagen RGBA sobre la que se compone. img_path: foto local del usuario."""
    from PIL import Image, ImageDraw
    key = (img_path, r)
    if key not in _PHOTO_CACHE:
        try:
            im = Image.open(img_path).convert("RGBA")
        except Exception:
            return
        # recorte cuadrado centrado (levemente arriba: las caras van en el tercio superior)
        s = min(im.width, im.height)
        cx, cy = im.width // 2, int(im.height * 0.42)
        box = (max(0, cx - s // 2), max(0, cy - s // 2))
        im = im.crop((box[0], box[1], box[0] + s, box[1] + s)).resize((2 * r, 2 * r), Image.LANCZOS)
        mask = Image.new("L", (2 * r, 2 * r), 0)
        ImageDraw.Draw(mask).ellipse([0, 0, 2 * r - 1, 2 * r - 1], fill=255)
        im.putalpha(mask)
        _PHOTO_CACHE[key] = im
    photo = _PHOTO_CACHE[key]

    # linea guia desde el punto del mapa hasta el pin
    if anchor is not None:
        d.line([anchor[0], anchor[1], x, y], fill=_a(lead, 0.85 * alpha), width=3)
        d.ellipse([anchor[0] - 6, anchor[1] - 6, anchor[0] + 6, anchor[1] + 6],
                  fill=_a(lead, alpha))

    # aro blanco + sombra suave
    d.ellipse([x - r - ring_w - 2, y - r - ring_w - 2, x + r + ring_w + 2, y + r + ring_w + 2],
              fill=_a((0, 0, 0), 0.18 * alpha))
    d.ellipse([x - r - ring_w, y - r - ring_w, x + r + ring_w, y + r + ring_w],
              fill=_a(ring, alpha))

    if alpha < 0.999:
        ph = photo.copy()
        aband = ph.split()[3].point(lambda v: int(v * alpha))
        ph.putalpha(aband)
    else:
        ph = photo
    frame.alpha_composite(ph, (int(x - r), int(y - r)))

    if label and font_obj:
        tw = d.textlength(label, font=font_obj)
        fs = getattr(font_obj, "size", 28)
        bx, by = x - tw / 2 - 12, y + r + ring_w + 8
        d.rounded_rectangle([bx, by, bx + tw + 24, by + fs + 14], radius=8,
                            fill=_a((255, 255, 255), 0.92 * alpha))
        d.text((bx + 12, by + 6), label, fill=_a(ink, alpha), font=font_obj)


def title_banner(d, W, H, text, font_obj, y_frac=0.42, alpha=1.0,
                 hl=(245, 232, 70), ink=(15, 15, 18), pad=26, skew=0.012):
    """Banner de titulo con marcador amarillo (highlighter) estilo Caspian."""
    tw = d.textlength(text, font=font_obj)
    fs = font_obj.size if hasattr(font_obj, "size") else 60
    x = (W - tw) / 2
    y = H * y_frac
    dy = W * skew
    # cinta amarilla levemente inclinada
    d.polygon([(x - pad, y - pad * 0.5 + dy), (x + tw + pad, y - pad * 0.5 - dy),
               (x + tw + pad, y + fs + pad * 0.6 - dy), (x - pad, y + fs + pad * 0.6 + dy)],
              fill=_a(hl, 0.92 * alpha))
    d.text((x, y), text, fill=_a(ink, alpha), font=font_obj)


def date_chip(d, W, H, text, font_obj, alpha=1.0, margin=0.045,
              bg=(18, 18, 24), ink=(245, 242, 235)):
    """Chip de fecha/timeline arriba a la izquierda (estilo Caspian/Rhodesia)."""
    tw = d.textlength(text, font=font_obj)
    fs = font_obj.size if hasattr(font_obj, "size") else 40
    x, y = W * margin, H * margin
    d.rounded_rectangle([x, y, x + tw + 32, y + fs + 20], radius=10, fill=_a(bg, 0.92 * alpha))
    d.text((x + 16, y + 8), text, fill=_a(ink, alpha), font=font_obj)
