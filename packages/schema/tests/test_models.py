from typing import Any

import pytest
from archimind_schema import Project, Wall, wall_height
from pydantic import ValidationError


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
    ],
)
def test_proyecto_rechaza_incoherencias(changes: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        Project.model_validate(_project(**changes))


def test_eje_con_tramo_nulo() -> None:
    with pytest.raises(ValidationError, match="longitud nula"):
        Wall(id="muro-0001", level_id="niv-0001", axis=[(0, 0), (0, 0)], thickness=0.1)
