# archimind-docs

Servidor MCP `archimind-docs`. Depende de `archimind-schema` y de `archimind-core` (cantidades
y render de la planta).

- Documentos del proyecto: cifras verificadas para la memoria, presupuesto preliminar, programa
  de áreas, COS/CUS y ficha PDF.
- Lee el modelo; nunca lo escribe. Toda cantidad sale del modelo (funciones de core) y todo
  precio, material o mínimo de área, de la base SQLite del usuario (`database.py`).
- La base es una para todos los proyectos, en la carpeta de datos del usuario
  (`ARCHIMIND_DATOS` en las pruebas). Solo el comando `archimind-docs-importar` la escribe;
  el servidor la lee.
- Las salidas van a `salidas/` del proyecto y se pueden renderizar a PNG.
