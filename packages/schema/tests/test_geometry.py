import math

from archimind_schema import (
    Point2D,
    Space,
    SpacePolygon,
    Wall,
    space_area,
    wall_length,
    wall_polygon,
)
from hypothesis import given
from hypothesis import strategies as st
from schema_strategies import coords, sizes, space_polygons, thicknesses, wall_axes
from shapely import LineString, affinity

angles = st.floats(min_value=-360, max_value=360, allow_nan=False)


def _move(points: list[Point2D], dx: float, dy: float, angle: float) -> list[Point2D]:
    line = affinity.translate(affinity.rotate(LineString(points), angle, origin=(0, 0)), dx, dy)
    return [(x, y) for x, y in line.coords]


def _space(polygon: SpacePolygon) -> Space:
    return Space(id="esp-0001", level_id="niv-0001", name="", polygon=polygon, category="useful")


@given(space_polygons, coords, coords, angles)
def test_area_de_espacio_invariante_a_traslacion_y_rotacion(
    polygon: SpacePolygon, dx: float, dy: float, angle: float
) -> None:
    moved = SpacePolygon(
        exterior=_move(polygon.exterior, dx, dy, angle),
        holes=[_move(hole, dx, dy, angle) for hole in polygon.holes],
    )
    assert math.isclose(
        space_area(_space(polygon)), space_area(_space(moved)), rel_tol=1e-7, abs_tol=1e-9
    )


@given(wall_axes(), thicknesses, coords, coords, angles)
def test_area_de_muro_invariante_a_traslacion_y_rotacion(
    axis: list[Point2D], thickness: float, dx: float, dy: float, angle: float
) -> None:
    wall = Wall(id="muro-0001", level_id="niv-0001", axis=axis, thickness=thickness)
    moved = wall.model_copy(update={"axis": _move(axis, dx, dy, angle)})
    assert math.isclose(wall_polygon(wall).area, wall_polygon(moved).area, rel_tol=1e-6)


@given(coords, coords, sizes, st.floats(0, 2 * math.pi), thicknesses)
def test_muro_recto_tiene_area_longitud_por_espesor(
    x: float, y: float, length: float, angle: float, thickness: float
) -> None:
    end = (x + length * math.cos(angle), y + length * math.sin(angle))
    wall = Wall(id="muro-0001", level_id="niv-0001", axis=[(x, y), end], thickness=thickness)
    assert math.isclose(wall_length(wall), length, rel_tol=1e-9)
    assert math.isclose(wall_polygon(wall).area, length * thickness, rel_tol=1e-6)


def test_area_descuenta_huecos() -> None:
    polygon = SpacePolygon(
        exterior=[(0, 0), (4, 0), (4, 3), (0, 3)],
        holes=[[(1, 1), (2, 1), (2, 2), (1, 2)]],
    )
    assert space_area(_space(polygon)) == 11
