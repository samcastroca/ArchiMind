"""El vano en su muro: dónde empieza y termina, hacia qué lado queda «adentro» y cómo se inserta
el bloque para que su +y mire hacia ese lado.

Los lados son los del eje del muro recorrido de su inicio a su final (`AxisSide`). El bloque se
inserta sin espejar, así que conserva su mano: con adentro a la izquierda va en el inicio del
vano con el ángulo del eje; a la derecha, en el final del vano y girado 180°.
"""

import math
from dataclasses import dataclass

from archimind_schema import (
    AxisSide,
    Opening,
    Point2D,
    Project,
    Space,
    Wall,
    space_area,
    wall_polygon,
)
from shapely import LineString, Point, Polygon, get_coordinates
from shapely.ops import substring

from archimind_bloques.resolve import FitError, plain

# Cuánto más allá de la cara del muro se busca el recinto de cada lado.
PROBE_M = 0.05
# Nombres de recinto que son circulación (sin tildes ni mayúsculas), además de la categoría.
CIRCULATION_WORDS = (
    "pasillo",
    "hall",
    "corredor",
    "circulacion",
    "distribuidor",
    "vestibulo",
    "recibidor",
)


@dataclass(frozen=True)
class Site:
    start: Point2D  # inicio del vano sobre el eje
    end: Point2D  # final del vano sobre el eje
    side: AxisSide  # lado de «adentro»: hacia donde mira el +y del bloque
    room: Space | None  # el recinto de adentro, si lo hay
    note: str  # por qué ese lado, para el usuario


@dataclass(frozen=True)
class Run:
    """Cara de muro libre desde un borde del vano hasta el primer muro que la corta (`wall_id`)
    o, si ninguno la corta, hasta el extremo del eje (`wall_id` None)."""

    length: float
    wall_id: str | None


def span(wall: Wall, opening: Opening) -> tuple[Point2D, Point2D]:
    """Inicio y final del vano sobre el eje. Un vano tiene que caer en un tramo recto."""
    line = substring(LineString(wall.axis), opening.offset, opening.offset + opening.width)
    coords = list(line.coords)
    if len(coords) != 2:
        raise FitError(
            f"El vano {opening.id} cae sobre un quiebre del eje de {wall.id}: un bloque de "
            "carpintería necesita un tramo recto."
        )
    (x0, y0), (x1, y1) = coords
    return (x0, y0), (x1, y1)


def locate(project: Project, wall: Wall, opening: Opening, opens_into: str | None = None) -> Site:
    """Elige el lado de adentro: el recinto `opens_into` si se pide; en un muro con un solo
    recinto al lado (exterior), ese; entre dos, el que no es circulación y si no, el más
    pequeño; sin recintos, la izquierda del eje, con aviso."""
    start, end = span(wall, opening)
    rooms = _neighbours(project, wall, start, end)
    if opens_into is not None:
        return _requested(project, opening, start, end, rooms, opens_into)
    present = [(side, room) for side, room in rooms.items() if room is not None]
    if not present:
        note = (
            f"no hay recintos a los lados de {opening.id}: se supone adentro a la izquierda del "
            f"eje de {wall.id}; para cambiarlo, indica opens_into"
        )
        return Site(start, end, "left", None, note)
    if len(present) == 1:
        side, room = present[0]
        return Site(start, end, side, room, f"muro exterior: adentro es {_name(room)}")
    (_, left), (_, right) = present
    side, note = _between(left, right)
    return Site(start, end, side, left if side == "left" else right, note)


def insertion(site: Site) -> tuple[Point2D, float]:
    """Punto de inserción y rotación en grados (0 a 360) del bloque de planta."""
    (x0, y0), (x1, y1) = site.start, site.end
    angle = math.degrees(math.atan2(y1 - y0, x1 - x0))
    if site.side == "left":
        return site.start, angle % 360
    return site.end, (angle + 180) % 360


