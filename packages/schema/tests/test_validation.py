from typing import Any

import pytest
from archimind_schema import Level, Opening, Problem, Project, Space, Wall, validate
from hypothesis import given
from schema_strategies import projects


def _wall(wall_id: str, axis: list[tuple[float, float]], thickness: float = 0.15) -> Any:
    return {"id": wall_id, "level_id": "niv-0001", "axis": axis, "thickness": thickness}


def _data() -> dict[str, Any]:
    """Planta en L con una puerta y un espacio: no tiene ningún problema."""
    return {
        "id": "p",
        "name": "casa",
        "scale_confirmed": True,
        "levels": [
            {"id": "niv-0001", "name": "PB", "elevation": 0, "default_height": 2.7},
            {"id": "niv-0002", "name": "P1", "elevation": 2.7, "default_height": 2.7},
        ],
        "walls": [_wall("muro-0001", [(0, 0), (5, 0)]), _wall("muro-0002", [(5, 0), (5, 4)])],
        "openings": [
            {
                "id": "vano-0001",
                "wall_id": "muro-0001",
                "kind": "door",
                "offset": 1,
                "width": 0.9,
                "height": 2.1,
                "sill_height": 0,
            }
        ],
        "spaces": [
            {
                "id": "esp-0001",
                "level_id": "niv-0001",
                "name": "sala",
                "polygon": {"exterior": [(0, 0), (4, 0), (4, 4), (0, 4)]},
                "category": "useful",
            }
        ],
        "next_ids": {"niv": 3, "muro": 10, "vano": 10, "esp": 10, "blq": 10},
    }


def _problems(data: dict[str, Any]) -> list[Problem]:
    return validate(Project.model_validate(data))


def _codes(data: dict[str, Any]) -> list[str]:
    return [problem.code for problem in _problems(data)]


def _only(data: dict[str, Any], code: str) -> Problem:
    matches = [problem for problem in _problems(data) if problem.code == code]
    assert len(matches) == 1, matches
    return matches[0]


def _opening(opening_id: str, offset: float, width: float = 0.9) -> dict[str, Any]:
    return {
        "id": opening_id,
        "wall_id": "muro-0001",
        "kind": "window",
        "offset": offset,
        "width": width,
        "height": 1.2,
        "sill_height": 0.9,
    }


def _space(space_id: str, exterior: list[tuple[float, float]], level: str = "niv-0001") -> Any:
    return {
        "id": space_id,
        "level_id": level,
        "name": "x",
        "polygon": {"exterior": exterior},
        "category": "useful",
    }


def test_proyecto_base_sin_problemas() -> None:
    assert _problems(_data()) == []


def test_id_repetido() -> None:
    data = _data()
    data["spaces"].append(_space("esp-0001", [(10, 10), (11, 10), (11, 11)]))
    problem = _only(data, "id_repetido")
    assert (problem.severity, problem.ids) == ("error", ["esp-0001"])


@pytest.mark.parametrize(
    ("path", "value", "bad_id"),
    [
        (("walls", 1, "id"), "muro-2", "muro-2"),
        (("levels", 1, "id"), "nivel-0002", "nivel-0002"),
        (("openings", 0, "block_id"), "bloque", "bloque"),
    ],
)
def test_prefijo_invalido(path: tuple[str, int, str], value: str, bad_id: str) -> None:
    data = _data()
    collection, index, field = path
    data[collection][index][field] = value
    problem = _only(data, "prefijo_invalido")
    assert (problem.severity, problem.ids) == ("error", [bad_id])


def test_prefijo_valido_con_bloque() -> None:
    data = _data()
    data["openings"][0]["block_id"] = "blq-0001"
    assert "prefijo_invalido" not in _codes(data)


def test_nivel_inexistente() -> None:
    data = _data()
    data["spaces"][0]["level_id"] = "niv-0009"
    problem = _only(data, "nivel_inexistente")
    assert (problem.severity, problem.ids) == ("error", ["esp-0001"])


def test_muro_inexistente_no_evalua_el_vano() -> None:
    data = _data()
    data["openings"][0]["wall_id"] = "muro-0009"
    data["openings"][0]["offset"] = 40
    assert _codes(data) == ["muro_inexistente"]
    assert _only(data, "muro_inexistente").ids == ["vano-0001"]


@pytest.mark.parametrize(
    "exterior",
    [
        [(0, 0), (1, 1), (1, 0), (0, 1)],  # autointersecante
        [(0, 0), (1, 0), (0, 0)],  # no cierra un área
        [(0, 0), (1, 0), (2, 0)],  # área nula
    ],
)
def test_poligono_invalido(exterior: list[tuple[float, float]]) -> None:
    data = _data()
    data["spaces"][0]["polygon"]["exterior"] = exterior
    problem = _only(data, "poligono_invalido")
    assert (problem.severity, problem.ids) == ("error", ["esp-0001"])


