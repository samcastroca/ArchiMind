import csv
import math
from pathlib import Path

import pytest
from archimind_core import (
    PRELIMINARY_LABEL,
    OpeningCount,
    QuantitiesError,
    area_table,
    build_model,
    export_area_table_csv,
    opening_counts,
    proposals_to_mapping,
    propose_mapping,
    read_drawing,
    wall_quantities,
)
from archimind_schema import Level, Project, Space, SpacePolygon, Wall, new_id
from cases import CASES, expected_project
from golden import GOLDEN_DIR
from hypothesis import given
from hypothesis import strategies as st

AREA_REL_TOL = 0.005

# Áreas calculadas a mano a partir de las caras interiores de cada caso (tests/fixtures/cases.py).
_DIAGONAL = 10 - 0.10 * math.sqrt(2) - 3.90 - 0.10  # x del chaflán interior en y = 3.90, − 0.10
APTO_2HAB = (
    3.34 * 2.75  # habitación 1
    + 3.34 * 3.45  # habitación 2
    + 1.89 * 1.55  # baño
    + (4.84 * 6.30 - 1.99 * 1.65)  # sala-comedor-cocina, menos la esquina del baño
)
EN_L_ESTAR = 9.80 * 3.80 + 1.05 * (_DIAGONAL + (_DIAGONAL - 1.05)) / 2
# El triángulo del dormitorio tiene por cateto la x del chaflán en y = 5.05, menos 3.90.
EN_L_DORMITORIO = 3.80 * 4.85 + (_DIAGONAL - 4.95) ** 2 / 2
# Contorno exterior de en_l: el cuadrado de 10.20 menos el brazo vacío de 6 × 6, al que le falta
# el triángulo que queda bajo la cara exterior del chaflán.
_CHAMFER_LEG = 10 + 0.10 * math.sqrt(2) - 4.10 - 4.10
USEFUL = {
    "rect_simple": 4.00 * 3.00,
    "planta_y_alzado": 4.00 * 3.00,  # solo la planta: el alzado no se reconstruye
    "apto_2hab": APTO_2HAB,
    "apto_capas_caoticas": APTO_2HAB,
    "muros_linea_doble": APTO_2HAB,
    "milimetros": APTO_2HAB,
    "en_l": EN_L_ESTAR + EN_L_DORMITORIO,
}
BUILT = {
    "rect_simple": 4.30 * 3.30,
    "planta_y_alzado": 4.30 * 3.30,
    "apto_2hab": 8.70 * 6.70,
    "apto_capas_caoticas": 8.70 * 6.70,
    "muros_linea_doble": 8.70 * 6.70,
    "milimetros": 8.70 * 6.70,
    "en_l": 10.20**2 - (6.00**2 - _CHAMFER_LEG**2 / 2),
}


def _rebuilt(case: str) -> Project:
    drawing = read_drawing(GOLDEN_DIR / case / "input.dxf")
    mapping = proposals_to_mapping(propose_mapping(drawing))
    return build_model(drawing, mapping, view=CASES[case].view).project


def test_hand_values_cover_every_case() -> None:
    assert set(USEFUL) == set(BUILT) == set(CASES)


@pytest.mark.parametrize("case", sorted(CASES))
def test_useful_and_built_area_of_the_rebuilt_case_match_hand_values(case: str) -> None:
    table = area_table(_rebuilt(case))
    assert table.useful_area == pytest.approx(USEFUL[case], rel=AREA_REL_TOL)
    assert table.built_area == pytest.approx(BUILT[case], rel=AREA_REL_TOL)
    assert table.balcony_area == 0
    assert not table.preliminary and table.label is None


@pytest.mark.parametrize("case", sorted(CASES))
def test_useful_and_built_area_of_the_expected_model_match_hand_values(case: str) -> None:
    table = area_table(expected_project(case))
    assert table.useful_area == pytest.approx(USEFUL[case], rel=AREA_REL_TOL)
    assert table.built_area == pytest.approx(BUILT[case], rel=AREA_REL_TOL)


def test_area_table_lists_each_space() -> None:
    table = area_table(expected_project("apto_2hab"))
    by_name = {s.name: s for s in table.spaces}
    assert set(by_name) == {"Habitación 1", "Habitación 2", "Baño", "Sala-comedor-cocina"}
    assert by_name["Baño"].category == "service"
    assert by_name["Baño"].area == pytest.approx(1.89 * 1.55)


