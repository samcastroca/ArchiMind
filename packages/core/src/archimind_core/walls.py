"""Reconstrucción de muros: de las caras dibujadas a ejes rectos con espesor.

1. Los tramos de cada capa de muros que cierran anillos forman el material del muro; los que
   no, quedan como líneas abiertas.
2. Dos caras paralelas, separadas por un espesor posible y con material entre ambas, dan un
   tramo de muro: eje a media distancia sobre lo que solapan.
3. Los tramos colineales de igual espesor se unen. Lo que hay entre dos consecutivos es una
   unión (lo cruza material de otro muro) o un hueco, que luego será un vano.
4. Cada extremo se lleva hasta el eje del muro con el que forma una L o una T; el que acaba
   en un vano pegado a una esquina se alarga a través del vano.
"""

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from functools import partial

from archimind_schema import ANGLE_TOL_DEG, LENGTH_TOL, Point2D, Problem
from shapely import (
    LineString,
    MultiLineString,
    Polygon,
    line_merge,
    simplify,
    unary_union,
)
from shapely.geometry.base import BaseGeometry

from archimind_core.build_rules import BuildRules
from archimind_core.extract import PlanContent
from archimind_core.layer_roles import ParallelGroup, Placed, Segment, neighbours, parallel_groups

MIN_SIN = math.sin(math.radians(ANGLE_TOL_DEG))


@dataclass(frozen=True)
class WallPiece:
    start: Point2D
    end: Point2D
    thickness: float
    layer: str


@dataclass(frozen=True)
class Gap:
    """Tramo de eje vacío entre dos tramos de un mismo muro: un vano candidato."""

    start: Point2D
    end: Point2D


@dataclass
class WallDraft:
    start: Point2D
    end: Point2D
    thickness: float
    layer: str
    gaps: list[Gap] = field(default_factory=list)

    @property
    def length(self) -> float:
        return math.dist(self.start, self.end)


@dataclass
class WallsResult:
    walls: list[WallDraft]
    # Material de todos los muros: el dibujado más las huellas de los ejes con ancho.
    material: BaseGeometry
    warnings: list[Problem]


def reconstruct_walls(
    content: PlanContent, symbols: BaseGeometry, rules: BuildRules
) -> WallsResult:
    warnings: list[Problem] = []
    pieces: list[WallPiece] = []
    drawn = []
    for layer, segments in sorted(content.wall_segments.items()):
        material, open_segments = wall_material(segments)
        drawn.append(material)
        faces = boundary_segments(material)
        pieces += pair_faces(faces, layer, rules, partial(_is_material, material, rules))
        if open_segments:
            found = pair_faces(open_segments, layer, rules, partial(_is_clear, open_segments))
            pieces += found
            used = len(found)
            warnings.append(
                _warning(
                    "muro_de_lineas_abiertas" if used else "linea_de_muro_sin_interpretar",
                    f"la capa {layer!r} tiene {len(open_segments)} tramos de muro que no cierran "
                    "un contorno"
                    + (
                        f"; se dedujeron {used} tramos de muro de sus pares paralelos: revisar"
                        if used
                        else ": sin espesor no se puede crear un muro"
                    ),
                )
            )
    axis_pieces = [
        WallPiece(a, b, axis.thickness, axis.layer)
        for axis in content.wall_axes
        for a, b in zip(axis.points, axis.points[1:], strict=False)
        if math.dist(a, b) > LENGTH_TOL
    ]
    pieces += axis_pieces
    material = unary_union(
        [
            *drawn,
            *(
                LineString([p.start, p.end]).buffer(p.thickness / 2, cap_style="flat")
                for p in axis_pieces
            ),
        ]
    )
    for kind, count in sorted(content.unsupported_walls.items()):
        warnings.append(
            _warning(
                "entidad_de_muro_no_soportada",
                f"{count} entidades {kind} en capas de muros no se interpretan: solo se leen "
                "tramos rectos",
            )
        )

    walls = merge_collinear(pieces, material, symbols, rules)
    kept = [wall for wall in walls if wall.length >= wall.thickness]
    resolve_joints(kept, rules.joint_slack_m)
    bridge_corner_openings(kept, material, symbols, rules)
    # Los extremos alargados hasta una esquina permiten ahora cerrar la L del otro muro.
    resolve_joints(kept, rules.joint_slack_m)
    warnings += _discarded(walls, kept)
    return WallsResult(kept, material, warnings)


