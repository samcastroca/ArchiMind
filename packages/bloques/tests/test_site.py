"""El vano en su muro: el lado de adentro, la inserción y la cara libre."""

import math
from typing import Any

import pytest
from archimind_bloques.resolve import FitError
from archimind_bloques.site import Site, free_runs, insertion, is_circulation, locate, span
from archimind_schema import ID_PREFIXES, Project, Space
from hypothesis import given
from hypothesis import strategies as st

ABOVE = (0.0, 0.1, 6.0, 4.0)  # a la izquierda del eje (0, 0) → (6, 0): 23.4 m²
BELOW = (0.0, -2.0, 6.0, -0.1)  # a la derecha: 11.4 m²


def _space(space_id: str, name: str, box: tuple[float, ...], **changes: Any) -> dict[str, Any]:
    x0, y0, x1, y1 = box
    return {
        "id": space_id,
        "level_id": "niv-0001",
        "name": name,
        "polygon": {"exterior": [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]},
        "category": "useful",
    } | changes


def _project(
    *spaces: dict[str, Any], axis: list[tuple[float, float]] | None = None, walls: Any = ()
) -> Project:
    return Project.model_validate(
        {
            "id": "p",
            "name": "p",
            "scale_confirmed": True,
            "levels": [{"id": "niv-0001", "name": "PB", "elevation": 0, "default_height": 2.6}],
            "walls": [
                {
                    "id": "muro-0001",
                    "level_id": "niv-0001",
                    "axis": axis or [(0, 0), (6, 0)],
                    "thickness": 0.20,
                },
                *walls,
            ],
            "openings": [
                {
                    "id": "vano-0001",
                    "wall_id": "muro-0001",
                    "kind": "door",
                    "offset": 2.0,
                    "width": 0.8,
                    "height": 2.1,
                    "sill_height": 0,
                }
            ],
            "spaces": list(spaces),
            "next_ids": dict.fromkeys(ID_PREFIXES, 100),
        }
    )


def _locate(project: Project, opens_into: str | None = None) -> Site:
    return locate(project, project.walls[0], project.openings[0], opens_into)


def test_an_exterior_wall_has_its_room_inside() -> None:
    site = _locate(_project(_space("esp-0001", "Dormitorio", ABOVE)))
    assert (site.start, site.end, site.side) == ((2.0, 0.0), (2.8, 0.0), "left")
    assert site.room is not None and site.room.id == "esp-0001"
    assert site.note == "muro exterior: adentro es Dormitorio (esp-0001)"


def test_the_side_follows_the_direction_of_the_axis() -> None:
    project = _project(_space("esp-0001", "Dormitorio", ABOVE), axis=[(6, 0), (0, 0)])
    assert _locate(project).side == "right"


@pytest.mark.parametrize(
    "below",
    [
        _space("esp-0002", "Pasillo", BELOW),
        _space("esp-0002", "CIRCULACIÓN norte", BELOW),
        _space("esp-0002", "Estar", BELOW, category="circulation"),
    ],
)
def test_a_door_never_opens_into_the_circulation(below: dict[str, Any]) -> None:
    site = _locate(_project(_space("esp-0001", "Dormitorio", ABOVE), below))
    assert site.side == "left"  # hacia el dormitorio, aunque sea el recinto más grande
    assert "no hacia la circulación" in site.note


def test_between_two_rooms_it_opens_into_the_smaller_one() -> None:
    site = _locate(_project(_space("esp-0001", "Estar", ABOVE), _space("esp-0002", "Baño", BELOW)))
    assert site.side == "right"
    assert site.note == (
        "abre hacia el recinto más pequeño, Baño (esp-0002) (11.40 m²), y no hacia Estar "
        "(esp-0001) (23.40 m²)"
    )


def test_opens_into_decides() -> None:
    project = _project(_space("esp-0001", "Estar", ABOVE), _space("esp-0002", "Baño", BELOW))
    site = _locate(project, "esp-0001")
    assert site.side == "left" and site.note == "abre hacia Estar (esp-0001), como se pidió"