def test_poligono_con_cierre_explicito_es_valido() -> None:
    data = _data()
    data["spaces"][0]["polygon"]["exterior"] = [(0, 0), (4, 0), (4, 4), (0, 4), (0, 0)]
    assert _problems(data) == []


def test_espacios_superpuestos() -> None:
    data = _data()
    data["spaces"].append(_space("esp-0002", [(3.95, 0), (8, 0), (8, 4), (3.95, 4)]))
    problem = _only(data, "espacios_superpuestos")
    assert (problem.severity, problem.ids) == ("error", ["esp-0001", "esp-0002"])


@pytest.mark.parametrize(
    ("x0", "level"),
    [
        (4, "niv-0001"),  # contiguos
        (3.9995, "niv-0001"),  # solape de 0.5 mm, dentro de la tolerancia
        (3.5, "niv-0002"),  # se solapan, pero en otro nivel
    ],
)
def test_espacios_sin_superposicion(x0: float, level: str) -> None:
    data = _data()
    data["spaces"].append(_space("esp-0002", [(x0, 0), (8, 0), (8, 4), (x0, 4)], level))
    assert "espacios_superpuestos" not in _codes(data)


def test_vano_fuera_del_muro() -> None:
    data = _data()
    data["openings"][0]["offset"] = 4.5
    problem = _only(data, "vano_fuera_del_muro")
    assert (problem.severity, problem.ids) == ("error", ["vano-0001", "muro-0001"])


def test_vano_hasta_el_extremo_del_muro() -> None:
    data = _data()
    data["openings"][0]["offset"] = 4.1
    assert _problems(data) == []


def test_vanos_superpuestos() -> None:
    data = _data()
    data["openings"].append(_opening("vano-0002", offset=1.5))
    problem = _only(data, "vanos_superpuestos")
    assert (problem.severity, problem.ids) == ("error", ["vano-0001", "vano-0002"])


def test_vanos_contiguos() -> None:
    data = _data()
    data["openings"].append(_opening("vano-0002", offset=1.9))
    assert _problems(data) == []


@pytest.mark.parametrize("thickness", [0, -0.1])
def test_espesor_no_positivo(thickness: float) -> None:
    data = _data()
    data["walls"][1]["thickness"] = thickness
    problem = _only(data, "espesor_no_positivo")
    assert (problem.severity, problem.ids) == ("error", ["muro-0002"])
    assert "espesor_inusual" not in _codes(data)


def test_espesor_inusual_es_warning() -> None:
    data = _data()
    data["walls"][1]["thickness"] = 0.17
    problem = _only(data, "espesor_inusual")
    assert (problem.severity, problem.ids) == ("warning", ["muro-0002"])
    assert "espesor_no_positivo" not in _codes(data)


@pytest.mark.parametrize("thickness", [0.10, 0.12, 0.15, 0.20, 0.25, 0.2004])
def test_espesor_habitual(thickness: float) -> None:
    data = _data()
    data["walls"][1]["thickness"] = thickness
    assert _problems(data) == []


def _with_partition(gap: float) -> dict[str, Any]:
    """Tabique que baja hacia la cara superior de muro-0001 (y = 0.075) y se queda a `gap`."""
    data = _data()
    start = 0.075 + gap
    data["walls"].append(_wall("muro-0003", [(3, 3), (3, start)], thickness=0.1))
    return data


def test_union_abierta() -> None:
    problem = _only(_with_partition(0.03), "union_abierta")
    assert (problem.severity, problem.ids) == ("warning", ["muro-0003", "muro-0001"])
    assert "unión abierta" in problem.message


@pytest.mark.parametrize("gap", [0, -0.075, 0.0005, 0.06])
def test_union_cerrada_o_lejana(gap: float) -> None:
    assert "union_abierta" not in _codes(_with_partition(gap))


def test_union_abierta_solo_en_el_mismo_nivel() -> None:
    data = _with_partition(0.03)
    data["walls"][2]["level_id"] = "niv-0002"
    assert "union_abierta" not in _codes(data)


def test_escala_no_confirmada() -> None:
    data = _data()
    data["scale_confirmed"] = False
    problem = _only(data, "escala_no_confirmada")
    assert (problem.severity, problem.ids) == ("warning", [])
    assert "preliminares" in problem.message


@given(projects())
def test_proyectos_generados_sin_errores_de_integridad(project: Project) -> None:
    problems = validate(project)
    entities: list[Level | Wall | Opening | Space] = [
        *project.levels,
        *project.walls,
        *project.openings,
        *project.spaces,
    ]
    known = {entity.id for entity in entities}
    assert all(set(problem.ids) <= known for problem in problems)
    guaranteed = {
        "id_repetido",
        "prefijo_invalido",
        "nivel_inexistente",
        "muro_inexistente",
        "poligono_invalido",
        "vano_fuera_del_muro",
        "espesor_no_positivo",
        "espesor_inusual",
    }
    assert not guaranteed & {problem.code for problem in problems}
    assert ("escala_no_confirmada" in {p.code for p in problems}) is not project.scale_confirmed
