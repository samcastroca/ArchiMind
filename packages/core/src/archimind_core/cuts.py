"""Líneas de corte propuestas: longitudinal, transversal y por la escalera si la hay.

Los cortes siguen el rectángulo mínimo que encierra los muros: el longitudinal va paralelo a su
lado largo y el transversal al corto. De las posiciones del 60 % central del edificio se
descartan las que corren a lo largo de un muro (el corte quedaría dentro del muro o rozándolo) y
se elige la que atraviesa más vanos; a igualdad, la más cercana al centro. El schema no tiene
escaleras: se toma como escalera un espacio cuyo nombre la contenga.
"""

import hashlib
import math
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from archimind_schema import (
    ANGLE_TOL_DEG,
    CUTS_FILENAME,
    LENGTH_TOL,
    MODEL_FILENAME,
    CutLine,
    CutProposals,
    Opening,
    Point2D,
    Project,
    opening_polygon,
    wall_polygon,
)
from shapely import LineString, Polygon, minimum_rotated_rectangle, unary_union

from archimind_core.project import outputs_dir

STEP_M = 0.05
# Posiciones probadas por corte, como máximo: en edificios grandes el paso crece.
MAX_POSITIONS = 200
CENTRAL_FRACTION = 0.6
# Distancia mínima entre el corte y la cara de un muro paralelo.
WALL_CLEARANCE_M = 0.10
# Lo que la línea sobresale del edificio en cada extremo.
OVERHANG_M = 1.0
STAIR_WORD = "escalera"
KIND_NAMES = {"door": ("puerta", "puertas"), "window": ("ventana", "ventanas")}
KIND_NAMES["void"] = ("vano libre", "vanos libres")

Vector = tuple[float, float]


class CutsError(Exception):
    """No se pueden proponer cortes; el mensaje está pensado para el usuario final."""


@dataclass(frozen=True)
class _Frame:
    center: Point2D
    long_dir: Vector
    short_dir: Vector
    long_len: float
    short_len: float


def propose_cuts(project: Project) -> list[CutLine]:
    """El longitudinal y el transversal (si hay una posición que no corra por un muro) y el de
    la escalera si existe."""
    if not project.walls:
        raise CutsError(
            f"El modelo de {project.name} no tiene muros: reconstrúyelo con aplicar_mapeo antes "
            "de proponer cortes."
        )
    footprint = unary_union([wall_polygon(wall) for wall in project.walls])
    frame = _frame(footprint)
    cuts = []
    longitudinal = _best_line(
        project, frame.center, frame.long_dir, frame.long_len, frame.short_len
    )
    if longitudinal is not None:
        cuts.append(_cut(project, "longitudinal", "A-A", longitudinal, "paralelo al lado largo"))
    transversal = _best_line(
        project, frame.center, frame.short_dir, frame.short_len, frame.long_len
    )
    if transversal is not None:
        cuts.append(_cut(project, "transversal", "B-B", transversal, "paralelo al lado corto"))
    stair = _stair_line(project, footprint)
    if stair is not None:
        line, name = stair
        cuts.append(_cut(project, "escalera", "C-C", line, f"por {name}"))
    return cuts


def write_cut_proposals(project_path: str | Path, cuts: list[CutLine]) -> Path:
    """`salidas/cortes.json`, con el SHA-256 de la versión de modelo.json que se usó."""
    folder = Path(project_path).expanduser().resolve()
    text = (folder / MODEL_FILENAME).read_text(encoding="utf-8")
    proposals = CutProposals(
        base_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(), cuts=cuts
    )
    path = outputs_dir(folder) / CUTS_FILENAME
    path.write_text(proposals.model_dump_json(indent=2), encoding="utf-8")
    return path


def _frame(footprint: Polygon) -> _Frame:
    corners = list(minimum_rotated_rectangle(footprint).exterior.coords)
    edges = [(corners[i + 1][0] - corners[i][0], corners[i + 1][1] - corners[i][1]) for i in (0, 1)]
    long_edge, short_edge = sorted(edges, key=lambda e: -math.hypot(*e))
    cx = sum(p[0] for p in corners[:4]) / 4
    cy = sum(p[1] for p in corners[:4]) / 4
    return _Frame(
        (cx, cy),
        _canonical(long_edge),
        _canonical(short_edge),
        math.hypot(*long_edge),
        math.hypot(*short_edge),
    )


def _canonical(v: Vector) -> Vector:
    """El vector unitario apuntando hacia +x (o hacia +y si es vertical): así la propuesta no
    depende del orden de los vértices."""
    length = math.hypot(*v)
    x, y = v[0] / length, v[1] / length
    if x < -1e-9 or (abs(x) <= 1e-9 and y < 0):
        x, y = -x, -y
    return (x, y)


