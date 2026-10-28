# ArchiMind

Proyecto personal para procesar planos arquitectónicos con IA. Importa DXF/DWG e imágenes a un
modelo semántico (niveles, muros, vanos, espacios) y genera cuadros de áreas, bloques de
carpintería, axonometrías y cortes, todo a través de servidores MCP usados desde Claude Desktop.

Es un workspace de [uv](https://docs.astral.sh/uv/) con Python >= 3.11. Para instalarlo y
probarlo: `uv sync` y luego `uv run pytest`. Arquitectura, reglas y comandos en [CLAUDE.md](CLAUDE.md).

## Instalación paso a paso (Windows)

Esta guía no necesita saber programar. Se hace una sola vez y toma unos 20 minutos. Hace falta
un equipo con Windows 10 u 11, conexión a internet, una cuenta de Claude y una cuenta de GitHub
con acceso a este repositorio (es privado: hay que pedir la invitación al dueño).

En varios pasos se usa **PowerShell**, la ventana de comandos de Windows: se abre con el botón
Inicio, escribiendo `PowerShell` y pulsando Intro. Para ejecutar un comando, se copia de esta
guía, se pega en la ventana con clic derecho y se pulsa Intro.

### 1. Instalar Claude Desktop

Descargarlo desde <https://claude.ai/download>, instalarlo y entrar con la cuenta de Claude.

### 2. Instalar Git

ArchiMind lo usa para guardar el historial de cada proyecto (cada cambio queda como una
versión a la que se puede volver). Descargar el instalador de Windows desde
<https://git-scm.com/downloads/win> y ejecutarlo pulsando **Next** en todas las pantallas, sin
cambiar nada.

### 3. Instalar uv

uv es el programa que descarga Python y todo lo que ArchiMind necesita, y lo pone en marcha. No
hace falta instalar Python aparte. En PowerShell, ejecutar:

```
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Al terminar, **cerrar PowerShell y abrirlo de nuevo**, y comprobar que quedó instalado con:

```
uv --version
```

Debe responder algo como `uv 0.9.x`. Si dice que no reconoce `uv`, reiniciar el equipo y
probar otra vez.

### 4. Descargar ArchiMind

1. Entrar en GitHub con la cuenta invitada y abrir la página de este repositorio.
2. Pulsar el botón verde **Code** y luego **Download ZIP**.
3. Abrir el ZIP descargado (en la carpeta Descargas), pulsar **Extraer todo** y elegir una
   carpeta fácil de encontrar, p. ej. `C:\ArchiMind`.
4. Entrar en la carpeta extraída hasta ver los archivos `README.md` y `pyproject.toml`: esa es
   la carpeta de ArchiMind. A veces el ZIP crea una carpeta dentro de otra
   (`ArchiMind-main\ArchiMind-main`); lo que cuenta es la que tiene esos archivos.
5. Copiar su ruta: hacer clic en la barra de direcciones del Explorador (arriba, donde aparece
   la ubicación) y copiar el texto, p. ej. `C:\ArchiMind\ArchiMind-main`. Se usa en los pasos
   5 y 6.

### 5. Preparar ArchiMind

En PowerShell, ejecutar estos dos comandos, cambiando la ruta por la copiada en el paso 4 (con
las comillas):

```
cd "C:\ArchiMind\ArchiMind-main"
uv sync
```

`uv sync` descarga Python y las librerías; la primera vez puede tardar unos minutos. Termina
cuando la ventana vuelve a mostrar la ruta y queda esperando otro comando.

### 6. Conectar ArchiMind con Claude Desktop

1. En Claude Desktop, abrir **Configuración → Desarrollador → Editar configuración**. Se abre
   la carpeta donde está el archivo `claude_desktop_config.json`.
2. Abrirlo con el Bloc de notas: clic derecho sobre el archivo → **Abrir con** → **Bloc de
   notas**.
3. Si el archivo está vacío o solo tiene `{}`, borrar lo que haya y pegar el bloque de abajo. Si
   ya tiene otras cosas, seguir las indicaciones de [Uso desde Claude
   Desktop](#uso-desde-claude-desktop) para no estropearlo.
4. En el bloque pegado, cambiar las dos veces que aparece `C:\\RUTA\\ABSOLUTA\\A\\ArchiMind` por
   la ruta del paso 4, **escribiendo cada barra `\` dos veces**: `C:\ArchiMind\ArchiMind-main`
   se escribe `C:\\ArchiMind\\ArchiMind-main`. Hay que conservar las comillas.
5. Guardar (Ctrl + G o Archivo → Guardar) y cerrar el Bloc de notas.

```json
{
  "mcpServers": {
    "archimind-core": {
      "command": "uv",
      "args": ["run", "--directory", "C:\\RUTA\\ABSOLUTA\\A\\ArchiMind", "--package", "archimind-core", "archimind-core"],
      "env": { "PYTHONUTF8": "1" }
    },
    "archimind-bloques": {
      "command": "uv",
      "args": ["run", "--directory", "C:\\RUTA\\ABSOLUTA\\A\\ArchiMind", "--package", "archimind-bloques", "archimind-bloques"],
      "env": { "PYTHONUTF8": "1" }
    },
    "archimind-docs": {
      "command": "uv",
      "args": ["run", "--directory", "C:\\RUTA\\ABSOLUTA\\A\\ArchiMind", "--package", "archimind-docs", "archimind-docs"],
      "env": { "PYTHONUTF8": "1" }
    }
  }
}
```

### 7. Reiniciar Claude Desktop y comprobar

1. Cerrar Claude Desktop **del todo**: cerrar la ventana no basta. Hay que buscar su icono en la
   bandeja del sistema (junto al reloj, a veces detrás de la flecha `^`), hacer clic derecho y
   elegir **Salir**.
2. Abrirlo de nuevo y entrar en **Configuración → Desarrollador**: deben aparecer
   `archimind-core`, `archimind-bloques` y `archimind-docs`, los tres en marcha (*running*).
3. Probarlo en un chat nuevo con un plano de ejemplo que viene incluido, cambiando las rutas por
   las de este equipo:

   > Abre el proyecto en C:\Users\<usuario>\Documents\ArchiMind-proyectos\prueba e importa el
   > plano C:\ArchiMind\ArchiMind-main\tests\golden\apto_2hab\input.dxf

   Claude pide permiso para usar las herramientas de ArchiMind: pulsar **Permitir**. Debe
   responder con las capas del plano y sus unidades. A partir de ahí basta con pedirle lo
   siguiente en lenguaje normal (proponer el mapeo de capas, confirmar la escala, el cuadro de
   áreas, exportar el plano…).

Conviene guardar los proyectos **fuera** de la carpeta de ArchiMind (como en el ejemplo, en
Documentos): así, al actualizar ArchiMind no se tocan.

### Si algo falla

- **Un servidor aparece con error en Configuración → Desarrollador**: ahí mismo está el botón
  para abrir los registros (`mcp-server-archimind-core.log`); las últimas líneas suelen decir
  qué pasa.
- **El registro dice que no encuentra `uv`**: en PowerShell, ejecutar `where.exe uv`. Responde
  con una ruta como `C:\Users\<usuario>\.local\bin\uv.exe`; en el archivo de configuración, poner
  esa ruta en lugar de `"uv"` en las dos líneas `"command"`, con las barras dobles
  (`"C:\\Users\\<usuario>\\.local\\bin\\uv.exe"`), y reiniciar Claude Desktop como en el paso 7.
- **Claude Desktop dice que la configuración no es válida**: casi siempre falta o sobra una coma
  o una comilla, o hay una barra `\` simple. Comparar con el bloque del paso 6.
- **Un plano DWG no se puede abrir o exportar**: hace falta un programa más, ver
  [DWG: ODA File Converter](#dwg-oda-file-converter-opcional). Con DXF no hace falta.

### Actualizar ArchiMind

Descargar el ZIP de nuevo (paso 4), reemplazar la carpeta de ArchiMind por la nueva **en la
misma ubicación**, repetir el paso 5 y reiniciar Claude Desktop (paso 7). Si la carpeta queda
en la misma ruta, no hay que cambiar la configuración.

## Uso desde Claude Desktop

Referencia técnica de la configuración; la guía de arriba cubre el caso habitual. Hace falta [uv](https://docs.astral.sh/uv/) y [git](https://git-scm.com/downloads) instalados.
Hay cuatro servidores: `archimind-core` (planos y modelo), `archimind-bloques` (carpintería),
`archimind-docs` (memoria, presupuesto, programa de áreas, COS/CUS y ficha PDF) y
`rhino-bridge` (el modelo en Rhino 8, ver [bridges/rhino](bridges/rhino/README.md)). Se declaran en `claude_desktop_config.json`. Para abrirlo, en Claude Desktop:
**Configuración → Desarrollador → Editar configuración**. Así se abre (o se crea) el archivo
que la app lee de verdad: si Claude Desktop se instaló desde Microsoft Store, Windows redirige
su carpeta y el archivo no está en `%APPDATA%\Claude\`.

En el JSON hay que cambiar `C:\\RUTA\\ABSOLUTA\\A\\ArchiMind` por la ruta absoluta de este
repositorio, con las barras invertidas dobles:

```json
{
  "mcpServers": {
    "archimind-core": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "C:\\RUTA\\ABSOLUTA\\A\\ArchiMind",
        "--package",
        "archimind-core",
        "archimind-core"
      ],
      "env": { "PYTHONUTF8": "1" }
    },
    "archimind-bloques": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "C:\\RUTA\\ABSOLUTA\\A\\ArchiMind",
        "--package",
        "archimind-bloques",
        "archimind-bloques"
      ],
      "env": { "PYTHONUTF8": "1" }
    },
    "archimind-docs": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "C:\\RUTA\\ABSOLUTA\\A\\ArchiMind",
        "--package",
        "archimind-docs",
        "archimind-docs"
      ],
      "env": { "PYTHONUTF8": "1" }
    },
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
  }
}
```

Dónde va en el archivo:

- **Archivo vacío o recién creado**: se pega el bloque completo.
- **Archivo con contenido y sin `mcpServers`**: `mcpServers` se añade como una clave más del
  objeto de primer nivel, junto a las que ya hay (p. ej. `preferences`), separada por una coma.
- **Archivo que ya tiene `mcpServers`**: solo se añaden las entradas `"archimind-core": {…}`,
  `"archimind-bloques": {…}`, `"archimind-docs": {…}` y `"rhino-bridge": {…}` dentro de ese objeto, separadas por comas de los otros servidores. El archivo debe tener una sola
  clave `mcpServers`.

El resultado tiene esta forma, donde los `…` son lo que ya hubiera en el archivo:

```
{
  "preferences": { … },
  "mcpServers": {
    "otro-servidor": { … },
    "archimind-core": { "command": …, "args": […], "env": { … } },
    "archimind-bloques": { "command": …, "args": […], "env": { … } },
    "archimind-docs": { "command": …, "args": […], "env": { … } },
    "rhino-bridge": { "command": …, "args": […], "env": { … } }
  }
}
```

Después se guarda y se cierra Claude Desktop del todo (también desde la bandeja del sistema)
antes de volver a abrirlo. En **Configuración → Desarrollador**, los servidores deben
aparecer en marcha; ahí mismo está el botón para abrir la carpeta de registros
(`mcp-server-archimind-core.log`, `mcp-server-archimind-bloques.log`). Si no encuentra `uv`, en
`command` va su ruta completa (`where uv` en Windows, `which uv` en macOS). Para probar un
servidor sin Claude Desktop: `uv run --package archimind-core archimind-core` (o
`archimind-bloques`) arranca y espera mensajes por stdio.

### DWG: ODA File Converter (opcional)

Solo hace falta para **importar un DWG** (`importar_plano`) y **exportar en DWG**
(`exportar_plano(formato="dwg")`); DXF y PNG funcionan sin él. ArchiMind no lo llama
directamente: usa el complemento `odafc` de ezdxf, que ejecuta el programa en el equipo donde
corre `archimind-core`. Sin él, las herramientas responden con un mensaje que ofrece el DXF.

1. **Instalarlo**: descargar el instalador gratuito de Windows desde
   <https://www.opendesign.com/guestfiles/oda_file_converter> (pide aceptar la licencia) y
   ejecutarlo con las opciones por defecto.
2. **Buscar el ejecutable**: el instalador lo deja en una carpeta con la versión en el nombre,
   p. ej. `C:\Program Files\ODA\ODAFileConverter 25.12.0\ODAFileConverter.exe`, mientras que
   ezdxf lo busca por defecto en `C:\Program Files\ODA\ODAFileConverter\ODAFileConverter.exe`.
   En Windows ezdxf solo mira esa ruta configurada (no el `PATH`), así que casi siempre hay que
   indicársela.
3. **Configurar ezdxf**: crear el archivo `%USERPROFILE%\.config\ezdxf\ezdxf.ini` (p. ej.
   `C:\Users\<usuario>\.config\ezdxf\ezdxf.ini`; la carpeta `.config\ezdxf` se crea a mano si no
   existe) con la ruta real del paso 2:

   ```ini
   [odafc-addon]
   win_exec_path = "C:\Program Files\ODA\ODAFileConverter 25.12.0\ODAFileConverter.exe"
   ```

   Las barras van simples (no es JSON) y las comillas son opcionales. Este archivo vale para el
   servidor y para las pruebas. Si se prefiere otro sitio, se puede apuntar a él con la variable
   de entorno `EZDXF_CONFIG_FILE`, por ejemplo dentro de `"env"` en `claude_desktop_config.json`.
4. **Comprobarlo** desde la carpeta del repositorio:

   ```
   uv run python -c "from ezdxf.addons import odafc; print(odafc.get_win_exec_path(), odafc.is_installed())"
   ```

   Debe imprimir la ruta del paso 2 seguida de `True`. Con `uv run ezdxf config -p` se ve la
   configuración completa que ezdxf cargó. La prueba
   `uv run --package archimind-core pytest packages/core/tests/test_export_dwg.py -rs` deja de
   aparecer como `SKIPPED`.
5. **Reiniciar Claude Desktop** del todo: el servidor lee la configuración al arrancar.

Al actualizar ODA File Converter cambia el número de versión de la carpeta: hay que corregir
`win_exec_path`. En macOS y Linux, ezdxf busca `ODAFileConverter` en el `PATH`, o la ruta de
`unix_exec_path` en la misma sección (útil para el AppImage). Con `ARCHIMIND_REMOTO=1` el DWG
queda deshabilitado aunque ODA esté instalado.

Flujo de trabajo: abrir_proyecto → importar_plano → proponer_mapeo_capas → aplicar_mapeo →
confirmar_escala → consultas, vista y exportación. Carpintería: exportar_plano (dxf) →
ajustar_bloque_a_vano → insertar_bloques_en_plano → asignar_bloques. Para probarlo hay 20
pedidos de ejemplo en `tests/pedidos_bloques.yaml`, con la llamada y el resultado esperados, y
los pasos en `packages/bloques/PRUEBA_MANUAL.md`. Rhino: con el puente iniciado en Rhino 8,
abrir_en_rhino → editar en Rhino → leer_cambios → aplicar_borrador (core) → cuadro_de_areas →
abrir_en_rhino para seguir editando. Dibujos: make2d_axonometria, y proponer_cortes (core) → el
usuario elige un nombre → corte. Los pasos, en `bridges/rhino/PRUEBA_MANUAL.md`.

## Estado

Está implementado `packages/schema`, el contrato del que dependen los demás paquetes; en
`packages/core` la importación de planos con su servidor MCP; en `packages/bloques` la
carpintería paramétrica con el suyo, y en `bridges/rhino` el puente con Rhino 8. `schema`:

- **Modelo semántico** (Pydantic v2): proyecto, niveles, muros, vanos, espacios, bloques y
  anotaciones, en metros. Pydantic comprueba la forma y los tipos. Cada nivel tiene una altura
  por defecto para sus muros sin altura propia, que no cuenta como medida hasta que se confirma
  (`height_confirmed`, falso al importar).
- **Bloques**: cada `Block` (`blq-`) guarda el nombre, el tipo (puerta o ventana), el ancho, el
  alto y los parámetros completos de su carpintería, con el perfil, para regenerarla aunque cambie
  el catálogo. Los vanos con la misma carpintería comparten bloque; cada vano guarda `block_id` y
  `block_side`, el lado del eje (recorrido de inicio a fin) hacia el que mira el «adentro» del
  bloque.
- **Borradores**, en un JSON de la carpeta del proyecto, para que core los valide y los aplique:
  `BlocksDraft`, la carpintería que `bloques` propone para unos vanos, y `EditsDraft`, lo editado
  en Rhino sobre una versión del modelo (muros, vanos y espacios con sus valores nuevos —el
  espacio también con su nombre—, IDs borrados y entidades nuevas sin ID: `NewWall`,
  `NewOpening` y `NewSpace`, con un `ref` temporal `nuevo-N` al que core pone un ID inédito; un
  vano nuevo puede ir en un muro nuevo por su `ref`) con el SHA-256 de esa versión
  (`base_sha256`), para rechazarlo si el modelo cambió.
- **Cortes propuestos** (`CutProposals`, en `salidas/cortes.json`): cada `CutLine` con su nombre
  para elegirla (`longitudinal`…), su rótulo (`A-A`), sus dos puntos en planta y una
  descripción, con el SHA-256 de la versión del modelo con la que se propusieron.
- **IDs inéditos** con prefijo (`niv-`, `muro-`, `vano-`, `esp-`, `blq-`): `new_id` usa un contador
  por prefijo que solo avanza y se guarda con el modelo.
- **Geometría derivada** con shapely: longitud y huella de muros, huella de vanos
  (`opening_polygon`), área de espacios y altura efectiva de muros.
- **Persistencia atómica** de `modelo.json`: `load_project` / `save_project`.
- **`validate(project)`**: devuelve todos los problemas del modelo a la vez, cada uno con código,
  severidad (`error` | `warning`), IDs afectados y mensaje en español. Son errores: IDs repetidos
  o mal formados, referencias a niveles, muros o bloques inexistentes, polígonos inválidos,
  espacios superpuestos, vanos fuera del muro o superpuestos, espesor ≤ 0, vano con bloque y sin
  lado (o al revés) y bloque de puerta en un vano de ventana (o al revés). Son avisos: espesor
  fuera de los habituales, unión abierta (extremo de muro a menos de 5 cm de otro sin tocarlo),
  bloque que no mide lo que su vano (p. ej. tras recalcular la escala) y escala no confirmada, que
  marca las cantidades como preliminares.

Casos golden para probar importadores, en `tests/golden/<caso>/` (`input.dxf`, `expected.json` e
`input.png`): `rect_simple`, `apto_2hab`, `apto_capas_caoticas`, `en_l`, `muros_linea_doble`,
`milimetros` y `planta_y_alzado` (la planta de `rect_simple` con un alzado al lado y sombreados en
la misma capa de muros; se reconstruye con `vista=1`). El modelo esperado está escrito a mano en
`tests/fixtures/cases.py` y el DXF se dibuja a partir de él con ezdxf.

- `uv run python tests/fixtures/generate.py [--caso X] --force` regenera los casos (sin `--force`
  no sobrescribe nada).
- `assert_matches_golden(project, caso)` (en `tests/fixtures/golden.py`, importable desde
  cualquier prueba) compara con tolerancia: coordenadas ±1 cm, áreas ±0.5 %, mismos conteos de
  muros y vanos y mismos nombres de espacios; los IDs pueden diferir. Un muro es un tramo recto
  continuo de eje, sin partir en las uniones en T. `assert_matches(project, esperado)` hace lo
  mismo frente a un modelo en memoria.
- `uv run python scripts/render_dxf.py plano.dxf [salida.png]` renderiza cualquier DXF a PNG.
- `uv run python scripts/render_model.py plano.dxf [salida.png]` reconstruye el modelo con
  `build_model` y lo renderiza sobre el DXF: muros en azul, vanos en naranja y espacios rellenos
  con nombre y área. Con `--all` hace los casos golden en `tests/output/build_model/` (ignorada
  por git).

**Servidor MCP `archimind-core`** (`archimind_core/server.py`, con el SDK oficial `mcp` 2.x y
`MCPServer`). Son 14 herramientas, todas con `project_path`, que responden con un resumen de
menos de 50 líneas y rutas de archivo. Las que modifican el modelo hacen un commit en el
repositorio del proyecto y responden con el hash de la versión:

- `abrir_proyecto`: crea la carpeta, `modelo.json`, `salidas/`, `.gitignore` y el repositorio
  si faltan, y devuelve el resumen del proyecto.
- `importar_plano(file_path)`: copia el DXF/DWG a `planos/`, lo deja activo y devuelve las capas
  y las unidades detectadas con su evidencia.
- `proponer_mapeo_capas`: rol, confianza y evidencia por capa, con el mapeo listo para aplicar.
- `aplicar_mapeo(mapping, vista=None)`: guarda el mapeo y reconstruye el modelo, con IDs nuevos.
  Si los muros forman varias vistas separadas, no cambia nada y responde con un aviso que lista
  cada vista con su extensión; se repite con `vista` = el número de la planta.
- `confirmar_escala(muro_id=None, longitud_real=None)`: sin argumentos confirma las unidades
  detectadas; con argumentos recalcula la escala.
- `definir_alturas(por_nivel=None, por_espacio=None)`: las alturas que da el usuario. Por nivel,
  confirma la altura del nivel; por espacio, la pone en los muros que lo delimitan (un muro entre
  espacios de alturas distintas, la pedida o la del nivel confirmado, toma la mayor, con aviso).
  Si un vano quedaría más alto que su muro, no aplica nada.
- `validar_modelo` y `listar_modelo(que)`: `"espacios"` o `"vanos"` (con el bloque de cada vano).
- `cuadro_de_areas`: con la escala confirmada, además escribe `salidas/cuadro_de_areas.csv`.
- `comparar_versiones(version_a, version_b)`: hashes o referencias como `HEAD~1`.
- `exportar_plano(formato="dxf", version_dwg="R2018", espesor_losa=None)`: `"png"` →
  `salidas/vista.png`; `"dxf"` → `salidas/<proyecto>.dxf`; `"dwg"` → `salidas/<proyecto>.dwg`
  (R2013 o R2018) con el DXF al lado, mediante ODA File Converter; `"3dm"` →
  `salidas/<proyecto>-3d.3dm`, el modelo 3D (sin pisar el `.3dm` del puente con Rhino). Si
  faltan alturas, el 3D no escribe nada y responde qué niveles y muros no la tienen, para
  pedírselas al usuario. Si el servidor corre en remoto, con la variable de entorno
  `ARCHIMIND_REMOTO=1`, el DWG queda deshabilitado con un mensaje que ofrece el DXF.
- `asignar_bloques(borrador="salidas/borrador_bloques.json")`: guarda en el modelo la
  carpintería que propuso `archimind-bloques`.
- `aplicar_borrador(borrador="salidas/borrador_rhino.json")`: guarda en el modelo lo editado en
  Rhino (el `EditsDraft` de `leer_cambios`) y lo renombra a `borrador_rhino.aplicado.json`.
  Responde con lo editado, lo nuevo (`ref` → ID), los renombrados, los espacios cuya área cambió
  (antes → después), los avisos nuevos y la versión. Si el modelo cambió desde la lectura o
  quedaría con errores de `validate`, no aplica nada y los explica.
- `proponer_cortes`: 2 o 3 líneas de corte con nombre, `longitudinal` (A-A) y `transversal`
  (B-B), paralelas a los lados del rectángulo mínimo que encierra los muros, y `escalera` (C-C)
  si un espacio se llama así (el schema no tiene escaleras). De las posiciones del 60 % central
  descarta las que corren a lo largo de un muro y elige la que corta más vanos. Responde qué
  espacios cruza y qué vanos corta cada una, sin coordenadas, y las guarda en
  `salidas/cortes.json` (`CutProposals`) para que `corte` de `rhino-bridge` las use por nombre.

El recurso `archimind://proyecto/modelo` resume el último proyecto abierto o usado en la sesión:
plano activo, escala, conteos, áreas, validación y últimas versiones. Toda excepción llega al
cliente como `ToolError`: los errores previstos con su mensaje en español, y los imprevistos con
la etapa de la reconstrucción en que fallaron (lectura del plano, vistas, muros, vanos, espacios
o validación), la entidad o el muro si se sabe, y el traceback en el registro (stderr). Las pruebas de integración
(`tests/integration/`) llaman a cada herramienta en proceso con un cliente MCP en memoria, y
una más arranca el servidor por stdio.

