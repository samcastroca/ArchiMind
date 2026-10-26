from typing import Any

import pytest
from archimind_schema import BlocksDraft, Project, Wall, wall_height
from pydantic import ValidationError

_BLOCK = {
    "id": "blq-0001",
    "name": "PUERTA-BATIENTE-900x2100",
    "kind": "door",
    "width": 0.9,
    "height": 2.1,
    "parameters": {"type": "swing_door", "profile": {"name": "Madera"}},
}


def _project(**changes: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": "p",
        "name": "casa",
        "scale_confirmed": True,
        "levels": [{"id": "niv-0001", "name": "PB", "elevation": 0, "default_height": 2.7}],
        "walls": [
            {"id": "muro-0001", "level_id": "niv-0001", "axis": [(0, 0), (5, 0)], "thickness": 0.15}
        ],
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
        "next_ids": {"niv": 2, "muro": 2, "vano": 2, "esp": 1, "blq": 1},
    }
    data.update(changes)
    return data


def test_proyecto_valido() -> None:
    project = Project.model_validate(_project())
    assert wall_height(project, project.walls[0]) == 2.7


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"units": "mm"}, "units"),
        ({"next_ids": {"niv": 1, "muro": 2, "vano": 2, "esp": 1, "blq": 1}}, "contador"),
        ({"next_ids": {"niv": 2, "muro": 2}}, "prefijos"),
        ({"layer_mapping": {"A-MURO": "muros"}}, "layer_mapping"),
        ({"blocks": [_BLOCK]}, "contador"),  # blq-0001 con el contador de blq en 1
        ({"blocks": [_BLOCK | {"parameters": {"width": float("inf")}}]}, "finite"),
    ],
)
def test_proyecto_rechaza_incoherencias(changes: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        Project.model_validate(_project(**changes))


def test_eje_con_tramo_nulo() -> None:
    with pytest.raises(ValidationError, match="longitud nula"):
        Wall(id="muro-0001", level_id="niv-0001", axis=[(0, 0), (0, 0)], thickness=0.1)


def test_borrador_de_bloques() -> None:
    block = {key: value for key, value in _BLOCK.items() if key != "id"}
    assignment = {"opening_id": "vano-0001", "side": "right", "block": block}
    draft = BlocksDraft.model_validate({"assignments": [assignment]})
    assert BlocksDraft.model_validate_json(draft.model_dump_json()) == draft
    with pytest.raises(ValidationError, match="at least 1"):
        BlocksDraft.model_validate({"assignments": []})
    with pytest.raises(ValidationError, match="side"):
        BlocksDraft.model_validate({"assignments": [assignment | {"side": "in"}]})