def _best_line(
    project: Project, center: Point2D, along: Vector, length: float, width: float
) -> LineString | None:
    """La mejor línea paralela a `along`: el edificio mide `length` a lo largo de ella y
    `width` en perpendicular."""
    across = (-along[1], along[0])
    step = max(STEP_M, width * CENTRAL_FRACTION / MAX_POSITIONS)
    steps = int(width * CENTRAL_FRACTION / 2 / step)
    offsets = sorted((k * step for k in range(-steps, steps + 1)), key=lambda t: (abs(t), t))
    reach = length / 2 + OVERHANG_M
    best: tuple[int, LineString] | None = None
    for t in offsets:
        origin = (center[0] + t * across[0], center[1] + t * across[1])
        line = _line(origin, along, -reach, reach)
        if _runs_along_a_wall(project, line, along):
            continue
        crossed = len(_crossed_openings(project, line))
        if best is None or crossed > best[0]:
            best = (crossed, line)
    return best[1] if best else None


def _line(origin: Point2D, direction: Vector, lo: float, hi: float) -> LineString:
    return LineString(
        [
            (origin[0] + lo * direction[0], origin[1] + lo * direction[1]),
            (origin[0] + hi * direction[0], origin[1] + hi * direction[1]),
        ]
    )


def _runs_along_a_wall(project: Project, line: LineString, direction: Vector) -> bool:
    """Si algún tramo recto de muro es paralelo a la línea, la toca a menos de medio espesor más
    la holgura y se solapa con ella a lo largo."""
    (x0, y0), _ = line.coords
    normal = (-direction[1], direction[0])
    for wall in project.walls:
        limit = wall.thickness / 2 + WALL_CLEARANCE_M
        for a, b in zip(wall.axis, wall.axis[1:], strict=False):
            length = math.dist(a, b)
            if length <= LENGTH_TOL:
                continue
            sin = abs(direction[0] * (b[1] - a[1]) - direction[1] * (b[0] - a[0])) / length
            if sin > math.sin(math.radians(ANGLE_TOL_DEG)):
                continue
            gaps = [(p[0] - x0) * normal[0] + (p[1] - y0) * normal[1] for p in (a, b)]
            if min(abs(g) for g in gaps) < limit:
                return True
    return False


def _crossed_openings(project: Project, line: LineString) -> list[Opening]:
    walls = {wall.id: wall for wall in project.walls}
    return [o for o in project.openings if line.intersects(opening_polygon(walls[o.wall_id], o))]


def _stair_line(project: Project, footprint: Polygon) -> tuple[LineString, str] | None:
    stairs = sorted((s for s in project.spaces if STAIR_WORD in _plain(s.name)), key=lambda s: s.id)
    if not stairs:
        return None
    space = stairs[0]
    polygon = Polygon(space.polygon.exterior, space.polygon.holes)
    corners = list(minimum_rotated_rectangle(polygon).exterior.coords)
    edges = [(corners[i + 1][0] - corners[i][0], corners[i + 1][1] - corners[i][1]) for i in (0, 1)]
    direction = _canonical(max(edges, key=lambda e: math.hypot(*e)))
    center = polygon.centroid
    origin = (center.x, center.y)
    along = [
        (x - origin[0]) * direction[0] + (y - origin[1]) * direction[1]
        for x, y in _coords(footprint)
    ]
    line = _line(origin, direction, min(along) - OVERHANG_M, max(along) + OVERHANG_M)
    return line, space.name


def _coords(geometry: Polygon) -> list[tuple[float, float]]:
    parts = getattr(geometry, "geoms", [geometry])
    return [(x, y) for part in parts for x, y in part.exterior.coords]


def _plain(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _cut(project: Project, name: str, label: str, line: LineString, where: str) -> CutLine:
    (x0, y0), (x1, y1) = line.coords
    return CutLine(
        name=name,
        label=label,
        start=(x0, y0),
        end=(x1, y1),
        description=_description(project, line, where),
    )


def _description(project: Project, line: LineString, where: str) -> str:
    (x0, y0), (x1, y1) = line.coords
    length = math.hypot(x1 - x0, y1 - y0)
    direction = ((x1 - x0) / length, (y1 - y0) / length)
    crossed = []
    for space in project.spaces:
        part = line.intersection(Polygon(space.polygon.exterior, space.polygon.holes))
        if part.length > LENGTH_TOL:
            c = part.centroid
            crossed.append(((c.x - x0) * direction[0] + (c.y - y0) * direction[1], space.name))
    kinds = Counter(o.kind for o in _crossed_openings(project, line))
    parts = [where[0].upper() + where[1:]]
    if crossed:
        parts.append("cruza " + ", ".join(name for _, name in sorted(crossed)))
    if kinds:
        listed = [
            f"{n} {KIND_NAMES[kind][0] if n == 1 else KIND_NAMES[kind][1]}"
            for kind, n in sorted(kinds.items())
        ]
        parts.append("corta " + " y ".join(listed))
    else:
        parts.append("no corta vanos")
    return "; ".join(parts) + "."
