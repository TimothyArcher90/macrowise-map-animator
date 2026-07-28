"""
build_map_native.py — mapa animado estilo Johnny Harris SIN GeoLayers.

Toma un story-spec (con 'bbox'), baja el basemap satelital (fetch_basemap), proyecta
fronteras/rutas/labels (project), y emite un ExtendScript que en After Effects:
  - importa el basemap PNG como capa,
  - dibuja fronteras/rutas como shape layers con glow,
  - pone labels de texto tracked-caps (paleta MacroWise),
  - anima una CAMARA (Null padre) con Scale/Position + micro-pausas (map_camera),
  - NO renderiza dentro del jsx (lo hace aerender aparte — aprendizaje del repo graficas).

Formatos: horizontal 1920x1080 | vertical 1080x1920.
Uso:
  python build_map_native.py stories/estrecho_ormuz.json --format horizontal --comp MWMAP_ormuz --out mapa.jsx
"""
import argparse
import json
import math
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from map_camera import build_camera            # noqa: E402
from project import make_projector, download_natural_earth, country_rings  # noqa: E402

FORMATS = {"horizontal": (1920, 1080), "vertical": (1080, 1920)}
PAL = {"ink": "#f2efe9", "accent": "#e0533d", "mustard": "#e8b93a",
       "iran": "#e0533d", "oman": "#4ec9b0", "uae": "#e8b93a"}

TMP = os.path.join(HERE, "..", ".tmp")


def hex_rgb(h):
    h = h.lstrip("#")
    return [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]


def ensure_basemap(bbox, zoom):
    os.makedirs(TMP, exist_ok=True)
    tag = "%.2f_%.2f_%.2f_%.2f_z%d" % (bbox[0], bbox[1], bbox[2], bbox[3], zoom)
    out = os.path.join(TMP, "basemap_%s.png" % tag)
    if not os.path.exists(out):
        subprocess.run([sys.executable, os.path.join(HERE, "fetch_basemap.py"),
                        "--bbox", *[str(x) for x in bbox], "--zoom", str(zoom),
                        "--out", out], check=True)
    from PIL import Image
    w, h = Image.open(out).size
    return out, w, h


def fit_basemap_layout(bw, bh, W, H):
    """Escala el basemap para CUBRIR el lienzo (cover), centrado. Devuelve scale% y offset."""
    s = max(W / bw, H / bh)
    dw, dh = bw * s, bh * s
    return s, (W - dw) / 2.0, (H - dh) / 2.0


def build(story, fmt, comp_name, out_jsx):
    W, H = FORMATS[fmt]
    bbox = story["bbox"]
    zoom = story.get("basemap_zoom", 7)
    dur = story.get("duration", 20)

    basemap_path, bw, bh = ensure_basemap(bbox, zoom)
    # el basemap se dibuja a resolucion nativa en el centro de un mundo grande;
    # la CAMARA (null) hace zoom/pan. Proyectamos en pixeles del basemap nativo.
    proj = make_projector(bbox, zoom, bw, bh)
    ge = download_natural_earth(TMP)

    # fronteras -> polilineas en px del basemap
    regions = []
    for reg in story.get("regions", []):
        rings = country_rings(ge, reg["query"])
        col = PAL.get(reg.get("color", ""), PAL["accent"])
        polys = []
        for ring in rings:
            polys.append([list(proj(lon, lat)) for lon, lat in ring])
        regions.append({"name": reg["query"], "col": hex_rgb(col), "polys": polys})

    routes = []
    for ro in story.get("routes", []):
        pts = [list(proj(lon, lat)) for lon, lat in ro["path"]] if "path" in ro \
              else [list(proj(*ro["from"])), list(proj(*ro["to"]))]
        routes.append({"pts": pts, "draw_t": ro.get("draw_t", [4, 10])})

    labels = []
    for lb in story.get("labels", []):
        px, py = proj(lb["lon"], lb["lat"])
        labels.append({"x": px, "y": py, "text": lb["text"], "t": lb.get("t", 5)})

    # camara: waypoints lat/lon -> px del basemap + zoom relativo
    cam_raw = build_camera(story["waypoints"], dur)
    # convertir cada muestra a transform del basemap para encuadrar (lon/lat->px) + zoom
    s_fit, ox, oy = fit_basemap_layout(bw, bh, W, H)
    cam = []
    for k in cam_raw:
        cx, cy = proj(k["lon"], k["lat"])
        cam.append({"t": k["t"], "cx": cx, "cy": cy, "zoom": k["zoom"],
                    "pitch": k["pitch"], "bearing": k["bearing"]})

    data = {
        "comp": comp_name, "W": W, "H": H, "dur": dur, "fps": 30,
        "basemap": basemap_path.replace("\\", "/"), "bw": bw, "bh": bh,
        "regions": regions, "routes": routes, "labels": labels, "cam": cam,
        "pal": {k: hex_rgb(v) for k, v in PAL.items()},
        "zoom_ref": story["waypoints"][0].get("zoom", 5),
    }
    jsx = JSX % json.dumps(data)
    with open(out_jsx, "w", encoding="utf-8") as f:
        f.write(jsx)
    print("OK: %s  (%s %dx%d, %d regiones, %d rutas, %d labels, %d cam-keys)" % (
        out_jsx, fmt, W, H, len(regions), len(routes), len(labels), len(cam)))