def free_runs(project: Project, wall: Wall, opening: Opening, face: AxisSide) -> tuple[Run, Run]:
    """La cara `face` del muro libre antes del inicio del vano y después de su final. Los muros
    que la cortan (en L o en T) se buscan en una paralela a la cara, un poco hacia el recinto."""
    axis = LineString(wall.axis)
    sign = 1 if face == "left" else -1
    face_line = axis.offset_curve(sign * (wall.thickness / 2 + PROBE_M))
    start, end = opening.offset, opening.offset + opening.width
    before, after = Run(start, None), Run(float(axis.length) - end, None)
    for other in project.walls:
        if other.id == wall.id or other.level_id != wall.level_id:
            continue
        crossing = face_line.intersection(wall_polygon(other))
        if crossing.is_empty:
            continue
        along = [float(axis.project(Point(xy))) for xy in get_coordinates(crossing)]
        if max(along) <= start and start - max(along) < before.length:
            before = Run(start - max(along), other.id)
        if min(along) >= end and min(along) - end < after.length:
            after = Run(min(along) - end, other.id)
    return before, after


def is_circulation(space: Space) -> bool:
    name = plain(space.name)
    return space.category == "circulation" or any(word in name for word in CIRCULATION_WORDS)


def _between(left: Space, right: Space) -> tuple[AxisSide, str]:
    """Entre dos recintos: el que no es circulación y, si eso no decide, el más pequeño."""
    if is_circulation(left) != is_circulation(right):
        room, other = (right, left) if is_circulation(left) else (left, right)
        note = f"abre hacia {_name(room)} y no hacia la circulación ({_name(other)})"
    else:
        room, other = (left, right) if space_area(left) <= space_area(right) else (right, left)
        note = (
            f"abre hacia el recinto más pequeño, {_name(room)} ({space_area(room):.2f} m²), y "
            f"no hacia {_name(other)} ({space_area(other):.2f} m²)"
        )
    return ("left" if room is left else "right"), note


def _neighbours(
    project: Project, wall: Wall, start: Point2D, end: Point2D
) -> dict[AxisSide, Space | None]:
    """El recinto del mismo nivel que hay a cada lado del centro del vano, o None."""
    (x0, y0), (x1, y1) = start, end
    length = math.dist(start, end)
    normal = (-(y1 - y0) / length, (x1 - x0) / length)  # hacia la izquierda del eje
    reach = wall.thickness / 2 + PROBE_M
    middle = ((x0 + x1) / 2, (y0 + y1) / 2)
    spaces = [s for s in project.spaces if s.level_id == wall.level_id]
    found: dict[AxisSide, Space | None] = {}
    sides: tuple[tuple[AxisSide, int], ...] = (("left", 1), ("right", -1))
    for side, sign in sides:
        probe = Point(middle[0] + sign * normal[0] * reach, middle[1] + sign * normal[1] * reach)
        found[side] = next((s for s in spaces if _polygon(s).contains(probe)), None)
    return found


def _requested(
    project: Project,
    opening: Opening,
    start: Point2D,
    end: Point2D,
    rooms: dict[AxisSide, Space | None],
    opens_into: str,
) -> Site:
    if opens_into not in {space.id for space in project.spaces}:
        raise FitError(f"No existe el recinto {opens_into}: usa listar_espacios de archimind-core.")
    for side, room in rooms.items():
        if room is not None and room.id == opens_into:
            return Site(start, end, side, room, f"abre hacia {_name(room)}, como se pidió")
    beside = [_name(room) for room in rooms.values() if room is not None]
    listed = " y ".join(beside) if beside else "ningún recinto"
    raise FitError(
        f"El recinto {opens_into} no está junto a {opening.id}: a sus lados hay {listed}."
    )


def _polygon(space: Space) -> Polygon:
    return Polygon(space.polygon.exterior, space.polygon.holes)


def _name(space: Space) -> str:
    return f"{space.name} ({space.id})"
