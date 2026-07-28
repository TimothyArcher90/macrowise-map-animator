# Instrucciones del agente — macrowise-map-animator

> Replicado en CLAUDE.md / AGENTS.md / GEMINI.md.

Repo hermano de `macrowise-chart-animator`, para **mapas animados** (GEOlayers 3)
en vez de graficas. Mismo patron de 3 capas: `directives/` (SOP) + `execution/`
(Python determinista + ExtendScript emitido) + salida a `D:\...\Julio`.

Leer primero `directives/animate_map.md`.

## Aprendizajes

- **2026-07-28 — GEOlayers se automatiza por ExtendScript API, con 2 anclas manuales:**
  la API (`setViewAtTime`, `draw`, `addToBrowser`+`drawBrowserSelection`, `addLabel`,
  `finalize`) permite scriptear todo el movimiento y los datos, PERO (1) el panel de
  GEOlayers debe estar ABIERTO o `geolayers3` no existe, y (2) el Mapcomp base se crea
  a mano una vez (la API no lo hace de cero). **Por que importa:** no es cero-toque como
  las graficas — es setup de 5 min + un clic por video. El `.jsx` generado detecta el
  panel cerrado y avisa en vez de fallar mudo.
- **2026-07-28 — heredado del repo de graficas:** `AfterFX -r` solo se acopla a la
  instancia de AE desde una **terminal interactiva** (no tarea de fondo), y AE debe
  estar **sin dialogos**. NUNCA meter `renderQueue.render()` ni `project.save()` dentro
  del `.jsx` (cuelga AE con un modal y bloquea los `-r` siguientes) — el render lo hace
  `aerender`/`finalize` aparte. Salida siempre a D:, no a C: (C: se llena).
- **2026-07-28 — micro-pausas = punch-in Johnny Harris:** `map_camera.py` congela la
  camara los `dwell` segundos al llegar a un waypoint. Es lo que hace que el zoom
  "aterrice y respire" en vez de deslizar continuo. Auto-testeado (el zoom no varia
  durante el dwell).
