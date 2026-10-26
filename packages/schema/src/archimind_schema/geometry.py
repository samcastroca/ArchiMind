"""Geometría derivada del modelo, calculada con shapely."""

from typing import TYPE_CHECKING

from shapely import LineString, Polygon

if TYPE_CHECKING:
    from archimind_schema.models import Project, Space, Wall


def wall_length(wall: "Wall") -> float:
    return float(LineString(wall.axis).length)


def wall_polygon(wall: "Wall") -> Polygon:
    """Huella del muro: el eje engrosado a cada lado, con extremos planos e ingletes."""
    return LineString(wall.axis).buffer(wall.thickness / 2, cap_style="flat", join_style="mitre")


def space_area(space: "Space") -> float:
    return float(Polygon(space.polygon.exterior, space.polygon.holes).area)


def wall_height(project: "Project", wall: "Wall") -> float:
    """Altura propia del muro o, si no la tiene, la altura por defecto de su nivel."""
    if wall.height is not None:
        return wall.height
    for level in project.levels:
        if level.id == wall.level_id:
            return level.default_height
    raise ValueError(f"el muro {wall.id} apunta al nivel inexistente {wall.level_id}")
