# Puente con Rhino 8

Lleva el modelo de un proyecto de ArchiMind a Rhino 8 y lee lo que se editó allí.

- `plugin/archimind_bridge.py`: script para el editor de scripts de Rhino 8. Arranca un servidor
  HTTP en `127.0.0.1` (puerto y token en `~/.archimind/rhino_bridge.json`, que crea la primera
  vez) con cinco operaciones fijas: `ping`, `open_file`, `load_model_layers`,
  `read_tagged_objects` y `save_as`. Todo lo que toca el documento corre en el hilo de la
  interfaz de Rhino.
- `mcp/`: el servidor MCP `rhino-bridge` (paquete `archimind-rhino-bridge`) con `estado_rhino`,
  `abrir_en_rhino`, `leer_cambios` y `guardar_3dm`.

Para iniciarlo: en Rhino, `ScriptEditor` → abrir `plugin/archimind_bridge.py` → Ejecutar (F5).
La configuración de Claude Desktop y la prueba completa están en
[PRUEBA_MANUAL.md](PRUEBA_MANUAL.md).
