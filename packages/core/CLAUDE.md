# archimind-core

Servidor MCP `archimind-core`. Depende de `archimind-schema`.

- Único escritor de `modelo.json` de un proyecto: valida y aplica los borradores que entregan
  los demás servidores.
- Importa DXF/DWG y lleva la confirmación de escala.
- El estado vive en la carpeta del proyecto, nunca en el servidor: `modelo.json`, `planos/` y
  `.gitignore` en su propio repositorio git, y `salidas/` fuera de git. Toda herramienta que
  modifica el modelo termina con `history.commit`. La única memoria del servidor es qué proyecto
  resume el recurso `archimind://proyecto/modelo`.
- `server.py` solo envuelve: la lógica va en los módulos del paquete y los textos de respuesta
  en `summaries.py`. Ya tiene 13 herramientas, el máximo: una capacidad nueva amplía una
  herramienta existente o va a otro servidor.
