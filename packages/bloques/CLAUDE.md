# archimind-bloques

Servidor MCP `archimind-bloques`. Depende de `archimind-schema`.

- Genera bloques de carpintería (`blq-`) a partir de los vanos del modelo.
- Entrega borradores a core; nunca escribe `modelo.json` directamente.
- Las salidas van a `salidas/` del proyecto.
- Hoy solo existen los generadores (sin servidor):
  - `params.py`: los parámetros validados contra el perfil;
  - `doors.py` y `windows.py`: la geometría;
  - `export_dxf.py`, `render.py` (SVG y PNG) y `export_3dm.py`: las salidas.
- El ancho y el alto de las hojas (o del paño) son las propiedades `leaf_width` y `leaf_height`
  de los parámetros: la validación y los generadores parten de ellas, sin repetir la fórmula.
- Todo número sale del perfil o de los parámetros; en el código solo quedan los grosores de
  pluma y las proporciones del dibujo.
- `catalog.yaml` está fuera de `src/` y es del usuario. Las pruebas usan
  `tests/catalog_prueba.yaml`, para que cambiar el catálogo real no las rompa.
- Convenciones del bloque en los docstrings de `geometry.py`, `params.py`, `doors.py` y
  `windows.py`: el origen en el borde del vano sobre el eje, +y adentro, el alzado visto desde
  afuera y la mano según EN 12519.
