"""Partidas del modelo, materiales asignados y cifras para la memoria."""

import json

import pytest
from archimind_core import define_heights
from archimind_docs.database import BudgetItem, Material
from archimind_docs.items import MISSING_HEIGHT, assigned_materials, measure, model_items
from archimind_docs.memory import memory_data
from archimind_schema import Block, Level, Opening, Project, Wall, new_id, space_area
from cases import apto_2hab
from hypothesis import given, settings
from hypothesis import strategies as st


def _confirmed() -> Project:
    project, _ = apto_2hab()
    return define_heights(project, {project.levels[0].id: 2.6}, None).project


def _items(project: Project) -> dict[str, tuple[float | None, str | None]]:
    return {i.key: (i.quantity, i.missing) for i in model_items(project)}


def test_apto_2hab_items() -> None:
    items = _items(_confirmed())
    assert items["puerta-0.90x2.10"] == (1, None)
    assert items["puerta-0.80x2.10"] == (2, None)
    assert items["ventana-1.50x1.20"] == (3, None)
    assert items["ventana-0.60x0.60"] == (1, None)
    assert {k for k in items if k.startswith("muro-")} == {"muro-0.10", "muro-0.12", "muro-0.20"}
    assert items["piso-servicio"][0] == pytest.approx(1.89 * 1.55)  # el baño
    assert "piso-balcon" not in items


def test_walls_without_heights_have_no_quantity() -> None:
    project, _ = apto_2hab()
    items = _items(project)
    assert items["muro-0.20"] == (None, MISSING_HEIGHT)
    assert items["puerta-0.90x2.10"] == (1, None)


@settings(max_examples=40, deadline=None)
@given(
    length=st.floats(2, 20),
    height=st.floats(2, 4),
    width=st.floats(0.5, 1.5),
    tall=st.floats(0.5, 3),
    sill=st.floats(0, 1.5),
)
def test_a_wall_face_is_length_by_height_minus_its_openings(
    length: float, height: float, width: float, tall: float, sill: float
) -> None:
    project = Project(id="p", name="p", scale_confirmed=True)
    level = Level(id=new_id(project, "niv"), name="PB", elevation=0, default_height=height)
    level.height_confirmed = True
    wall = Wall(
        id=new_id(project, "muro"), level_id=level.id, axis=[(0, 0), (length, 0)], thickness=0.15
    )
    opening = Opening(
        id=new_id(project, "vano"),
        wall_id=wall.id,
        kind="window",
        offset=0.1,
        width=width,
        height=tall,
        sill_height=sill,
    )
    project.levels, project.walls, project.openings = [level], [wall], [opening]
    inside = max(0.0, min(tall, height - sill))  # lo que el vano ocupa dentro del muro
    expected = length * height - width * inside
    assert _items(project)["muro-0.15"][0] == pytest.approx(expected)


def test_measures_keep_two_decimals_or_three_if_needed() -> None:
    assert [measure(v) for v in (0.1, 0.15, 0.125, 2.1)] == ["0.10", "0.15", "0.125", "2.10"]


def test_materials_from_the_budget_and_from_carpentry() -> None:
    project = _confirmed()
    block = Block(
        id=new_id(project, "blq"),
        name="P-090",
        kind="door",
        width=0.9,
        height=2.1,
        parameters={"profile": {"name": "Madera maciza", "material": "madera"}},
    )
    project.blocks = [block]
    door = next(o for o in project.openings if o.kind == "door" and o.width == 0.9)
    door.block_id, door.block_side = block.id, "left"
    budget = {
        "muro-0.20": BudgetItem(partida="muro-0.20", codigo_apu="A1", codigo_material="M-01"),
        "piso-util": BudgetItem(partida="piso-util", codigo_apu="A2", codigo_material="X-9"),
        "muro-0.12": BudgetItem(partida="muro-0.12", codigo_apu="A3"),
    }
    stored = {"M-01": Material(codigo="M-01", norma="NTC 4026", descripcion="Bloque", unidad="un")}
    assigned = assigned_materials(project, model_items(project), budget, stored)
    assert [(m.source, m.code, m.description, m.standard, m.note) for m in assigned] == [
        ("partida muro-0.20", "M-01", "Bloque", "NTC 4026", None),
        ("partida piso-util", "X-9", "", None, "el código no está en la tabla materials"),
        ("carpintería P-090 (perfil Madera maciza, 1 vanos)", None, "madera", None, None),
    ]


def test_memory_data_has_the_verified_figures() -> None:
    project = _confirmed()
    data = memory_data(project, model_items(project), [])
    json.dumps(data)  # serializable
    assert data["proyecto"] == {"nombre": "apto_2hab", "escala_confirmada": True, "aviso": None}
    assert data["niveles"] == [{"nombre": "Planta baja", "cota_m": 0.0, "altura_m": 2.6}]
    assert data["conteos"]["vanos_por_tipo"] == {"puertas": 4, "ventanas": 5}
    areas = data["areas_m2"]
    assert [s["nombre"] for s in areas["espacios"]] == [s.name for s in project.spaces]
    assert areas["util"] == round(sum(space_area(s) for s in project.spaces), 2)


def test_an_unconfirmed_height_is_not_a_figure() -> None:
    project, _ = apto_2hab()
    project.scale_confirmed = False
    data = memory_data(project, model_items(project), [])
    assert data["niveles"][0]["altura_m"] is None
    assert data["proyecto"]["aviso"] == "PRELIMINAR: escala sin confirmar"
