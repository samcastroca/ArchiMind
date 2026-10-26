# archimind-core

Servidor MCP `archimind-core`. Depende de `archimind-schema`.

- Único escritor de `modelo.json` de un proyecto: valida y aplica los borradores que entregan
  los demás servidores.
- Importa DXF/DWG y lleva la confirmación de escala.
- El estado vive en la carpeta del proyecto (`modelo.json` + `salidas/`), nunca en el servidor.
