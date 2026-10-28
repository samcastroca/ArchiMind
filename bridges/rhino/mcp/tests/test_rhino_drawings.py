"""Lo que se dibuja con HiddenLineDrawing y cómo se escribe: piezas, cámaras, planos de recorte,
estilos y los archivos DXF y SVG. Sin Rhino."""

import math
from pathlib import Path
from typing import Any

import ezdxf
import pytest
from archimind_core import define_heights, model_pieces
from archimind_rhino_bridge.drawing_files import DrawingError, parse_segments, write_drawing
from archimind_rhino_bridge.styles import DEFAULT_STYLES_PATH, StylesError, load_styles
from archimind_rhino_bridge.views import (
    ISO_FROM,
    ViewError,
    cut_camera,
    cut_planes,
    default_depth,
    drawing_pieces,
    iso_camera,
    looking,
    solids_payload,
)
from archimind_schema import Level, Project, Wall, new_id
from cases import apto_2hab
from hypothesis import given, settings
from hypothesis import strategies as st
from shapely import Polygon

SLAB = 0.15


def _project() -> Project:
    project, _ = apto_2hab()
    return define_heights(project, {project.levels[0].id: 2.6}, None).project


def _two_levels() -> Project:
    project = Project(id="p", name="p", scale_confirmed=True)
    for elevation in (3.0, 0.0):  # desordenados a propósito: manda la cota
        level = Level(
            id=new_id(project, "niv"),
            name=f"{elevation}",
            elevation=elevation,
            default_height=2.5,
            height_confirmed=True,
        )
        project.levels.append(level)
        project.walls.append(
            Wall(
                id=new_id(project, "muro"), level_id=level.id, axis=[(0, 0), (4, 0)], thickness=0.2
            )
        )
    return project


def _dot(a: Any, b: Any) -> float:
    return float(sum(x * y for x, y in zip(a, b, strict=True)))


# --- Piezas -------------------------------------------------------------------------------


def test_without_explosion_the_pieces_are_the_3d_model() -> None:
    project = _project()
    assert drawing_pieces(project, False, 1.0, SLAB) == model_pieces(project, SLAB)


@settings(max_examples=25, deadline=None)
@given(st.floats(min_value=0.1, max_value=5))
def test_explosion_lifts_walls_off_their_slab_and_levels_off_each_other(gap: float) -> None:
    project = _two_levels()
    low, high = sorted(project.levels, key=lambda lv: lv.elevation)
    pieces = drawing_pieces(project, True, gap, SLAB)
    slabs = {p.owner_id: p for p in pieces if p.kind == "losa"}
    walls = {w.level_id: next(p for p in pieces if p.owner_id == w.id) for w in project.walls}
    assert slabs[low.id].z1 == pytest.approx(low.elevation)
    assert walls[low.id].z0 == pytest.approx(low.elevation + gap)
    assert slabs[high.id].z1 == pytest.approx(high.elevation + 2 * gap)
    assert walls[high.id].z0 == pytest.approx(high.elevation + 3 * gap)
    for piece, original in zip(pieces, model_pieces(project, SLAB), strict=True):
        assert piece.z1 - piece.z0 == pytest.approx(original.z1 - original.z0)


def test_the_payload_has_counterclockwise_outlines_and_slab_holes() -> None:
    project = _project()
    solids = solids_payload(model_pieces(project, SLAB))
    for solid in solids:
        assert solid["footprint"][0] != solid["footprint"][-1]
        assert Polygon(solid["footprint"]).exterior.is_ccw
        assert all(not Polygon(h).exterior.is_ccw for h in solid["holes"])
    assert len(solids) == len(model_pieces(project, SLAB))


# --- Cámaras y planos ---------------------------------------------------------------------


@pytest.mark.parametrize("view", list(ISO_FROM))
def test_iso_cameras_look_down_from_their_quadrant(view: Any) -> None:
    pieces = model_pieces(_project(), SLAB)
    camera = iso_camera(view, pieces)
    d, up = camera["direction"], camera["up"]
    sx, sy = ISO_FROM[view]
    assert d == pytest.approx([-sx / math.sqrt(3), -sy / math.sqrt(3), -1 / math.sqrt(3)])
    assert _dot(d, up) == pytest.approx(0, abs=1e-12)
    assert _dot(up, up) == pytest.approx(1) and up[2] > 0
    # La cámara está, respecto del centro del edificio (4.25, 3.25), del lado del que mira, y
    # el encuadre contiene todas las piezas.
    location = camera["location"]
    assert (location[0] - 4.25) * sx > 0 and (location[1] - 3.25) * sy > 0 and location[2] > 0
    left, right, bottom, top, near, far = camera["frustum"]
    assert 0 < near < far and left == -right and bottom == -top
    for piece in pieces:
        for x, y in piece.footprint.exterior.coords:
            for z in (piece.z0, piece.z1):
                v = [x - location[0], y - location[1], z - location[2]]
                assert near <= _dot(v, d) <= far