def _discarded(walls: Sequence[WallDraft], kept: Sequence[WallDraft]) -> list[Problem]:
    """Aviso por cada tramo más corto que grueso que se descarta sin quedar cubierto por los
    muros que quedan. Los cubiertos son restos del emparejado en las uniones (la jamba de un
    vano junto a una esquina frente a la cara del muro perpendicular) y no se avisan."""
    covered = unary_union(
        [LineString([w.start, w.end]).buffer(w.thickness / 2, cap_style="square") for w in kept]
    )
    warnings = []
    for wall in walls:
        if wall in kept:
            continue
        footprint = LineString([wall.start, wall.end]).buffer(wall.thickness / 2, cap_style="flat")
        if footprint.difference(covered).area > 0.05 * footprint.area:
            warnings.append(
                _warning(
                    "tramo_descartado",
                    f"se descartó un tramo de muro de {wall.length:.2f} m y espesor "
                    f"{wall.thickness:.2f} m cerca de {_fmt(wall.start)}: es más corto que grueso",
                )
            )
    return warnings


# --- 1. Material -----------------------------------------------------------------------------


def wall_material(segments: Sequence[Segment]) -> tuple[BaseGeometry, list[Segment]]:
    """Material encerrado por los anillos que forman los tramos, y los tramos que no cierran.

    Un anillo dentro de un número impar de anillos es un hueco (el patio de un contorno); los
    anillos que se solapan sin contenerse se suman, como muros dibujados como rectángulos sueltos.
    """
    merged = line_merge(MultiLineString([[s.start, s.end] for s in segments]))
    lines = list(getattr(merged, "geoms", [merged]))
    rings = [Polygon(line.coords) for line in lines if line.is_ring]
    rings = [ring for ring in rings if ring.is_valid and ring.area > 0]
    open_segments = [
        Segment(a, b)
        for line in lines
        if not line.is_ring
        for a, b in zip(line.coords, line.coords[1:], strict=False)
    ]
    depth = [sum(other.contains(ring) for other in rings if other is not ring) for ring in rings]
    material: BaseGeometry = Polygon()
    for level in sorted(set(depth)):
        layer = unary_union([ring for ring, d in zip(rings, depth, strict=True) if d == level])
        material = material.union(layer) if level % 2 == 0 else material.difference(layer)
    return material, open_segments


def boundary_segments(material: BaseGeometry) -> list[Segment]:
    """Caras del material: los lados de sus anillos, sin vértices intermedios colineales."""
    faces = []
    for polygon in getattr(material, "geoms", [material]):
        if polygon.is_empty:
            continue
        for ring in [polygon.exterior, *polygon.interiors]:
            coords = list(simplify(ring, LENGTH_TOL / 10).coords)
            faces += [
                Segment(a, b)
                for a, b in zip(coords, coords[1:], strict=False)
                if math.dist(a, b) > LENGTH_TOL
            ]
    return faces


def _is_material(material: BaseGeometry, rules: BuildRules, strip: Polygon) -> bool:
    return bool(strip.difference(material).area <= (1 - rules.material_share) * strip.area)


def _is_clear(segments: Sequence[Segment], strip: Polygon) -> bool:
    """Ninguna línea atraviesa la franja: entre las dos caras no hay nada dibujado."""
    inner = strip.buffer(-LENGTH_TOL)
    return inner.is_empty or not any(
        LineString([s.start, s.end]).intersects(inner) for s in segments
    )


# --- 2. Pares de caras -----------------------------------------------------------------------


def pair_faces(
    faces: Sequence[Segment],
    layer: str,
    rules: BuildRules,
    accept: Callable[[Polygon], bool],
) -> list[WallPiece]:
    """Tramos de muro de pares de caras paralelas. Los pares más próximos van primero y cada
    trozo de cara se usa en un solo par."""
    candidates: list[tuple[float, ParallelGroup, Placed, Placed, float, float]] = []
    for group in parallel_groups(faces, ANGLE_TOL_DEG):
        for position, a in enumerate(group.placed):
            for b in neighbours(group.placed, position, rules.max_thickness_m + LENGTH_TOL):
                gap = b.offset - a.offset
                s0, s1 = max(a.s0, b.s0), min(a.s1, b.s1)
                if gap >= rules.min_thickness_m - LENGTH_TOL and s1 - s0 > LENGTH_TOL:
                    candidates.append((gap, group, a, b, s0, s1))
    used: dict[int, list[tuple[float, float]]] = {}
    pieces = []
    for gap, group, a, b, s0, s1 in sorted(candidates, key=lambda c: (c[0], c[4])):
        if _taken(used, a.index, s0, s1) or _taken(used, b.index, s0, s1):
            continue
        d, n = group.direction, group.normal
        strip = Polygon(
            [
                _at(d, n, s, t)
                for s, t in ((s0, a.offset), (s1, a.offset), (s1, b.offset), (s0, b.offset))
            ]
        )
        if not accept(strip):
            continue
        used.setdefault(a.index, []).append((s0, s1))
        used.setdefault(b.index, []).append((s0, s1))
        mid = (a.offset + b.offset) / 2
        pieces.append(WallPiece(_at(d, n, s0, mid), _at(d, n, s1, mid), gap, layer))
    return pieces


