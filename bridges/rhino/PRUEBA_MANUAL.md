# Prueba manual: el puente con Rhino 8

Las pruebas automáticas cubren el servidor MCP y la parte del script que no depende de Rhino,
contra un documento de Rhino falso. Lo que solo se ve en Rhino —RhinoCommon, el hilo de la
interfaz, las unidades— se comprueba con estos pasos. Hace falta Rhino 8 para Windows.

## Preparación

1. En el repositorio: `uv sync`.
2. Conectar `rhino-bridge` con Claude Desktop. Con Rhino 8 instalado, doble clic en
   `Instalar ArchiMind` lo añade solo (o `uv run python scripts\instalacion.py --uv <ruta de
   uv.exe> --rhino`). A mano, en el archivo de configuración que lee Claude Desktop (ver la
   [instalación manual](../../docs/instalacion-manual.md#6-conectar-archimind-con-claude-desktop))
   y dentro de `mcpServers`, junto a `archimind-core`, añadir:

   ```json
   "rhino-bridge": {
     "command": "uv",
     "args": [
       "run",
       "--directory",
       "C:\\RUTA\\ABSOLUTA\\A\\ArchiMind",
       "--package",
       "archimind-rhino-bridge",
       "archimind-rhino-bridge"
     ],
     "env": { "PYTHONUTF8": "1" }
   }
   ```

3. Cerrar Claude Desktop del todo y volver a abrirlo. En **Configuración → Desarrollador**,
   `rhino-bridge` debe estar en marcha, con 6 herramientas. El registro es
   `mcp-server-rhino-bridge.log`.

## Sin Rhino

Con Rhino cerrado, crear el proyecto desde core: «Abre el proyecto C:\Temp\casa-prueba, importa
`<repositorio>\tests\golden\apto_2hab\input.dxf`, propón el mapeo y aplícalo, y confirma la
escala». Después, «¿Está Rhino abierto para C:\Temp\casa-prueba?». Debe responder
«Rhino no está abierto o el puente no está iniciado; ejecuta
`<repositorio>\bridges\rhino\plugin\archimind_bridge.py` desde el editor de scripts», con la
ruta real del script.

## Iniciar el puente

1. Abrir Rhino 8 con un documento nuevo, sin dibujar nada.
2. Escribir `ScriptEditor` en la línea de comandos. En el editor: **Abrir** →
   `<repositorio>\bridges\rhino\plugin\archimind_bridge.py` → **Ejecutar** (F5).
3. En la pestaña **Terminal** debe aparecer «Puente ArchiMind activo en 127.0.0.1:48765
   (configuración en C:\Users\<usuario>\.archimind\rhino_bridge.json)». Ese archivo debe
   existir, con `port` y `token`.
4. Ejecutar el script otra vez: debe volver a decir «activo», sin error de puerto ocupado
   (`scriptcontext.sticky` guarda el servidor entre ejecuciones y reiniciar libera el puerto).
5. Pedir «¿Está Rhino abierto para C:\Temp\casa-prueba?»: «Rhino 8.x…: el puente responde», el
   documento sin título y «El documento no tiene las capas de ArchiMind».

## Abrir el proyecto

1. Pedir «Abre el proyecto C:\Temp\casa-prueba en Rhino». Debe responder «Proyecto abierto en
   Rhino: C:\Temp\casa-prueba\salidas\casa-prueba.3dm» con «8 muros, 9 vanos, 4 espacios».
2. En Rhino:
   - el título de la ventana es `casa-prueba` y el comando `Units` dice metros;
   - en el panel **Capas** está `ArchiMind` con `Muros` (8 objetos), `Vanos` (9) y
     `Espacios` (4);
   - los muros son sólidos desde el piso (cota 0) hasta su altura, los vanos son cajas dentro de
     los huecos y los espacios, superficies en el piso (vista **Perspectiva**, modo Sombreado);
   - al seleccionar un muro, **Propiedades** muestra el nombre `muro-000N` y, en **Texto de
     usuario de atributos**, `archimind_id = muro-000N`;
   - al seleccionar un espacio, el nombre es el del espacio (p. ej. `Habitación 1`) y el
     `archimind_id`, `esp-000N`.
3. `Deshacer` (Ctrl+Z) debe quitar la carga entera en un paso («ArchiMind: cargar el modelo»);
   rehacerla con Ctrl+Y.
4. Pedir el estado: «Capas ArchiMind de este proyecto: 8 muros, 9 vanos, 4 espacios» y «El
   modelo está al día con lo que se cargó en Rhino».

## Editar y leer los cambios

Antes de cada lectura, terminar el comando en curso (Esc).

1. Pedir «Lee los cambios de Rhino»: «Sin cambios en Rhino respecto del modelo cargado».
2. Editar:
   - mover un muro 0.5 m con `Move`, junto con sus vanos;
   - cambiar la altura de otro muro con el Gumball (el cuadrado de escala en Z);
   - girar otro muro 5° con `Rotate`;
   - borrar un vano;
   - ensanchar otro vano con el Gumball, a lo largo de su muro.
3. Pedir «Lee los cambios»: una línea por cada edición («muro-…: movido 0.50 m»,
   «muro-…: alto 2.60 → …», «vano-…: borrado», «vano-…: ancho … → …»; el muro girado aparece
   como movido) y «Borrador: …\salidas\borrador_rhino.json». En ese archivo: `"source":
   "rhino"`, `base_sha256` y los mismos IDs en `walls`, `openings` y `deleted`. `modelo.json` no
   cambia: `git status` en la carpeta del proyecto queda limpio.
4. Nuevos y renombrados, con la capa actual en `ArchiMind::…` según el caso:
   - en **Propiedades** de un espacio, cambiar el **Nombre** a `Estudio`;
   - en `ArchiMind::Muros`, `Box` de 3 m × 0.10 m en planta y 2.60 m de alto, apoyada en la cota
     0;
   - en `ArchiMind::Vanos`, `Box` de 0.80 m de largo que atraviese esa caja nueva a lo largo,
     desde la cota 0 y de 2.0 m de alto;
   - en `ArchiMind::Espacios`, `Rectangle` y `PlanarSrf` en la cota 0, con Nombre `Depósito`.

   «Lee los cambios»: «esp-…: renombrado «…» → «Estudio»», «nuevo muro nuevo-1: largo 3.00 m,
   espesor 0.100 m», «nuevo vano nuevo-2 en nuevo-1: ancho 0.80 m, alto 2.00 m» y «nuevo espacio
   nuevo-3 «Depósito»: … m²»; en el borrador, `new_walls`, `new_openings` (con `"wall":
   "nuevo-1"` y `"kind": "void"`) y `new_spaces`. Deshacer esas ediciones con Ctrl+Z.
5. Avisos: copiar un muro (`Copy`), dibujar una caja en `ArchiMind::Muros` a 1 m de altura
   (cota 1, fuera de todo nivel) y aplicar `BooleanDifference` a otro muro con una caja que lo
   corte. «Lee los cambios»: «… está 2 veces en Rhino (¿una copia?)», «Muro nuevo a la cota 1.00
   m: no está en ningún nivel» y, para el muro cortado, «su huella ya no es un rectángulo» o «no
   se pudo leer». Deshacer esas tres ediciones con Ctrl+Z.
6. Unidades: `Units` → Milímetros, contestando **Sí** a escalar los objetos. «Lee los cambios»
   debe dar los mismos cambios que en el paso 3, con las medidas en metros. Volver a metros del
   mismo modo.
7. Pedir «Guarda el 3dm»: «Documento de Rhino guardado en …\salidas\casa-prueba.3dm». Cerrar
   Rhino, abrirlo de nuevo, iniciar el puente y pedir «Abre el proyecto en Rhino»: «Las capas
   ArchiMind ya estaban al día… se conservan las ediciones hechas en Rhino», con las ediciones del
   paso 2 a la vista.

## Ciclo de edición con apto_2hab

El ciclo completo: editar en Rhino, guardar la edición en el modelo y ver sus cantidades nuevas.
Se hace con un proyecto recién creado, sin las ediciones de las secciones anteriores.

1. Crear el proyecto desde core: «Abre el proyecto C:\Temp\apto-ciclo, importa
   `<repositorio>\tests\golden\apto_2hab\input.dxf`, propón el mapeo y aplícalo, y confirma la
   escala».
2. «Dame el cuadro de áreas de C:\Temp\apto-ciclo». Anotar: **Habitación 1 9.19 m²**,
   **Habitación 2 11.52 m²**, Baño 2.93 m², Sala-comedor-cocina 27.21 m² y el área útil.
3. «Abre el proyecto en Rhino»: «8 muros, 9 vanos, 4 espacios».
4. En Rhino, vista **Superior**: seleccionar el tabique de 0.10 m que separa las dos habitaciones
   (el muro horizontal a la izquierda, a 3.60 m del borde inferior) y anotar su `archimind_id` en
   **Propiedades → Texto de usuario de atributos**. `Move` → punto base cualquiera → escribir
   `r0,0.2` e Intro: el tabique sube 20 cm (de y = 3.60 a y = 3.80). Esc para terminar.
5. «Lee los cambios»: «1 cambio(s) en Rhino…», «- muro-…: movido 0.20 m» (el ID anotado),
   «Borrador: …\salidas\borrador_rhino.json» y «Para guardarlo en el modelo: aplicar_borrador de
   archimind-core». `modelo.json` sigue igual.
6. «Aplica el borrador»: «Borrador de Rhino aplicado: 1 cambio.», «Muros editados: muro-…»,
   «Espacios con otra área:» con **Habitación 1: 9.19 → 8.52 m²** y **Habitación 2: 11.52 →
   12.19 m²**, y «Versión …». En la carpeta, `salidas\borrador_rhino.json` pasó a
   `salidas\borrador_rhino.aplicado.json`, y `git log --oneline -1` (en
   C:\Temp\apto-ciclo) muestra «Aplica 1 cambio de Rhino».
7. «Dame el cuadro de áreas»: **Habitación 1 8.52 m²**, **Habitación 2 12.19 m²**; Baño,
   Sala-comedor-cocina, el área útil y la construida, iguales que en el paso 2. El CSV
   `salidas\cuadro_de_areas.csv` tiene los valores nuevos.
8. «Lee los cambios» otra vez: «Los 1 cambio(s) de Rhino ya se aplicaron al modelo…». «Abre el
   proyecto en Rhino»: recarga las capas («Las ediciones que había en Rhino ya estaban aplicadas
   en el modelo»), sin pedir descartar nada; el tabique queda en y = 3.80.

Variantes, cada una desde el estado del paso 8 y terminando con «Aplica el borrador» y el cuadro
de áreas:

- **Renombrar**: en **Propiedades** de la superficie de Habitación 1, Nombre `Estudio`. «Lee los
  cambios» → «renombrado «Habitación 1» → «Estudio»»; al aplicar, «Renombrado: …» y el cuadro
  de áreas dice Estudio con la misma área.
- **Muro nuevo**: en `ArchiMind::Muros`, `Box` de 0.10 m × 4.80 m en planta, de (5.45, 0) a
  (5.55, 4.80), 2.60 m de alto desde la cota 0 (parte la sala en dos). Al aplicar: «Nuevos:
  nuevo-1 → muro-…» con un ID que nunca se usó, la sala pasa a 17.96 m² y aparece «Espacio sin
  nombre 1» de 8.79 m², con un aviso `espacio_nuevo`.
- **Borrar un vano**: borrar la caja de la puerta del baño. Al aplicar: «Borrados: vano-…»; las
  áreas no cambian.
- **Error de validación**: con `Move`, llevar la caja de una ventana del muro inferior encima de
  la puerta de entrada (las dos en el mismo muro). «Lee los cambios» → «vano-…: desplazado …».
  «Aplica el borrador» → «No se aplicó nada: con estos cambios el modelo tendría 1 error(es):
  los vanos … y … se superponen en el muro …». `modelo.json` y `git log` no cambian. Deshacer
  con Ctrl+Z.

## Proteger lo que no se leyó

1. Con esas ediciones en Rhino, cambiar el modelo en core: «El muro muro-0001 mide en realidad
   2 m: recalcula la escala».
2. «Abre el proyecto en Rhino»: debe negarse con «En Rhino hay cambios que aún no se leyeron y el
   modelo cambió…», listando los primeros, sin tocar las capas.
3. «Ábrelo descartando esos cambios»: «Se descartaron N cambio(s)», las capas recargadas con la
   escala nueva (todo cambia de tamaño) y el archivo guardado.

## Axonometrías con apto_2hab y en_l

Las isométricas de líneas ocultas se calculan en Rhino con `HiddenLineDrawing`, la clase de
Make2D, sobre las piezas del 3D del modelo, y quedan en DXF y SVG. Se hacen con proyectos recién
creados. Rhino debe estar abierto con el puente iniciado; da igual qué documento tenga.

1. Crear los dos proyectos desde core: «Abre el proyecto C:\Temp\axo-apto, importa
   `<repositorio>\tests\golden\apto_2hab\input.dxf`, propón el mapeo y aplícalo, y confirma la
   escala», y lo mismo con `C:\Temp\axo-l` y `tests\golden\en_l\input.dxf`.
2. «Dibuja la axonometría de C:\Temp\axo-apto»: debe negarse con «faltan alturas y no se
   suponen». Responder «La altura es 2.60 m» (core la aplica con `definir_alturas`) y pedirla de
   nuevo: «Axonometría isométrica desde el suroeste: DXF en
   C:\Temp\axo-apto\salidas\axonometria-iso_so.dxf (metros) y SVG en … (1:50)», con «VISIBLES
   N (0.25 mm), OCULTAS M (0.13 mm)».
3. Abrir el DXF en Rhino (`Import`, unidades en metros) o en LibreCAD:
   - se ve el apartamento desde el suroeste, con la fachada sur (la de la puerta de entrada y la
     ventana de la habitación 2) al frente y a la izquierda;
   - los huecos de puertas y ventanas están abiertos, con el dintel encima y el antepecho debajo
     en las ventanas; la losa asoma bajo los muros;
   - las aristas visibles son continuas en la capa VISIBLES, y las que quedan detrás de un muro
     van a trazos en OCULTAS. En **Propiedades de capa**, VISIBLES tiene 0.25 mm y OCULTAS
     0.13 mm, de tipo DASHED;
   - no hay aristas sueltas a lo largo de las caras de los muros. Si aparecen en las uniones
     entre machón y dintel, anotarlo: son aristas entre piezas, no un error de la vista.
4. Abrir el SVG en el navegador: el mismo dibujo en negro, con las ocultas a trazos y más finas.
5. Pedir las otras tres vistas («desde el noreste», «noroeste», «sureste»): cada una con su
   archivo `axonometria-iso_ne.dxf`… y la fachada que corresponde al frente (desde el noreste,
   la norte con la ventana alta del baño).
6. «Dibújala explotada»: `axonometria-iso_so-explotada.dxf`, con «Explotada: 1.00 m entre cada
   losa y sus muros». La losa queda abajo, sola, y los muros flotan 1 m por encima. «Explotada con
   0.5 m de separación»: la distancia se reduce a la mitad.
7. Repetir los pasos 2, 3 y 6 con C:\Temp\axo-l: el chaflán a 45° con su puerta y el tabique que
   llega a su punto medio se ven enteros; la losa en L sigue el contorno de los muros.
8. En Rhino, el documento abierto no cambió: no hay objetos nuevos, el título no tiene el
   asterisco de cambios y `Undo` no tiene nada de ArchiMind.

## Cortes con apto_2hab y en_l

Con los proyectos de la sección anterior (con alturas).

1. «Propón cortes para C:\Temp\axo-apto» (core): dos cortes,
   - «longitudinal (corte A-A): Paralelo al lado largo; cruza Habitación 2, Sala-comedor-cocina;
     corta 1 puerta y 1 ventana.»
   - «transversal (corte B-B): Paralelo al lado corto; cruza Sala-comedor-cocina, Baño; corta 1
     puerta y 1 ventana.»

   y «Guardados en C:\Temp\axo-apto\salidas\cortes.json». Sin escalera: ningún espacio se llama
   así.
2. «Dibuja el corte longitudinal mirando hacia la izquierda» (rhino-bridge): «Corte A-A mirando
   hacia la izquierda: DXF en C:\Temp\axo-apto\salidas\corte-longitudinal.dxf…», con «CORTADO N
   (0.50 mm), PROYECTADO M (0.18 mm)» y «Profundidad: 3.35 m (hasta el fondo del edificio)».
3. Abrir el DXF en Rhino o LibreCAD. El corte va de oeste a este a y = 3.25 m y mira al norte:
   - **en CORTADO** (0.50 mm en las propiedades de la capa): los muros oeste y este, cada uno con
     su espesor (0.20 m), el tabique de 0.12 m con la puerta de la habitación 2 abierta (solo el
     dintel cortado arriba), la ventana del muro este (dintel arriba y antepecho abajo) y la
     losa de 0.15 m de punta a punta bajo todo;
   - **en PROYECTADO** (0.18 mm): detrás, la fachada norte con sus tres ventanas, el tabique
     entre las habitaciones y los del baño;
   - **nada** de lo que queda al sur de la línea: ni la puerta de entrada ni la ventana de la
     habitación 2. Si aparecen, o si en lugar de lo de detrás aparece lo de delante, el lado del
     recorte está invertido: anotarlo (es el signo de `cut_planes` en
     `mcp/src/archimind_rhino_bridge/views.py`);
   - y = 0 es la cara inferior de la losa: los muros llegan a 0.15 + 2.60 = 2.75 m.
4. «El mismo corte mirando hacia la derecha»: se ve la fachada sur desde dentro, con la puerta de
   entrada y la ventana de la habitación 2, y el dibujo queda como en un espejo.
5. «Con 1 m de profundidad»: «Profundidad: 1.00 m.»; de lo que hay detrás solo sale lo que está a
   menos de 1 m de la línea (el tabique en y = 3.60 m) y no la fachada norte.
6. «Dibuja el corte transversal mirando hacia la derecha»: B-B, por el baño, con su puerta y su
   ventana alta cortadas.
7. Abrir `corte-longitudinal.svg` en el navegador: las líneas cortadas se ven claramente más
   gruesas que las proyectadas.
8. Con C:\Temp\axo-l: «Propón cortes»: el longitudinal cruza Estar y Dormitorio y el transversal
   solo el Estar. Dibujar los dos. Después, un corte **por dos puntos** que atraviese el chaflán:
   «Dibuja un corte de (2, 8) a (8, 2) mirando hacia la izquierda». Debe responder «Corte por
   dos puntos…» y escribir `salidas\corte.dxf`. En CORTADO, el muro diagonal se corta de frente
   con su puerta.
9. «Dibuja el corte escalera»: «No hay un corte propuesto llamado «escalera»; los propuestos son:
   longitudinal, transversal».
10. Escalera: renombrar un espacio de C:\Temp\axo-l a «Escalera» (abrir_en_rhino, en Rhino
    Nombre `Escalera` en las Propiedades de su superficie, leer_cambios y aplicar_borrador) y
    pedir los cortes otra vez: aparece «escalera (corte C-C):
    Por Escalera; …», y se puede dibujar por su nombre.
11. En Rhino, el documento sigue sin cambios.

## Errores

- **Documento ajeno con cambios**: `New` en Rhino, dibujar una línea sin guardar y pedir «Abre el
  proyecto en Rhino»: debe decir que el documento tiene cambios sin guardar, sin que Rhino abra
  ningún cuadro de diálogo.
- **Comando a medias**: empezar `Box` y dejarlo esperando un punto. «Lee los cambios»: «Rhino
  está ejecutando un comando: termínalo o cancélalo (Esc)…». El estado sí responde y lo menciona.
- **Token cambiado**: editar `token` en `rhino_bridge.json` sin reiniciar el puente. Cualquier
  pedido: «El puente de Rhino rechazó el token: vuelve a ejecutar …». Ejecutar el script otra
  vez (lee el token nuevo) y comprobar que responde.
- **Rhino cerrado** a mitad de la sesión: el mensaje «Rhino no está abierto…» con la ruta.
- **Otro proyecto**: crear `C:\Temp\otra` desde core y pedir «Lee los cambios de C:\Temp\otra»:
  «El documento abierto en Rhino no es el de otra: ábrelo con abrir_en_rhino».

## Lo que esta prueba confirma

Lo que no se pudo comprobar sin Rhino, y qué paso lo confirma:

- que el hilo del servidor sigue vivo al terminar el script y que `scriptcontext.sticky` lo
  guarda entre ejecuciones (Iniciar, paso 4);
- que `RhinoDoc.Open` y `TryGetPolyline` devuelven sus parámetros `out` como tupla (Abrir; Editar,
  paso 3);
- que las extrusiones suben desde la cota del nivel (Abrir, paso 2);
- que un sólido escalado con el Gumball se sigue leyendo, sea extrusión o polisuperficie
  (Editar, paso 3);
- que `ObjectAttributes.Name` guarda y devuelve el nombre del espacio, y que una `Box` y una
  `PlanarSrf` dibujadas a mano se leen como prisma y como superficie (Editar, paso 4);
- la conversión de unidades del documento (Editar, paso 6);
- que el texto del documento admite el `modelo.json` entero (Editar, paso 7);
- que una `ViewportInfo` nueva acepta la proyección paralela (la documentación da
  `ChangeToParallelProjection` con y sin argumento; el script prueba las dos), la cámara y el
  encuadre de `SetFrustum`, y que `HiddenLineDrawing` devuelve las curvas en el sistema de la
  vista, sin z (Axonometrías, pasos 2 y 3: si sale una planta o un dibujo deformado, falla esto);
- que `getattr(SilhouetteType, "None")` lee ese miembro y que los segmentos ocultos llegan como
  `Visibility.Hidden` (Axonometrías, paso 3);
- que `Extrusion.AddInnerProfile` abre los huecos de las losas (Axonometrías, paso 7: la losa en
  L sin rellenos raros);
- que el cálculo no agrega nada al documento (Axonometrías, paso 8; Cortes, paso 11);
- que `AddClippingPlane` quita el lado hacia el que apunta la normal, como dijo McNeel, y que el
  segundo plano limita la profundidad (Cortes, pasos 3 y 5);
- que lo cortado llega con `SilhouetteType.SectionCut` y va a CORTADO (Cortes, paso 3).
