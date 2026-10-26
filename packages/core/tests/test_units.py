from pathlib import Path

import ezdxf
import pytest
from archimind_core import detect_units, read_drawing
from archimind_schema import WALL_THICKNESSES
from ezdxf import units
from golden import GOLDEN_DIR
from hypothesis import given
from hypothesis import strategies as st


def _without_insunits(case: str, tmp_path: Path) -> Path:
    doc = ezdxf.readfile(GOLDEN_DIR / case / "input.dxf")
    doc.header["$INSUNITS"] = 0
    path = tmp_path / f"{case}.dxf"
    doc.saveas(path)
    return path


def test_millimetre_case_declares_millimetres() -> None:
    drawing = read_drawing(GOLDEN_DIR / "milimetros" / "input.dxf")
    assert drawing.units.name == "Millimeters"
    assert drawing.units.to_metres == pytest.approx(0.001)
    assert drawing.units.confirmed
    assert drawing.units.source == "insunits"


@pytest.mark.parametrize("case", ["rect_simple", "apto_2hab", "en_l", "muros_linea_doble"])
def test_metre_cases_declare_metres(case: str) -> None:
    drawing = read_drawing(GOLDEN_DIR / case / "input.dxf")
    assert drawing.units.to_metres == 1.0
    assert drawing.units.confirmed


@pytest.mark.parametrize(
    ("case", "factor"), [("milimetros", 0.001), ("apto_2hab", 1.0), ("rect_simple", 1.0)]
)
def test_missing_insunits_is_inferred_and_unconfirmed(
    case: str, factor: float, tmp_path: Path
) -> None:
    drawing = read_drawing(_without_insunits(case, tmp_path))
    assert drawing.units.to_metres == pytest.approx(factor)
    assert not drawing.units.confirmed
    assert drawing.units.source == "inferidas"
    assert "no declara unidades" in drawing.units.evidence


UNITS = {units.M: 1.0, units.CM: 100.0, units.MM: 1000.0}


@given(
    unit=st.sampled_from(sorted(UNITS)),
    thickness=st.sampled_from(WALL_THICKNESSES),
    length=st.floats(3.0, 30.0),
)
def test_single_wall_outline_reveals_its_unit(unit: int, thickness: float, length: float) -> None:
    """Un muro dibujado como rectángulo sin unidades: sus testas miden el espesor."""
    k = UNITS[unit]
    doc = ezdxf.new(units=0)
    corners = [(0, 0), (length, 0), (length, thickness), (0, thickness)]
    doc.modelspace().add_lwpolyline([(x * k, y * k) for x, y in corners], close=True)
    detected = detect_units(doc)
    assert detected.to_metres == pytest.approx(1 / k)
    assert not detected.confirmed
