import math
from pathlib import Path

import ezdxf
import pytest
from archimind_core import (
    DEFAULT_RULES_PATH,
    LayerProposal,
    LayerRulesError,
    load_rules,
    propose_mapping,
    read_drawing,
)
from archimind_core.layer_roles import Segment, find_wall_pairs
from archimind_schema import WALL_THICKNESSES
from golden import GOLDEN_DIR
from hypothesis import given
from hypothesis import strategies as st

RULES = load_rules()


def _proposals(path: Path) -> dict[str, LayerProposal]:
    return {p.layer: p for p in propose_mapping(read_drawing(path))}


def _case(case: str) -> dict[str, LayerProposal]:
    return _proposals(GOLDEN_DIR / case / "input.dxf")


def _roles(proposals: dict[str, LayerProposal]) -> dict[str, str]:
    return {layer: p.role for layer, p in proposals.items()}


APARTMENT_ROLES = {
    "A-MURO": "walls",
    "A-PUERTA": "doors",
    "A-VENTANA": "windows",
    "A-TEXTO": "text",
    "A-COTA": "dimensions",
}


def test_apartment_layers_are_all_right_and_confident() -> None:
    proposals = _case("apto_2hab")
    assert _roles(proposals) == APARTMENT_ROLES
    for proposal in proposals.values():
        assert proposal.confidence >= 0.9, proposal
        assert proposal.evidence.endswith(".")
    assert "MURO" in proposals["A-MURO"].evidence
    assert "0.20" in proposals["A-MURO"].evidence


@pytest.mark.parametrize("case", ["milimetros", "muros_linea_doble"])
def test_same_mapping_whatever_the_units_or_wall_entities(case: str) -> None:
    assert _roles(_case(case)) == APARTMENT_ROLES


def test_chaotic_layers_find_the_walls_by_geometry() -> None:
    proposals = _case("apto_capas_caoticas")
    assert proposals["0"].role == "walls"
    assert 0.5 < proposals["0"].confidence < 0.9
    assert [layer for layer, p in proposals.items() if p.role == "walls"] == ["0"]
    # Sin meta exigida, pero la geometría también las reconoce.
    assert proposals["Capa1"].role == "doors"
    assert proposals["xx_tmp"].role == "windows"
    assert proposals["nueva"].role == "text"
    # El nombre dice DEFPOINTS (ignorar), pero lleva cotas: gana la geometría.
    assert proposals["DEFPOINTS_2"].role == "dimensions"
    assert proposals["DEFPOINTS_2"].confidence == RULES.confidence.conflict


def _wall_rectangle(msp: ezdxf.layouts.Modelspace, layer: str, thickness: float) -> None:
    for y in (0.0, thickness):
        msp.add_line((0, y), (5, y), dxfattribs={"layer": layer})


def test_layer_mixing_roles_is_marked_mixed(tmp_path: Path) -> None:
    doc = ezdxf.new(units=6)
    msp = doc.modelspace()
    _wall_rectangle(msp, "A-MURO", 0.15)
    for i in range(10):
        msp.add_text(f"Texto {i}", dxfattribs={"layer": "A-MURO"})
    doc.saveas(tmp_path / "mixta.dxf")
    proposal = _proposals(tmp_path / "mixta.dxf")["A-MURO"]
    assert proposal.role == "mixed"
    assert "textos" in proposal.evidence and "pares de tramos" in proposal.evidence


def test_geometry_wins_over_a_contradicting_name(tmp_path: Path) -> None:
    doc = ezdxf.new(units=6)
    doc.modelspace().add_text("Salón", dxfattribs={"layer": "MUROS"})
    doc.saveas(tmp_path / "conflicto.dxf")
    proposal = _proposals(tmp_path / "conflicto.dxf")["MUROS"]
    assert proposal.role == "text"
    assert proposal.confidence == RULES.confidence.conflict
    assert "muros (MUROS)" in proposal.evidence


def test_name_alone_and_no_signal(tmp_path: Path) -> None:
    doc = ezdxf.new(units=6)
    msp = doc.modelspace()
    msp.add_line((0, 0), (30, 0), dxfattribs={"layer": "S-GRID"})
    msp.add_circle((0, 0), 1, dxfattribs={"layer": "basura"})
    doc.saveas(tmp_path / "ejes.dxf")
    proposals = _proposals(tmp_path / "ejes.dxf")
    assert proposals["S-GRID"].role == "axes"
    assert proposals["S-GRID"].confidence == RULES.confidence.name_only
    assert proposals["basura"].role == "ignore"
    assert proposals["basura"].confidence == RULES.confidence.none