@pytest.mark.parametrize(("side", "expected"), [("izquierda", (0, 1)), ("derecha", (0, -1))])
def test_a_cut_looks_to_one_side_of_its_line(side: Any, expected: tuple[int, int]) -> None:
    start, end = (-1.0, 3.25), (9.6, 3.25)
    assert looking(start, end, side) == pytest.approx(expected)
    camera = cut_camera(start, end, side, model_pieces(_project(), SLAB))
    assert camera["direction"] == pytest.approx([*expected, 0])
    assert camera["up"] == pytest.approx([0, 0, 1])


def test_the_cut_keeps_what_lies_between_the_line_and_the_depth() -> None:
    start, end = (-1.0, 3.0), (9.0, 3.0)
    behind, beyond = cut_planes(start, end, "izquierda", 2.0)

    def clipped(y: float) -> bool:
        """HiddenLineDrawing quita el lado hacia el que apunta la normal."""
        return any(_dot([0, y - p["origin"][1], 0], p["normal"]) > 0 for p in (behind, beyond))

    assert [clipped(y) for y in (2.9, 3.1, 4.9, 5.1)] == [True, False, False, True]


def test_the_default_depth_reaches_the_far_side_of_the_building() -> None:
    pieces = model_pieces(_project(), SLAB)
    # apto_2hab llega a y = 6.6 con medio espesor del muro norte.
    assert default_depth(pieces, (-1, 3.25), (9.6, 3.25), "izquierda") == pytest.approx(3.35)
    assert default_depth(pieces, (-1, 3.25), (9.6, 3.25), "derecha") == pytest.approx(3.35)
    with pytest.raises(ViewError, match="otro lado"):
        default_depth(pieces, (-1, 8.0), (9.6, 8.0), "izquierda")


# --- Estilos ------------------------------------------------------------------------------


def test_the_default_styles_have_the_section_weights() -> None:
    styles = load_styles()
    assert styles.layers["CORTADO"].lineweight == 50
    assert styles.layers["PROYECTADO"].lineweight == 18
    assert styles.layers["OCULTAS"].linetype == "DASHED"


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (("0.50", "0.45"), "no es un grosor de DXF"),
        (("CORTADO:", "CORTE:"), "faltan las capas CORTADO"),
        (("svg_scale: 50", "svg_scale: -1"), "estilos inválidos"),
    ],
)
def test_invalid_styles_are_explained(
    tmp_path: Path, change: tuple[str, str], message: str
) -> None:
    path = tmp_path / "estilos.yaml"
    path.write_text(
        DEFAULT_STYLES_PATH.read_text(encoding="utf-8").replace(*change), encoding="utf-8"
    )
    with pytest.raises(StylesError, match=message):
        load_styles(path)


# --- Archivos -----------------------------------------------------------------------------


def test_writes_layers_with_weights_and_moves_the_drawing_to_the_origin(tmp_path: Path) -> None:
    segments = parse_segments(
        {
            "segments": [
                {"kind": "section", "points": [[10, 5], [14, 5], [14, 8]]},
                {"kind": "visible", "points": [[11, 6], [13, 6]]},
                {"kind": "hidden", "points": [[11, 7], [13, 7]]},
            ]
        }
    )
    files = write_drawing(
        segments,
        {"section": "CORTADO", "visible": "PROYECTADO"},
        load_styles(),
        tmp_path / "corte.dxf",
        tmp_path / "corte.svg",
    )
    assert files.counts == {"CORTADO": 1, "PROYECTADO": 1}
    doc = ezdxf.readfile(files.dxf)
    assert doc.units == ezdxf.units.M
    assert doc.layers.get("CORTADO").dxf.lineweight == 50
    assert doc.layers.get("PROYECTADO").dxf.lineweight == 18
    polylines = list(doc.modelspace().query("LWPOLYLINE"))
    assert [p.dxf.layer for p in polylines] == ["CORTADO", "PROYECTADO"]
    assert [tuple(v) for v in polylines[0].get_points("xy")] == [(0, 0), (4, 0), (4, 3)]
    assert files.svg.read_text(encoding="utf-8").startswith("<?xml")


def test_hidden_lines_are_dashed(tmp_path: Path) -> None:
    segments = parse_segments({"segments": [{"kind": "hidden", "points": [[0, 0], [1, 1]]}]})
    files = write_drawing(
        segments,
        {"visible": "VISIBLES", "hidden": "OCULTAS"},
        load_styles(),
        tmp_path / "a.dxf",
        tmp_path / "a.svg",
    )
    assert ezdxf.readfile(files.dxf).layers.get("OCULTAS").dxf.linetype == "DASHED"


def test_an_empty_or_broken_answer_is_explained(tmp_path: Path) -> None:
    with pytest.raises(DrawingError, match="mal formadas"):
        parse_segments({"segments": [{"kind": "visible"}]})
    with pytest.raises(DrawingError, match="ninguna línea"):
        write_drawing(
            [], {"visible": "VISIBLES"}, load_styles(), tmp_path / "a.dxf", tmp_path / "a.svg"
        )