# ExtendScript. La camara se implementa con un Null "CAM" al que se parentan el
# basemap y todas las capas de mapa; anima Scale/Position para el zoom/pan + micro-pausas.
JSX = r"""// AUTO-GENERADO por build_map_native.py — NO editar a mano.
var D = %s;
function log(m){ try{ var f=new File(Folder.temp.fsName+"/mw_mapnative_log.txt");
  f.open("a"); f.writeln(m); f.close(); }catch(e){} }
function rgb(a){ return [a[0],a[1],a[2]]; }

(function(){
  app.beginUndoGroup("MW Map Native");
  try {
    var comp = app.project.items.addComp(D.comp, D.W, D.H, 1.0, D.dur, D.fps);
    comp.openInViewer();

    // --- MUNDO: un Null "CAM" centrado; todo se parenta a el para zoom/pan ---
    var cam = comp.layers.addNull(D.dur);
    cam.name = "CAM";
    cam.property("Transform").property("Position").setValue([D.W/2, D.H/2]);

    // --- BASEMAP (imagen satelital) ---
    var io = new ImportOptions(new File(D.basemap));
    var foot = app.project.importFile(io);
    var base = comp.layers.add(foot);
    base.property("Transform").property("Anchor Point").setValue([D.bw/2, D.bh/2]);
    base.property("Transform").property("Position").setValue([D.W/2, D.H/2]);
    base.parent = cam;

    // --- FRONTERAS (shape layers con glow) ---
    function polyShape(pts, col, w){
      var sh = comp.layers.addShape(); sh.name="border";
      var grp = sh.property("Contents").addProperty("ADBE Vector Group");
      var path = grp.property("Contents").addProperty("ADBE Vector Shape - Group");
      var v=[]; for (var i=0;i<pts.length;i++) v.push(pts[i]);
      var sp = new Shape(); sp.vertices=v; sp.closed=false;
      path.property("Path").setValue(sp);
      var st = grp.property("Contents").addProperty("ADBE Vector Graphic - Stroke");
      st.property("Color").setValue(rgb(col));
      st.property("Stroke Width").setValue(w);
      // posicionar la shape respecto al basemap (mismo anchor que el basemap)
      sh.property("Transform").property("Anchor Point").setValue([D.W/2,D.H/2]);
      var off = [D.W/2 - D.bw/2, D.H/2 - D.bh/2];
      sh.property("Transform").property("Position").setValue([D.W/2+off[0], D.H/2+off[1]]);
      try{ sh.property("Effects").addProperty("ADBE Glo2"); }catch(e){}
      sh.parent = cam;
      return sh;
    }
    for (var r=0;r<D.regions.length;r++){
      var reg=D.regions[r];
      for (var p=0;p<reg.polys.length;p++){ if(reg.polys[p].length>1) polyShape(reg.polys[p], reg.col, 3); }
    }
    log("fronteras dibujadas");

    // --- RUTAS (linea con reveal temporal via trim path) ---
    for (var i=0;i<D.routes.length;i++){
      var ro=D.routes[i];
      var sh=polyShape(ro.pts, D.pal.mustard, 4);
      try {
        var tr=sh.property("Contents").property(1).property("Contents").addProperty("ADBE Vector Filter - Trim");
        var e=tr.property("End");
        e.setValueAtTime(ro.draw_t[0],0); e.setValueAtTime(ro.draw_t[1],100);
      } catch(e){ log("ruta trim ERROR: "+e.toString()); }
    }

    // --- LABELS (texto tracked-caps, aparecen en su t) ---
    var off2=[D.W/2 - D.bw/2, D.H/2 - D.bh/2];
    for (var k=0;k<D.labels.length;k++){
      var lb=D.labels[k];
      var tl=comp.layers.addText(lb.text);
      var td=tl.property("Source Text").value;
      td.applyFill=true; td.fillColor=rgb(D.pal.ink); td.fontSize=34; td.tracking=60;
      tl.property("Source Text").setValue(td);
      tl.property("Transform").property("Position").setValue([D.W/2+lb.x-D.bw/2+off2[0]+8, D.H/2+lb.y-D.bh/2+off2[1]-8]);
      tl.parent=cam;
      var op=tl.property("Transform").property("Opacity");
      op.setValueAtTime(0,0); op.setValueAtTime(Math.max(0,lb.t-0.3),0); op.setValueAtTime(lb.t+0.3,100);
    }
    log("labels: "+D.labels.length);

    // --- CAMARA: zoom/pan via Scale y Position del Null (con micro-pausas ya en cam) ---
    var scl=cam.property("Transform").property("Scale");
    var pos=cam.property("Transform").property("Position");
    var zref=D.zoom_ref;
    for (var c=0;c<D.cam.length;c++){
      var v=D.cam[c];
      var f=Math.pow(2, (v.zoom - zref));           // zoom relativo -> escala
      scl.setValueAtTime(v.t, [100*f,100*f]);
      // centrar el punto (cx,cy) del basemap en el centro del lienzo
      var bx=D.W/2 + (D.W/2 - v.cx);
      var by=D.H/2 + (D.H/2 - v.cy);
      pos.setValueAtTime(v.t, [D.W/2 + (D.W/2 - v.cx)*f, D.H/2 + (D.H/2 - v.cy)*f]);
    }
    log("camara: "+D.cam.length+" keys");

    // motion blur off (paneo difumina); look nitido
    comp.motionBlur=false;
  } catch(e){ log("FATAL: "+e.toString()+" @"+e.line); }
  app.endUndoGroup();
})();
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("story")
    ap.add_argument("--format", choices=list(FORMATS), default="horizontal")
    ap.add_argument("--comp", default="MWMAP")
    ap.add_argument("--out", default="mapa_native.jsx")
    a = ap.parse_args()
    with open(a.story, encoding="utf-8") as f:
        story = json.load(f)
    build(story, a.format, a.comp, a.out)


if __name__ == "__main__":
    main()
