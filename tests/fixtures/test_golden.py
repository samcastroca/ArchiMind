import math

import ezdxf
import pytest
from archimind_schema import Point2D, Project, validate, wall_length
from cases import CASES, expected_project
from ezdxf import bbox, units
from golden import GOLDEN_DIR, assert_matches_golden, load_expected
from hypothesis import given
from hypothesis import strategies as st

CASE_NAMES = sorted(CASES)


@pytest.mark.parametrize("case", CASE_NAMES)
def test_expected_json_is_the_hand_written_model(case: str) -> None:
    assert load_expected(case) == expected_project(case)


@pytest.mark.parametrize("case", CASE_NAMES)
def test_expected_model_has_no_problems(case: str) -> None:
    assert validate(load_expected(case)) == []


@pytest.mark.parametrize("case", CASE_NAMES)
def test_expected_matches_itself(case: str) -> None:
    assert_matches_golden(load_expected(case), case)


def _read_dxf(case: str) -> ezdxf.document.Drawing:
    return ezdxf.readfile(GOLDEN_DIR / case / "input.dxf")


def _wall_extents(case: str) -> bbox.BoundingBox:
    doc = _read_dxf(case)
    layer = CASES[case].style.layers.wall
    return bbox.extents(doc.modelspace().query(f'*[layer=="{layer}"]'))


@pytest.mark.parametrize("case", CASE_NAMES)
def test_input_dxf_has_units_layers_and_wall_entities(case: str) -> None:
    style = CASES[case].style
    doc = _read_dxf(case)
    assert doc.header["$INSUNITS"] == style.insunits
    for layer in vars(style.layers).values():
        assert layer in doc.layers
    on_wall_layer = doc.modelspace().query(f'*[layer=="{style.layers.wall}"]')
    types = {entity.dxftype() for entity in on_wall_layer}
    if CASES[case].extras is not None:
        types.discard("HATCH")  # los sombreados de muro que añade el caso
    assert types == ({"LWPOLYLINE"} if style.wall_entities == "polyline" else {"LINE"})


def test_chaotic_case_puts_walls_on_layer_zero() -> None:
    assert CASES["apto_capas_caoticas"].style.layers.wall == "0"
    assert all(wall.source_layer == "0" for wall in load_expected("apto_capas_caoticas").walls)


def test_millimetre_case_is_the_apartment_scaled_by_1000() -> None:
    assert _read_dxf("milimetros").header["$INSUNITS"] == units.MM
    metres, millimetres = _wall_extents("apto_2hab"), _wall_extents("milimetros")
    assert millimetres.extmin.isclose(metres.extmin * 1000, abs_tol=1e-6)
    assert millimetres.extmax.isclose(metres.extmax * 1000, abs_tol=1e-6)


# --- Tolerancia del helper ---------------------------------------------------------------


def _rebuild(project: Project) -> Project:
    return Project.model_validate(project.model_dump())


def _translated(project: Project, dx: float, dy: float) -> Project:
    def move(points: list[Point2D]) -> list[Point2D]:
        return [(x + dx, y + dy) for x, y in points]

    moved = project.model_copy(deep=True)
    for wall in moved.walls:
        wall.axis = move(wall.axis)
    for space in moved.spaces:
        space.polygon.exterior = move(space.polygon.exterior)
        space.polygon.holes = [move(hole) for hole in space.polygon.holes]
    return _rebuild(moved)


def _renumbered(project: Project, shift: int) -> Project:
    """Mismos objetos con otros IDs, como los asignaría un importador."""
    renamed = project.model_copy(deep=True)
    mapping: dict[str, str] = {}

    def rename(old: str) -> str:
        prefix, number = old.rsplit("-", 1)
        mapping[old] = f"{prefix}-{int(number) + shift:04d}"
        return mapping[old]

    for level in renamed.levels:
        level.id = rename(level.id)
    for wall in renamed.walls:
        wall.id, wall.level_id = rename(wall.id), mapping[wall.level_id]
    for opening in renamed.openings:
        opening.id, opening.wall_id = rename(opening.id), mapping[opening.wall_id]
    for space in renamed.spaces:
        space.id, space.level_id = rename(space.id), mapping[space.level_id]
    renamed.next_ids = {prefix: n + shift for prefix, n in renamed.next_ids.items()}
    return _rebuild(renamed)


