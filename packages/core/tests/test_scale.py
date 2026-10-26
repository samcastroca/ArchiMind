import pytest
from archimind_core import ScaleError, confirm_scale, rescale
from archimind_schema import Project, space_area, wall_length
from cases import expected_project
from hypothesis import given
from hypothesis import strategies as st
from schema_strategies import projects

factors = st.floats(min_value=0.01, max_value=100, allow_nan=False, allow_infinity=False)


@given(projects(), factors)
def test_rescale_multiplies_what_the_plan_measures(project: Project, k: float) -> None:
    scaled = rescale(project, k)

    for before, after in zip(project.walls, scaled.walls, strict=True):
        assert after.id == before.id
        assert wall_length(after) == pytest.approx(wall_length(before) * k)
        assert after.thickness == pytest.approx(before.thickness * k)
        assert after.height == before.height
    for before_o, after_o in zip(project.openings, scaled.openings, strict=True):
        assert (after_o.id, after_o.wall_id) == (before_o.id, before_o.wall_id)
        assert after_o.offset == pytest.approx(before_o.offset * k)
        assert after_o.width == pytest.approx(before_o.width * k)
        assert (after_o.height, after_o.sill_height) == (before_o.height, before_o.sill_height)
    for before_s, after_s in zip(project.spaces, scaled.spaces, strict=True):
        assert space_area(after_s) == pytest.approx(space_area(before_s) * k * k)
    for before_a, after_a in zip(project.annotations, scaled.annotations, strict=True):
        x, y = before_a.position
        assert after_a.position == pytest.approx((x * k, y * k))
    assert scaled.levels == project.levels
    assert scaled.next_ids == project.next_ids
    assert scaled.scale_confirmed == project.scale_confirmed


@given(projects().filter(lambda p: bool(p.walls)), st.data())
def test_the_reference_wall_ends_up_measuring_the_real_length(
    project: Project, data: st.DataObject
) -> None:
    wall = data.draw(st.sampled_from(project.walls))
    real = data.draw(st.floats(min_value=0.5, max_value=100))

    confirmation = confirm_scale(project, wall.id, real)

    scaled = next(w for w in confirmation.project.walls if w.id == wall.id)
    assert wall_length(scaled) == pytest.approx(real)
    assert confirmation.measured_length == pytest.approx(wall_length(wall))
    assert confirmation.factor == pytest.approx(real / wall_length(wall))
    assert confirmation.project.scale_confirmed and confirmation.changed


def test_without_arguments_confirms_the_units() -> None:
    project = expected_project("apto_2hab").model_copy(update={"scale_confirmed": False})
    confirmation = confirm_scale(project)
    assert confirmation.project.scale_confirmed
    assert confirmation.factor == 1.0 and confirmation.changed
    assert confirmation.project.walls == project.walls


def test_an_already_confirmed_scale_is_left_alone() -> None:
    project = expected_project("apto_2hab")
    confirmation = confirm_scale(project)
    assert confirmation.project is project
    assert not confirmation.changed


@pytest.mark.parametrize(
    ("wall_id", "real_length", "message"),
    [
        ("muro-0001", None, "hacen falta muro_id y longitud_real juntos"),
        (None, 4.2, "hacen falta muro_id y longitud_real juntos"),
        ("muro-0999", 4.2, "No existe el muro muro-0999. Los muros del modelo son muro-0001"),
        ("muro-0001", 0.0, "mayor que 0"),
        ("muro-0001", float("nan"), "mayor que 0"),
    ],
)
def test_rejects_invalid_requests(
    wall_id: str | None, real_length: float | None, message: str
) -> None:
    with pytest.raises(ScaleError, match=message):
        confirm_scale(expected_project("apto_2hab"), wall_id, real_length)


def test_needs_a_model_with_walls() -> None:
    with pytest.raises(ScaleError, match="aplica el mapeo"):
        confirm_scale(Project(id="p", name="p", scale_confirmed=False))