La lógica de `core`:

- **`read_drawing(path)`** abre un DXF con ezdxf, o un DWG mediante ODA File Converter si está
  instalado; si no, `DrawingError` explica cómo instalarlo o exportar a DXF. Devuelve un
  `Drawing` con el documento y sus unidades.
- **Unidades**: se toman de `$INSUNITS` (escala confirmada). Si faltan, se infieren entre m, cm
  y mm por los tramos que miden un espesor de muro habitual (un tramo de 150 sugiere mm) y por
  el tamaño del plano; la escala queda no confirmada y la evidencia se explica.
- **`layer_inventory(drawing)`**: por capa, cantidad de entidades por tipo, longitud total de
  líneas y polilíneas en metros (preliminar si la escala no está confirmada), bloques
  insertados y hasta 5 textos de ejemplo. Solo el espacio modelo; los bloques anidados se
  explotan como entidades virtuales sin tocar el documento, y lo que está en la capa "0" de un
  bloque cuenta en la capa del INSERT.
- **`propose_mapping(drawing)`**: por capa, un rol (`walls`, `doors`, `windows`, `text`,
  `dimensions`, `axes`, `furniture`, `ignore` o `mixed`), una confianza entre 0 y 1 y la
  evidencia en una frase. Combina el nombre (patrones en español e inglés: MURO, WALL, PUERTA,
  DOOR, VENTANA, WIN, COTA, DIM…) con la geometría en metros: pares de tramos paralelos a un
  espesor de muro habitual, arcos de 90° con su hoja, ventanas de tres líneas paralelas, textos,
  cotas e INSERT con nombre de puerta, ventana o mueble. Si dos roles explican una parte
  importante de la capa, es `mixed`; si el nombre y la geometría se contradicen, gana la
  geometría con menos confianza. Las reglas y umbrales están en
  `packages/core/config/layer_rules.yaml` (fuera de `src/`: vale en el workspace, no en un
  wheel); `load_rules(ruta)` carga otras.
