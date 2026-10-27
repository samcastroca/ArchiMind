# Puente con Rhino 8

Dos mitades que hablan por HTTP local: `plugin/archimind_bridge.py` corre dentro de Rhino y
`mcp/` (paquete `archimind-rhino-bridge`, servidor `rhino-bridge`) corre en el workspace.

- El script es **un solo archivo en Python 3.9** (el CPython de Rhino 8), solo stdlib +
  RhinoCommon: así se abre y ejecuta tal cual en el ScriptEditor, sin `sys.path` ni la caché de
  módulos de Rhino. ruff lo lint con `py39` y una prueba lo parsea con `feature_version=(3, 9)`.
- Su primera mitad (configuración, HTTP, espera al hilo de la interfaz, validación) no importa
  Rhino y tiene pruebas; la parte RhinoCommon (`RhinoOps`) es delgada y se prueba a mano con
  `PRUEBA_MANUAL.md`. Toda lógica que se pueda probar va al lado del servidor MCP, que recibe
  datos crudos (caras como bucles de puntos, en metros).
- Las operaciones son las cinco de `OPS`: una operación nueva se agrega a `OPS`, a `RhinoOps` y a
  `mcp/tests/fake_rhino.py`, que imita a `RhinoOps` para las pruebas.
- RhinoCommon siempre contra su documentación; lo que no se pudo verificar se dice en
  `PRUEBA_MANUAL.md`. En las ops, `RhinoDoc.ActiveDoc` (no `scriptcontext.doc`); los parámetros
  `out` vuelven como tupla.
- Una entidad en Rhino se identifica por el user string `archimind_id`, no por su capa. El .3dm
  guarda el `modelo.json` con el que se cargó: los cambios se leen contra esa base.
- El puente nunca escribe `modelo.json`: entrega `salidas/borrador_rhino.json` (`EditsDraft` de
  schema), que core aplica con `aplicar_borrador` y renombra a `borrador_rhino.aplicado.json`.
