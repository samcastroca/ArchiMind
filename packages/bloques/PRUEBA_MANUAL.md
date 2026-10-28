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

# Prueba manual: carpintería insertada en un plano y pedidos desde Claude Desktop

Las pruebas automáticas llaman a los dos servidores en proceso y releen el DXF con ezdxf. Estos
pasos comprueban lo que no ven: que Claude convierta los pedidos en llamadas válidas y que
AutoCAD dibuje los bloques donde corresponde.

## Preparación en Claude Desktop

1. Configurar `archimind-core` y `archimind-bloques` como dice el README («Uso desde Claude
   Desktop») y reiniciar Claude Desktop. En **Configuración → Desarrollador** los dos deben estar
   en marcha.
2. Pedirle a Claude, con una carpeta nueva (p. ej. `C:\ArchiMind\casa`): «abre el proyecto en
   C:\ArchiMind\casa, importa el plano `<repositorio>\tests\golden\apto_2hab\input.dxf`, aplica el
   mapeo que propongas y exporta el plano a DXF». Debe usar abrir_proyecto, importar_plano,
   proponer_mapeo_capas, aplicar_mapeo y exportar_plano con formato "dxf". El resultado: 9
   vanos y 4 recintos (esp-0001 Baño, esp-0002 Habitación 1, esp-0003 Sala-comedor-cocina,
   esp-0004 Habitación 2) y `salidas\casa.dxf`.

## Los 20 pedidos

`tests/pedidos_bloques.yaml` trae cada pedido con la herramienta, los argumentos y lo esperado.
Por cada uno:

1. Escribir el `pedido` tal cual, en una conversación con el proyecto abierto.
2. Desplegar la llamada a la herramienta en Claude Desktop: debe ser `herramienta` con
   `argumentos` (más `project_path`, salvo en listar_catalogo y agregar_al_catalogo). Anotar si
   Claude agrega medidas que el pedido no da: no debería; lo que falta lo completa el servidor y
   la respuesta lo dice en «Elegido o supuesto».
3. La respuesta debe mostrar lo `esperado` (tipo, perfil, hojas, mano, recinto de adentro) o, en
   los pedidos con `error`, un error con ese texto y la salida que propone.

El pedido 20 (agregar_al_catalogo) cambia `packages/bloques/catalog.yaml` de verdad; después se
deshace con `git checkout packages/bloques/catalog.yaml`. Los pedidos 17 y 18 dejan
`salidas\borrador_bloques.json`: decirle a Claude «guárdalo en el modelo» debe llamar a
asignar_bloques de archimind-core, y listar_modelo(que="vanos") debe mostrar después el `blq-` de cada vano.

## AutoCAD: el plano con la carpintería

Después del pedido 17 («Pon puertas y ventanas en todos los vanos del plano»):

1. Abrir `C:\ArchiMind\casa\salidas\casa-carpinteria.dxf`. `UNITS` debe indicar metros.
2. Capas A-PUERTA y A-VENTANA: los rectángulos de los vanos ya no están; en su lugar hay 4
   inserciones de puerta y 5 de ventana. `LIST` sobre cada una:
   - puerta de entrada `PUERTA-BATIENTE-900x2100-…`: punto (6.00, 0.00), rotación 0;
   - puerta del baño `PUERTA-BATIENTE-700x2100-…`: punto (4.60, 4.80), rotación 0;
   - puertas de las habitaciones `PUERTA-BATIENTE-800x2100-…`: puntos (3.50, 2.60) y
     (3.50, 3.75), rotación 90;
   - ventana de la sala `VENTANA-CORREDIZA-2H-2000x1200-…`: punto (8.50, 1.50), rotación 90.
3. A ojo, cada puerta abre hacia su recinto (la de entrada hacia la sala, la del baño hacia el
   baño, las de las habitaciones hacia cada habitación) y no hacia la sala. Las bisagras van en
   la jamba más cercana a un muro: la de entrada en la del este (centro del arco en
   (6.85, 0.04), radio 0.80), la del baño junto al tabique del este del baño (5.25, 4.84) y las
   de las habitaciones junto al tabique entre ellas, (3.46, 3.35) y (3.46, 3.80).
4. `BEDIT` sobre la puerta de entrada: el punto base del bloque está en el borde del vano, sobre
   el eje del muro (a media profundidad de la jamba).
