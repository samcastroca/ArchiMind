"""Cantidades del modelo: cuadro de áreas, metros lineales de muro y conteo de vanos.

Todo número sale de la geometría del modelo. Si la escala no está confirmada, cada resultado
lleva `preliminary` y la etiqueta `PRELIMINARY_LABEL`, y el cuadro de áreas no se exporta.
"""

import csv
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from archimind_schema import (
    ANGLE_TOL_DEG,
    LENGTH_TOL,
    Point2D,
    Project,
    Wall,
    space_area,
    wall_length,
    wall_polygon,
)
from shapely import LineString, Polygon, unary_union
from shapely.geometry.base import BaseGeometry

PRELIMINARY_LABEL = "PRELIMINAR: escala sin confirmar"
CSV_HEADER = ("id", "nombre", "categoría", "área_m2")


class QuantitiesError(Exception):
    """La cantidad no se puede entregar; el mensaje está pensado para el usuario final."""


@dataclass(frozen=True)
class SpaceArea:
    id: str
    name: str
    category: str
    area: float


@dataclass(frozen=True)
class AreaTable:
    """Áreas en m². Útil: todos los espacios menos los balcones. Construida: lo que encierra el
    contorno exterior de esos espacios y de los muros. Los balcones van aparte."""

    spaces: list[SpaceArea]
    useful_area: float
    built_area: float
    balcony_area: float
    preliminary: bool
    label: str | None


@dataclass(frozen=True)
class WallQuantities:
    """Metros lineales de eje por espesor (el medido, sin redondear a los habituales), con los
    vanos incluidos."""

    length_by_thickness: dict[float, float]
    preliminary: bool
    label: str | None


@dataclass(frozen=True)
class OpeningCount:
    kind: str
    width: float
    height: float
    count: int


@dataclass(frozen=True)
class OpeningCounts:
    counts: list[OpeningCount]
    preliminary: bool
    label: str | None


def area_table(project: Project) -> AreaTable:
    spaces = [SpaceArea(s.id, s.name, s.category, space_area(s)) for s in project.spaces]
    preliminary, label = _preliminary(project)
    return AreaTable(
        spaces=spaces,
        useful_area=sum(s.area for s in spaces if s.category != "balcony"),
        built_area=_built_area(project),
        balcony_area=sum(s.area for s in spaces if s.category == "balcony"),
        preliminary=preliminary,
        label=label,
    )


def export_area_table_csv(table: AreaTable, path: Path) -> Path:
    """Escribe el cuadro en CSV (UTF-8 con BOM, para que Excel lea los acentos)."""
    if table.preliminary:
        raise QuantitiesError(
            f"{PRELIMINARY_LABEL}: confirma la escala del plano antes de exportar el cuadro de "
            "áreas."
        )
    path = Path(path)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(CSV_HEADER)
        for space in table.spaces:
            writer.writerow((space.id, space.name, space.category, f"{space.area:.2f}"))
        writer.writerow(("", "Área útil", "", f"{table.useful_area:.2f}"))
        writer.writerow(("", "Área construida", "", f"{table.built_area:.2f}"))
        writer.writerow(("", "Área de balcones", "", f"{table.balcony_area:.2f}"))
    return path


def wall_quantities(project: Project) -> WallQuantities:
    lengths: dict[float, float] = defaultdict(float)
    for wall in project.walls:
        lengths[round(wall.thickness, 3)] += wall_length(wall)
    return WallQuantities(dict(sorted(lengths.items())), *_preliminary(project))


def opening_counts(project: Project) -> OpeningCounts:
    counter = Counter((o.kind, round(o.width, 2), round(o.height, 2)) for o in project.openings)
    counts = [OpeningCount(*key, count) for key, count in sorted(counter.items())]
    return OpeningCounts(counts, *_preliminary(project))


def _preliminary(project: Project) -> tuple[bool, str | None]:
    if project.scale_confirmed:
        return False, None
    return True, PRELIMINARY_LABEL


def _built_area(project: Project) -> float:
    """Por nivel, el contorno exterior de los espacios no balcón y las huellas de muro, con las
    esquinas en L rellenas. Los patios y huecos interiores cuentan como construidos."""
    shapes: dict[str, list[Polygon]] = defaultdict(list)
    for space in project.spaces:
        if space.category != "balcony":
            polygon = Polygon(space.polygon.exterior, space.polygon.holes)
            shapes[space.level_id].append(polygon)
    walls_by_level: dict[str, list[Wall]] = defaultdict(list)
    for wall in project.walls:
        walls_by_level[wall.level_id].append(wall)
    for level_id, walls in walls_by_level.items():
        shapes[level_id] += [wall_polygon(wall) for wall in walls]
        shapes[level_id] += corner_patches(walls)

    total = 0.0
    for polygons in shapes.values():
        footprint: BaseGeometry = unary_union(polygons)
        parts = getattr(footprint, "geoms", [footprint])
        total += sum(Polygon(part.exterior).area for part in parts if not part.is_empty)
    return float(total)


def corner_patches(walls: list[Wall]) -> list[Polygon]:
    """Los extremos planos de dos muros que se encuentran en L dejan una muesca en la esquina
    exterior. La rellena la intersección de las franjas de ambos muros prolongadas a través de
    la esquina, a cualquier ángulo y espesor."""
    ends = [(wall, end) for wall in walls for end in _ends(wall)]
    patches = []
    for i, (wall_a, (corner_a, dir_a)) in enumerate(ends):
        for wall_b, (corner_b, dir_b) in ends[i + 1 :]:
            if wall_a is wall_b or math.dist(corner_a, corner_b) > LENGTH_TOL:
                continue
            sine = abs(dir_a[0] * dir_b[1] - dir_a[1] * dir_b[0])
            if sine < math.sin(math.radians(ANGLE_TOL_DEG)):
                continue  # colineales: no hay muesca
            reach = max(wall_a.thickness, wall_b.thickness) / sine
            strip_a = _strip(corner_a, dir_a, reach, wall_a.thickness)
            strip_b = _strip(corner_a, dir_b, reach, wall_b.thickness)
            patches.append(strip_a.intersection(strip_b))
    return patches


def _ends(wall: Wall) -> list[tuple[Point2D, Point2D]]:
    """Cada extremo del eje con la dirección unitaria de su tramo."""
    result = []
    for corner, neighbour in ((wall.axis[0], wall.axis[1]), (wall.axis[-1], wall.axis[-2])):
        length = math.dist(corner, neighbour)
        direction = ((neighbour[0] - corner[0]) / length, (neighbour[1] - corner[1]) / length)
        result.append((corner, direction))
    return result


def _strip(center: Point2D, direction: Point2D, reach: float, thickness: float) -> Polygon:
    dx, dy = direction[0] * reach, direction[1] * reach
    line = LineString([(center[0] - dx, center[1] - dy), (center[0] + dx, center[1] + dy)])
    return line.buffer(thickness / 2, cap_style="flat")
