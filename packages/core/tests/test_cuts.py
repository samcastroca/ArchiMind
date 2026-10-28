"""Líneas de corte propuestas para elegir por nombre."""

import math
from pathlib import Path

import pytest
from archimind_core.cuts import (
    WALL_CLEARANCE_M,
    CutsError,
    propose_cuts,
    write_cut_proposals,
)
from archimind_core.project import open_project
from archimind_schema import (
    ANGLE_TOL_DEG,
    CutLine,
    CutProposals,
    Project,
    Space,
    SpacePolygon,
    new_id,
    save_project,
    wall_polygon,
)
from cases import apto_2hab, en_l
from hypothesis import assume, given, settings
from schema_strategies import projects
from shapely import LineString, Point, unary_union


def _direction(cut: CutLine) -> tuple[float, float]:
    length = math.dist(cut.start, cut.end)
    return ((cut.end[0] - cut.start[0]) / length, (cut.end[1] - cut.start[1]) / length)


def _along_a_wall(project: Project, cut: CutLine) -> bool:
    """Lo mismo que descarta propose_cuts, calculado aparte: un tramo de muro paralelo al corte
    cuyo eje queda a menos de medio espesor más la holgura de la línea."""
    d = _direction(cut)
    line = LineString([cut.start, cut.end])
    for wall in project.walls:
        for a, b in zip(wall.axis, wall.axis[1:], strict=False):
            length = math.dist(a, b)
            cross = abs(d[0] * (b[1] - a[1]) - d[1] * (b[0] - a[0])) / length
            if cross > math.sin(math.radians(ANGLE_TOL_DEG)):
                continue
            near = wall.thickness / 2 + WALL_CLEARANCE_M
            if min(line.distance(Point(a)), line.distance(Point(b))) < near - 1e-9:
                return True
    return False


@pytest.mark.parametrize("case", [apto_2hab, en_l])
def test_golden_cases_get_two_cuts_that_cut_openings(case) -> None:  # type: ignore[no-untyped-def]
    project, _ = case()
    cuts = propose_cuts(project)
    assert [(c.name, c.label) for c in cuts] == [("longitudinal", "A-A"), ("transversal", "B-B")]
    for cut in cuts:
        assert not _along_a_wall(project, cut)
        assert "corta 1 puerta" in cut.description
    longitudinal, transversal = (_direction(c) for c in cuts)
    assert abs(longitudinal[0] * transversal[0] + longitudinal[1] * transversal[1]) < 1e-9


def test_apto_2hab_longitudinal_follows_the_long_side() -> None:
    project, _ = apto_2hab()
    longitudinal, transversal = propose_cuts(project)
    assert _direction(longitudinal) == pytest.approx((1.0, 0.0))
    assert longitudinal.description.startswith("Paralelo al lado largo; cruza Habitación 2")
    # El edificio va de 0 a 8.5 m (más medio espesor): la línea sobresale 1 m de cada lado.
    assert longitudinal.start[0] == pytest.approx(-1.1)
    assert longitudinal.end[0] == pytest.approx(9.6)
    assert "Baño" in transversal.description


def test_a_space_named_staircase_adds_a_third_cut() -> None:
    project, _ = apto_2hab()
    project.spaces.append(
        Space(
            id=new_id(project, "esp"),
            level_id=project.levels[0].id,
            name="ESCALERA de servicio",
            category="circulation",
            polygon=SpacePolygon(exterior=[(6.0, 0.5), (7.0, 0.5), (7.0, 3.5), (6.0, 3.5)]),
        )
    )
    *_, stair = propose_cuts(project)
    assert (stair.name, stair.label) == ("escalera", "C-C")
    assert stair.description.startswith("Por ESCALERA de servicio")
    # A lo largo del lado largo de la escalera, por su centro, de punta a punta del edificio.
    assert stair.start == pytest.approx((6.5, -1.1))
    assert stair.end == pytest.approx((6.5, 7.6))


def test_accents_do_not_matter_for_the_staircase() -> None:
    project, _ = en_l()
    project.spaces[0].name = "Escalera"
    project.spaces[1].name = "Hall y escalera"
    names = [c.name for c in propose_cuts(project)]
    assert names.count("escalera") == 1


def test_a_model_without_walls_says_how_to_build_it() -> None:
    with pytest.raises(CutsError, match="aplicar_mapeo"):
        propose_cuts(Project(id="p", name="vacío", scale_confirmed=True))


def test_writes_the_proposals_with_the_model_version(tmp_path: Path) -> None:
    folder = tmp_path / "casa"
    open_project(folder)
    project, _ = apto_2hab()
    save_project(project, folder)
    path = write_cut_proposals(folder, propose_cuts(project))
    assert path == folder / "salidas" / "cortes.json"
    proposals = CutProposals.model_validate_json(path.read_text(encoding="utf-8"))
    assert [c.name for c in proposals.cuts] == ["longitudinal", "transversal"]
    assert len(proposals.base_sha256) == 64


@settings(max_examples=60, deadline=None)
@given(projects())
def test_properties_on_random_projects(project: Project) -> None:
    assume(project.walls)
    footprint = unary_union([wall_polygon(w) for w in project.walls])
    assume(footprint.is_valid and footprint.area > 0)
    cuts = propose_cuts(project)
    assert propose_cuts(project) == cuts
    assert len({c.name for c in cuts}) == len(cuts)
    for cut in cuts:
        assert not footprint.contains(Point(cut.start))
        assert not footprint.contains(Point(cut.end))
        if cut.name != "escalera":
            assert not _along_a_wall(project, cut)
