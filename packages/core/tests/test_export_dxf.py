from collections import Counter
from pathlib import Path

import ezdxf
import pytest
from archimind_core import ExportError, build_model, export_dxf, read_drawing
from archimind_schema import Project
from cases import CASES, expected_project
from ezdxf import units
from ezdxf.entities import LWPolyline
from golden import assert_matches

REIMPORT_MAPPING = {
    "A-MURO": "walls",
    "A-PUERTA": "doors",
    "A-VENTANA": "windows",
    "A-TEXTO": "text",
}


def test_refuses_an_unconfirmed_scale(tmp_path: Path) -> None:
    project = expected_project("apto_2hab").model_copy(update={"scale_confirmed": False})
    with pytest.raises(ExportError, match="PRELIMINAR: escala sin confirmar"):
        export_dxf(project, tmp_path / "casa.dxf")
    assert not (tmp_path / "casa.dxf").exists()


def test_writes_metres_with_one_layer_per_role(tmp_path: Path) -> None:
    project = expected_project("apto_2hab")
    path = export_dxf(project, tmp_path / "salidas" / "casa.dxf")

    doc = ezdxf.readfile(path)
    assert doc.units == units.M
    msp = doc.modelspace()
    polylines = Counter(e.dxf.layer for e in msp.query("LWPOLYLINE"))
    assert all(isinstance(e, LWPolyline) and e.closed for e in msp.query("LWPOLYLINE"))
    kinds = Counter(o.kind for o in project.openings)
    assert polylines["A-PUERTA"] == kinds["door"]
    assert polylines["A-VENTANA"] == kinds["window"]
    assert polylines["A-ESPACIO"] == len(project.spaces)
    assert polylines["A-MURO"] >= 1
    names = sorted(e.dxf.text for e in msp.query("TEXT[layer=='A-TEXTO']"))
    assert names == sorted(s.name for s in project.spaces)
    areas = [e.dxf.text for e in msp.query("TEXT[layer=='A-AREA']")]
    assert len(areas) == len(project.spaces) and all(a.endswith(" m²") for a in areas)


@pytest.mark.parametrize("case", sorted(set(CASES) - {"milimetros"}))
def test_the_export_imports_back_as_the_same_model(tmp_path: Path, case: str) -> None:
    project = expected_project(case)
    path = export_dxf(project, tmp_path / f"{case}.dxf")
    rebuilt = build_model(read_drawing(path), REIMPORT_MAPPING).project
    # La exportación normaliza las capas: todo muro sale en A-MURO.
    for wall in project.walls:
        wall.source_layer = "A-MURO"
    assert_matches(rebuilt, project, f"el modelo exportado de {case}")


def test_an_empty_model_exports_an_empty_drawing(tmp_path: Path) -> None:
    path = export_dxf(Project(id="p", name="p", scale_confirmed=True), tmp_path / "p.dxf")
    assert len(ezdxf.readfile(path).modelspace()) == 0