- **Carpeta del proyecto**: `modelo.json`, los planos importados en `planos/`, las salidas
  regenerables en `salidas/` (fuera de git) y su propio repositorio git. `open_project(ruta)`
  crea lo que falte. `import_drawing(ruta, plano)` lee el plano, lo copia a `planos/` y lo deja
  como plano activo (el último de `source_files`); un plano ilegible no deja rastro.
  `active_drawing(ruta)` lee el plano activo.
- **Historial** con git: `commit(carpeta, mensaje)` versiona `modelo.json`, `planos/` y
  `.gitignore` firmando como ArchiMind y devuelve el hash corto, o `None` si no cambió nada.
  `recent_versions(carpeta)` y `load_version(carpeta, "HEAD~1")` leen las versiones anteriores.
- **`apply_edits(project, draft)`** aplica un `EditsDraft` sobre una copia: valores nuevos de
  muros, vanos y espacios, borrados (los vanos de un muro borrado también), IDs inéditos para lo
  nuevo y los bloques sin uso retirados; valida y, con algún error, lanza `EditsError` sin
  cambiar nada. `apply_edits_draft(project_path, ruta)` además rechaza el borrador si el SHA-256
  de `modelo.json` no es su `base_sha256`, guarda y lo marca como aplicado.
- **`recompute_spaces(project, rules, edited)`**: si el borrador cambia muros, los espacios se
  recalculan desde ellos (huellas con las esquinas en L rellenas y los vanos tapados, como al
  importar). Cada cara hereda ID, nombre y categoría del espacio con el que comparte más área
  (al menos la mitad de la menor de las dos) y conserva su contorno si no cambió; las caras sin
  espacio son «Espacio sin nombre N» y los espacios sin cara se quitan, con un aviso que dice si
  se unieron a otro.
