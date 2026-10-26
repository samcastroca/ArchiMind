# archimind-schema

Modelo semántico (Pydantic v2) y validadores: niveles, muros, vanos, espacios y bloques.

- Es el contrato del monorepo: todos los demás paquetes dependen de él; él no depende de ninguno.
- Define los IDs con prefijo (`niv-`, `muro-`, `vano-`, `esp-`, `blq-`), las unidades (metros)
  y las tolerancias de la raíz.
- Sin servidor MCP. La única I/O es leer y escribir `modelo.json` de forma atómica
  (`load_project`/`save_project`); core es quien la invoca para escribir.
- Las estrategias hypothesis de prueba viven en `tests/schema_strategies.py` (en el `pythonpath`
  de pytest, así que otros paquetes pueden importarlas).