def test_opens_into_must_be_beside_the_opening() -> None:
    far = _space("esp-0003", "Cocina", (10, 0, 12, 2))
    project = _project(_space("esp-0001", "Estar", ABOVE), far)
    with pytest.raises(FitError, match="no está junto a vano-0001: a sus lados hay Estar"):
        _locate(project, "esp-0003")
    with pytest.raises(FitError, match="No existe el recinto esp-0099"):
        _locate(project, "esp-0099")


def test_without_rooms_inside_is_on_the_left_with_a_warning() -> None:
    other_level = _space("esp-0001", "Dormitorio", ABOVE, level_id="niv-0002")
    project = _project()
    project.spaces.append(Space.model_validate(other_level))
    site = _locate(project)
    assert site.side == "left" and site.room is None
    assert "no hay recintos a los lados de vano-0001" in site.note


def test_an_opening_over_a_bend_of_the_axis_is_rejected() -> None:
    project = _project(axis=[(0, 0), (2.5, 0), (2.5, 3)])
    with pytest.raises(FitError, match="cae sobre un quiebre del eje de muro-0001"):
        span(project.walls[0], project.openings[0])


def test_insertion_point_and_rotation() -> None:
    left = Site((1.0, 1.0), (1.0, 2.0), "left", None, "")
    right = Site((1.0, 1.0), (1.0, 2.0), "right", None, "")
    assert insertion(left) == ((1.0, 1.0), 90.0)
    assert insertion(right) == ((1.0, 2.0), 270.0)


def _to_world(site: Site, local: tuple[float, float]) -> tuple[float, float]:
    (px, py), rotation = insertion(site)
    a = math.radians(rotation)
    x, y = local
    return px + x * math.cos(a) - y * math.sin(a), py + x * math.sin(a) + y * math.cos(a)


@given(
    angle=st.floats(0, 2 * math.pi),
    width=st.floats(0.3, 3.0),
    side=st.sampled_from(["left", "right"]),
)
def test_the_block_spans_the_opening_and_looks_inside(
    angle: float, width: float, side: Any
) -> None:
    start = (3.0, -2.0)
    end = (start[0] + width * math.cos(angle), start[1] + width * math.sin(angle))
    site = Site(start, end, side, None, "")

    corners = {_to_world(site, (0, 0)), _to_world(site, (width, 0))}
    assert all(any(math.dist(c, p) < 1e-9 for c in corners) for p in (start, end))
    x, y = _to_world(site, (width / 2, 1.0))  # un punto «adentro» del bloque
    cross = (end[0] - start[0]) * (y - start[1]) - (end[1] - start[1]) * (x - start[0])
    assert (cross > 0) == (side == "left")


def test_free_runs_stop_at_the_walls_that_cut_each_face() -> None:
    project = _project(
        axis=[(0, 0), (10, 0)],
        walls=[
            {"id": "muro-0002", "level_id": "niv-0001", "axis": [(3, 0), (3, 4)], "thickness": 0.1},
            {
                "id": "muro-0003",
                "level_id": "niv-0001",
                "axis": [(8, 0), (8, -3)],
                "thickness": 0.1,
            },
        ],
    )
    project.openings[0].offset, project.openings[0].width = 4.0, 1.0
    wall, opening = project.walls[0], project.openings[0]

    before, after = free_runs(project, wall, opening, "left")
    assert (before.wall_id, after.wall_id) == ("muro-0002", None)
    assert before.length == pytest.approx(0.95) and after.length == pytest.approx(5.0)

    before, after = free_runs(project, wall, opening, "right")
    assert (before.wall_id, after.wall_id) == (None, "muro-0003")
    assert before.length == pytest.approx(4.0) and after.length == pytest.approx(2.95)


@pytest.mark.parametrize(
    ("name", "category", "expected"),
    [
        ("Hall de entrada", "useful", True),
        ("Vestíbulo", "useful", True),
        ("Sala", "circulation", True),
        ("Sala", "useful", False),
    ],
)
def test_circulation(name: str, category: str, expected: bool) -> None:
    space = Space.model_validate(_space("esp-0001", name, ABOVE, category=category))
    assert is_circulation(space) is expected