def _reversed_walls(project: Project, flags: list[bool]) -> Project:
    """Invierte el sentido de algunos ejes; los vanos se miden entonces desde el otro extremo."""
    flipped = project.model_copy(deep=True)
    for wall, flip in zip(flipped.walls, flags, strict=False):
        if not flip:
            continue
        length = wall_length(wall)
        wall.axis = wall.axis[::-1]
        for opening in flipped.openings:
            if opening.wall_id == wall.id:
                opening.offset = length - opening.offset - opening.width
    return _rebuild(flipped)


cases = st.sampled_from(CASE_NAMES)
small = st.floats(-0.006, 0.006)


@given(
    case=cases,
    dx=small,
    dy=small,
    shift=st.integers(1, 500),
    flags=st.lists(st.booleans(), min_size=8, max_size=8),
    data=st.data(),
)
def test_equivalent_models_match(
    case: str, dx: float, dy: float, shift: int, flags: list[bool], data: st.DataObject
) -> None:
    project = _reversed_walls(_renumbered(_translated(load_expected(case), dx, dy), shift), flags)
    project.walls = data.draw(st.permutations(project.walls))
    project.openings = data.draw(st.permutations(project.openings))
    project.spaces = data.draw(st.permutations(project.spaces))
    assert_matches_golden(project, case)


def _assert_fails(project: Project, case: str) -> None:
    with pytest.raises(AssertionError, match="no coincide con el golden"):
        assert_matches_golden(project, case)


@given(case=cases, angle=st.floats(0, 2 * math.pi), distance=st.floats(0.015, 1.0))
def test_moved_model_fails(case: str, angle: float, distance: float) -> None:
    dx, dy = distance * math.cos(angle), distance * math.sin(angle)
    _assert_fails(_translated(load_expected(case), dx, dy), case)


@given(case=cases, data=st.data())
def test_space_area_off_by_one_percent_fails(case: str, data: st.DataObject) -> None:
    project = load_expected(case)
    space = data.draw(st.sampled_from(project.spaces))
    # Escalar en x un 1 % sube el área un 1 %, fuera del ±0.5 %.
    x0 = space.polygon.exterior[0][0]
    space.polygon.exterior = [(x0 + (x - x0) * 1.01, y) for x, y in space.polygon.exterior]
    _assert_fails(_rebuild(project), case)


@given(case=cases, data=st.data())
def test_renamed_space_fails(case: str, data: st.DataObject) -> None:
    project = load_expected(case)
    data.draw(st.sampled_from(project.spaces)).name += " bis"
    _assert_fails(project, case)


@given(case=cases, data=st.data())
def test_missing_wall_fails(case: str, data: st.DataObject) -> None:
    project = load_expected(case)
    wall = data.draw(st.sampled_from(project.walls))
    project.walls.remove(wall)
    project.openings = [o for o in project.openings if o.wall_id != wall.id]
    _assert_fails(project, case)


@given(case=cases, data=st.data())
def test_missing_opening_fails(case: str, data: st.DataObject) -> None:
    project = load_expected(case)
    project.openings.remove(data.draw(st.sampled_from(project.openings)))
    _assert_fails(project, case)


def test_failure_lists_every_difference() -> None:
    project = load_expected("rect_simple")
    project.spaces[0].name = "Oficina"
    project.openings.clear()
    with pytest.raises(AssertionError) as error:
        assert_matches_golden(project, "rect_simple")
    message = str(error.value)
    assert "nombres de espacios ['Oficina']" in message
    assert "0 vanos de tipo door; se esperaban 1" in message
