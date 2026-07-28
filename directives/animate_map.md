# Directiva: animar un mapa estilo Johnny Harris / Caspian con GEOlayers 3

## Objetivo
Producir un mapa animado (zoom cinematografico, fronteras que se dibujan, rutas,
etiquetas) desde un **story-spec JSON**, con After Effects + GEOlayers 3, calidad
Johnny Harris / Caspian Report. Look 100% MacroWise, movimiento 100% documental.

## Setup ONE-TIME (una sola vez, a mano — la API de GEOlayers no lo automatiza)
1. Instalar GEOlayers 3 (aescripts manager o ZXP Installer). Reiniciar AE.
2. `Window > GEOlayers 3` -> abrir el panel. Dejarlo abierto SIEMPRE que se corra el pipeline.
3. En Settings del panel, pegar el **token de MapTiler/Mapbox**.
4. Elegir el **estilo de mapa** (terreno oscuro + hillshade = look Johnny Harris) y
   crear un **Mapcomp base** (boton "Create Map"). Ese Mapcomp es el lienzo que el
   scripting despues manipula. Anota su nombre (lo usa `aerender -comp`).

## Flujo por video (de un clic)
1. Escribir/editar el story-spec en `execution/stories/<nombre>.json`
   (waypoints de camara con lat/lon/zoom/pitch/bearing/dwell, regions, routes, labels).
2. AE abierto + panel GEOlayers abierto + Mapcomp base seleccionado.
3. Terminal INTERACTIVA:
   `powershell -File execution/one_click_map.ps1 -Story execution/stories/<nombre>.json -Name <nombre>`
4. El script: `build_map.py` genera el `.jsx` -> `AfterFX -r` corre la API de GEOlayers
   (dibuja regiones/rutas/labels + recorrido de camara + finalize) -> `aerender` saca el MP4 a D:.

## API de GEOlayers usada (verificada en github.com/GEOlayers/Help)
- `geolayers3.addToBrowser(query)` + `drawBrowserSelection()` -> fronteras/regiones.
- `geolayers3.draw(geojson)` -> rutas (LineString).
- `geolayers3.addLabel(lat, lon, text)` -> etiquetas/marcadores.
- `geolayers3.setViewAtTime(lat, lon, zoom, bearing, pitch, t)` -> keyframes de camara.
- `geolayers3.finalize()` -> render (async).

## Limites reales (no son bugs, son de GEOlayers)
- **El panel debe estar ABIERTO** o `geolayers3` no existe (el .jsx lo detecta y avisa).
- **El Mapcomp base es manual** (one-time). El scripting no lo crea de cero.
- `AfterFX -r` solo se acopla a AE desde **terminal interactiva**, AE **sin dialogos**.
  (Mismo aprendizaje que macrowise-chart-animator.)

## Micro-pausas cinematograficas
`map_camera.py` congela la camara los `dwell` segundos al llegar a un waypoint marcado
= el "punch-in que aterriza y respira" de Johnny Harris. Sin `dwell` el recorrido es continuo.

## Verificacion
- Sin GEOlayers (ahora): `python execution/map_camera.py` (auto-test micro-pausa) y
  `python execution/build_map.py execution/stories/estrecho_ormuz.json --out /tmp/m.jsx`
  -> el `.jsx` debe contener `geolayers3.setViewAtTime`, `addLabel`, `draw`, `finalize`.
- Con GEOlayers: frames con `ae_export_frame`, luego el MP4 en D:.
