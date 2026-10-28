"""Exportación del modelo a un DXF limpio, en metros.

Los muros salen como el contorno de su material con los vanos recortados; los vanos, los
espacios, sus nombres y sus áreas, cada uno en su capa. El DXF exportado se vuelve a importar
como el mismo modelo con el mapeo A-MURO walls, A-PUERTA doors, A-VENTANA windows y A-TEXTO
text (las demás capas, ignoradas). proponer_mapeo_capas no lo acierta solo: los rectángulos de
vanos y espacios parecen caras de muro, y la geometría manda sobre el nombre.
"""

from pathlib import Path

import ezdxf
from archimind_schema import Project, opening_polygon, space_area, wall_polygon
from ezdxf import units
from ezdxf.enums import TextEntityAlignment
from ezdxf.layouts import Modelspace
from shapely import Polygon, unary_union
from shapely.geometry.base import BaseGeometry

from archimind_core.quantities import PRELIMINARY_LABEL, corner_patches

WALL_LAYER = "A-MURO"
OPENING_LAYERS = {"door": "A-PUERTA", "window": "A-VENTANA", "void": "A-VANO"}
SPACE_LAYER = "A-ESPACIO"
NAME_LAYER = "A-TEXTO"
AREA_LAYER = "A-AREA"
LAYER_COLORS = {
    WALL_LAYER: 7,
    "A-PUERTA": 3,
    "A-VENTANA": 4,
    "A-VANO": 8,
    SPACE_LAYER: 9,
    NAME_LAYER: 2,
    AREA_LAYER: 2,
}
TEXT_HEIGHT_M = 0.20


class ExportError(Exception):
    """El modelo no se puede exportar; el mensaje está pensado para el usuario final."""


def require_confirmed_scale(project: Project) -> None:
    """Un plano exportado lleva medidas definitivas: sin la escala confirmada, no se exporta."""
    if not project.scale_confirmed:
        raise ExportError(
            f"{PRELIMINARY_LABEL}: confirma la escala con confirmar_escala antes de exportar el "
            "plano."
        )


def export_dxf(project: Project, path: str | Path) -> Path:
    """Escribe el modelo en un DXF R2010 en metros. Se niega si la escala no está confirmada."""
    require_confirmed_scale(project)
    doc = ezdxf.new("R2010", setup=True, units=units.M)
    for name, color in LAYER_COLORS.items():
        doc.layers.add(name, color=color)
    msp = doc.modelspace()

    walls = {wall.id: wall for wall in project.walls}
    openings = [
        (opening, opening_polygon(walls[opening.wall_id], opening))
        for opening in project.openings
        if opening.wall_id in walls
    ]
    material = unary_union(
        [wall_polygon(wall) for wall in project.walls] + corner_patches(project.walls)
    )
    material = material.difference(unary_union([footprint for _, footprint in openings]))
    _add_polygons(msp, material, WALL_LAYER)
    for opening, footprint in openings:
        _add_polygons(msp, footprint, OPENING_LAYERS[opening.kind])

    for space in project.spaces:
        polygon = Polygon(space.polygon.exterior, space.polygon.holes)
        _add_polygons(msp, polygon, SPACE_LAYER)
        point = polygon.representative_point()
        gap = TEXT_HEIGHT_M * 0.75
        msp.add_text(
            space.name, height=TEXT_HEIGHT_M, dxfattribs={"layer": NAME_LAYER}
        ).set_placement((point.x, point.y + gap), align=TextEntityAlignment.MIDDLE_CENTER)
        msp.add_text(
            f"{space_area(space):.2f} m²", height=TEXT_HEIGHT_M, dxfattribs={"layer": AREA_LAYER}
        ).set_placement((point.x, point.y - gap), align=TextEntityAlignment.MIDDLE_CENTER)

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(target)
    return target


def _add_polygons(msp: Modelspace, geometry: BaseGeometry, layer: str) -> None:
    """Cada anillo de cada polígono como una LWPOLYLINE cerrada."""
    for part in getattr(geometry, "geoms", [geometry]):
        if not isinstance(part, Polygon) or part.is_empty:
            continue
        for ring in [part.exterior, *part.interiors]:
            points = list(ring.coords)[:-1]  # cerrada: sin repetir el primer punto
            msp.add_lwpolyline(points, close=True, dxfattribs={"layer": layer})
