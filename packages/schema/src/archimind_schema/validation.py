"""Reglas semánticas del modelo: devuelven todos los problemas a la vez, sin lanzar."""

from collections import Counter
from collections.abc import Iterator
from itertools import combinations
from typing import Literal

from pydantic import BaseModel, ConfigDict
from shapely import Point, Polygon, is_valid_reason

from archimind_schema.geometry import wall_length, wall_polygon
from archimind_schema.models import (
    LENGTH_TOL,
    WALL_THICKNESSES,
    Level,
    Opening,
    Project,
    Space,
    Wall,
    id_pattern,
)

OPEN_JOINT_MAX = 0.05


class Problem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str
    severity: Literal["error", "warning"]
    ids: list[str]
    message: str


def validate(project: Project) -> list[Problem]:
    return [
        *_duplicate_ids(project),
        *_id_prefixes(project),
        *_references(project),
        *_space_polygons(project),
        *_space_overlaps(project),
        *_openings(project),
        *_thicknesses(project),
        *_open_joints(project),
        *_scale(project),
    ]


def _error(code: str, ids: list[str], message: str) -> Problem:
    return Problem(code=code, severity="error", ids=ids, message=message)


def _warning(code: str, ids: list[str], message: str) -> Problem:
    return Problem(code=code, severity="warning", ids=ids, message=message)


def _duplicate_ids(project: Project) -> Iterator[Problem]:
    entities: list[Level | Wall | Opening | Space] = [
        *project.levels,
        *project.walls,
        *project.openings,
        *project.spaces,
    ]
    counts = Counter(entity.id for entity in entities)
    for entity_id, count in counts.items():
        if count > 1:
            yield _error("id_repetido", [entity_id], f"el ID {entity_id} aparece {count} veces")


def _id_prefixes(project: Project) -> Iterator[Problem]:
    typed_ids = [
        *(("niv", level.id) for level in project.levels),
        *(("muro", wall.id) for wall in project.walls),
        *(("vano", opening.id) for opening in project.openings),
        *(("esp", space.id) for space in project.spaces),
        *(("blq", o.block_id) for o in project.openings if o.block_id is not None),
    ]
    for prefix, entity_id in typed_ids:
        if not id_pattern(prefix).match(entity_id):
            yield _error(
                "prefijo_invalido",
                [entity_id],
                f"el ID '{entity_id}' no tiene el formato '{prefix}-NNNN'",
            )


def _references(project: Project) -> Iterator[Problem]:
    level_ids = {level.id for level in project.levels}
    wall_ids = {wall.id for wall in project.walls}
    located: list[Wall | Space] = [*project.walls, *project.spaces]
    for item in located:
        if item.level_id not in level_ids:
            yield _error(
                "nivel_inexistente",
                [item.id],
                f"{item.id} apunta al nivel inexistente {item.level_id}",
            )
    for opening in project.openings:
        if opening.wall_id not in wall_ids:
            yield _error(
                "muro_inexistente",
                [opening.id],
                f"{opening.id} apunta al muro inexistente {opening.wall_id}",
            )


def _polygon_problem(space: Space) -> str | None:
    """Motivo por el que el polígono no es válido, o None. El anillo se cierra implícitamente."""
    rings = [space.polygon.exterior, *space.polygon.holes]
    if any(len(set(ring)) < 3 for ring in rings):
        return "un anillo tiene menos de 3 vértices distintos y no cierra un área"
    polygon = Polygon(space.polygon.exterior, space.polygon.holes)
    if not polygon.is_valid:
        return str(is_valid_reason(polygon))
    if polygon.area <= 0:
        return "el polígono tiene área nula"
    return None


def _space_polygons(project: Project) -> Iterator[Problem]:
    for space in project.spaces:
        reason = _polygon_problem(space)
        if reason is not None:
            yield _error(
                "poligono_invalido", [space.id], f"el polígono de {space.id} no es válido: {reason}"
            )


def _space_overlaps(project: Project) -> Iterator[Problem]:
    # Erosionar cada uno media tolerancia deja fuera los solapes de ancho <= LENGTH_TOL.
    eroded = [
        (space, Polygon(space.polygon.exterior, space.polygon.holes).buffer(-LENGTH_TOL / 2))
        for space in project.spaces
        if _polygon_problem(space) is None
    ]
    for (a, poly_a), (b, poly_b) in combinations(eroded, 2):
        if a.level_id == b.level_id and poly_a.intersection(poly_b).area > 0:
            yield _error(
                "espacios_superpuestos",
                [a.id, b.id],
                f"los espacios {a.id} y {b.id} se superponen",
            )


def _openings(project: Project) -> Iterator[Problem]:
    walls = {wall.id: wall for wall in project.walls}
    for opening in project.openings:
        wall = walls.get(opening.wall_id)
        if wall is not None and opening.offset + opening.width > wall_length(wall) + LENGTH_TOL:
            yield _error(
                "vano_fuera_del_muro",
                [opening.id, wall.id],
                f"{opening.id} se sale de la longitud del muro {wall.id}",
            )
    for a, b in combinations(project.openings, 2):
        if a.wall_id != b.wall_id or a.wall_id not in walls:
            continue
        overlap = min(a.offset + a.width, b.offset + b.width) - max(a.offset, b.offset)
        if overlap > LENGTH_TOL:
            yield _error(
                "vanos_superpuestos",
                [a.id, b.id],
                f"los vanos {a.id} y {b.id} se superponen en el muro {a.wall_id}",
            )


def _thicknesses(project: Project) -> Iterator[Problem]:
    usual = ", ".join(f"{t:.2f}" for t in WALL_THICKNESSES)
    for wall in project.walls:
        if wall.thickness <= 0:
            yield _error(
                "espesor_no_positivo",
                [wall.id],
                f"el muro {wall.id} tiene espesor {wall.thickness} m; debe ser mayor que 0",
            )
        elif all(abs(wall.thickness - t) > LENGTH_TOL for t in WALL_THICKNESSES):
            yield _warning(
                "espesor_inusual",
                [wall.id],
                f"el muro {wall.id} tiene espesor {wall.thickness} m, fuera de los habituales "
                f"({usual} m)",
            )


def _open_joints(project: Project) -> Iterator[Problem]:
    walls = [wall for wall in project.walls if wall.thickness > 0]
    footprints = {wall.id: wall_polygon(wall) for wall in walls}
    for wall in walls:
        for end in (wall.axis[0], wall.axis[-1]):
            for other in walls:
                if other is wall or other.level_id != wall.level_id:
                    continue
                gap = Point(end).distance(footprints[other.id])
                if LENGTH_TOL < gap < OPEN_JOINT_MAX:
                    yield _warning(
                        "union_abierta",
                        [wall.id, other.id],
                        f"unión abierta: un extremo de {wall.id} queda a {gap * 100:.1f} cm de "
                        f"{other.id} sin tocarlo",
                    )


def _scale(project: Project) -> Iterator[Problem]:
    if not project.scale_confirmed:
        yield _warning(
            "escala_no_confirmada",
            [],
            "la escala no está confirmada: todas las cantidades son preliminares",
        )
