# ArchiMind

Proyecto personal para procesar planos arquitectónicos con IA. Importa DXF/DWG e imágenes a un
modelo semántico (niveles, muros, vanos, espacios) y genera cuadros de áreas, bloques de
carpintería, axonometrías y cortes, todo a través de servidores MCP usados desde Claude Desktop.

Es un workspace de [uv](https://docs.astral.sh/uv/) con Python >= 3.11. Para instalarlo y
probarlo: `uv sync` y luego `uv run pytest`. Arquitectura, reglas y comandos en [CLAUDE.md](CLAUDE.md).

## Uso desde Claude Desktop

Hace falta [uv](https://docs.astral.sh/uv/) y [git](https://git-scm.com/downloads) instalados.
Se añade el servidor a `claude_desktop_config.json` (en Windows,
`%APPDATA%\Claude\claude_desktop_config.json`; en macOS,
`~/Library/Application Support/Claude/claude_desktop_config.json`), cambiando la ruta por la
ruta absoluta de este repositorio:

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
    }
  }
}
```

Después hay que reiniciar Claude Desktop. Si no encuentra `uv`, en `command` va su ruta
completa (`where uv` en Windows, `which uv` en macOS). Para probar el servidor sin Claude
Desktop: `uv run --package archimind-core archimind-core` arranca y espera mensajes por stdio.

Flujo de trabajo: abrir_proyecto → importar_plano → proponer_mapeo_capas → aplicar_mapeo →
confirmar_escala → consultas, vista y exportación.

## Estado

Está implementado `packages/schema`, el contrato del que dependen los demás paquetes, y en
`packages/core` la importación de planos con su servidor MCP. `schema`:

- **Modelo semántico** (Pydantic v2): proyecto, niveles, muros, vanos, espacios y anotaciones, en
  metros. Pydantic comprueba la forma y los tipos.
- **IDs inéditos** con prefijo (`niv-`, `muro-`, `vano-`, `esp-`, `blq-`): `new_id` usa un contador
  por prefijo que solo avanza y se guarda con el modelo.
- **Geometría derivada** con shapely: longitud y huella de muros, huella de vanos
  (`opening_polygon`), área de espacios y altura efectiva de muros.
- **Persistencia atómica** de `modelo.json`: `load_project` / `save_project`.
- **`validate(project)`**: devuelve todos los problemas del modelo a la vez, cada uno con código,
  severidad (`error` | `warning`), IDs afectados y mensaje en español. Son errores: IDs repetidos
  o mal formados, referencias a niveles o muros inexistentes, polígonos inválidos, espacios
  superpuestos, vanos fuera del muro o superpuestos y espesor ≤ 0. Son avisos: espesor fuera de
  los habituales, unión abierta (extremo de muro a menos de 5 cm de otro sin tocarlo) y escala no
  confirmada, que marca las cantidades como preliminares.

Casos golden para probar importadores, en `tests/golden/<caso>/` (`input.dxf`, `expected.json` e
`input.png`): `rect_simple`, `apto_2hab`, `apto_capas_caoticas`, `en_l`, `muros_linea_doble` y
`milimetros`. El modelo esperado está escrito a mano en `tests/fixtures/cases.py` y el DXF se
dibuja a partir de él con ezdxf.

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
`MCPServer`). Son 12 herramientas, todas con `project_path`, que responden con un resumen de
menos de 50 líneas y rutas de archivo. Las que modifican el modelo hacen un commit en el
repositorio del proyecto y responden con el hash de la versión:

- `abrir_proyecto`: crea la carpeta, `modelo.json`, `salidas/`, `.gitignore` y el repositorio
  si faltan, y devuelve el resumen del proyecto.
- `importar_plano(file_path)`: copia el DXF/DWG a `planos/`, lo deja activo y devuelve las capas
  y las unidades detectadas con su evidencia.
- `proponer_mapeo_capas`: rol, confianza y evidencia por capa, con el mapeo listo para aplicar.
- `aplicar_mapeo(mapping)`: guarda el mapeo y reconstruye el modelo, con IDs nuevos.
- `confirmar_escala(muro_id=None, longitud_real=None)`: sin argumentos confirma las unidades
  detectadas; con argumentos recalcula la escala.
- `validar_modelo`, `listar_espacios` y `listar_vanos`.
- `cuadro_de_areas`: con la escala confirmada, además escribe `salidas/cuadro_de_areas.csv`.
- `comparar_versiones(version_a, version_b)`: hashes o referencias como `HEAD~1`.
- `renderizar_vista` → `salidas/vista.png`.
- `exportar_dxf` → `salidas/<proyecto>.dxf`.

El recurso `archimind://proyecto/modelo` resume el último proyecto abierto o usado en la sesión:
plano activo, escala, conteos, áreas, validación y últimas versiones. Los errores previstos
llegan al cliente con su mensaje en español (`ToolError`). Las pruebas de integración
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
- **`apply_mapping(project_path, drawing, mapping)`** valida los roles y las capas, reconstruye
  el modelo del proyecto con `build_model` y lo guarda; si el mapeo no es válido, no escribe
  nada. La reconstrucción conserva el nombre, las fuentes y los contadores de IDs: los muros,
  vanos y espacios reciben IDs nuevos, nunca uno retirado, y la escala vuelve a ser la del plano.
  `proposals_to_mapping` convierte la propuesta en mapeo.
- **`build_model(drawing, mapping, base=None)`** reconstruye el modelo y devuelve un
  `BuildResult` con el `Project` y sus problemas (los avisos de la reconstrucción más los de
  `validate`). No escribe nada. Con `base`, el modelo conserva el id, el nombre, las fuentes y
  los contadores de IDs de ese proyecto.
  - Muros: las líneas de muro que cierran anillos forman el material; dos caras paralelas
    separadas entre 0.05 y 0.50 m con material entre ambas dan un tramo (eje a media distancia,
    espesor medido sin redondear). Los tramos colineales de igual espesor se unen a través de
    las uniones y de los huecos, y cada extremo se lleva al eje del muro con el que forma una L
    o una T, a cualquier ángulo. También lee polilíneas de eje con ancho constante; las líneas
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
- **`compare_versions(model_a, model_b)`** empareja por ID las dos versiones y devuelve los
  espacios cuya área cambia más de 0.5 %, los muros añadidos, eliminados y movidos (eje o
  espesor distinto en más de 0.001 m) y los vanos modificados (muro, tipo, bloque o cualquier
  medida). Es preliminar si alguna de las dos versiones no tiene la escala confirmada.

En `schema`, `layer_mapping` solo admite esos nueve roles (`LayerRole`).

Siguen pendientes los muros curvos, varios niveles por plano, `bloques`, `docs`, `vision` y los
puentes con Rhino, AutoCAD e Illustrator.
