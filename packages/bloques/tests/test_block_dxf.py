"""Ida y vuelta DXF: lo que se escribe se relee con ezdxf igual que las primitivas generadas."""

from pathlib import Path

import ezdxf
import pytest
from archimind_bloques import (
    Arc,
    AwningWindow,
    FixedWindow,
    Pen,
    Polyline,
    SlidingWindow,
    Stroke,
    elevation_block_name,
    export_dxf,
    generate,
)
from archimind_bloques.export_dxf import LINEWEIGHTS
from carpentry_cases import EXAMPLES, TOL
from ezdxf import bbox, units
from ezdxf.entities import Arc as DxfArc
from ezdxf.entities import DXFGraphic, Insert, LWPolyline


def _assert_same(entity: DXFGraphic, stroke: Stroke) -> None:
    assert entity.dxf.layer == "0"
    assert entity.dxf.color == 0  # BYBLOCK
    assert entity.dxf.lineweight == LINEWEIGHTS[stroke.pen]
    expected_linetype = "DASHED" if stroke.pen is Pen.HIDDEN else "CONTINUOUS"
    assert entity.dxf.linetype == expected_linetype
    match stroke:
        case Polyline():
            assert isinstance(entity, LWPolyline)
            assert entity.closed == stroke.closed
            points = list(entity.get_points("xy"))
            assert len(points) == len(stroke.points)
            for read, written in zip(points, stroke.points, strict=True):
                assert read == pytest.approx(written, abs=TOL)
        case Arc():
            assert isinstance(entity, DxfArc)
            assert (entity.dxf.center.x, entity.dxf.center.y) == pytest.approx(
                stroke.center, abs=TOL
            )
            assert entity.dxf.radius == pytest.approx(stroke.radius, abs=TOL)
            assert entity.dxf.start_angle == pytest.approx(stroke.start_angle, abs=TOL)
            assert entity.dxf.end_angle == pytest.approx(stroke.end_angle, abs=TOL)


@pytest.mark.parametrize("case", sorted(EXAMPLES))
def test_the_blocks_read_back_as_generated(tmp_path: Path, case: str) -> None:
    carpentry = generate(EXAMPLES[case])
    path = export_dxf(carpentry, tmp_path / "salidas" / f"{carpentry.name}.dxf")

    doc = ezdxf.readfile(path)
    assert doc.units == units.M
    assert doc.header["$LWDISPLAY"] == 1
    for name, strokes in (
        (carpentry.name, carpentry.plan),
        (elevation_block_name(carpentry), carpentry.elevation),
    ):
        block = doc.blocks.get(name)
        assert block is not None, name
        assert tuple(block.base_point) == (0, 0, 0)
        entities = list(block)
        assert len(entities) == len(strokes)
        for entity, stroke in zip(entities, strokes, strict=True):
            assert isinstance(entity, DXFGraphic)
            _assert_same(entity, stroke)


@pytest.mark.parametrize("case", sorted(EXAMPLES))
def test_the_plan_is_inserted_at_the_origin(tmp_path: Path, case: str) -> None:
    carpentry = generate(EXAMPLES[case])
    doc = ezdxf.readfile(export_dxf(carpentry, tmp_path / "bloque.dxf"))
    plan, elevation = doc.modelspace().query("INSERT")
    assert isinstance(plan, Insert) and isinstance(elevation, Insert)
    assert plan.dxf.name == carpentry.name
    assert plan.dxf.layer == ("A-PUERTA" if carpentry.kind == "door" else "A-VENTANA")
    assert tuple(plan.dxf.insert) == (0, 0, 0)
    assert elevation.dxf.name == elevation_block_name(carpentry)
    assert elevation.dxf.layer == "A-ALZADO"
    # El alzado va encima de la planta, alineado en x.
    assert elevation.dxf.insert.x == 0
    assert bbox.extents([elevation]).extmin.y > bbox.extents([plan]).extmax.y


@pytest.mark.parametrize("case", [c for c in sorted(EXAMPLES) if c.startswith("ventana")])
def test_window_blocks_measure_the_opening(tmp_path: Path, case: str) -> None:
    params = EXAMPLES[case]
    assert isinstance(params, SlidingWindow | FixedWindow | AwningWindow)
    carpentry = generate(params)
    doc = ezdxf.readfile(export_dxf(carpentry, tmp_path / "bloque.dxf"))
    plan = bbox.extents(doc.blocks.get(carpentry.name))
    assert (plan.extmin.x, plan.extmax.x) == pytest.approx((0, params.width), abs=TOL)
    assert (plan.extmin.y, plan.extmax.y) == pytest.approx(
        (-params.wall_thickness / 2, params.wall_thickness / 2), abs=TOL
    )
    elevation = bbox.extents(doc.blocks.get(elevation_block_name(carpentry)))
    assert (elevation.extmin.y, elevation.extmax.y) == pytest.approx(
        (params.sill_height, params.sill_height + params.height),
        abs=TOL,
    )


def test_door_block_measures_the_swing(tmp_path: Path) -> None:
    carpentry = generate(EXAMPLES["puerta_batiente"])  # 0.90, abre adentro, hoja de 0.80
    doc = ezdxf.readfile(export_dxf(carpentry, tmp_path / "bloque.dxf"))
    plan = bbox.extents(doc.blocks.get(carpentry.name))
    assert (plan.extmin.x, plan.extmax.x) == pytest.approx((0, 0.90), abs=TOL)
    assert (plan.extmin.y, plan.extmax.y) == pytest.approx((-0.04, 0.84), abs=TOL)
