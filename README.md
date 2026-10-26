# ArchiMind

Proyecto personal para procesar planos arquitectónicos con IA. Importa DXF/DWG e imágenes a un
modelo semántico (niveles, muros, vanos, espacios) y genera cuadros de áreas, bloques de
carpintería, axonometrías y cortes, todo a través de servidores MCP usados desde Claude Desktop.

Es un workspace de [uv](https://docs.astral.sh/uv/) con Python >= 3.11. Para instalarlo y
probarlo: `uv sync` y luego `uv run pytest`. Arquitectura, reglas y comandos en [CLAUDE.md](CLAUDE.md).

## Estado

Está implementado `packages/schema`, el contrato del que dependen los demás paquetes, y la
importación de planos en `packages/core`. `schema`:

- **Modelo semántico** (Pydantic v2): proyecto, niveles, muros, vanos, espacios y anotaciones, en
  metros. Pydantic comprueba la forma y los tipos.
- **IDs inéditos** con prefijo (`niv-`, `muro-`, `vano-`, `esp-`, `blq-`): `new_id` usa un contador
  por prefijo que solo avanza y se guarda con el modelo.
- **Geometría derivada** con shapely: longitud y huella de muros, área de espacios y altura
  efectiva de muros.
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
  continuo de eje, sin partir en las uniones en T.
- `uv run python scripts/render_dxf.py plano.dxf [salida.png]` renderiza cualquier DXF a PNG.

`core` (por ahora solo la lógica, sin servidor MCP ni reconstrucción de muros):

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

Siguen pendientes la reconstrucción de muros y el servidor MCP de `core`, `bloques`, `docs`,
`vision` y los puentes con Rhino, AutoCAD e Illustrator.
