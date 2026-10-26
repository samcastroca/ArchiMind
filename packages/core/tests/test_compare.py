import pytest
from archimind_core import PRELIMINARY_LABEL, compare_versions
from archimind_schema import Project, SpacePolygon, Wall, new_id, space_area
from cases import expected_project


def _scaled_space(project: Project, name: str, factor: float) -> str:
    """Estira en x el espacio `name` para que su área se multiplique por `factor`."""
    space = next(s for s in project.spaces if s.name == name)
    x0 = min(x for x, _ in space.polygon.exterior)
    space.polygon = SpacePolygon(
        exterior=[(x0 + (x - x0) * factor, y) for x, y in space.polygon.exterior]
    )
    return space.id


def test_identical_versions_have_no_changes() -> None:
    diff = compare_versions(expected_project("apto_2hab"), expected_project("apto_2hab"))
    assert diff.spaces_changed == []
    assert diff.walls_added == diff.walls_removed == diff.walls_moved == []
    assert diff.openings_modified == []
    assert not diff.preliminary and diff.label is None


def test_detects_every_kind_of_change() -> None:
    before = expected_project("apto_2hab")
    after = before.model_copy(deep=True)
    grown = _scaled_space(after, "Habitación 1", 1.01)
    _scaled_space(after, "Habitación 2", 1.003)  # por debajo del 0.5 %
    removed = after.walls.pop(5)  # tabique entre habitaciones
    moved = after.walls[4]
    moved.axis = [(3.6, 0.0), (3.6, 6.5)]
    added = new_id(after, "muro")
    after.walls.append(
        Wall(id=added, level_id=after.levels[0].id, axis=[(6, 0), (6, 2)], thickness=0.10)
    )
    widened = after.openings[0]
    widened.width += 0.10

    diff = compare_versions(before, after)

    assert [c.id for c in diff.spaces_changed] == [grown]
    change = diff.spaces_changed[0]
    assert change.name == "Habitación 1"
    assert change.relative_change == pytest.approx(0.01)
    assert change.area_after == pytest.approx(space_area(after.spaces[0]))
    assert diff.walls_added == [added]
    assert diff.walls_removed == [removed.id]
    assert diff.walls_moved == [moved.id]
    assert diff.openings_modified == [widened.id]


def test_thickness_change_counts_as_moved() -> None:
    before = expected_project("rect_simple")
    after = before.model_copy(deep=True)
    after.walls[0].thickness = 0.20
    assert compare_versions(before, after).walls_moved == [after.walls[0].id]


def test_changes_below_tolerance_are_ignored() -> None:
    before = expected_project("rect_simple")
    after = before.model_copy(deep=True)
    start, end = after.walls[0].axis
    after.walls[0].axis = [(start[0] + 0.0005, start[1]), end]
    after.openings[0].offset += 0.0005
    diff = compare_versions(before, after)
    assert diff.walls_moved == diff.openings_modified == []


def test_unconfirmed_scale_in_either_version_is_preliminary() -> None:
    before = expected_project("rect_simple")
    after = before.model_copy(deep=True)
    after.scale_confirmed = False
    diff = compare_versions(before, after)
    assert diff.preliminary and diff.label == PRELIMINARY_LABEL
