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
- Toda herramienta recibe `project_path`, salvo `listar_catalogo` y `agregar_al_catalogo` de
  bloques: el catálogo es uno para todos los proyectos.
- Las respuestas son resúmenes y rutas de archivo; las coordenadas se quedan en los archivos.
- Errores con mensajes claros para el usuario final (p. ej., "Rhino no está abierto"), lanzados
  como `ToolError`: es la única excepción cuyo mensaje el SDK hace llegar al cliente.
- Máximo 13 herramientas por servidor (core tiene 14, por decisión del usuario). La lógica vive
  en el paquete; la herramienta es una envoltura delgada.

## Pruebas
- Toda funcionalidad nueva llega con pruebas. Geometría: pruebas de propiedades con hypothesis.
- `tests/golden/<caso>/` contiene entrada y salida esperada. Las salidas esperadas solo se
  regeneran cuando el usuario lo pide.
- Toda salida gráfica se puede renderizar a PNG para revisión visual.

## Comandos
- `uv sync` — instala el workspace completo.
- `uv run pytest` — todas las pruebas.
- `uv run --package <nombre> pytest` — pruebas de un paquete (p. ej. `archimind-core`).
- `uv run ruff check . && uv run mypy packages bridges/rhino/mcp` — lint y tipos.
- `uv run --package archimind-core archimind-core` — arranca el servidor de core por stdio (el
  paquete se llama `archimind-core`, no `core`). El puente con Rhino:
  `uv run --package archimind-rhino-bridge archimind-rhino-bridge`.
- `uv run --package archimind-docs archimind-docs-importar <tabla> <archivo.csv>` — carga un CSV
  en la base de datos del usuario (materiales, APU, programa de áreas, partidas). Para el
  usuario lo envuelve `Importar datos.bat` (`scripts/importar_datos.ps1`).
- `Instalar ArchiMind.bat` (`scripts/instalar.ps1` → `scripts/instalacion.py`) — la instalación
  de doble clic: uv, Git, `uv sync` y la configuración de Claude Desktop. Solo esa configuración:
  `uv run python scripts/instalacion.py --uv <ruta de uv.exe>`. Un servidor nuevo, o uno que
  arranca distinto, se añade a `SERVERS` de `instalacion.py`. Los `.ps1` van en UTF-8 con BOM
  (PowerShell 5.1); una prueba lo exige.

## Forma de trabajo
- Plan antes de cambios grandes. Cambios pequeños, un commit por tarea.
- Documentación al día: si la tarea añade o quita una capacidad, cambia el contrato de `schema`
  o los comandos, ese mismo commit actualiza la sección «Estado» de `docs/referencia-tecnica.md`;
  si además cambia lo que el usuario pide o ve, también `docs/guia-de-uso.md` (o `docs/rhino.md`)
  y, si cambia la instalación, `README.md` y `docs/instalacion-manual.md`. El README y las guías
  son para personas no técnicas: frases de ejemplo en su lenguaje y respuestas reales de
  ArchiMind.
- APIs de ezdxf, rhino3dm, RhinoCommon, AutoCAD e Illustrator: siempre contra su documentación.
  Si hay duda, se dice explícitamente.
- Si una tarea requiere un programa que no se puede ejecutar aquí (Rhino, AutoCAD, Illustrator),
  se escribe un `PRUEBA_MANUAL.md` con los pasos exactos.
