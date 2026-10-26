# ArchiMind

Proyecto personal para procesar planos arquitectónicos con IA. Importa DXF/DWG e imágenes a un
modelo semántico (niveles, muros, vanos, espacios) y genera cuadros de áreas, bloques de
carpintería, axonometrías y cortes, todo a través de servidores MCP usados desde Claude Desktop.

Es un workspace de [uv](https://docs.astral.sh/uv/) con Python >= 3.11. Para instalarlo y
probarlo: `uv sync` y luego `uv run pytest`. Arquitectura, reglas y comandos en [CLAUDE.md](CLAUDE.md).

## Estado

Por ahora solo está implementado `packages/schema`, el contrato del que dependen los demás
paquetes:

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

Siguen pendientes `core`, `bloques`, `docs`, `vision` y los puentes con Rhino, AutoCAD e
Illustrator.
