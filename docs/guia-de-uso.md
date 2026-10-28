# Guía de uso

Cómo trabajar con ArchiMind desde Claude Desktop, tarea por tarea. Cada sección trae una frase de
ejemplo y lo que responde. Las respuestas son del plano de ejemplo que deja el instalador
(`ejemplo-apartamento.dxf`), así que puedes repetirlas tal cual.

Si aún no lo instalaste, empieza por el [README](../README.md#instalación-unos-10-minutos-una-sola-vez).

## Contenido

- [Cómo se trabaja](#cómo-se-trabaja)
- [La carpeta del proyecto](#la-carpeta-del-proyecto)
- [1. Abrir un proyecto e importar un plano](#1-abrir-un-proyecto-e-importar-un-plano)
- [2. Decirle qué es cada capa](#2-decirle-qué-es-cada-capa)
- [3. Confirmar la escala](#3-confirmar-la-escala)
- [4. Las alturas](#4-las-alturas)
- [5. Consultar el modelo](#5-consultar-el-modelo)
- [6. Cuadro de áreas](#6-cuadro-de-áreas)
- [7. Exportar: imagen, DXF, DWG y 3D](#7-exportar-imagen-dxf-dwg-y-3d)
- [8. Versiones](#8-versiones)
- [9. Puertas y ventanas (carpintería)](#9-puertas-y-ventanas-carpintería)
- [10. Precios, materiales y programa de áreas](#10-precios-materiales-y-programa-de-áreas)
- [11. Documentos: memoria, ficha PDF, presupuesto, programa y COS/CUS](#11-documentos-memoria-ficha-pdf-presupuesto-programa-y-coscus)
- [12. Rhino: edición 3D, axonometrías y cortes](#12-rhino-edición-3d-axonometrías-y-cortes)
- [Dónde queda cada archivo](#dónde-queda-cada-archivo)

## Cómo se trabaja

- **Hablas normal.** No hace falta saber el nombre de ninguna herramienta: «dame el cuadro de
  áreas» basta. Claude elige la herramienta de ArchiMind y te muestra su respuesta.
- **Claude pide permiso** la primera vez que usa cada herramienta: pulsa **Permitir**.
- **Las cifras las calcula ArchiMind.** Áreas, longitudes, conteos y precios salen siempre del
  modelo o de tu base de datos, nunca de Claude. Si Claude da un número sin haber usado una
  herramienta, pídele que lo calcule con ArchiMind.
- **Di siempre en qué proyecto.** Cada proyecto es una carpeta, y la primera vez en cada chat
  conviene decir cuál («en el proyecto C:\…\casa-lopez»). Dentro del mismo chat, Claude la
  recuerda.
- **Nada se inventa.** Si falta un dato que el plano no trae (una altura, el área del lote), Claude
  te lo pide; no lo supone.

## La carpeta del proyecto

Cada proyecto es una carpeta. El instalador crea `Documentos\ArchiMind-proyectos` para ponerlas
ahí, fuera de la carpeta de ArchiMind. Dentro de cada proyecto:

| Qué | Para qué |
|---|---|
| `modelo.json` | El modelo: niveles, muros, vanos y espacios. **No lo edites a mano**: lo escribe ArchiMind. |
| `planos\` | Copia de cada plano importado. El último es el **plano activo**. |
| `salidas\` | Todo lo que genera ArchiMind: imágenes, DXF, DWG, 3D, CSV, PDF. Se puede borrar: se vuelve a generar. |
| `.git` (oculta) | El historial de versiones. No la borres. |

## 1. Abrir un proyecto e importar un plano

> Abre el proyecto en C:\Users\Ana\Documents\ArchiMind-proyectos\mi-primer-proyecto e importa el
> plano C:\Users\Ana\Documents\ArchiMind-proyectos\ejemplo-apartamento.dxf

Si la carpeta no existe, la crea. Del plano dice sus capas y en qué unidades está:

```
Plano importado: planos/ejemplo-apartamento.dxf (copiado en la carpeta del proyecto; es el plano activo).
Unidades: metros, declaradas en el plano ($INSUNITS = 6 (Meters)); escala confirmada.
5 capas:
  A-COTA: 2 DIMENSION
  A-MURO: 6 LWPOLYLINE; 68.2 m de línea
  A-PUERTA: 4 ARC, 4 LINE; 3.2 m de línea
  A-TEXTO: 4 TEXT; textos: Habitación 1, Habitación 2, Baño
  A-VENTANA: 15 LINE; 21.3 m de línea
```

- Acepta **DXF** y **DWG**. Para DWG hace falta ODA File Converter
  ([instalación manual](instalacion-manual.md#oda-file-converter-para-dwg)); si no lo tienes,
  exporta el plano a DXF desde AutoCAD (Guardar como → DXF).
- Para copiar la ruta de un archivo: clic derecho sobre él → **Copiar como ruta de acceso** (en
  Windows 10, con la tecla Mayúsculas pulsada).
- Si el plano cambia, impórtalo otra vez: queda como plano activo y se repiten los pasos 2 y 3.

## 2. Decirle qué es cada capa

ArchiMind necesita saber qué dibuja cada capa: muros, puertas, ventanas, textos (los nombres de
los espacios), cotas, ejes, mobiliario o nada que le importe.

> Propón qué es cada capa

```
A-COTA → dimensions (cotas, 0.95): El nombre contiene COTA y hay 2 cotas (100 % del contenido).
A-MURO → walls (muros, 0.95): El nombre contiene MURO y hay 24 pares de tramos paralelos a 0.10, 0.12, 0.20, 0.25 m (96 % del contenido).
A-PUERTA → doors (puertas, 0.95): El nombre contiene PUERTA y hay 4 arcos de giro de 90° con su hoja (100 % del contenido).
A-TEXTO → text (textos, 0.95): El nombre contiene TEXTO y hay 4 textos (100 % del contenido).
A-VENTANA → windows (ventanas, 0.95): El nombre contiene VENTANA y hay 5 ventanas de tres líneas paralelas (100 % del contenido).
```

El número entre paréntesis es la **confianza** (de 0 a 1). Revisa sobre todo las de confianza
baja. Para aplicarla:

> Aplícalo tal cual

o corrigiendo lo que haga falta:

> Aplícalo, pero la capa MOB-COCINA es mobiliario y la capa VIEJO-MUROS no la uses

```
Modelo reconstruido desde planos/ejemplo-apartamento.dxf.
Modelo: 1 nivel, 8 muros, 9 vanos, 4 espacios.
Escala: confirmada.
Problemas: 0 errores, 1 aviso.
  aviso valores_por_defecto: el plano no transmite estos datos y se usan los valores por defecto: nivel «Planta baja» a 0.00 m con altura 2.60 m; vanos door: altura 2.10 m, antepecho 0.00 m; vanos window: altura 1.20 m, antepecho 0.90 m; …
```

- Los **avisos** no impiden seguir, pero conviene leerlos: dicen qué no se pudo leer del plano o
  qué valores se supusieron.
- **Si el plano tiene varias vistas** (por ejemplo, la planta y un alzado lado a lado), no
  mezcla nada: te dice cuántas vistas hay y dónde está cada una. Contesta cuál es la planta
  («usa la vista 1»).
- Volver a aplicar el mapeo reconstruye el modelo desde cero: los muros, vanos y espacios reciben
  identificadores nuevos y la escala vuelve a la del plano.

## 3. Confirmar la escala

Mientras la escala no está confirmada, toda cantidad sale marcada **PRELIMINAR**, y no se puede
exportar a DXF, DWG ni 3D.

- **Si el plano declara sus unidades**, como el de ejemplo, ya está confirmada.
- **Si no las declara**, ArchiMind las deduce (metros, centímetros o milímetros) y lo explica.
  Si es correcto:

  > Sí, el plano está en milímetros: confirma la escala

- **Si sabes cuánto mide de verdad un muro**, ArchiMind escala todo el modelo para que mida eso
  (de eje a eje). El identificador de un muro aparece en la lista de puertas y ventanas (cada
  vano dice en qué muro está) y, en Rhino, como nombre del muro:

  > El muro muro-0003 mide en realidad 4.20 m

  Se escalan muros, vanos y espacios; las alturas y los antepechos no.

## 4. Las alturas

Un plano en planta no dice alturas. ArchiMind usa 2.60 m por defecto, pero **no la da por buena**
hasta que la confirmas, y el 3D la exige confirmada:

> La altura de piso a techo es 2.60 m

```
Alturas confirmadas por nivel:
  niv-0001: 2.60 m
```

Para un espacio con otra altura:

> El baño (esp-0001) tiene 2.40 m de altura

Pone esa altura a los muros que rodean el espacio. Un muro entre dos espacios de alturas distintas
toma la mayor, y te avisa. Si algún vano quedara más alto que su muro, no cambia nada y lo dice.

## 5. Consultar el modelo

> ¿Qué espacios tiene?

```
4 espacios: id · nombre · categoría · área
  esp-0001 · Baño · útil · 2.93 m²
  esp-0002 · Habitación 1 · útil · 9.19 m²
  esp-0003 · Sala-comedor-cocina · útil · 27.21 m²
  esp-0004 · Habitación 2 · útil · 11.52 m²
```

> ¿Qué puertas y ventanas hay?

```
9 vanos (4 puertas, 5 ventanas).
Por medida:
  puerta 0.70 × 2.10 m: 1
  puerta 0.80 × 2.10 m: 2
  …
  vano-0001 · puerta 0.70 × 2.10 m · antepecho 0.00 m · muro-0002 a 0.20 m
  …
```

> Revisa si el modelo tiene errores

Lista los errores (que hay que corregir) y los avisos: muros que casi se tocan pero no, espacios
superpuestos, vanos fuera de su muro, espesores poco habituales…

Los identificadores (`niv-`, `muro-`, `vano-`, `esp-`, `blq-`) no cambian mientras no se vuelva
a aplicar el mapeo: sirven para referirse a un elemento concreto.

## 6. Cuadro de áreas

> Dame el cuadro de áreas

```
Cuadro de áreas de «mi-primer-proyecto»
  Baño (útil): 2.93 m²
  Habitación 1 (útil): 9.19 m²
  Sala-comedor-cocina (útil): 27.21 m²
  Habitación 2 (útil): 11.52 m²
Área útil: 50.85 m² · Área construida: 58.29 m² · Balcones: 0.00 m²
CSV: …\mi-primer-proyecto\salidas\cuadro_de_areas.csv
```

- **Área útil**: la suma de los espacios, menos los balcones.
- **Área construida**: lo que encierra el contorno exterior de los espacios y los muros (los
  patios interiores cuentan).
- **Balcones**: aparte.
- El CSV se abre con Excel. Solo se escribe con la escala confirmada.

## 7. Exportar: imagen, DXF, DWG y 3D

| Pide | Obtienes, en `salidas\` |
|---|---|
| «Muéstrame la planta en una imagen» | `vista.png`: espacios con nombre y área, muros en azul y vanos en naranja. |
| «Exporta el plano en DXF» | `<proyecto>.dxf`: un plano limpio en metros, con capas `A-MURO`, `A-PUERTA`, `A-VENTANA`, `A-ESPACIO`, nombres y áreas. Se abre en AutoCAD, BricsCAD, Rhino, LibreCAD… |
| «Exporta el plano en DWG» (o «en DWG para AutoCAD 2016») | `<proyecto>.dwg` (y el DXF al lado). Necesita ODA File Converter. |
| «Exporta el modelo 3D» | `<proyecto>-3d.3dm` para Rhino: cada muro en macizos, dinteles y antepechos, y una losa de piso. |

DXF, DWG y 3D exigen la escala confirmada. El 3D, además, las alturas: si faltan, no hace nada y
dice cuáles:

```
No se construyó el 3D: faltan alturas y no se suponen.
  niv-0001 «Planta baja» (por defecto 2.60 m, sin confirmar): 8 muros: muro-0001, …
```

## 8. Versiones

Cada cambio del modelo (importar, aplicar el mapeo, confirmar la escala, alturas, carpintería,
cambios de Rhino) se guarda como una versión, con un código como `f48f9fd`.

> ¿Qué cambió desde la versión anterior?

> Compara la versión f48f9fd con la actual

Responde los espacios cuya área cambió más de 0.5 %, los muros añadidos, quitados o movidos y los
vanos modificados.

## 9. Puertas y ventanas (carpintería)

ArchiMind dibuja la carpintería con los perfiles de su catálogo (`packages\bloques\catalog.yaml`,
el mismo para todos los proyectos). Tipos: **puerta batiente, batiente doble y corrediza;
ventana corrediza de 2 a 4 hojas, fija y proyectante.**

**Antes de nada**, exporta el plano en DXF (sección 7): la carpintería se inserta sobre ese
plano.

**Ver qué propone para un vano** (no escribe nada):

> ¿Qué puerta pondrías en el vano-0001?

```
vano-0001: puerta de 0.70 × 2.10 m en muro-0002
Puerta batiente, 0.70 × 2.10 m, perfil aluminio_pesado (Aluminio serie pesada)
… · mano izquierda · abre hacia adentro · muro de 0.10 m
Elegido o supuesto:
  - abre hacia el recinto más pequeño, Baño (esp-0001) (2.93 m²), y no hacia Sala-comedor-cocina (esp-0003) (27.21 m²)
  - mano izquierda ("left"): bisagras hacia muro-0001, a 0.15 m: la hoja abierta queda contra el muro
```

**Ponerla en el plano**:

> Pon la carpintería en el plano

> En el vano-0004 pon una ventana corrediza de aluminio de 3 hojas, y la puerta del baño
> (vano-0001) que abra hacia la sala (esp-0003)

Escribe `salidas\<proyecto>-carpinteria.dxf` con cada bloque en su sitio. Revísalo en tu CAD. Si
te gusta:

> Guarda la carpintería en el modelo

**Un bloque suelto**, con las medidas que digas:

> Hazme una ventana corrediza de aluminio de 3 hojas de 2.40 × 1.50

```
Bloque VENTANA-CORREDIZA-3H-2400x1500-DA50C1
Ventana corrediza de 3 hojas, 2.40 × 1.50 m, perfil aluminio_pesado (Aluminio serie pesada)
Cada hoja de 0.787 × 1.400 m · antepecho 0.90 m · muro de 0.15 m
Elegido o supuesto:
  - muro de 0.15 m de espesor, el del catálogo
  - antepecho de 0.90 m, el del catálogo
```

Queda en `salidas\bloques\` (DXF e imagen; pide «también en SVG y para Rhino» si los quieres).
«A × B» es siempre ancho × alto.

**El catálogo**: «¿Qué perfiles de carpintería hay?». Para añadir uno de un fabricante, dale
todas sus medidas: Claude no las inventa, te pregunta las que falten. Los perfiles que trae son de
ejemplo: complétalos con medidas reales.

## 10. Precios, materiales y programa de áreas

Algunos documentos usan datos que el plano no trae: los precios unitarios (APU), los materiales y
el programa de áreas. Viven en **una base de datos única para todos tus proyectos**, que se carga
desde archivos CSV (se hacen con Excel: Guardar como → **CSV UTF-8**).

1. Copia la plantilla de la carpeta `packages\docs\plantillas` de ArchiMind y llénala. Las
   columnas de cada tabla están en [packages/docs/README.md](../packages/docs/README.md).
2. Haz doble clic en **Importar datos**, en la carpeta de ArchiMind (o suelta el CSV encima).
3. Elige qué es (precios, materiales, programa de áreas o partidas) y arrastra el CSV a la
   ventana.

```
Cargando …\precios.csv en unit_prices...
1 filas cargadas en unit_prices (…\AppData\Local\ArchiMind\archimind.sqlite3).
```

Si una fila tiene un problema, **no carga nada** y dice qué fila y qué falla. Por ejemplo, un
precio escrito `45.000` es ambiguo (¿45 o 45 mil?): escribe `45000`.

Un ejemplo, separado por punto y coma, como lo guarda Excel en español:

`precios.csv` (tabla de precios unitarios):

```
codigo;descripcion;unidad;precio;fecha;fuente
APU-MURO-10;Muro en bloque de 10 cm;m2;85000;2026-09-01;Lista de precios septiembre
APU-PUERTA-80;Puerta de madera 0,80 × 2,10;un;650000;2026-09-01;Proveedor
```

`partidas.csv` (qué APU va con cada partida del modelo):

```
partida;codigo_apu;codigo_material
muro-0.10;APU-MURO-10;
puerta-0.80x2.10;APU-PUERTA-80;
```

Las claves de partida (`muro-0.10`, `puerta-0.80x2.10`, `piso-util`…) son las del modelo: pídele a
Claude «¿qué partidas tiene el proyecto?».

## 11. Documentos: memoria, ficha PDF, presupuesto, programa y COS/CUS

**COS y CUS** (el área del lote la das tú):

> Calcula el COS y el CUS con un lote de 120 m²

```
Lote de 120.00 m².
COS = 0.49: huella construida del nivel más bajo (Planta baja, 58.29 m²) / área del lote.
CUS = 0.49: área construida de todos los niveles (58.29 m²) / área del lote.
```

**Presupuesto preliminar**: cada partida del modelo por el precio de su APU.

> Haz el presupuesto preliminar

Las partidas sin APU quedan **SIN PRECIO**, con el motivo, y no suman: nunca se estima un precio.
Sin datos cargados, todas salen así:

```
Presupuesto PRELIMINAR de «mi-primer-proyecto»: 0.00 en 0 de 10 partidas con precio (moneda de los APU).
SIN PRECIO, no suman al total (10):
  muro-0.10: la partida no está en budget_items
  …
```

El detalle queda en `salidas\presupuesto_preliminar.csv`.

**Programa de áreas**: compara los espacios con las áreas mínimas que cargaste.

> ¿Cumple el programa de áreas?

Empareja por nombre, sin contar mayúsculas, tildes ni el número final («Habitación» vale para
«Habitación 1»), y responde qué cumple, qué no llega (y cuánto le falta) y qué falta.

**Memoria y ficha PDF**:

> Redacta la memoria descriptiva del proyecto y genera la ficha en PDF

Claude pide las cifras verificadas, redacta la memoria **solo con ellas** y genera
`salidas\ficha_<proyecto>.pdf`: datos del proyecto, cuadro de áreas, planta y memoria. Antes,
ArchiMind comprueba **cada número** del texto. Si alguno no sale del modelo, no genera nada:

```
No se generó la ficha: 1 número(s) de la memoria no están en datos_para_memoria. …
  «2026» en: …2 habitaciones construido en 2026.…
```

Años, fechas, escalas o costos que no estén en el modelo se rechazan: escríbelos con letras o
déjalos fuera.

## 12. Rhino: edición 3D, axonometrías y cortes

Con Rhino 8 puedes abrir el modelo, mover o estirar muros y vanos, guardar los cambios en el
modelo y dibujar axonometrías y cortes con líneas ocultas. Todo eso está en
[Rhino 8](rhino.md).

## Dónde queda cada archivo

Todo en la carpeta `salidas\` del proyecto:

| Archivo | Lo genera |
|---|---|
| `vista.png` | «Muéstrame la planta» |
| `cuadro_de_areas.csv` | «Dame el cuadro de áreas» (con la escala confirmada) |
| `<proyecto>.dxf`, `<proyecto>.dwg` | «Exporta el plano en DXF / DWG» |
| `<proyecto>-3d.3dm` | «Exporta el modelo 3D» |
| `<proyecto>-carpinteria.dxf` | «Pon la carpintería en el plano» |
| `bloques\` | Los bloques sueltos |
| `cortes.json` | «Propón cortes» |
| `axonometria-….dxf` y `.svg`, `corte-….dxf` y `.svg` | Los dibujos de Rhino |
| `presupuesto_preliminar.csv` | «Haz el presupuesto preliminar» |
| `datos_memoria.json`, `ficha_<proyecto>.pdf` | La memoria y la ficha |
| `<proyecto>.3dm` | El archivo de Rhino del proyecto |
