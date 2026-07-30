"""
places.py — busqueda de lugares por NOMBRE -> coordenadas.

Permite escribir el story con nombres ("Fuzhou", "Taipei", "Moscu") en vez de
lat/lon a mano. Usa Natural Earth populated_places (7000+ ciudades con poblacion),
puertos y aeropuertos, ya descargados en el cache.
"""
import os
import sys
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from fetch_geodata import load  # noqa

_INDEX = None


def _norm(s):
    s = unicodedata.normalize("NFD", str(s or ""))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.lower().strip()


def _build():
    global _INDEX
    if _INDEX is not None:
        return _INDEX
    idx = {}

    def add(name, lon, lat, kind, pop=0):
        k = _norm(name)
        if not k:
            return
        prev = idx.get(k)
        if prev is None or pop > prev["pop"]:
            idx[k] = {"name": name, "lon": float(lon), "lat": float(lat),
                      "kind": kind, "pop": pop}

    for f in load("cities").get("features", []):
        p = f.get("properties", {})
        g = f.get("geometry", {})
        if g.get("type") != "Point":
            continue
        lon, lat = g["coordinates"][:2]
        pop = p.get("POP_MAX") or p.get("POP_MIN") or 0
        for key in ("NAME", "NAMEASCII", "NAME_ES", "NAME_EN", "NAME_ALT"):
            v = p.get(key)
            if v:
                for part in str(v).split("|"):
                    add(part, lon, lat, "city", pop or 0)
    for layer, kind in (("ports", "port"), ("airports", "airport")):
        try:
            for f in load(layer).get("features", []):
                p = f.get("properties", {})
                g = f.get("geometry", {})
                if g.get("type") != "Point":
                    continue
                lon, lat = g["coordinates"][:2]
                add(p.get("name") or p.get("NAME"), lon, lat, kind, 0)
        except SystemExit:
            pass
    _INDEX = idx
    return idx


def find(name):
    """Devuelve {'name','lon','lat','kind','pop'} o None."""
    idx = _build()
    k = _norm(name)
    if k in idx:
        return idx[k]
    # match parcial: prioriza la de mayor poblacion
    cands = [v for kk, v in idx.items() if k and (kk.startswith(k) or k in kk)]
    if cands:
        return max(cands, key=lambda v: v["pop"])
    return None


def coords(name):
    r = find(name)
    if not r:
        raise SystemExit("No encontre el lugar: %s" % name)
    return [r["lon"], r["lat"]]


def resolve_story(story):
    """Reemplaza 'place': 'Fuzhou' por lon/lat en cities/icons/callouts/leaders/pins,
    y 'from_place'/'to_place' en arrows. Asi el story se escribe con NOMBRES."""
    def fix(obj):
        if isinstance(obj, dict) and "place" in obj and "lon" not in obj:
            c = coords(obj.pop("place"))
            obj["lon"], obj["lat"] = c[0], c[1]
        return obj

    for key in ("cities", "icons", "callouts", "leaders", "pins", "map_labels", "labels"):
        for o in story.get(key, []) or []:
            fix(o)
    for a in story.get("arrows", []) or []:
        if "from_place" in a:
            a["from"] = coords(a.pop("from_place"))
        if "to_place" in a:
            a["to"] = coords(a.pop("to_place"))
        if "path_places" in a:
            a["path"] = [coords(p) for p in a.pop("path_places")]
    if story.get("focus") and "place" in story["focus"]:
        fix(story["focus"])
    return story


if __name__ == "__main__":
    for q in sys.argv[1:] or ["Fuzhou", "Taipei", "Moscu", "Teheran", "Kaohsiung"]:
        r = find(q)
        print("%-14s -> %s" % (q, r if r else "NO ENCONTRADO"))
