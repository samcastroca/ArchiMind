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
SPACE = {"id": "esp-0003", "polygon": {"exterior": [(0, 0), (4, 0), (4, 3)]}}


def test_round_trips_through_json() -> None:
    draft = EditsDraft.model_validate(
        _draft(walls=[WALL], openings=[OPENING], spaces=[SPACE], deleted=["vano-0009"])
    )
    assert EditsDraft.model_validate_json(draft.model_dump_json()) == draft


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
