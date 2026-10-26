from pathlib import Path

import ezdxf
import pytest
from archimind_core import LayerSummary, layer_inventory, read_drawing
from golden import GOLDEN_DIR


def _inventory(case: str) -> dict[str, LayerSummary]:
    drawing = read_drawing(GOLDEN_DIR / case / "input.dxf")
    return {summary.layer: summary for summary in layer_inventory(drawing)}


def test_apartment_layers() -> None:
    layers = _inventory("apto_2hab")
    assert {"A-MURO", "A-PUERTA", "A-VENTANA", "A-TEXTO", "A-COTA"} <= set(layers)
    assert set(layers["A-MURO"].entity_counts) == {"LWPOLYLINE"}
    assert layers["A-PUERTA"].entity_counts == {"ARC": 4, "LINE": 4}
    assert set(layers["A-VENTANA"].entity_counts) == {"LINE"}
    assert layers["A-COTA"].entity_counts == {"DIMENSION": 2}
    assert "Baño" in layers["A-TEXTO"].sample_texts
    assert layers["A-MURO"].line_length_m > 0
    assert not layers["A-MURO"].preliminary


def test_door_length_counts_leaves_not_swing_arcs() -> None:
    # Hojas de 0.90 + 0.80 + 0.80 + 0.70; los arcos sueltos no son líneas.
    assert _inventory("apto_2hab")["A-PUERTA"].line_length_m == pytest.approx(3.20)


def test_lengths_are_in_metres_whatever_the_drawing_unit() -> None:
    metres, millimetres = _inventory("apto_2hab"), _inventory("milimetros")
    for layer in ("A-MURO", "A-PUERTA", "A-VENTANA"):
        assert millimetres[layer].line_length_m == pytest.approx(metres[layer].line_length_m)


def test_chaotic_layers_are_reported_as_found() -> None:
    layers = _inventory("apto_capas_caoticas")
    assert {"0", "Capa1", "xx_tmp", "nueva", "DEFPOINTS_2"} <= set(layers)
    assert set(layers["0"].entity_counts) == {"LWPOLYLINE"}


def test_double_line_walls_have_the_same_length_as_polylines() -> None:
    lines, polylines = _inventory("muros_linea_doble"), _inventory("apto_2hab")
    assert set(lines["A-MURO"].entity_counts) == {"LINE"}
    assert lines["A-MURO"].line_length_m == pytest.approx(polylines["A-MURO"].line_length_m)


def _nested_blocks(path: Path) -> None:
    doc = ezdxf.new(units=6)
    leg = doc.blocks.new("PATA")
    leg.add_line((0, 0), (0, 0.5), dxfattribs={"layer": "0"})
    table = doc.blocks.new("MESA")
    table.add_blockref("PATA", (0, 0))
    table.add_blockref("PATA", (1, 0))
    table.add_line((0, 0.5), (1, 0.5), dxfattribs={"layer": "TABLERO"})
    table.add_text("Mesa", dxfattribs={"layer": "0"})
    msp = doc.modelspace()
    msp.add_blockref("MESA", (5, 5), dxfattribs={"layer": "MUEBLE"})
    msp.add_line((0, 0), (10, 0), dxfattribs={"layer": "A-MURO"})
    doc.paperspace().add_line((0, 0), (99, 0), dxfattribs={"layer": "PAPEL"})
    doc.saveas(path)


def test_nested_blocks_are_exploded_for_analysis_only(tmp_path: Path) -> None:
    path = tmp_path / "bloques.dxf"
    _nested_blocks(path)
    drawing = read_drawing(path)
    entity_count = len(drawing.doc.entitydb)
    block_sizes = {name: len(drawing.doc.blocks.get(name)) for name in ("MESA", "PATA")}
    modelspace_size = len(drawing.doc.modelspace())

    layers = {summary.layer: summary for summary in layer_inventory(drawing)}

    # Las patas (capa 0 dentro de PATA, insertada en capa 0 dentro de MESA) heredan MUEBLE.
    assert layers["MUEBLE"].entity_counts == {"INSERT": 3, "LINE": 2, "TEXT": 1}
    assert layers["MUEBLE"].blocks == {"MESA": 1, "PATA": 2}
    assert layers["MUEBLE"].line_length_m == pytest.approx(1.0)
    assert layers["MUEBLE"].sample_texts == ["Mesa"]
    assert layers["TABLERO"].line_length_m == pytest.approx(1.0)
    assert "PAPEL" not in layers
    assert "0" not in layers
    assert len(drawing.doc.entitydb) == entity_count
    assert len(drawing.doc.modelspace()) == modelspace_size
    assert {name: len(drawing.doc.blocks.get(name)) for name in block_sizes} == block_sizes


def test_unconfirmed_scale_marks_inventory_preliminary(tmp_path: Path) -> None:
    doc = ezdxf.readfile(GOLDEN_DIR / "milimetros" / "input.dxf")
    doc.header["$INSUNITS"] = 0
    doc.saveas(tmp_path / "sin_unidades.dxf")
    drawing = read_drawing(tmp_path / "sin_unidades.dxf")
    summaries = layer_inventory(drawing)
    assert all(summary.preliminary for summary in summaries)
    metres = _inventory("apto_2hab")
    walls = next(s for s in summaries if s.layer == "A-MURO")
    assert walls.line_length_m == pytest.approx(metres["A-MURO"].line_length_m)