- **`apply_mapping(project_path, drawing, mapping)`** valida los roles y las capas, reconstruye
  el modelo del proyecto con `build_model` y lo guarda; si el mapeo no es válido, no escribe
  nada. La reconstrucción conserva el nombre, las fuentes y los contadores de IDs: los muros,
  vanos y espacios reciben IDs nuevos, nunca uno retirado, y la escala vuelve a ser la del plano.
  `proposals_to_mapping` convierte la propuesta en mapeo.
- **`build_model(drawing, mapping, base=None, view=None)`** reconstruye el modelo y devuelve un
  `BuildResult` con el `Project` y sus problemas (los avisos de la reconstrucción más los de
  `validate`). No escribe nada. Con `base`, el modelo conserva el id, el nombre, las fuentes y
  los contadores de IDs de ese proyecto. Un fallo imprevisto sale como `BuildStageError`.
  - Vistas: los tramos de muro separados más de `view_gap_m` (8 m) forman vistas distintas, como
    una planta y un alzado lado a lado. Con más de una, sin `view` lanza `ViewChoiceNeeded` con
    la lista; con `view` solo se lee esa vista, con el aviso `vista_elegida`.
  - Limpieza: los tramos repetidos y los de longitud cero se descartan, los arcos (también los
    bulges de las polilíneas) se aproximan con tramos rectos a 1 mm, y un contorno que se corta
    a sí mismo se repara con `make_valid`. Los sombreados (HATCH) de las capas de muros no se
    usan y se avisan con su cantidad (`sombreado_en_capa_de_muros`).
  - Muros: las líneas de muro que cierran anillos forman el material; dos caras paralelas
    separadas entre 0.05 y 0.50 m con material entre ambas dan un tramo (eje a media distancia,
    espesor medido sin redondear). Los tramos colineales de igual espesor se unen a través de
    las uniones y de los huecos, y cada extremo se lleva al eje del muro con el que forma una L
    o una T, a cualquier ángulo; un tramo que cabe entero en la huella de otro muro (como las
    hiladas de una pilastra) se descarta. También lee polilíneas de eje con ancho constante; las líneas
    abiertas sin ancho se avisan.
  - Vanos: cada hueco del muro con su símbolo de puerta o ventana encima (líneas o bloque), con
    offset y ancho medidos. Sin símbolo es un vano `void` con aviso; más largo de 3 m sin
    símbolo, separa el muro en dos. Un bloque sobre un muro sin hueco crea el vano con aviso;
    una puerta de líneas sin hueco solo se avisa.
  - Espacios: el material más los vanos tapados se poligoniza; las caras que no son muro son
    espacios, con el nombre del texto que cae dentro (sin texto o con varios, aviso).
  - Lo que un plano 2D no transmite (nivel, alturas de vano, categoría) sale de
    `packages/core/config/build_rules.yaml`, con los umbrales, y se declara en el aviso
    `valores_por_defecto`.

