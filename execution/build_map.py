"""
build_map.py — genera un ExtendScript (.jsx) que anima un mapa en GeoLayers 3.

Entrada: un "story-spec" JSON (ver stories/estrecho_ormuz.json).
Salida:  un .jsx que, corrido en AE con el PANEL DE GEOLAYERS ABIERTO y un Mapcomp
         base ya creado, llama la API de GeoLayers para:
           - recorrer la camara (setViewAtTime) con micro-pausas cinematograficas,
           - dibujar regiones/fronteras (addToBrowser + draw),
           - marcar rutas y etiquetas (addLabel),
           - finalizar el render (finalize).

IMPORTANTE (limites reales de GeoLayers, ver directives/animate_map.md):
  * El panel de GeoLayers debe estar ABIERTO o la API no responde.
  * La API NO crea el Mapcomp base -> se crea a mano una vez (setup one-time).
  * Correr el .jsx con AfterFX -r desde una TERMINAL INTERACTIVA, AE sin dialogos.

Uso:
  python build_map.py stories/estrecho_ormuz.json --out mapa.jsx
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from map_camera import build_camera  # noqa: E402

# Paleta MacroWise (misma que macrowise-chart-animator) para etiquetas/acentos.
PALETTE = {
    "ink": "#2a2a2a", "accent": "#c44933", "mustard": "#b8912e", "bg": "#0f141b",
}


def load_story(path):
    with open(path, encoding="utf-8") as f:
        s = json.load(f)
    s.setdefault("duration", 20)
    s.setdefault("waypoints", [])
    s.setdefault("regions", [])
    s.setdefault("routes", [])
    s.setdefault("labels", [])
    if not s["waypoints"]:
        raise SystemExit("story-spec sin 'waypoints': la camara necesita al menos 2")
    return s


def emit_jsx(story, cam_keys):
    data = {
        "dur": story["duration"],
        "cam": cam_keys,
        "regions": story["regions"],
        "routes": story["routes"],
        "labels": story["labels"],
        "pal": PALETTE,
    }
    blob = json.dumps(data)
    # El .jsx: toda la logica vive en GeoLayers; nosotros solo secuenciamos su API.
    return r"""// AUTO-GENERADO por build_map.py — NO editar a mano.
// Requiere: panel GEOlayers 3 ABIERTO + un Mapcomp base ya creado y seleccionado.
var D = %s;
function log(m){ try{ var f=new File(Folder.temp.fsName+"/mw_map_log.txt");
  f.open("a"); f.writeln(m); f.close(); }catch(e){} }

(function(){
  if (typeof geolayers3 === "undefined"){
    log("ERROR: geolayers3 no esta definido. Abrir el panel de GEOlayers 3.");
    alert("Abri el panel de GEOlayers 3 (Window > GEOlayers 3) antes de correr esto.");
    return;
  }
  app.beginUndoGroup("MW Map Animate");
  try {
    // 1) REGIONES / FRONTERAS: importar al browser y dibujar como shape layers.
    for (var r=0; r<D.regions.length; r++){
      var reg = D.regions[r];
      try {
        if (reg.query) geolayers3.addToBrowser(reg.query);      // geocoding / OSM
        geolayers3.drawBrowserSelection();                       // dibuja lo seleccionado
        log("region: "+(reg.query||"(sel)"));
      } catch(er){ log("region ERROR "+r+": "+er.toString()); }
    }

    // 2) RUTAS: dibujar una linea entre 'from' y 'to' con reveal temporal.
    for (var i=0; i<D.routes.length; i++){
      var ro = D.routes[i];
      try {
        var geo = { "type":"LineString", "coordinates":[ro.from, ro.to] };
        geolayers3.draw(geo);
        log("ruta "+i+" "+JSON.stringify(ro.from)+" -> "+JSON.stringify(ro.to));
      } catch(er){ log("ruta ERROR "+i+": "+er.toString()); }
    }

    // 3) ETIQUETAS / MARCADORES por coordenada.
    for (var k=0; k<D.labels.length; k++){
      var lb = D.labels[k];
      try {
        geolayers3.addLabel(lb.lat, lb.lon, lb.text);
        log("label: "+lb.text);
      } catch(er){ log("label ERROR "+k+": "+er.toString()); }
    }

    // 4) CAMARA: un keyframe setViewAtTime por muestra (incluye micro-pausas).
    for (var c=0; c<D.cam.length; c++){
      var v = D.cam[c];
      try {
        geolayers3.setViewAtTime(v.lat, v.lon, v.zoom, v.bearing, v.pitch, v.t);
      } catch(er){ if (c===0) log("camara ERROR: "+er.toString()); }
    }
    log("camara: "+D.cam.length+" keyframes, dur "+D.dur+"s");

    // 5) FINALIZE: render del Mapcomp (async).
    try { geolayers3.finalize(); log("finalize lanzado"); }
    catch(er){ log("finalize ERROR: "+er.toString()); }

  } catch(e){ log("FATAL: "+e.toString()+" @"+e.line); }
  app.endUndoGroup();
})();
""" % blob


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("story", help="ruta al story-spec JSON")
    ap.add_argument("--out", default="mapa.jsx")
    a = ap.parse_args()

    story = load_story(a.story)
    cam_keys = build_camera(story["waypoints"], story["duration"])
    jsx = emit_jsx(story, cam_keys)
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(jsx)
    print("OK: %s  (%d keyframes camara, %d regiones, %d rutas, %d labels)" % (
        a.out, len(cam_keys), len(story["regions"]),
        len(story["routes"]), len(story["labels"])))


if __name__ == "__main__":
    main()
