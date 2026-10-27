"""Borrador de ediciones de geometría que entrega el puente de Rhino."""

from typing import Any

import pytest
from archimind_schema import EditsDraft
from pydantic import ValidationError

SHA = "a" * 64


def _draft(**changes: Any) -> dict[str, Any]:
    return {"source": "rhino", "base_sha256": SHA, **changes}


WALL = {"id": "muro-0001", "axis": [(0, 0), (4, 0)], "thickness": 0.15, "height": None}
OPENING = {"id": "vano-0002", "offset": 0.5, "width": 0.9, "height": 2.1, "sill_height": 0}
SPACE = {"id": "esp-0003", "polygon": {"exterior": [(0, 0), (4, 0), (4, 3)]}, "name": "Estar"}
NEW_WALL = {"ref": "nuevo-1", "level_id": "niv-0001", "axis": [(0, 0), (0, 3)], "thickness": 0.1}
NEW_OPENING: dict[str, Any] = {"ref": "nuevo-2", "wall": "nuevo-1", "offset": 1, "width": 0.8}
NEW_OPENING |= {"height": 2.0, "sill_height": 0}
NEW_SPACE: dict[str, Any] = {"ref": "nuevo-3", "level_id": "niv-0001", "name": "Depósito"}
NEW_SPACE |= {"polygon": {"exterior": [(0, 0), (1, 0), (1, 1)]}}


def test_round_trips_through_json() -> None:
    draft = EditsDraft.model_validate(
        _draft(walls=[WALL], openings=[OPENING], spaces=[SPACE], deleted=["vano-0009"])
    )
    assert EditsDraft.model_validate_json(draft.model_dump_json()) == draft


def test_new_entities_round_trip_with_their_defaults() -> None:
    draft = EditsDraft.model_validate(
        _draft(new_walls=[NEW_WALL], new_openings=[NEW_OPENING], new_spaces=[NEW_SPACE])
    )
    assert draft.new_openings[0].kind == "void"
    assert draft.new_spaces[0].category == "useful"
    assert EditsDraft.model_validate_json(draft.model_dump_json()) == draft


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"new_walls": [NEW_WALL, NEW_WALL]}, "refs repetidos"),
        ({"new_openings": [NEW_OPENING]}, "no es un muro"),
        ({"new_openings": [NEW_OPENING | {"wall": "esp-0001"}]}, "no es un muro"),
        (
            {"new_openings": [NEW_OPENING | {"wall": "muro-0001"}], "deleted": ["muro-0001"]},
            "muro borrado",
        ),
        ({"new_walls": [NEW_WALL | {"ref": "muro-0001"}]}, "ref"),
        ({"new_spaces": [NEW_SPACE | {"name": ""}]}, "name"),
    ],
)
def test_rejects_inconsistent_new_entities(changes: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        EditsDraft.model_validate(_draft(**changes))


def test_rejects_an_empty_draft() -> None:
    with pytest.raises(ValidationError, match="ningún cambio"):
        EditsDraft.model_validate(_draft())


def test_rejects_repeated_ids() -> None:
    with pytest.raises(ValidationError, match="repetidos"):
        EditsDraft.model_validate(_draft(walls=[WALL], deleted=["muro-0001"]))


@pytest.mark.parametrize(
    "changes",
    [
        {"walls": [WALL | {"id": "vano-0001"}]},
        {"openings": [OPENING | {"id": "muro-0002"}]},
        {"spaces": [SPACE | {"id": "esp-3"}]},
        {"deleted": ["blq-0001"]},
    ],
)
def test_rejects_ids_with_the_wrong_prefix(changes: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        EditsDraft.model_validate(_draft(**changes))


def test_rejects_a_malformed_base_hash() -> None:
    with pytest.raises(ValidationError):
        EditsDraft.model_validate(_draft(deleted=["muro-0001"]) | {"base_sha256": "abc"})