- **Alturas**: `define_heights(project, by_level, by_space)` devuelve una copia con las alturas
  aplicadas, o lanza `HeightsError` sin cambiar nada. Un muro delimita un espacio si comparten un
  borde de más de 5 cm. `missing_heights(project)` lista, por nivel sin confirmar, los muros sin
  altura propia.
- **Escala**: `confirm_scale(project)` confirma las unidades con las que se leyó el plano.
  `confirm_scale(project, muro_id, longitud_real)` escala el modelo para que el eje de ese muro
  mida `longitud_real` metros, y también la confirma. `rescale(project, k)` multiplica lo
  medido en el plano (ejes, espesores, offsets y anchos de vano, espacios, anotaciones) y deja
  las alturas, los antepechos y las elevaciones, que salen de `build_rules.yaml`. Una
  reconstrucción con `apply_mapping` vuelve a la escala del plano.
- **Cantidades**, todas calculadas con la geometría del modelo. Si la escala no está confirmada,
  cada resultado lleva `preliminary` y la etiqueta «PRELIMINAR: escala sin confirmar».
  - `area_table(project)`: por espacio, nombre, categoría y área; totales de área útil (todos
    los espacios menos los balcones), área construida (el contorno exterior de esos espacios y
    de los muros, con las esquinas en L rellenas y los patios incluidos) y área de balcones,
    aparte. `export_area_table_csv(tabla, ruta)` la escribe en CSV (UTF-8 con BOM); con la
    escala sin confirmar lanza `QuantitiesError` y no escribe nada.
  - `wall_quantities(project)`: metros lineales de eje por espesor medido (redondeado al mm, sin
    llevarlo a los habituales), vanos incluidos.
  - `opening_counts(project)`: cantidad de vanos por tipo, ancho y alto.
- **`render_model(project, png)`** dibuja la planta del modelo en metros: espacios rellenos con
  su nombre y su área, muros en azul y vanos en naranja, y la marca PRELIMINAR si la escala no
  está confirmada. `draw_model(ax, project, k)` hace el mismo dibujo sobre unos ejes ya creados
  (lo usa `scripts/render_model.py` encima del DXF).
- **`export_dxf(project, ruta)`** escribe un DXF R2010 en metros: los muros como el contorno de
  su material con los vanos recortados (`A-MURO`), los vanos (`A-PUERTA`, `A-VENTANA`,
  `A-VANO`), los espacios (`A-ESPACIO`), sus nombres (`A-TEXTO`) y sus áreas (`A-AREA`). Con la
  escala sin confirmar lanza `ExportError` y no escribe nada. Al volver a importarlo con
  `build_model` sale el mismo modelo.