def _taken(used: dict[int, list[tuple[float, float]]], index: int, s0: float, s1: float) -> bool:
    return any(min(s1, u1) - max(s0, u0) > LENGTH_TOL for u0, u1 in used.get(index, []))


def _at(d: Point2D, n: Point2D, s: float, t: float) -> Point2D:
    return (d[0] * s + n[0] * t, d[1] * s + n[1] * t)


# --- 3. Unión de colineales ------------------------------------------------------------------


def merge_collinear(
    pieces: Sequence[WallPiece], material: BaseGeometry, symbols: BaseGeometry, rules: BuildRules
) -> list[WallDraft]:
    """Une los tramos de una misma recta, capa y espesor. Un hueco vacío entre dos tramos se
    salva como vano candidato, salvo que sea más largo que `max_void_width_m` y no tenga
    símbolo de puerta o ventana: entonces los muros quedan separados."""
    return [
        wall for cluster in _clusters(pieces) for wall in _merge(cluster, material, symbols, rules)
    ]


def _merge(
    cluster: Sequence[WallPiece], solid: BaseGeometry, symbols: BaseGeometry, rules: BuildRules
) -> list[WallDraft]:
    ref = max(cluster, key=lambda p: math.dist(p.start, p.end))
    origin = ref.start
    d = _unit(ref.start, ref.end)
    n = (-d[1], d[0])
    offset = sum(_dot(_sub(p.start, origin), n) for p in cluster) / len(cluster)

    def point(s: float) -> Point2D:
        return (origin[0] + d[0] * s + n[0] * offset, origin[1] + d[1] * s + n[1] * offset)

    def draft(s0: float, s1: float, gaps: list[Gap]) -> WallDraft:
        return WallDraft(point(s0), point(s1), ref.thickness, ref.layer, gaps)

    spans = sorted(
        sorted((_dot(_sub(p.start, origin), d), _dot(_sub(p.end, origin), d))) for p in cluster
    )
    walls = []
    start, end = spans[0]
    gaps: list[Gap] = []
    for s0, s1 in spans[1:]:
        if s0 <= end + LENGTH_TOL:
            end = max(end, s1)
            continue
        voids = _voids(LineString([point(end), point(s0)]), solid)
        if any(
            v.length > rules.max_void_width_m
            and not symbols.intersects(v.buffer(ref.thickness / 2 + rules.symbol_search_m))
            for v in voids
        ):
            walls.append(draft(start, end, gaps))
            start, gaps = s0, []
        else:
            gaps += [Gap(v.coords[0], v.coords[-1]) for v in voids]
        end = s1
    walls.append(draft(start, end, gaps))
    return walls


def _voids(line: LineString, solid: BaseGeometry) -> list[LineString]:
    rest = line.difference(solid)
    return [g for g in getattr(rest, "geoms", [rest]) if not g.is_empty and g.length > LENGTH_TOL]


