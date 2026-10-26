"""Vanos: los huecos de los muros con su símbolo de puerta o ventana, y los bloques de puerta o
ventana que no caen en un hueco."""

import math
from collections.abc import Sequence

from archimind_schema import (
    LENGTH_TOL,
    Opening,
    Point2D,
    Problem,
    Project,
    Wall,
    new_id,
    opening_polygon,
    wall_polygon,
)
from shapely import LineString, Point, unary_union
from shapely.geometry.base import BaseGeometry
from shapely.ops import substring

from archimind_core.build_rules import BuildRules, OpeningKind
from archimind_core.extract import PlanContent, SymbolKind
from archimind_core.walls import Gap


def place_openings(
    project: Project,
    gaps: dict[str, list[Gap]],
    content: PlanContent,
    rules: BuildRules,
) -> list[Problem]:
    """Añade al proyecto los vanos de sus muros y devuelve los avisos. `gaps` va por ID de muro."""
    walls = {wall.id: wall for wall in project.walls}
    symbols: dict[SymbolKind, BaseGeometry] = {
        kind: unary_union(
            [*content.symbols[kind], *(b.hull for b in content.blocks if b.kind == kind)]
        )
        for kind in ("door", "window")
    }
    warnings: list[Problem] = []
    for wall_id, wall_gaps in gaps.items():
        wall = walls[wall_id]
        for gap in wall_gaps:
            length = LineString(wall.axis).length
            s0, s1 = sorted(min(max(_along(wall, p), 0.0), length) for p in (gap.start, gap.end))
            search = _span(wall, s0, s1).buffer(rules.symbol_search_m)
            hits = [kind for kind, shapes in symbols.items() if shapes.intersects(search)]
            kind: OpeningKind = hits[0] if len(hits) == 1 else "void"
            opening = _add(project, wall, kind, s0, s1, rules)
            if len(hits) > 1:
                warnings.append(
                    _warning(
                        "vano_ambiguo",
                        f"el hueco de {opening.width:.2f} m en {wall.id} tiene símbolos de "
                        "puerta y de ventana: queda como vano sin tipo",
                        [opening.id, wall.id],
                    )
                )
            elif not hits:
                warnings.append(
                    _warning(
                        "hueco_sin_simbolo",
                        f"el hueco de {opening.width:.2f} m en {wall.id} no tiene símbolo "
                        "de puerta ni de ventana: queda como vano sin tipo",
                        [opening.id, wall.id],
                    )
                )
    warnings += _blocks_without_gap(project, content, rules)
    warnings += _loose_symbols(project, content, rules)
    return warnings


def _blocks_without_gap(project: Project, content: PlanContent, rules: BuildRules) -> list[Problem]:
    """Un bloque de puerta o ventana sobre un muro sin hueco crea el vano que ocupa a lo largo."""
    warnings = []
    for block in content.blocks:
        hosts = [
            (wall_polygon(wall).intersection(block.hull).area, wall)
            for wall in project.walls
            if wall_polygon(wall).intersects(block.hull)
        ]
        if not hosts:
            warnings.append(
                _warning(
                    "simbolo_sin_muro",
                    f"el bloque {block.name!r} ({_kind_name(block.kind)}) cerca de "
                    f"{_fmt(block.hull.centroid)} no está sobre ningún muro: no se crea vano",
                )
            )
            continue
        wall = max(hosts, key=lambda h: h[0])[1]
        length = LineString(wall.axis).length
        along = [_along(wall, p) for p in block.hull.exterior.coords]
        s0, s1 = max(0.0, min(along)), min(length, max(along))
        if any(_overlap(o, s0, s1) > 0.5 * min(o.width, s1 - s0) for o in _on(project, wall)):
            continue
        if s1 - s0 <= LENGTH_TOL:
            continue
        opening = _add(project, wall, block.kind, s0, s1, rules)
        warnings.append(
            _warning(
                "vano_sin_hueco",
                f"el bloque {block.name!r} crea una {_kind_name(block.kind)} de "
                f"{opening.width:.2f} m en {wall.id}, pero el muro no tiene hueco dibujado ahí",
                [opening.id, wall.id],
            )
        )
    return warnings


def _loose_symbols(project: Project, content: PlanContent, rules: BuildRules) -> list[Problem]:
    """Puertas y ventanas dibujadas con líneas que no caen en ningún vano."""
    walls = {wall.id: wall for wall in project.walls}
    openings = unary_union(
        [
            opening_polygon(walls[o.wall_id], o).buffer(rules.symbol_search_m)
            for o in project.openings
        ]
    )
    warnings = []
    for kind in ("door", "window"):
        shapes = content.symbols[kind]
        if not shapes:
            continue
        clusters = unary_union([s.buffer(LENGTH_TOL) for s in shapes])
        for cluster in getattr(clusters, "geoms", [clusters]):
            if not cluster.intersects(openings):
                warnings.append(
                    _warning(
                        "simbolo_sin_hueco",
                        f"hay una {_kind_name(kind)} dibujada cerca de {_fmt(cluster.centroid)} "
                        "sin hueco en ningún muro: no se deduce su vano",
                    )
                )
    return warnings


def _add(
    project: Project, wall: Wall, kind: OpeningKind, s0: float, s1: float, rules: BuildRules
) -> Opening:
    defaults = rules.openings[kind]
    opening = Opening(
        id=new_id(project, "vano"),
        wall_id=wall.id,
        kind=kind,
        offset=s0,
        width=s1 - s0,
        height=defaults.height,
        sill_height=defaults.sill_height,
    )
    project.openings.append(opening)
    return opening


def _on(project: Project, wall: Wall) -> Sequence[Opening]:
    return [o for o in project.openings if o.wall_id == wall.id]


def _overlap(opening: Opening, s0: float, s1: float) -> float:
    return min(opening.offset + opening.width, s1) - max(opening.offset, s0)


def _along(wall: Wall, point: Point2D) -> float:
    """Distancia a lo largo del eje desde su inicio hasta la proyección del punto."""
    (x0, y0), (x1, y1) = wall.axis[0], wall.axis[-1]
    length = math.dist(wall.axis[0], wall.axis[-1])
    return ((point[0] - x0) * (x1 - x0) + (point[1] - y0) * (y1 - y0)) / length


def _span(wall: Wall, s0: float, s1: float) -> BaseGeometry:
    line = substring(LineString(wall.axis), s0, s1)
    return line.buffer(wall.thickness / 2, cap_style="flat")


def _kind_name(kind: str) -> str:
    return "puerta" if kind == "door" else "ventana"


def _fmt(point: Point) -> str:
    return f"({point.x:.2f}, {point.y:.2f})"


def _warning(code: str, message: str, ids: list[str] | None = None) -> Problem:
    return Problem(code=code, severity="warning", ids=ids or [], message=message)
