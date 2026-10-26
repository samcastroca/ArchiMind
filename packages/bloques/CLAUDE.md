# archimind-bloques

Servidor MCP `archimind-bloques`. Depende de `archimind-schema`.

- Genera bloques de carpintería (`blq-`) a partir de los vanos del modelo.
- Entrega borradores a core; nunca escribe `modelo.json` directamente. `insert.py` deja
  `salidas/borrador_bloques.json` (`BlocksDraft` de schema) y `asignar_bloques` de core lo aplica.
- Las salidas van a `salidas/` del proyecto.
- Módulos, de los parámetros a la herramienta:
  - `params.py`: los parámetros validados contra el perfil;
  - `doors.py` y `windows.py`: la geometría;
  - `export_dxf.py`, `render.py` (SVG y PNG) y `export_3dm.py`: las salidas;
  - `resolve.py` (pedido → parámetros), `create.py` (bloque suelto), `site.py` (el vano en su
    muro), `fit.py` (`fit_to_opening`) e `insert.py` (`insert_blocks`);
  - `server.py` solo envuelve; los textos de respuesta van en `summaries.py`.
- El ancho y el alto de las hojas (o del paño) son las propiedades `leaf_width` y `leaf_height`
  de los parámetros: la validación y los generadores parten de ellas, sin repetir la fórmula.
- Todo número sale del perfil, del vano o de los parámetros; en el código solo quedan los grosores
  de pluma, las proporciones del dibujo y `PROBE_M` de `site.py`.
- `catalog.yaml` está fuera de `src/` y es del usuario: el orden de los perfiles es el de
  preferencia y `profiles` va al final del archivo, porque `add_profile` agrega ahí. Las pruebas
  usan `tests/catalog_prueba.yaml`, para que cambiar el catálogo real no las rompa; la excepción
  es `tests/integration/test_pedidos_bloques.py`, que comprueba los pedidos de ejemplo contra el
  catálogo real.
- Convenciones del bloque en los docstrings de `geometry.py`, `params.py`, `doors.py`,
  `windows.py` y `site.py`: el origen en el borde del vano sobre el eje, +y adentro, el alzado
  visto desde afuera, la mano según EN 12519 y la inserción sin espejar.
