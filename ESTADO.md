# Estado del sistema — cierre de sesión 2026-07-30

## Cómo se usa (lo único que importa para David)

Vos pedís en español. Yo escribo el JSON, renderizo y entrego el MP4.

> *"Mapa de Corea, resaltá el Norte en rojo, marcá Seúl y Pionyang, flecha de
> Pionyang a Seúl, título 'A 40 kilómetros'"*

**Cero coordenadas, cero JSON, cero configuración de tu parte.**
Salida: `D:\IA - PROYECTS 2026\After Effects\Julio\`

## Qué tiene el motor

**Base del mapa**
- Relieve real desde elevación satelital (AWS Terrarium, gratis)
- Tema claro (terreno crema tipo papel) y oscuro (tierra negra + océano azul)
- Océano con degradado de profundidad (gamma 0.45)
- Tinte de país en **Multiply** (el relieve se ve a través del color), con
  compensación por luminosidad para que no se lave en terreno claro
- Fuentes alternativas: satélite ESRI, CartoDB claro/oscuro

**Capas geográficas** (17 capas Natural Earth, 188 MB en `.tmp`)
- Ríos, lagos, costas, fronteras (países e internas), áreas urbanas
- Costa resaltada en color (con `min_ring_px` para no pintar islotes, o
  `segments` para tramos concretos)
- Tramas rayadas para zonas urbanas/disputadas
- Extrusión 2.5D de país (canto desplazado y oscurecido)

**Elementos sobre el mapa**
- Ciudades: punto + nombre en **serif itálica**, con halo y anti-colisión
- Nombres de país con **biselado 3D**, que se pegan al borde en vez de
  desaparecer al hacer zoom, y esquivan las zonas de UI
- Flechas dasheadas animadas + punta triangular; arcos Bézier
- Call-outs: caja blanca con sombra y línea líder
- Íconos vectoriales: ancla, barco, avión, alerta, base, punto (disco oscuro)
- Pins con **foto de líder** (recorte circular + aro + línea guía)
- Banner highlighter, chip de fecha, lower-third y logo de marca

**Cámara y cine**
- Recorrido con micro-pausas (`dwell`)
- Inclinación en grados (`tilt_deg`) — **rango útil 20–35**
- Profundidad de campo: radial o tilt-shift (banda horizontal nítida)
- Grado de color, viñeta, grano estático

**Utilidades**
- `places.py`: nombre de lugar → coordenadas (7000+ ciudades, puertos, aeropuertos)
- `brand.json`: identidad MacroWise centralizada
- Renders en paralelo (carpeta de frames única por render)

## Calibración de la inclinación (aprendido a los golpes)

| bulge | Resultado |
|---|---|
| 0.85 | No se nota, se lee plano |
| **1.15** | **Calibrado — perspectiva legible, forma intacta** |
| 1.9 | Se nota pero DEFORMA el país (aspecto "derretido") |

`tilt_deg` útil: **20–35**. Con tilt activo el recorte se expande x1.85 para que
el cuadro quede lleno de mapa (sin el borde flotando, "la mesa").

## Límite conocido y honesto

La perspectiva se hace con una **deformación 2D (homografía)**, no con una cámara
3D real. Funciona bien en valores moderados; forzada, distorsiona la geometría.
Una cámara 3D verdadera (lo que usa la referencia) no tiene ese techo. Subir el
número no lo resuelve — haría falta otro enfoque de render.

## Tests corridos (9) y bugs corregidos (11)

Regiones: Taiwán, Ormuz, Ucrania, Corea, Darién, USA-Rusia, Irán, Nueva York.

1. Etiqueta de país ilegible en tema oscuro
2. Costa resaltada gruesa pintando islotes
3. Ícono tapando nombre de ciudad
4. Renders paralelos pisándose la carpeta de frames
5. Tintes lavados sobre terreno claro
6. Etiquetas de país desapareciendo al hacer zoom
7. Etiqueta superpuesta al chip de fecha
8. Trama rayada ilegible (se leía como ruido)
9. Ícono de barco irreconocible
10. Íconos y ciudades dibujados bajo la UI
11. Tilt que mostraba el borde del mapa

Cada corrección vive en el **motor**, no en el mapa puntual: benefician a todo
mapa futuro.

## Lo que falta

- **Colores exactos de la referencia**: hace falta una captura de un video suyo
  (no un thumbnail) para muestrear los hex con cuentagotas.
- Narración, música y SFX.
- Perspectiva 3D real (ver límite arriba).
