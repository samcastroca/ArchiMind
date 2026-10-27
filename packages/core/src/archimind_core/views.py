"""Vistas del dibujo: agrupaciones de muros separadas entre sí, como una planta y un alzado
dibujados lado a lado en la misma capa. Solo se reconstruye una, la que el usuario elige."""

from dataclasses import dataclass, field

from archimind_schema import Problem
from shapely import GeometryCollection, LineString, MultiLineString, Point, STRtree
from shapely.geometry.base import BaseGeometry

from archimind_core.extract import PlanContent


class ViewError(Exception):
    """La vista pedida no existe; el mensaje está pensado para el usuario final."""


@dataclass(frozen=True)
class View:
    number: int
    # (x mín., y mín., x máx., y máx.) de sus muros, en metros.
    bounds: tuple[float, float, float, float]
    pieces: int
    # Lo que está a menos de media separación de sus muros: ahí caen sus vanos y sus textos.
    region: BaseGeometry = field(repr=False)

    @property
    def width(self) -> float:
        return self.bounds[2] - self.bounds[0]

    @property
    def height(self) -> float:
        return self.bounds[3] - self.bounds[1]


class ViewChoiceNeeded(Exception):
    """El dibujo tiene varias vistas y no se dijo cuál es la planta: mezclarlas daría muros y
    espacios falsos."""

    def __init__(self, views: list[View]) -> None:
        self.views = views
        super().__init__(f"El plano tiene {len(views)} vistas: hay que elegir cuál es la planta")


def find_views(content: PlanContent, gap: float) -> list[View]:
    """Las agrupaciones de tramos y ejes de muro, de todas las capas de muros, que distan entre
    sí más que `gap`. Se numeran de izquierda a derecha y, a igual x, de arriba abajo."""
    lines = [
        LineString([s.start, s.end])
        for segments in content.wall_segments.values()
        for s in segments
    ]
    lines += [LineString(axis.points) for axis in content.wall_axes if len(axis.points) >= 2]
    if not lines:
        return []
    regions = MultiLineString(lines).buffer(gap / 2)
    tree = STRtree(lines)
    found = []
    for region in getattr(regions, "geoms", [regions]):
        inside = [lines[i] for i in tree.query(region, predicate="intersects")]
        found.append((GeometryCollection(inside).bounds, len(inside), region))
    found.sort(key=lambda item: (item[0][0], -item[0][3]))
    return [
        View(number, tuple(bounds), pieces, region)
        for number, (bounds, pieces, region) in enumerate(found, start=1)
    ]


def choose_view(
    content: PlanContent, views: list[View], number: int | None
) -> tuple[PlanContent, list[Problem]]:
    """Lo que el dibujo tiene en la vista elegida, con el aviso de las que se ignoran. Con una
    sola vista no hace falta elegir."""
    if len(views) <= 1:
        if number not in (None, 1):
            raise ViewError(f"No existe la vista {number}: el plano tiene una sola vista")
        return content, []
    if number is None:
        raise ViewChoiceNeeded(views)
    if not 1 <= number <= len(views):
        raise ViewError(f"No existe la vista {number}: el plano tiene vistas de 1 a {len(views)}")
    chosen = views[number - 1]
    others = ", ".join(str(v.number) for v in views if v is not chosen)
    warning = Problem(
        code="vista_elegida",
        severity="warning",
        ids=[],
        message=(
            f"el plano tiene {len(views)} vistas: se reconstruye la vista {number} "
            f"({describe(chosen)}) y se ignoran las demás ({others})"
        ),
    )
    return within(content, chosen.region), [warning]


def within(content: PlanContent, region: BaseGeometry) -> PlanContent:
    """Lo extraído que cae en la región. Los recuentos por capa (sombreados, entidades no
    soportadas, capas mixtas) se conservan: describen la capa entera."""
    return PlanContent(
        wall_segments={
            layer: kept
            for layer, segments in content.wall_segments.items()
            if (kept := [s for s in segments if region.intersects(LineString([s.start, s.end]))])
        },
        wall_axes=[a for a in content.wall_axes if region.intersects(Point(a.points[0]))],
        symbols={
            kind: [shape for shape in shapes if region.intersects(shape)]
            for kind, shapes in content.symbols.items()
        },
        blocks=[b for b in content.blocks if region.intersects(b.hull)],
        labels=[label for label in content.labels if region.intersects(Point(label.position))],
        mixed_layers=set(content.mixed_layers),
        unsupported_walls=content.unsupported_walls.copy(),
        wall_hatches=content.wall_hatches.copy(),
    )


def describe(view: View) -> str:
    x0, y0, x1, y1 = view.bounds
    return (
        f"x de {x0:.2f} a {x1:.2f}, y de {y0:.2f} a {y1:.2f}: {view.width:.2f} × "
        f"{view.height:.2f} m, {view.pieces} tramos de muro"
    )
