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
        ({"levels": []}, "nivel inexistente"),
        ({"walls": []}, "muro inexistente"),
        ({"next_ids": {"niv": 1, "muro": 2, "vano": 2, "esp": 1, "blq": 1}}, "contador"),
        ({"next_ids": {"niv": 2, "muro": 2}}, "prefijos"),
    ],
)
def test_proyecto_rechaza_incoherencias(changes: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        Project.model_validate(_project(**changes))


def test_vano_fuera_del_muro() -> None:
    data = _project()
    data["openings"][0]["offset"] = 4.5
    with pytest.raises(ValidationError, match="se sale"):
        Project.model_validate(data)


def test_ids_repetidos() -> None:
    data = _project()
    data["levels"].append(dict(data["levels"][0]))
    with pytest.raises(ValidationError, match="repetido"):
        Project.model_validate(data)


def test_prefijo_erroneo() -> None:
    with pytest.raises(ValidationError, match="muro-NNNN"):
        Wall(id="niv-0001", level_id="niv-0001", axis=[(0, 0), (1, 0)], thickness=0.1)


def test_eje_con_tramo_nulo() -> None:
    with pytest.raises(ValidationError, match="longitud nula"):
        Wall(id="muro-0001", level_id="niv-0001", axis=[(0, 0), (0, 0)], thickness=0.1)


def test_poligono_autointersecante() -> None:
    data = _project(
        spaces=[
            {
                "id": "esp-0001",
                "level_id": "niv-0001",
                "name": "x",
                "polygon": {"exterior": [(0, 0), (1, 1), (1, 0), (0, 1)]},
                "category": "useful",
            }
        ],
        next_ids={"niv": 2, "muro": 2, "vano": 2, "esp": 2, "blq": 1},
    )
    with pytest.raises(ValidationError, match="no válido"):
        Project.model_validate(data)