- **`export_dwg(project, ruta, version="R2018")`** escribe ese DXF junto a la ruta y lo convierte
  a DWG R2013 o R2018 con ODA File Converter. Sin la escala confirmada o sin ODA instalado lanza
  `ExportError` y no escribe nada; el mensaje explica cómo instalarlo y ofrece el DXF. La prueba
  de ida y vuelta (mismas entidades y longitudes por capa que el DXF) se omite si ODA no está.
- **`build_3d(project, ruta, espesor_losa)`** escribe un .3dm en metros con rhino3dm, sin
  operaciones booleanas: cada muro, por tramos a lo largo del eje, en machones de altura completa
  entre los vanos, un dintel sobre cada vano que no llega arriba y un antepecho bajo cada vano
  con antepecho; cada nivel, una losa de piso bajo su cota con el contorno de sus espacios y sus
  muros (esquinas en L rellenas; lo encerrado sin espacio es un hueco). Cada pieza es una
  extrusión cerrada: la banda de un tramo recto del eje, con ingletes en los quiebres, cortada en
  perpendicular, así que las piezas de un muro llenan su huella sin solapes. Capas Machones,
  Dinteles, Antepechos y Losas; el user string `archimind_id` es el muro, el vano o el nivel.
  La altura de un muro es la suya o la de su nivel; si es la de un nivel sin confirmar, lanza
  `HeightsMissing` con la lista. Sin la escala confirmada o con errores de `validate`, lanza
  `ExportError`. En ningún caso escribe nada. `wall_pieces` y `slab_pieces` dan las piezas sin
  rhino3dm. El espesor de losa por defecto (0.15 m) está en `build_rules.yaml`
  (`slab_thickness_m`). La prueba de propiedades comprueba que el volumen de un muro es
  longitud × espesor × altura menos sus vanos (± 0.5 %), y la de `test_build_3d.py` deja una
  axonometría en `tests/output/build_3d/`; `packages/core/PRUEBA_MANUAL.md` explica cómo
  revisar el .3dm en Rhino.
- **`assign_blocks(project, draft)`** aplica un `BlocksDraft`: comprueba todo antes de cambiar
  nada (que cada vano exista, sea del tipo del bloque —un vano sin tipo adopta el del bloque— y
  mida lo mismo ± 1 mm; si no, el modelo cambió desde el borrador y hay que repetirlo), pone a
  cada bloque nuevo un `blq-` inédito, reutiliza el de un bloque con el mismo nombre y quita los
  que quedan sin uso. `apply_block_draft(carpeta, ruta)` lo lee de la carpeta y guarda el modelo.
  Una reconstrucción con `apply_mapping` deja el modelo sin bloques (los IDs quedan retirados).
- **`compare_versions(model_a, model_b)`** empareja por ID las dos versiones y devuelve los
  espacios cuya área cambia más de 0.5 %, los muros añadidos, eliminados y movidos (eje o
  espesor distinto en más de 0.001 m) y los vanos modificados (muro, tipo, bloque, lado del
  bloque o cualquier medida). Es preliminar si alguna de las dos versiones no tiene la escala confirmada.

En `schema`, `layer_mapping` solo admite esos nueve roles (`LayerRole`).

**Servidor MCP `archimind-bloques`** (`archimind_bloques/server.py`). Son 5 herramientas que
responden con un resumen de menos de 50 líneas y rutas de archivo; nunca escriben el modelo. Las
descripciones explican el esquema con un ejemplo («ventana corrediza de aluminio de 3 hojas de
2.40 × 1.50» → `tipo="sliding_window"`, `parametros={"width": 2.40, "height": 1.50, "leaves": 3,
"material": "aluminio"}`) y piden no inventar medidas: lo que falta sale del vano o del catálogo.

- `listar_catalogo` y `agregar_al_catalogo(clave, perfil)`: el catálogo es único, así que no
  reciben `project_path`.
- `crear_bloque(project_path, tipo, parametros, formatos)`: un bloque suelto en
  `salidas/bloques/` (dxf, svg, png, 3dm).
- `ajustar_bloque_a_vano(project_path, vano_id, preferencias)`: la carpintería de un vano con el
  porqué de cada elección, sin escribir nada.
- `insertar_bloques_en_plano(project_path, asignaciones)`: el DXF con la carpintería y el
  borrador para `asignar_bloques` de core.

**Generadores de carpintería** en `packages/bloques`, deterministas y sin LLM:

- **Tipos**: puerta batiente, batiente doble y corrediza; ventana corrediza de 2 a 4 hojas, fija
  y proyectante. Cada uno es un modelo Pydantic (`SwingDoor`, `DoubleSwingDoor`, `SlidingDoor`,
  `SlidingWindow`, `FixedWindow`, `AwningWindow`; la unión es `CarpentryParams`). Todos llevan
  el ancho, el alto y el espesor de muro del vano y el perfil del catálogo. Según el tipo,
  además:
  - el espesor de hoja;
  - la mano (`left`/`right`, mirando desde el lado hacia el que se mueve la hoja, EN 12519);
  - la apertura o la cara del muro (`in`/`out`);
  - el antepecho y el número de hojas.

  Las combinaciones imposibles se rechazan con un mensaje que da la medida resultante, el
  límite del perfil y la salida: el ancho o el alto mínimo o máximo, menos o más hojas, u otro
  perfil.
- **Catálogo**: `packages/bloques/catalog.yaml`, con valores de ejemplo que hay que completar con
  medidas reales. Por perfil da el material, los tipos que admite, el marco y la hoja (ancho visto
  y fondo), el traslape, el vidrio y los límites de la hoja. En `defaults`, las medidas de lo que
  un pedido no dice: espesor de muro y antepecho de un bloque suelto, y alto de puerta y de
  ventana. `load_catalog(ruta)` lo valida; `add_profile(ruta, clave, perfil)` agrega un perfil al
  final del archivo (`profiles` es la última sección) conservando los comentarios, o lo deja
  intacto si la clave ya existe.
- **`generate(params)`** devuelve un `Carpentry`:
  - la planta y el alzado como trazos con su pluma (cortado, visto, fino u oculto);
  - las piezas macizas del marco y las hojas, y los vidrios.

  El bloque tiene el origen en el borde del vano sobre el eje del muro, x a lo largo del muro e
  +y adentro. El marco va centrado en el eje. El alzado se ve desde afuera, con el origen en el
  piso. El nombre es determinista: `PUERTA-BATIENTE-900x2100-IZQ-ADENTRO-<resumen>`.
