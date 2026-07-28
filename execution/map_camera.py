"""
map_camera.py — recorrido de camara cinematografico para mapas GeoLayers.

Toma una lista de waypoints (lat/lon/zoom/pitch/bearing con 'dwell' opcional) y
devuelve una lista densa de keyframes {t, lat, lon, zoom, pitch, bearing} lista
para emitir como llamadas geolayers3.setViewAtTime().

Porta la idea del camera_path() de macrowise-chart-animator: interpolar suave
entre puntos clave PERO clavando MICRO-PAUSAS dramaticas en los waypoints marcados
(el "punch-in" estilo Johnny Harris: la camara llega, se queda quieta un beat, sigue).
"""

FPS = 30.0


def _ease(u):
    # ease-in-out cubico (mismo criterio que el repo de graficas)
    return 3 * u * u - 2 * u * u * u


def _lerp(a, b, u):
    return a + (b - a) * u


def build_camera(waypoints, duration, fps=FPS):
    """
    waypoints: [{t, lat, lon, zoom, pitch?, bearing?, dwell?}, ...] ordenados por t.
    Devuelve [{t, lat, lon, zoom, pitch, bearing}, ...] muestreado por frame.
    En cada waypoint con 'dwell' > 0 la camara queda CONGELADA ese lapso (micro-pausa).
    """
    wps = sorted(waypoints, key=lambda w: w["t"])
    for w in wps:
        w.setdefault("pitch", 0.0)
        w.setdefault("bearing", 0.0)
        w.setdefault("dwell", 0.0)

    keys = []
    n_frames = int(round(duration * fps))
    for f in range(n_frames + 1):
        t = f / fps
        # localizar el segmento [a,b] que contiene t, respetando dwell en cada wp
        seg = _segment_state(wps, t)
        keys.append({"t": round(t, 4), **seg})
    return keys


def _segment_state(wps, t):
    # antes del primer waypoint: fijo en el primero
    if t <= wps[0]["t"]:
        return _state(wps[0])
    # despues del ultimo: fijo en el ultimo
    if t >= wps[-1]["t"]:
        return _state(wps[-1])

    for i in range(len(wps) - 1):
        a, b = wps[i], wps[i + 1]
        if a["t"] <= t <= b["t"]:
            # micro-pausa: los primeros 'dwell' segundos tras llegar a 'a' quedan fijos en a
            if a["dwell"] > 0 and t <= a["t"] + a["dwell"]:
                return _state(a)
            t0 = a["t"] + a["dwell"]
            span = b["t"] - t0
            u = 0.0 if span <= 0 else _ease((t - t0) / span)
            return {
                "lat": _lerp(a["lat"], b["lat"], u),
                "lon": _lerp(a["lon"], b["lon"], u),
                "zoom": _lerp(a["zoom"], b["zoom"], u),
                "pitch": _lerp(a["pitch"], b["pitch"], u),
                "bearing": _lerp(a["bearing"], b["bearing"], u),
            }
    return _state(wps[-1])


def _state(w):
    return {"lat": w["lat"], "lon": w["lon"], "zoom": w["zoom"],
            "pitch": w["pitch"], "bearing": w["bearing"]}


if __name__ == "__main__":
    # auto-test: micro-pausa real en el waypoint del medio
    wps = [
        {"t": 0, "lat": 26.5, "lon": 56.2, "zoom": 4.2, "dwell": 0.7},
        {"t": 6, "lat": 26.6, "lon": 56.5, "zoom": 6.8, "pitch": 45, "dwell": 0.7},
        {"t": 14, "lat": 25.9, "lon": 57.0, "zoom": 7.5, "pitch": 55},
    ]
    ks = build_camera(wps, 20)
    # durante la micro-pausa (t=6.0..6.7) el zoom no debe moverse
    z6 = [k["zoom"] for k in ks if 6.0 <= k["t"] <= 6.7]
    assert max(z6) - min(z6) < 1e-6, "micro-pausa fallo: la camara se movio"
    print("OK map_camera:", len(ks), "keyframes, micro-pausa en t=6 verificada")
