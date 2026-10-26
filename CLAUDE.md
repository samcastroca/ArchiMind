# ArchiMind

Monorepo para procesar planos arquitectónicos: importa DXF/DWG e imágenes a un modelo semántico
(niveles, muros, vanos, espacios) y genera cuadros de áreas, bloques de carpintería,
axonometrías y cortes. Se usa mediante servidores MCP desde Claude Desktop. Proyecto personal,
no comercial.

## Arquitectura
- `packages/schema`: modelo semántico (Pydantic v2) y validadores. Es el contrato: todo lo demás
  depende de él.
- `packages/core`: el **único** que escribe el modelo semántico de un proyecto. Los demás
  servidores entregan borradores que core valida y aplica.
- `packages/bloques`, `packages/docs`, `packages/vision`: servidores MCP especializados.
- `bridges/`: plugins dentro de Rhino, AutoCAD e Illustrator, cada uno con su servidor MCP.
- Estado: cada proyecto es una carpeta con `modelo.json` versionado con git y una subcarpeta
  `salidas/`. Los servidores no guardan estado propio: todo vive en la carpeta del proyecto.

## Reglas de dominio (no negociables)
- Unidades internas: metros, siempre. Se convierte al importar y al exportar.
- Tolerancia geométrica por defecto: 0.001 m. Tolerancia angular: 0.5°.
- IDs estables con prefijo: `niv-`, `muro-`, `vano-`, `esp-`, `blq-`. Un ID borrado queda retirado
  para siempre; los nuevos IDs son siempre inéditos.
- Espesores de muro habituales: 0.10, 0.12, 0.15, 0.20, 0.25 m. El snapping es solo una
  sugerencia: las medidas leídas de cotas se conservan intactas.
- Escala explícita: si no está confirmada, el modelo queda marcado como tal y toda cantidad se
  entrega como preliminar. Nunca se asume en silencio.
- Todo número (área, longitud, precio, código normativo) sale del modelo o de una base de datos,
  nunca de un LLM.

## Reglas de los servidores MCP
- SDK oficial de MCP para Python, v2: `from mcp.server import MCPServer`, el antiguo FastMCP
  (`mcp.server.fastmcp` ya no existe). Pruebas en proceso con `async with Client(mcp)`.
- Nombres de herramientas en español y snake_case. Código, clases y variables en inglés.
- Toda herramienta recibe `project_path`.
- Las respuestas son resúmenes y rutas de archivo; las coordenadas se quedan en los archivos.
- Errores con mensajes claros para el usuario final (p. ej., "Rhino no está abierto"), lanzados
  como `ToolError`: es la única excepción cuyo mensaje el SDK hace llegar al cliente.
- Máximo 12 herramientas por servidor. La lógica vive en el paquete; la herramienta es una
  envoltura delgada.

## Pruebas
- Toda funcionalidad nueva llega con pruebas. Geometría: pruebas de propiedades con hypothesis.
- `tests/golden/<caso>/` contiene entrada y salida esperada. Las salidas esperadas solo se
  regeneran cuando el usuario lo pide.
- Toda salida gráfica se puede renderizar a PNG para revisión visual.

## Comandos
- `uv sync` — instala el workspace completo.
- `uv run pytest` — todas las pruebas.
- `uv run --package <nombre> pytest` — pruebas de un paquete (p. ej. `archimind-core`).
- `uv run ruff check . && uv run mypy packages` — lint y tipos.
- `uv run --package archimind-core archimind-core` — arranca el servidor de core por stdio (el
  paquete se llama `archimind-core`, no `core`).

## Forma de trabajo
- Plan antes de cambios grandes. Cambios pequeños, un commit por tarea.
- README al día: si la tarea añade o quita una capacidad, cambia el contrato de `schema` o los
  comandos, ese mismo commit actualiza la sección «Estado» de `README.md`.
- APIs de ezdxf, rhino3dm, RhinoCommon, AutoCAD e Illustrator: siempre contra su documentación.
  Si hay duda, se dice explícitamente.
- Si una tarea requiere un programa que no se puede ejecutar aquí (Rhino, AutoCAD, Illustrator),
  se escribe un `PRUEBA_MANUAL.md` con los pasos exactos.