def _rectangle(width: float, depth: float, thickness: float) -> Project:
    """Un espacio de width × depth con muros por su cara exterior, ejes a thickness / 2."""
    project = Project(id="p", name="p", scale_confirmed=True)
    level_id = new_id(project, "niv")
    project.levels.append(Level(id=level_id, name="PB", elevation=0, default_height=2.6))
    h = thickness / 2
    corners = [(-h, -h), (width + h, -h), (width + h, depth + h), (-h, depth + h)]
    for start, end in zip(corners, corners[1:] + corners[:1], strict=True):
        project.walls.append(
            Wall(
                id=new_id(project, "muro"),
                level_id=level_id,
                axis=[start, end],
                thickness=thickness,
            )
        )
    exterior = [(0.0, 0.0), (width, 0.0), (width, depth), (0.0, depth)]
    project.spaces.append(
        Space(
            id=new_id(project, "esp"),
            level_id=level_id,
            name="Local",
            polygon=SpacePolygon(exterior=exterior),
            category="useful",
        )
    )
    return project


@given(
    width=st.floats(1.0, 30.0),
    depth=st.floats(1.0, 30.0),
    thickness=st.sampled_from([0.10, 0.12, 0.15, 0.20, 0.25]),
)
def test_rectangle_quantities(width: float, depth: float, thickness: float) -> None:
    project = _rectangle(width, depth, thickness)
    table = area_table(project)
    assert table.useful_area == pytest.approx(width * depth)
    assert table.built_area == pytest.approx((width + 2 * thickness) * (depth + 2 * thickness))
    axis_perimeter = 2 * (width + thickness) + 2 * (depth + thickness)
    lengths = wall_quantities(project).length_by_thickness
    assert lengths == {thickness: pytest.approx(axis_perimeter)}


def test_balconies_are_reported_apart() -> None:
    project = _rectangle(4.0, 3.0, 0.15)
    project.spaces.append(
        Space(
            id=new_id(project, "esp"),
            level_id=project.levels[0].id,
            name="Balcón",
            polygon=SpacePolygon(exterior=[(0, 3.15), (2, 3.15), (2, 4.15), (0, 4.15)]),
            category="balcony",
        )
    )
    table = area_table(project)
    assert table.balcony_area == pytest.approx(2.0)
    assert table.useful_area == pytest.approx(12.0)
    assert table.built_area == pytest.approx(4.30 * 3.30)


def test_wall_quantities_by_thickness() -> None:
    lengths = wall_quantities(expected_project("apto_2hab")).length_by_thickness
    assert lengths == {
        0.10: pytest.approx(3.5 + 2.0 + 1.7),
        0.12: pytest.approx(6.5),
        0.20: pytest.approx(2 * 8.5 + 2 * 6.5),
    }


def test_measured_thickness_is_not_snapped() -> None:
    project = _rectangle(4.0, 3.0, 0.15)
    project.walls[0].thickness = 0.153
    lengths = wall_quantities(project).length_by_thickness
    assert set(lengths) == {0.15, 0.153}


def test_opening_counts_by_kind_and_size() -> None:
    counts = opening_counts(expected_project("apto_2hab")).counts
    assert counts == [
        OpeningCount("door", 0.70, 2.10, 1),
        OpeningCount("door", 0.80, 2.10, 2),
        OpeningCount("door", 0.90, 2.10, 1),
        OpeningCount("window", 0.60, 0.60, 1),
        OpeningCount("window", 1.50, 1.20, 3),
        OpeningCount("window", 2.00, 1.20, 1),
    ]


def test_unconfirmed_scale_marks_everything_preliminary(tmp_path: Path) -> None:
    project = expected_project("apto_2hab")
    project.scale_confirmed = False
    table = area_table(project)
    for result in (table, wall_quantities(project), opening_counts(project)):
        assert result.preliminary
        assert result.label == PRELIMINARY_LABEL
    target = tmp_path / "areas.csv"
    with pytest.raises(QuantitiesError, match=PRELIMINARY_LABEL):
        export_area_table_csv(table, target)
    assert not target.exists()


def test_csv_round_trip(tmp_path: Path) -> None:
    table = area_table(expected_project("apto_2hab"))
    path = export_area_table_csv(table, tmp_path / "areas.csv")
    with path.open(encoding="utf-8-sig", newline="") as file:
        rows = list(csv.reader(file))
    assert rows[0] == ["id", "nombre", "categoría", "área_m2"]
    assert [row[1] for row in rows[1:5]] == [s.name for s in table.spaces]
    totals = {row[1]: float(row[3]) for row in rows[5:]}
    assert totals == {
        "Área útil": round(table.useful_area, 2),
        "Área construida": round(table.built_area, 2),
        "Área de balcones": 0.0,
    }