def _clusters(pieces: Sequence[WallPiece]) -> list[list[WallPiece]]:
    """Grupos de tramos sobre la misma recta, con la misma capa y el mismo espesor."""
    parent = list(range(len(pieces)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, a in enumerate(pieces):
        for j in range(i + 1, len(pieces)):
            if _collinear(a, pieces[j]):
                parent[find(j)] = find(i)
    groups: dict[int, list[WallPiece]] = {}
    for i, piece in enumerate(pieces):
        groups.setdefault(find(i), []).append(piece)
    return list(groups.values())


def _collinear(a: WallPiece, b: WallPiece) -> bool:
    if a.layer != b.layer or abs(a.thickness - b.thickness) > LENGTH_TOL:
        return False
    da, db = _unit(a.start, a.end), _unit(b.start, b.end)
    if abs(_cross(da, db)) > MIN_SIN:
        return False
    n = (-da[1], da[0])
    return all(abs(_dot(_sub(p, a.start), n)) <= LENGTH_TOL for p in (b.start, b.end))


# --- 4. Uniones en L y en T ------------------------------------------------------------------


def resolve_joints(walls: list[WallDraft], slack: float) -> None:
    """Lleva cada extremo hasta el eje del muro no paralelo con el que se une.

    El solape de las caras deja el extremo corto, como mucho, en V.t / (2·sen θ) + W.t / (2·tan θ)
    respecto del eje de V; dentro de ese alcance (más la holgura), el extremo pasa a la
    intersección de ejes. Un extremo que se pasa del eje de V sin salir de su huella se recorta.
    En una L se mueven los dos muros; en una T, solo el que llega.
    """
    new_ends = [
        (_joint(w, w.start, w.end, walls, slack), _joint(w, w.end, w.start, walls, slack))
        for w in walls
    ]
    for wall, (start, end) in zip(walls, new_ends, strict=True):
        wall.start, wall.end = start, end


def bridge_corner_openings(
    walls: list[WallDraft], material: BaseGeometry, symbols: BaseGeometry, rules: BuildRules
) -> None:
    """Un vano pegado a una esquina deja su muro sin tramo entre el vano y el muro que llega:
    el extremo queda en la jamba. Si desde ahí hasta un muro no paralelo solo hay vacío, a lo
    sumo `max_void_width_m`, y ese vacío tiene símbolo de puerta o ventana, el muro se alarga
    hasta ese eje y el vacío queda como hueco."""
    for wall in walls:
        for at_start in (True, False):
            end, other_end = (wall.start, wall.end) if at_start else (wall.end, wall.start)
            u = _unit(other_end, end)
            best: tuple[float, Point2D] | None = None
            for other in walls:
                crossing = _crossing(wall, end, u, other)
                if crossing is None:
                    continue
                s, r, sin, _ = crossing
                margin = wall.thickness / (2 * sin) + rules.joint_slack_m
                reach = rules.max_void_width_m + other.thickness / (2 * sin)
                if 0 < s <= reach and -margin <= r <= other.length + margin:
                    if best is None or s < best[0]:
                        best = (s, (end[0] + u[0] * s, end[1] + u[1] * s))
            if best is None:
                continue
            target = best[1]
            voids = _voids(LineString([end, target]), material)
            if len(voids) != 1 or math.dist(voids[0].coords[0], end) > LENGTH_TOL:
                continue
            void = voids[0]
            if not symbols.intersects(
                void.buffer(wall.thickness / 2 + rules.symbol_search_m, cap_style="flat")
            ):
                continue
            wall.gaps.append(Gap(void.coords[0], void.coords[-1]))
            if at_start:
                wall.start = target
            else:
                wall.end = target


def _crossing(
    wall: WallDraft, end: Point2D, u: Point2D, other: WallDraft
) -> tuple[float, float, float, float] | None:
    """Dónde corta la recta que sale de `end` en la dirección u el eje de `other`: (s a lo
    largo de u, r a lo largo de `other` desde su inicio, sen θ, cotangente de θ), o None si
    son paralelos."""
    if other is wall:
        return None
    v = _unit(other.start, other.end)
    cross = _cross(u, v)
    sin = abs(cross)
    if sin < MIN_SIN:
        return None
    # end + s·u = other.start + r·v
    w = _sub(other.start, end)
    return _cross(w, v) / cross, _cross(w, u) / cross, sin, abs(_dot(u, v)) / sin


def _joint(
    wall: WallDraft, end: Point2D, other_end: Point2D, walls: Sequence[WallDraft], slack: float
) -> Point2D:
    u = _unit(other_end, end)
    best: tuple[float, Point2D] | None = None
    for other in walls:
        crossing = _crossing(wall, end, u, other)
        if crossing is None:
            continue
        s, r, sin, cot = crossing
        reach = other.thickness / (2 * sin) + wall.thickness * cot / 2 + slack
        overshoot = other.thickness / (2 * sin) + slack
        margin = wall.thickness / (2 * sin) + slack
        if -overshoot <= s <= reach and -margin <= r <= other.length + margin:
            if best is None or abs(s) < best[0]:
                best = (abs(s), (end[0] + u[0] * s, end[1] + u[1] * s))
    return end if best is None else best[1]


# --- Utilidades ------------------------------------------------------------------------------


def _sub(a: Point2D, b: Point2D) -> Point2D:
    return (a[0] - b[0], a[1] - b[1])


def _dot(a: Point2D, b: Point2D) -> float:
    return a[0] * b[0] + a[1] * b[1]


def _cross(a: Point2D, b: Point2D) -> float:
    return a[0] * b[1] - a[1] * b[0]


def _unit(a: Point2D, b: Point2D) -> Point2D:
    length = math.dist(a, b)
    return ((b[0] - a[0]) / length, (b[1] - a[1]) / length)


def _fmt(point: Point2D) -> str:
    return f"({point[0]:.2f}, {point[1]:.2f})"


def _warning(code: str, message: str, ids: list[str] | None = None) -> Problem:
    return Problem(code=code, severity="warning", ids=ids or [], message=message)
