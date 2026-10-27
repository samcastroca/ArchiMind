"""El modelo como objetos para las capas ArchiMind:: de Rhino, en metros.

Un muro es un prisma: su huella (`wall_polygon`) extruida desde la cota de su nivel con su altura.
Un vano es la caja que ocupa el hueco: su huella (`opening_polygon`) desde el antepecho con su
alto, sin restarla del muro. Un espacio es una superficie plana a la cota de su nivel.
"""

from typing import Any

from archimind_schema import Project, opening_polygon, wall_height, wall_polygon
from shapely import Polygon

# Capa de cada tipo de entidad, por el prefijo de su ID.
LAYERS = {"muro": "Muros", "vano": "Vanos", "esp": "Espacios"}


def scene(project: Project) -> list[dict[str, Any]]:
    elevations = {level.id: level.elevation for level in project.levels}
    walls = {wall.id: wall for wall in project.walls}
    objects: list[dict[str, Any]] = []
    for wall in project.walls:
        z0 = elevations[wall.level_id]
        objects.append(_prism(wall.id, wall_polygon(wall), z0, z0 + wall_height(project, wall)))
    for opening in project.openings:
        wall = walls[opening.wall_id]
        z0 = elevations[wall.level_id] + opening.sill_height
        footprint = opening_polygon(wall, opening)
        objects.append(_prism(opening.id, footprint, z0, z0 + opening.height))
    for space in project.spaces:
        objects.append(
            {
                "id": space.id,
                "layer": LAYERS["esp"],
                "kind": "surface",
                "exterior": [list(p) for p in space.polygon.exterior],
                "holes": [[list(p) for p in hole] for hole in space.polygon.holes],
                "z": elevations[space.level_id],
            }
        )
    return objects


def layer_of(entity_id: str) -> str:
    return LAYERS[entity_id.rsplit("-", 1)[0]]


def _prism(entity_id: str, footprint: Polygon, z0: float, z1: float) -> dict[str, Any]:
    return {
        "id": entity_id,
        "layer": layer_of(entity_id),
        "kind": "prism",
        "footprint": [list(p) for p in footprint.exterior.coords[:-1]],
        "z0": z0,
        "z1": z1,
    }
