# Prueba manual: el puente con Rhino 8

Las pruebas automáticas cubren el servidor MCP y la parte del script que no depende de Rhino,
contra un documento de Rhino falso. Lo que solo se ve en Rhino —RhinoCommon, el hilo de la
interfaz, las unidades— se comprueba con estos pasos. Hace falta Rhino 8 para Windows.

## Preparación

1. En el repositorio: `uv sync`.
2. En Claude Desktop, **Configuración → Desarrollador → Editar configuración**, y dentro de
   `mcpServers` (junto a `archimind-core`, como explica el README) añadir:

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
   `rhino-bridge` debe estar en marcha, con 4 herramientas. El registro es
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

## Proteger lo que no se leyó

1. Con esas ediciones en Rhino, cambiar el modelo en core: «El muro muro-0001 mide en realidad
   2 m: recalcula la escala».
2. «Abre el proyecto en Rhino»: debe negarse con «En Rhino hay cambios que aún no se leyeron y el
   modelo cambió…», listando los primeros, sin tocar las capas.
3. «Ábrelo descartando esos cambios»: «Se descartaron N cambio(s)», las capas recargadas con la
   escala nueva (todo cambia de tamaño) y el archivo guardado.

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
- que el texto del documento admite el `modelo.json` entero (Editar, paso 7).
