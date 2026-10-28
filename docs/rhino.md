# Rhino 8

Con Rhino 8 puedes:

- **abrir el modelo en 3D**, mover o estirar muros y vanos, cambiar alturas, borrar, dibujar muros,
  vanos o espacios nuevos y renombrar espacios, y **guardar esos cambios en el modelo** (las
  áreas se recalculan solas);
- **dibujar axonometrías y cortes** con líneas ocultas, como el Make2D de Rhino, en DXF y SVG.

Todo se pide en el chat de Claude Desktop, como lo demás. Para las cosas generales (proyectos,
mapeo de capas, escala, alturas), mira la [guía de uso](guia-de-uso.md).

## Qué hace falta

- **Rhino 8 para Windows.**
- **El puente con Rhino conectado a Claude Desktop.** El instalador lo conecta solo si encuentra
  Rhino 8. Si instalaste Rhino después que ArchiMind, vuelve a hacer doble clic en **Instalar
  ArchiMind** y reinicia Claude Desktop. En **Configuración → Desarrollador** debe aparecer
  `rhino-bridge`.
- Para los dibujos, además: la escala confirmada y las alturas (sección 4 de la
  [guía de uso](guia-de-uso.md#4-las-alturas)).

## Iniciar el puente (cada vez que abras Rhino)

El puente es un pequeño programa que corre dentro de Rhino para que ArchiMind pueda hablar con él.

1. Abre Rhino 8.
2. Escribe `ScriptEditor` en la línea de comandos y pulsa Intro.
3. En el editor: **Abrir** (el icono de carpeta) → busca, en la carpeta de ArchiMind,
   `bridges\rhino\plugin\archimind_bridge.py` → **Ejecutar** (o F5). El instalador te mostró la
   ruta completa.
4. En la pestaña **Terminal** del editor debe aparecer «Puente ArchiMind activo en
   127.0.0.1:48765». Ya puedes cerrar el editor.

Si Claude responde «Rhino no está abierto o el puente no está iniciado», repite estos pasos. Para
saber si todo está bien: «¿Está Rhino listo para el proyecto C:\…\casa-lopez?».

## Editar el modelo en Rhino

1. **Ábrelo en Rhino:**

   > Abre el proyecto C:\Users\Ana\Documents\ArchiMind-proyectos\mi-primer-proyecto en Rhino

   Rhino abre `salidas\<proyecto>.3dm` con el modelo en tres capas: `ArchiMind::Muros` (los muros,
   como sólidos), `ArchiMind::Vanos` (una caja en cada puerta o ventana) y `ArchiMind::Espacios`
   (una superficie por espacio, con su nombre). Cada objeto lleva su identificador
   (`muro-0003`…): lo ves en **Propiedades**.

2. **Edita**, en esas capas:
   - **mover, girar o estirar un muro** (por ejemplo con el Gumball), **cambiar su espesor o su
     altura**;
   - **mover o cambiar el tamaño de un vano** a lo largo de su muro, o su altura y su antepecho;
   - **renombrar un espacio**: en **Propiedades**, cambia su **Nombre**;
   - **borrar** muros, vanos o espacios (al borrar un muro se borran sus vanos);
   - **dibujar nuevos**: un muro es una caja (`Box`) en `ArchiMind::Muros`, apoyada en el piso
     del nivel; un vano, una caja en `ArchiMind::Vanos` que atraviese un muro; un espacio, una
     superficie plana (`Rectangle` + `PlanarSrf`) en `ArchiMind::Espacios`, con su nombre en
     **Propiedades**.

3. **Lee los cambios** (termina antes el comando que tengas a medias con Esc):

   > Lee los cambios de Rhino

   Responde uno por línea, sin tocar todavía el modelo:

   ```
   1 cambio(s) en Rhino respecto del modelo cargado:
   - muro-000N: movido 0.20 m
   Borrador: …\salidas\borrador_rhino.json.
   ```

   Si algo no se puede leer (una copia, un sólido que ya no es una caja), lo dice en «Avisos» y
   lo deja como estaba.

4. **Guárdalos en el modelo:**

   > Aplícalos

   El modelo se actualiza, los espacios se recalculan con los muros nuevos y la respuesta dice qué
   áreas cambiaron. Por ejemplo, al subir 20 cm el tabique entre las dos habitaciones del plano de
   ejemplo: *Habitación 1: 9.19 → 8.52 m²* y *Habitación 2: 11.52 → 12.19 m²*. Queda una versión
   nueva, como cualquier otro cambio.

   Si con esos cambios el modelo quedara con errores (dos ventanas encima una de otra, por
   ejemplo), no aplica nada y explica qué corregir en Rhino.

5. Para seguir editando: «Abre el proyecto en Rhino» otra vez. Para guardar el archivo de Rhino
   tal cual: «Guarda el 3dm».

### Qué no se puede editar en Rhino

- Los **muros de varios tramos** (los que se quiebran): solo se editan los rectos.
- Un muro o un vano tiene que **seguir siendo una caja**. Si lo cortas con una booleana o lo
  deformas, ArchiMind avisa y lo deja como estaba.
- Las **copias** de un objeto de ArchiMind (con `Copy`) llevan su mismo identificador y se
  ignoran, con aviso: dibuja los objetos nuevos desde cero.
- Lo dibujado **fuera de las capas `ArchiMind::`** no se lee.
- Si el modelo cambió en ArchiMind mientras tenías ediciones sin leer en Rhino, «Abre el proyecto
  en Rhino» se niega para no perderlas: primero «Lee los cambios», o di «ábrelo descartando esos
  cambios» si no los quieres.

## Axonometrías

Rhino tiene que estar abierto con el puente iniciado, pero no se usa ni se cambia su documento.

> Haz una axonometría desde el suroeste

Escribe `salidas\axonometria-iso_so.dxf` (en metros) y `.svg` (a 1:50), con las líneas visibles
continuas y las ocultas a trazos, más finas. Hay cuatro vistas: desde el **suroeste**, el
**sureste**, el **noreste** y el **noroeste** (el norte es hacia arriba en la planta).

> Hazla explotada, con 0.5 m de separación

Separa en altura cada nivel y, dentro de él, los muros de su losa.

Si faltan alturas, no dibuja nada y lo dice: dáselas («la altura es 2.60 m») y vuelve a pedirla.

## Cortes

1. **Pide las propuestas** (las calcula ArchiMind, sin Rhino):

   > Propón cortes

   ```
   longitudinal (corte A-A): Paralelo al lado largo; cruza Habitación 2, Sala-comedor-cocina; corta 1 puerta y 1 ventana.
   transversal (corte B-B): Paralelo al lado corto; cruza Sala-comedor-cocina, Baño; corta 1 puerta y 1 ventana.
   ```

   Si un espacio se llama «Escalera», propone también un corte por ella.

2. **Elige uno y hacia dónde mira:**

   > Dibuja el corte longitudinal mirando hacia la izquierda

   «Izquierda» y «derecha» son según el recorrido de la línea de corte. Escribe
   `salidas\corte-longitudinal.dxf` y `.svg`: lo cortado, grueso (capa CORTADO), y lo que se ve
   detrás, fino (capa PROYECTADO), hasta el fondo del edificio. Para ver menos fondo: «con 1 m de
   profundidad».

3. **Un corte por donde tú quieras**, con dos puntos en metros:

   > Dibuja un corte de (2, 8) a (8, 2) mirando hacia la izquierda

Los grosores y tipos de línea de los dibujos están en
`bridges\rhino\mcp\config\estilos.yaml`.

## Si algo falla

- **«Rhino no está abierto o el puente no está iniciado»**: inicia el puente (arriba).
- **«Rhino está ejecutando un comando»**: termina o cancela el comando en Rhino (Esc).
- **«El documento abierto en Rhino tiene cambios sin guardar»**: guarda o cierra ese documento;
  ArchiMind no abre encima de uno con cambios.
- **«El documento abierto en Rhino no es el de …»**: pide «Abre el proyecto en Rhino» con el
  proyecto correcto.
- **«El puente de Rhino rechazó el token»**: vuelve a ejecutar el script del puente.

Detalles técnicos del puente: [bridges/rhino/README.md](../bridges/rhino/README.md).