- **Pedidos → parámetros** (`resolve.py`): prueba los tipos en orden y, para cada uno, los
  perfiles en el orden del catálogo (el de preferencia), filtrados por clave o material; en la
  corrediza sin número de hojas, de 2 a 4. Devuelve la primera combinación válida con notas de lo
  elegido, o un `FitError` con el motivo de cada intento.
  - `create_block(tipo, BlockRequest, catálogo)`: un bloque suelto. Solo el ancho es
    obligatorio: el alto, el muro y el antepecho salen de `defaults`, el espesor de hoja del
    fondo de hoja del perfil, y la mano y la apertura son `left` e `in`. Una opción que no es del
    tipo (p. ej. hojas en una puerta) se rechaza.
  - `fit_to_opening(proyecto, vano_id, Preferences, catálogo)`: la carpintería de un vano del
    modelo, con su ancho, alto y antepecho tal cual y el espesor de su muro. Sin tipo, puerta
    batiente (si no calza, doble) o ventana corrediza (si no, proyectante y si no, fija); un vano
    sin tipo exige uno. Con la escala sin confirmar, la nota PRELIMINAR.
- **El vano en su muro** (`site.py`): el lado de adentro es el recinto pedido (`opens_into`), el
  único recinto en un muro exterior o, entre dos, el que no es circulación (categoría o nombre:
  pasillo, hall, corredor…) y si no el más pequeño; sin recintos, la izquierda del eje, con aviso.
  La mano por defecto mira la cara hacia la que abre la hoja: las bisagras van hacia el muro más
  cercano que la corta (en L o en T) o hacia el extremo del muro; la corrediza corre hacia el lado
  con más muro libre. El bloque se inserta sin espejar: con adentro a la izquierda del eje, en el
  inicio del vano con el ángulo del eje; a la derecha, en el final y girado 180°.
- **`insert_blocks(carpeta, asignaciones, catálogo)`** parte del plano que exporta core
  (`salidas/<proyecto>.dxf`) y exige la escala confirmada. `asignaciones` va por vano; sin ellas,
  los vanos de puerta y ventana que aún no tienen bloque. Por cada vano con carpintería —la nueva
  y la que el modelo ya tenía, regenerada desde sus parámetros— quita el rectángulo del vano y
  pone el INSERT del bloque de planta, rotado y en la capa de su tipo; cada bloque se define una
  vez. Escribe `salidas/<proyecto>-carpinteria.dxf` y, con carpintería nueva,
  `salidas/borrador_bloques.json` para `asignar_bloques`. Si un vano no calza o el plano no
  coincide con el modelo, no escribe nada; un bloque del modelo que ya no mide lo que su vano se
  deja fuera con aviso.
- **Salidas**:
  - `export_dxf`: un R2010 en metros con el BLOCK de la planta y el `<nombre>-ALZADO`. Las
    entidades van en la capa 0 con color BYBLOCK y grosor fijo, insertadas en A-PUERTA o
    A-VENTANA y en A-ALZADO. `add_plan_block(doc, carpentry)` define el de la planta en otro
    documento.
  - `export_svg`: a 1:20, con los grosores reales en mm.
  - `export_3dm`: con rhino3dm; las piezas son extrusiones en las capas Marco y Hoja, y los
    vidrios, superficies en la capa Vidrio.
  - `render_png`: para revisión visual.
- `tests/pedidos_bloques.yaml`: 20 pedidos en lenguaje natural con la herramienta, los argumentos
  y lo que debe resultar. `tests/integration/test_pedidos_bloques.py` los llama por MCP con el
  `catalog.yaml` real (una copia): si se cambia el catálogo y un pedido deja de calzar, avisa.
- `uv run python scripts/render_dxf.py <proyecto>/salidas/<proyecto>-carpinteria.dxf` renderiza
  el plano con la carpintería a PNG.
- `uv run --package archimind-bloques pytest packages/bloques/tests/test_block_png.py` deja el
  PNG, el DXF, el SVG y el .3dm de cada tipo en `tests/output/bloques/`.
  `packages/bloques/PRUEBA_MANUAL.md` explica cómo revisarlos en Rhino y AutoCAD.

**Puente con Rhino 8** (`bridges/rhino`):

- `plugin/archimind_bridge.py`, un script de Python 3.9 para el editor de scripts de Rhino 8, solo
  con la biblioteca estándar y RhinoCommon. Arranca un servidor HTTP en `127.0.0.1` en un hilo
  secundario, con el puerto y un token compartido en `~/.archimind/rhino_bridge.json` (lo crea la
  primera vez; la variable `ARCHIMIND_RHINO_BRIDGE` da otra ruta). Seis operaciones fijas
  (`ping`, `open_file`, `load_model_layers`, `read_tagged_objects`, `save_as` y
  `hidden_lines`), sin ejecutar código; cada una corre en el hilo de la interfaz con `RhinoApp.InvokeOnUiThread` y se niega si
  Rhino está en medio de un comando. Las coordenadas viajan en metros y se convierten a las
  unidades del documento. Volver a ejecutar el script lo reinicia.
- En Rhino, el modelo va en `ArchiMind::Muros` (cada muro, su huella extruida con su altura),
  `ArchiMind::Vanos` (una caja en cada hueco, sin restarla del muro) y `ArchiMind::Espacios`
  (superficies a la cota del nivel, con el nombre del espacio como nombre del objeto). Cada
  objeto lleva su ID en el user string `archimind_id`, y el documento guarda el `modelo.json`
  con el que se cargó.
- `hidden_lines` arma en memoria, sin tocar el documento, los prismas que recibe (en metros, con
  huecos) y calcula con `HiddenLineDrawing` de RhinoCommon, en una vista paralela y con planos de
  recorte opcionales, los segmentos visibles, ocultos y cortados (`SilhouetteType.SectionCut`),
  como polilíneas 2D.
