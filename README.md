# macrowise-map-animator

Mapas animados estilo **Johnny Harris / Caspian Report** con **After Effects + GEOlayers 3**,
de un clic desde un **story-spec JSON**. Hermano del repo de graficas
[`macrowise-chart-animator`](https://github.com/TimothyArcher90/macrowise-chart-animator):
mismo patron (Python emite ExtendScript -> `AfterFX -r` -> `aerender` -> MP4 a D:),
misma paleta MacroWise, misma logica de camara con micro-pausas.

## Requisitos
- After Effects 2026.
- **GEOlayers 3** instalado (aescripts) con su **panel abierto**.
- Token de **MapTiler o Mapbox** cargado en el panel.
- Un **Mapcomp base** creado a mano una vez (ver `directives/animate_map.md`).

## Uso (terminal interactiva)
```powershell
powershell -File execution/one_click_map.ps1 -Story execution/stories/estrecho_ormuz.json -Name ormuz
```

## Estructura
- `execution/build_map.py` — story-spec JSON -> `.jsx` con la API de GEOlayers.
- `execution/map_camera.py` — recorrido de camara con micro-pausas (auto-testeable).
- `execution/one_click_map.ps1` — orquestador de un clic.
- `execution/stories/estrecho_ormuz.json` — demo: Estrecho de Ormuz.
- `directives/animate_map.md` — SOP + setup one-time + limites reales de GEOlayers.

## Estado
Codigo listo y validado en lo automatizable (genera el `.jsx` correcto). El render de
mapas requiere GEOlayers instalado + token + Mapcomp base (setup del usuario).
