"""Comparación de un modelo con su caso golden, con tolerancia y sin mirar los IDs.

Solo compara lo que un plano DXF 2D transmite: no las alturas de vano, los antepechos, la
elevación de los niveles, las categorías, las anotaciones, `layer_mapping` ni `next_ids`.
"""

import math
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

from archimind_schema import Opening, Point2D, Project, Space, Wall, space_area
from shapely import LineString, Polygon

GOLDEN_DIR = Path(__file__).resolve().parents[1] / "golden"
COORD_TOL = 0.01
AREA_REL_TOL = 0.005

T = TypeVar("T")


def load_expected(case: str) -> Project:
    path = GOLDEN_DIR / case / "expected.json"
    if not path.is_file():
        raise FileNotFoundError(f"No existe el caso golden '{case}' ({path})")
    return Project.model_validate_json(path.read_text(encoding="utf-8"))


def assert_matches_golden(project: Project, case: str) -> None:
    """Falla con todas las diferencias a la vez frente a tests/golden/<case>/expected.json."""
    expected = load_expected(case)
    failures = [
        *_compare_scalars(project, expected),
        *_compare_walls(project, expected),
        *_compare_openings(project, expected),
        *_compare_spaces(project, expected),
    ]
    if failures:
        raise AssertionError(
            f"El modelo no coincide con el golden '{case}':\n- " + "\n- ".join(failures)
        )


def _compare_scalars(actual: Project, expected: Project) -> list[str]:
    failures = []
    if actual.scale_confirmed != expected.scale_confirmed:
        failures.append(
            f"scale_confirmed es {actual.scale_confirmed}; se esperaba {expected.scale_confirmed}"
        )
    if len(actual.levels) != len(expected.levels):
        failures.append(f"{len(actual.levels)} niveles; se esperaban {len(expected.levels)}")
    return failures


def _match(
    expected: list[T], actual: list[T], close: Callable[[T, T], bool]
) -> tuple[list[T], list[T]]:
    """Empareja cada esperado con un real cercano. Devuelve los que quedan sin pareja."""
    pending = list(actual)
    missing = []
    for item in expected:
        partner = next((candidate for candidate in pending if close(item, candidate)), None)
        if partner is None:
            missing.append(item)
        else:
            pending.remove(partner)
    return missing, pending


def _same_point(a: Point2D, b: Point2D) -> bool:
    return math.dist(a, b) <= COORD_TOL


def _same_axis(a: Wall, b: Wall) -> bool:
    if len(a.axis) != len(b.axis):
        return False
    return all(map(_same_point, a.axis, b.axis)) or all(map(_same_point, a.axis, reversed(b.axis)))


def _compare_walls(actual: Project, expected: Project) -> list[str]:
    failures = []
    if len(actual.walls) != len(expected.walls):
        failures.append(f"{len(actual.walls)} muros; se esperaban {len(expected.walls)}")

    def close(e: Wall, a: Wall) -> bool:
        return (
            _same_axis(e, a)
            and abs(e.thickness - a.thickness) <= COORD_TOL
            and e.source_layer == a.source_layer
        )

    missing, extra = _match(expected.walls, actual.walls, close)
    failures += [
        f"falta el muro de eje {_fmt(w.axis)}, espesor {w.thickness:.2f}, capa {w.source_layer!r}"
        for w in missing
    ]
    failures += [
        f"sobra el muro de eje {_fmt(w.axis)}, espesor {w.thickness:.2f}, capa {w.source_layer!r}"
        for w in extra
    ]
    return failures


def opening_midpoint(project: Project, opening: Opening) -> Point2D:
    """Centro del vano en coordenadas del plano: no depende del sentido del eje ni de los IDs."""
    wall = next(w for w in project.walls if w.id == opening.wall_id)
    point = LineString(wall.axis).interpolate(opening.offset + opening.width / 2)
    return (point.x, point.y)


def _compare_openings(actual: Project, expected: Project) -> list[str]:
    failures = []
    for kind, count in sorted(Counter(o.kind for o in expected.openings).items()):
        actual_count = sum(o.kind == kind for o in actual.openings)
        if actual_count != count:
            failures.append(f"{actual_count} vanos de tipo {kind}; se esperaban {count}")
    for kind in sorted({o.kind for o in actual.openings} - {o.kind for o in expected.openings}):
        failures.append(f"sobran vanos de tipo {kind}")

    def located(project: Project) -> list[tuple[Opening, Point2D]]:
        return [(o, opening_midpoint(project, o)) for o in project.openings]

    def close(e: tuple[Opening, Point2D], a: tuple[Opening, Point2D]) -> bool:
        return (
            e[0].kind == a[0].kind
            and _same_point(e[1], a[1])
            and abs(e[0].width - a[0].width) <= COORD_TOL
        )

    missing, extra = _match(located(expected), located(actual), close)
    failures += [f"falta {o.kind} de {o.width:.2f} m centrada en {_fmt([p])}" for o, p in missing]
    failures += [f"sobra {o.kind} de {o.width:.2f} m centrada en {_fmt([p])}" for o, p in extra]
    return failures


def _space_shape(space: Space) -> Polygon:
    return Polygon(space.polygon.exterior, space.polygon.holes)


def _compare_spaces(actual: Project, expected: Project) -> list[str]:
    failures = []
    expected_names = Counter(s.name for s in expected.spaces)
    actual_names = Counter(s.name for s in actual.spaces)
    if expected_names != actual_names:
        failures.append(
            f"nombres de espacios {sorted(actual_names.elements())}; se esperaban "
            f"{sorted(expected_names.elements())}"
        )

    def close(e: Space, a: Space) -> bool:
        return (
            e.name == a.name
            and _area_close(space_area(a), space_area(e))
            and _space_shape(e).hausdorff_distance(_space_shape(a)) <= COORD_TOL
        )

    missing, _ = _match(expected.spaces, actual.spaces, close)
    for space in missing:
        candidates = [s for s in actual.spaces if s.name == space.name]
        detail = (
            "; áreas encontradas: " + ", ".join(f"{space_area(s):.2f}" for s in candidates)
            if candidates
            else ""
        )
        failures.append(
            f"el espacio {space.name!r} ({space_area(space):.2f} m²) no coincide en área "
            f"(±{AREA_REL_TOL:.1%}) o contorno (±{COORD_TOL * 100:.0f} cm){detail}"
        )
    actual_total = sum(map(space_area, actual.spaces))
    expected_total = sum(map(space_area, expected.spaces))
    if not _area_close(actual_total, expected_total):
        failures.append(
            f"área total {actual_total:.2f} m²; se esperaban {expected_total:.2f} m² "
            f"(±{AREA_REL_TOL:.1%})"
        )
    return failures


def _area_close(actual: float, expected: float) -> bool:
    return abs(actual - expected) <= AREA_REL_TOL * expected


def _fmt(points: list[Point2D]) -> str:
    return " → ".join(f"({x:.3f}, {y:.3f})" for x, y in points)
