import pytest
from archimind_core import HeightsError, define_heights, missing_heights
from archimind_schema import Project, wall_height
from cases import expected_project


def _apto() -> Project:
    return expected_project("apto_2hab")


def _space(project: Project, name: str) -> str:
    return next(s.id for s in project.spaces if s.name == name)


def test_imported_levels_are_missing_their_heights() -> None:
    project = _apto()
    [missing] = missing_heights(project)
    assert missing.level_id == project.levels[0].id
    assert missing.default_height == 2.60
    assert missing.wall_ids == [w.id for w in project.walls]


def test_by_level_confirms_the_height_and_nothing_is_missing() -> None:
    project = _apto()
    level_id = project.levels[0].id
    result = define_heights(project, by_level={level_id: 2.45})

    level = result.project.levels[0]
    assert (level.default_height, level.height_confirmed) == (2.45, True)
    assert all(wall_height(result.project, w) == 2.45 for w in result.project.walls)
    assert missing_heights(result.project) == []
    assert not project.levels[0].height_confirmed  # el original no cambia


def test_by_space_sets_only_the_walls_around_it() -> None:
    project = _apto()
    bath = _space(project, "Baño")
    result = define_heights(project, by_space={bath: 2.30})

    # Norte, tabique de 0.12 en x=3.5 y los dos tabiques del baño.
    expected = {project.walls[i].id for i in (2, 4, 6, 7)}
    assert set(result.walls) == expected
    for wall in result.project.walls:
        assert wall.height == (2.30 if wall.id in expected else None)
    # El nivel sigue sin confirmar: faltan los muros que no rodean el baño.
    [missing] = missing_heights(result.project)
    assert set(missing.wall_ids) == {w.id for w in project.walls} - expected


def test_a_wall_between_two_heights_takes_the_higher_with_a_warning() -> None:
    project = _apto()
    bath, living = _space(project, "Baño"), _space(project, "Sala-comedor-cocina")
    result = define_heights(project, by_space={bath: 2.30, living: 2.70})

    bath_south = project.walls[6].id
    assert result.walls[bath_south] == 2.70
    assert any(bath_south in w and "queda con 2.70 m" in w for w in result.warnings)


def test_by_level_then_by_space_and_own_heights_are_kept() -> None:
    project = _apto()
    project.walls[0].height = 2.80
    level_id = project.levels[0].id
    bath = _space(project, "Baño")
    result = define_heights(project, by_level={level_id: 2.50}, by_space={bath: 2.30})

    assert result.kept_walls == [project.walls[0].id]
    assert wall_height(result.project, result.project.walls[0]) == 2.80
    assert wall_height(result.project, result.project.walls[2]) == 2.30
    assert wall_height(result.project, result.project.walls[1]) == 2.50


@pytest.mark.parametrize(
    ("by_level", "by_space", "message"),
    [
        (None, None, "por_nivel"),
        ({"niv-0099": 2.5}, None, "niv-0099"),
        (None, {"esp-0099": 2.5}, "esp-0099"),
        ({"niv-0001": 0.0}, None, "mayores que 0"),
        ({"niv-0001": float("nan")}, None, "mayores que 0"),
        ({"niv-0001": 2.0}, None, "más altos que su muro"),  # puertas de 2.10
    ],
)
def test_invalid_heights_change_nothing(
    by_level: dict[str, float] | None, by_space: dict[str, float] | None, message: str
) -> None:
    project = _apto()
    before = project.model_dump()
    with pytest.raises(HeightsError, match=message):
        define_heights(project, by_level, by_space)
    assert project.model_dump() == before
