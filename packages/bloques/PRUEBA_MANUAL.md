# Prueba manual: bloques de carpintería en Rhino y AutoCAD

Las pruebas automáticas releen el DXF con ezdxf y el .3dm con rhino3dm, pero no abren Rhino ni
AutoCAD. Estos pasos comprueban que los programas reales los leen igual.

## Preparación

En el repositorio: `uv sync` y luego
`uv run --package archimind-bloques pytest packages/bloques/tests/test_block_png.py`.
En `tests/output/bloques/` quedan, por cada caso, `<caso>.png`, `.dxf`, `.svg` y `.3dm`. Usan el
perfil de las pruebas (`packages/bloques/tests/catalog_prueba.yaml`): marco de 0.05 m de ancho
visto y 0.08 m de fondo, hoja de 0.04 × 0.025 m y traslape de 0.03 m.

Los casos que se revisan aquí:
- `puerta_batiente`: 0.90 × 2.10 m, mano izquierda, abre adentro, hoja de 0.04 m.
- `ventana_corrediza_4h`: 2.00 × 1.20 m, 4 hojas, antepecho 0.90 m.

## Rhino

1. Abrir `tests/output/bloques/ventana_corrediza_4h.3dm`. En **Archivo → Propiedades →
   Unidades**, las unidades del modelo deben ser metros.
2. Panel de capas: «Marco», «Hoja» y «Vidrio». `SelAll`: 24 objetos, 20 extrusiones y 4
   superficies. Con `What` sobre una pieza del marco: «closed extrusion» (sólido).
3. `BoundingBox` de todo: de (0, −0.04, 0.90) a (2.00, 0.04, 2.10).
4. Seleccionar el objeto «vidrio 1» (Propiedades → Nombre) y medir con `Distance` entre sus
   esquinas: 0.41 m de ancho, de x = 0.09 a x = 0.50, y 1.02 m de alto, de z = 0.99 a 2.01. Está
   en y = −0.0125, en el centro del riel exterior.
5. Abrir `puerta_batiente.3dm`. La pieza «hoja» mide 0.80 × 0.04 × 2.05 m y va de y = 0.00 a
   y = 0.04: enrasada con la cara de adentro del marco (+y).

## AutoCAD

1. Abrir `tests/output/bloques/puerta_batiente.dxf` (Abrir, tipo de archivo DXF). `UNITS` debe
   indicar metros.
2. `LWDISPLAY` en ON: el marco cortado en planta se ve más grueso (0.35 mm) que la hoja
   (0.25 mm) y que el arco (0.13 mm).
3. En el espacio modelo hay dos inserciones. La de abajo es la planta, en la capa A-PUERTA, y
   su bloque se llama `PUERTA-BATIENTE-900x2100-IZQ-ADENTRO-…`. La de arriba es el alzado, en la
   capa A-ALZADO, y su bloque termina en `-ALZADO`.
4. Insertar de nuevo el bloque de la planta (`INSERT`, en este mismo dibujo) en un punto
   cualquiera. El punto de inserción debe quedar en el borde izquierdo del vano y sobre el eje
   del muro, es decir, a media profundidad de la jamba.
5. `LIST` sobre el arco: radio 0.80 y centro a (0.85, 0.04) del punto de inserción. El centro
   son las bisagras, en la jamba del extremo opuesto al punto de inserción.
6. En el alzado, las líneas del triángulo de apertura deben verse discontinuas (la puerta abre
   adentro, lejos de quien mira desde afuera). Anotar si el trazo resulta demasiado largo o
   corto: se ajusta con `HIDDEN_LTSCALE` en `export_dxf.py`.
7. Abrir `ventana_corrediza_4h.dxf`. `DIST` entre los extremos de las líneas de las caras del
   vano en planta: 2.00 m, a ±0.075 m del eje.

## SVG

Abrir `tests/output/bloques/ventana_corrediza_4h.svg` en un navegador o en Illustrator. Debe
medir 120 mm de ancho: la ventana a 1:20, más 10 mm de margen a cada lado. Los trazos deben
tener tres grosores distintos: 0.35, 0.25 y 0.13 mm.
