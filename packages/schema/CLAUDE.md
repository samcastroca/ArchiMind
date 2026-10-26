# archimind-schema

Modelo semántico (Pydantic v2) y validadores: niveles, muros, vanos, espacios y bloques.

- Es el contrato del monorepo: todos los demás paquetes dependen de él; él no depende de ninguno.
- Define los IDs con prefijo (`niv-`, `muro-`, `vano-`, `esp-`, `blq-`), las unidades (metros)
  y las tolerancias de la raíz.
- Sin I/O ni servidor MCP: solo tipos y validación.