- **Servidor MCP `rhino-bridge`** (paquete `archimind-rhino-bridge` en `bridges/rhino/mcp`), con 6
  herramientas que reciben `project_path`. Si el puente no responde: «Rhino no está abierto o el
  puente no está iniciado; ejecuta <ruta del script> desde el editor de scripts».
  - `estado_rhino`: Rhino, el documento, si es del proyecto y si el modelo cambió desde la carga.
  - `abrir_en_rhino(descartar_cambios=False)`: abre `salidas/<proyecto>.3dm` (lo crea en metros
    con rhino3dm si no existe). Si el modelo no cambió desde la última carga, conserva lo editado;
    si cambió, recarga las capas ArchiMind y guarda. Si hay ediciones sin leer y el modelo
    cambió, se niega salvo `descartar_cambios=True`, o salvo que esas ediciones sean las que core
    ya aplicó (`salidas/borrador_rhino.aplicado.json`). Nunca abre encima de un documento con
    cambios sin guardar.
  - `leer_cambios`: compara Rhino con el modelo cargado (no con el actual) y escribe
    `salidas/borrador_rhino.json` (`EditsDraft`): muros rectos movidos, girados, estirados o con
    otro espesor o alto (de la huella rectangular), vanos desplazados o con otra medida en su
    muro, espacios con otro contorno o renombrados (el nombre del objeto), lo borrado (con un
    muro, sus vanos) y lo dibujado sin `archimind_id` en las subcapas ArchiMind: muros nuevos
    (prismas rectangulares a la cota de un nivel), vanos nuevos sin tipo en el muro recto,
    existente o nuevo, sobre el que caen, y espacios nuevos con el nombre del objeto. Avisa de
    las copias, los sólidos que ya no son prismas rectangulares, lo nuevo que no se puede leer y
    los muros de varios tramos; nada de eso entra. Si los cambios son los que core ya aplicó, no
    escribe borrador.
  - `guardar_3dm`: guarda el documento del proyecto en `salidas/<proyecto>.3dm`.
  - `make2d_axonometria(vista="iso_so", explotada=False, separacion=None, espesor_losa=None)`:
    isométrica de líneas ocultas desde `iso_ne`, `iso_no`, `iso_se` o `iso_so` (Y+ es el norte)
    de las piezas del 3D de core (`model_pieces`: machones, dinteles, antepechos y losas, con los
    vanos abiertos), tomadas de `modelo.json`. Las visibles van en la capa VISIBLES y las ocultas
    en OCULTAS, a trazos. Explotada: cada nivel sube `separacion` sobre el anterior y sus muros,
    `separacion` sobre su losa (por defecto, 1 m de `estilos.yaml`). Escribe
    `salidas/axonometria-<vista>[-explotada].dxf` (metros) y `.svg` (1:50). Necesita la escala
    confirmada y las alturas: si faltan, no dibuja y responde cuáles, como `exportar_plano`.
  - `corte(linea_de_corte, mirando, profundidad=None, espesor_losa=None)`: `linea_de_corte` es
    el nombre de un corte de `proponer_cortes` (leído de `salidas/cortes.json`; avisa si el
    modelo cambió desde la propuesta) o dos puntos en metros. Mira en horizontal hacia la
    `izquierda` o la `derecha` del recorrido y recorta con dos planos: el de la línea y el del
    fondo, a `profundidad` (por defecto, hasta el punto más lejano del edificio de ese lado). Lo
    cortado va en la capa CORTADO (0.50 mm) y lo que se ve detrás en PROYECTADO (0.18 mm), en
    `salidas/corte-<nombre>.dxf` y `.svg` (`corte.dxf` con puntos). El dibujo empieza en el
    origen: y = 0 es la cara inferior de la losa.
- **Estilos** en `bridges/rhino/mcp/config/estilos.yaml`: grosor (un lineweight estándar de
  DXF), color y tipo de línea de cada capa (VISIBLES 0.25 mm, OCULTAS 0.13 mm a trazos,
  CORTADO 0.50 mm y PROYECTADO 0.18 mm), la escala de los tipos de línea, la del SVG y la
  separación de la explosión.
- Las pruebas usan un documento de Rhino falso (`bridges/rhino/mcp/tests/fake_rhino.py`) detrás
  del servidor HTTP real del script; lo que depende de RhinoCommon está en
  `bridges/rhino/PRUEBA_MANUAL.md`.

**Documentos** (`packages/docs`):

- Base SQLite del usuario, `archimind.sqlite3`, en su carpeta de datos (en Windows,
  `%LOCALAPPDATA%\ArchiMind`; `ARCHIMIND_DATOS` da otra). Tiene cuatro tablas: `materials`
  (código, norma, descripción, unidad), `unit_prices` (APU: código, descripción, unidad,
  precio, fecha y fuente), `area_program` (espacio exigido y área mínima) y `budget_items`
  (partida del modelo → código APU y material).
- `uv run --package archimind-docs archimind-docs-importar <tabla> <archivo.csv>` carga un CSV
  todo o nada: si una fila falla, no carga ninguna y dice cuál y por qué. Acepta coma o punto y
  coma como separador y coma decimal. Las plantillas vacías están en `packages/docs/plantillas/`
  y las columnas, en `packages/docs/README.md`.
- **Partidas del modelo**, cada una con una clave fija que es la de `budget_items`:
  - `muro-<espesor>`, en m² de una cara (longitud × altura menos los vanos; sin cantidad si
    faltan alturas);
  - `puerta-`, `ventana-` y `vano-<ancho>x<alto>`, en unidades;
  - `piso-<categoría>`, en m², sumando las áreas de los espacios de esa categoría.

  Los materiales asignados salen de `budget_items` → `materials` y del perfil de la
  carpintería de cada bloque.
- **Servidor MCP `archimind-docs`** (`archimind_docs/server.py`). Lee el modelo, nunca lo
  escribe, y toma de la base lo que no sale del modelo. Herramientas, todas con `project_path`:
  - `datos_para_memoria`: en JSON, todas las cifras verificadas (niveles, conteos, cuadro de
    áreas, metros de muro por espesor, vanos por medida, partidas y materiales asignados), para
    que Claude redacte la memoria sin inventar números. Lo guarda también en
    `salidas/datos_memoria.json`. Una altura de nivel sin confirmar sale como `null`.
  - `presupuesto_preliminar`: cantidad de cada partida × precio de su APU, con la fecha y la
    fuente de cada precio. Una partida sin cantidad, sin fila en `budget_items`, con un APU
    que no está o en otra unidad (`m²` = `m2`, `und` = `un`…) queda SIN PRECIO con el motivo y
    no suma: no se estima. Escribe `salidas/presupuesto_preliminar.csv` con el total de lo
    que tiene precio.
  - `verificar_programa_areas`: cada fila de `area_program` toma un espacio con ese nombre, sin
    contar mayúsculas, tildes ni el número final; las exigencias mayores eligen primero.
    Responde lo que cumple, lo que no llega (con el faltante), lo que falta y lo que sobra.
  - `calcular_cos_cus(area_lote)`: COS = huella construida del nivel más bajo / lote; CUS =
    área construida de todos los niveles / lote.
  - `generar_ficha_pdf(memoria_texto)`: primero busca cada número de la memoria en
    `datos_para_memoria`. Vale si alguna cifra, redondeada a los decimales escritos, da ese
    número; se aceptan coma o punto decimal y separadores de miles, y también los números de los
    textos de los datos, como nombres y normas. Si alguno no está (un año, una escala, un costo
    inventado), no genera nada y lista cada uno con su contexto. Si todo cuadra, escribe
    `salidas/ficha_<proyecto>.pdf` con reportlab: datos del proyecto, cuadro de áreas, planta
    (`render_model` de core) y memoria, en DejaVu Sans (la fuente de matplotlib) y con la marca
    PRELIMINAR en cada página si la escala no está confirmada.

Siguen pendientes:
- los muros curvos y varios niveles por plano;
- `vision`;
- los puentes con AutoCAD e Illustrator.
