"""Programa de áreas y COS/CUS."""

import pytest
from archimind_docs.database import ProgramRow
from archimind_docs.errors import DocsError
from archimind_docs.program import check_program, normalize
from archimind_docs.zoning import coefficients
from archimind_schema import Level, Project, Space, SpacePolygon, Wall, new_id
from cases import apto_2hab


def _rows(*pairs: tuple[str, float]) -> list[ProgramRow]:
    return [ProgramRow(espacio=name, area_minima=area) for name, area in pairs]


def test_names_ignore_case_accents_and_the_final_number() -> None:
    assert normalize("  HABITACIÓN  2 ") == normalize("habitacion") == "habitacion"
    assert normalize("Sala-comedor-cocina") == "sala-comedor-cocina"
    assert normalize("Baño 2b") == "bano 2b"


def test_apto_2hab_against_a_program() -> None:
    project, _ = apto_2hab()  # Habitación 1: 9.19 m², Habitación 2: 11.52 m², Baño: 2.93 m²
    rows = _rows(("Habitación", 9), ("Habitación", 10), ("Baño", 3.5), ("Estudio", 6))
    check = check_program(project, rows)
    # La exigencia mayor elige primero: la de 10 m² toma Habitación 2 y la de 9, Habitación 1.
    assert [(m.space, m.met) for m in check.matches] == [
        ("Habitación 1", True),
        ("Habitación 2", True),
        ("Baño", False),
        (None, False),
    ]
    assert [name for name, _ in check.extra] == ["Sala-comedor-cocina"]
    assert not check.preliminary


def test_three_rooms_required_and_two_built() -> None:
    project, _ = apto_2hab()
    check = check_program(project, _rows(("habitacion", 8), ("habitacion", 8), ("habitacion", 8)))
    assert [m.space for m in check.matches].count(None) == 1


def _two_levels() -> Project:
    project = Project(id="p", name="p", scale_confirmed=True)
    for elevation, side in ((0.0, 10.0), (3.0, 5.0)):
        level = Level(
            id=new_id(project, "niv"),
            name=f"N{elevation:g}",
            elevation=elevation,
            default_height=2.6,
        )
        project.levels.append(level)
        corners = [(0, 0), (side, 0), (side, side), (0, side)]
        for a, b in zip(corners, [*corners[1:], corners[0]], strict=True):
            project.walls.append(
                Wall(id=new_id(project, "muro"), level_id=level.id, axis=[a, b], thickness=0.2)
            )
        inner = side - 0.1
        project.spaces.append(
            Space(
                id=new_id(project, "esp"),
                level_id=level.id,
                name="Local",
                category="useful",
                polygon=SpacePolygon(
                    exterior=[(0.1, 0.1), (inner, 0.1), (inner, inner), (0.1, inner)]
                ),
            )
        )
    return project


def test_cos_uses_the_lowest_level_and_cus_all_of_them() -> None:
    result = coefficients(_two_levels(), 200)
    # Cada nivel construido es su cuadrado a ejes más medio espesor de muro por lado.
    assert [lv.name for lv in result.levels] == ["N0", "N3"]
    assert result.footprint == pytest.approx(10.2**2)
    assert result.total_built == pytest.approx(10.2**2 + 5.2**2)
    assert result.cos == pytest.approx(10.2**2 / 200)
    assert result.cus == pytest.approx((10.2**2 + 5.2**2) / 200)


def test_a_lot_without_area_or_a_model_without_walls() -> None:
    with pytest.raises(DocsError, match="mayor que 0"):
        coefficients(_two_levels(), 0)
    with pytest.raises(DocsError, match="aplicar_mapeo"):
        coefficients(Project(id="p", name="vacío", scale_confirmed=True), 100)