def test_inserts_are_recognised_by_block_name(tmp_path: Path) -> None:
    doc = ezdxf.new(units=6)
    door = doc.blocks.new("PUERTA_90")
    door.add_line((0, 0), (0.9, 0))
    table = doc.blocks.new("MESA_4P")
    table.add_lwpolyline([(0, 0), (1, 0), (1, 1), (0, 1)], close=True)
    msp = doc.modelspace()
    msp.add_blockref("PUERTA_90", (0, 0), dxfattribs={"layer": "L1"})
    msp.add_blockref("PUERTA_90", (3, 0), dxfattribs={"layer": "L1"})
    msp.add_blockref("MESA_4P", (5, 5), dxfattribs={"layer": "L2"})
    doc.saveas(tmp_path / "bloques.dxf")
    proposals = _proposals(tmp_path / "bloques.dxf")
    assert proposals["L1"].role == "doors"
    assert "2 bloques PUERTA_90" in proposals["L1"].evidence
    assert proposals["L2"].role == "furniture"


def test_unconfirmed_scale_is_stated_in_the_evidence(tmp_path: Path) -> None:
    doc = ezdxf.readfile(GOLDEN_DIR / "milimetros" / "input.dxf")
    doc.header["$INSUNITS"] = 0
    doc.saveas(tmp_path / "sin_unidades.dxf")
    proposals = _proposals(tmp_path / "sin_unidades.dxf")
    assert _roles(proposals) == APARTMENT_ROLES
    assert all("escala no confirmada" in p.evidence for p in proposals.values())


def test_alternative_rules_file(tmp_path: Path) -> None:
    text = DEFAULT_RULES_PATH.read_text(encoding="utf-8").replace(
        "walls: [MURO, MUR, WALL, TABIQUE]", "walls: [PARED]"
    )
    (tmp_path / "reglas.yaml").write_text(text, encoding="utf-8")
    rules = load_rules(tmp_path / "reglas.yaml")
    assert rules.name_matches("A-PARED") == {"walls": "PARED"}
    assert rules.name_matches("A-MURO") == {}


@pytest.mark.parametrize(
    ("content", "message"),
    [("name_patterns: [", "YAML"), ("name_patterns: {paredes: [X]}", "inválidas")],
)
def test_broken_rules_file(tmp_path: Path, content: str, message: str) -> None:
    (tmp_path / "reglas.yaml").write_text(content, encoding="utf-8")
    with pytest.raises(LayerRulesError, match=message):
        load_rules(tmp_path / "reglas.yaml")


def test_missing_rules_file(tmp_path: Path) -> None:
    with pytest.raises(LayerRulesError, match="No se pudo leer"):
        load_rules(tmp_path / "no_existe.yaml")


def _transformed(points: list[tuple[float, float]], angle: float, dx: float, dy: float) -> Segment:
    c, s = math.cos(angle), math.sin(angle)
    (a, b) = [(x * c - y * s + dx, x * s + y * c + dy) for x, y in points]
    return Segment(a, b)


placements = st.tuples(
    st.floats(min_value=0, max_value=2 * math.pi),
    st.floats(min_value=-1000, max_value=1000),
    st.floats(min_value=-1000, max_value=1000),
)


@given(st.sampled_from(WALL_THICKNESSES), st.floats(min_value=0.5, max_value=20), placements)
def test_wall_pair_found_wherever_the_wall_is(
    thickness: float, length: float, placement: tuple[float, float, float]
) -> None:
    faces = [
        _transformed([(0, 0), (length, 0)], *placement),
        _transformed([(length, thickness), (0, thickness)], *placement),
    ]
    pairs = find_wall_pairs(faces, RULES)
    assert [(min(a, b), max(a, b), t) for a, b, t in pairs] == [(0, 1, thickness)]


@given(
    st.floats(min_value=0.03, max_value=0.40).filter(
        lambda gap: all(abs(gap - t) > 0.002 for t in WALL_THICKNESSES)
    ),
    placements,
)
def test_no_wall_pair_at_an_unusual_gap(gap: float, placement: tuple[float, float, float]) -> None:
    faces = [
        _transformed([(0, 0), (4, 0)], *placement),
        _transformed([(0, gap), (4, gap)], *placement),
    ]
    assert find_wall_pairs(faces, RULES) == []


@given(st.sampled_from(WALL_THICKNESSES), placements)
def test_no_wall_pair_without_overlap(
    thickness: float, placement: tuple[float, float, float]
) -> None:
    faces = [
        _transformed([(0, 0), (2, 0)], *placement),
        _transformed([(3, thickness), (5, thickness)], *placement),
    ]
    assert find_wall_pairs(faces, RULES) == []
