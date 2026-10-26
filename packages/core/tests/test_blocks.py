from pathlib import Path
from typing import Any

import pytest
from archimind_core import (
    BlocksError,
    apply_block_draft,
    assign_blocks,
    build_model,
    compare_versions,
    open_project,
    read_drawing,
)
from archimind_schema import BlocksDraft, Project, load_project, save_project, validate
from cases import expected_project
from golden import GOLDEN_DIR


def _block(name: str, kind: str = "door", width: float = 0.9, height: float = 2.1) -> Any:
    return {
        "name": name,
        "kind": kind,
        "width": width,
        "height": height,
        "parameters": {"type": "swing_door" if kind == "door" else "fixed_window"},
    }


def _draft(*assignments: tuple[str, str, Any]) -> BlocksDraft:
    return BlocksDraft.model_validate(
        {
            "assignments": [
                {"opening_id": opening, "side": side, "block": block}
                for opening, side, block in assignments
            ]
        }
    )


def _apto() -> Project:
    """apto_2hab: vano-0001 puerta 0.90 × 2.10; vano-0007 y vano-0008, puertas 0.80 × 2.10;
    vano-0005, ventana 0.60 × 0.60."""
    return expected_project("apto_2hab")


def test_assigns_new_blocks_with_unpublished_ids() -> None:
    project = _apto()
    project.next_ids["blq"] = 7  # como si se hubieran retirado blq-0001 a blq-0006

    result = assign_blocks(
        project,
        _draft(
            ("vano-0001", "left", _block("PUERTA-A")),
            ("vano-0005", "right", _block("VENTANA-B", "window", 0.6, 0.6)),
        ),
    )

    model = result.project
    assert [(b.id, b.name) for b in model.blocks] == [
        ("blq-0007", "PUERTA-A"),
        ("blq-0008", "VENTANA-B"),
    ]
    by_id = {o.id: o for o in model.openings}
    assert (by_id["vano-0001"].block_id, by_id["vano-0001"].block_side) == ("blq-0007", "left")
    assert (by_id["vano-0005"].block_id, by_id["vano-0005"].block_side) == ("blq-0008", "right")
    assert [(a.opening_id, a.block_id, a.new) for a in result.assigned] == [
        ("vano-0001", "blq-0007", True),
        ("vano-0005", "blq-0008", True),
    ]
    assert validate(model) == []
    assert project.blocks == []  # el modelo de entrada no cambia


def test_identical_carpentry_shares_one_block() -> None:
    door = _block("PUERTA-080", width=0.8)
    result = assign_blocks(
        _apto(), _draft(("vano-0007", "left", door), ("vano-0008", "right", door))
    )
    assert [b.id for b in result.project.blocks] == ["blq-0001"]
    assert [a.new for a in result.assigned] == [True, False]


def test_reuses_the_block_already_in_the_model() -> None:
    door = _block("PUERTA-080", width=0.8)
    first = assign_blocks(_apto(), _draft(("vano-0007", "left", door))).project
    second = assign_blocks(first, _draft(("vano-0008", "left", door)))
    assert [b.id for b in second.project.blocks] == ["blq-0001"]
    assert second.assigned[0].new is False and second.removed == []


def test_blocks_left_unused_are_removed_and_their_ids_retired() -> None:
    first = assign_blocks(_apto(), _draft(("vano-0001", "left", _block("PUERTA-A")))).project
    second = assign_blocks(first, _draft(("vano-0001", "right", _block("PUERTA-B"))))
    assert [b.id for b in second.project.blocks] == ["blq-0002"]
    assert second.removed == ["blq-0001"]
    assert second.project.next_ids["blq"] == 3


def test_a_void_takes_the_kind_of_its_block() -> None:
    project = _apto()
    project.openings[0].kind = "void"
    result = assign_blocks(project, _draft(("vano-0001", "left", _block("PUERTA-A"))))
    assert result.project.openings[0].kind == "door"


@pytest.mark.parametrize(
    ("assignments", "message"),
    [
        ((("vano-0099", "left", _block("P")),), "el vano vano-0099 no existe"),
        ((("vano-0005", "left", _block("P", width=0.6, height=0.6)),), "es una ventana"),
        ((("vano-0001", "left", _block("P", width=0.95)),), "mide 0.900 × 2.100 m"),
        ((("vano-0001", "left", _block("P")), ("vano-0001", "right", _block("Q"))), "dos"),
    ],
)
def test_a_draft_that_does_not_fit_changes_nothing(
    assignments: tuple[tuple[str, str, Any], ...], message: str
) -> None:
    project = _apto()
    with pytest.raises(BlocksError, match=message) as error:
        assign_blocks(project, _draft(("vano-0007", "left", _block("OK", width=0.8)), *assignments))
    assert "insertar_bloques_en_plano" in str(error.value)
    assert project.blocks == [] and all(o.block_id is None for o in project.openings)


def test_apply_reads_the_draft_from_the_project_folder(tmp_path: Path) -> None:
    folder = open_project(tmp_path / "casa").folder
    save_project(_apto().model_copy(update={"id": "casa", "name": "casa"}), folder)
    draft = folder / "salidas" / "borrador_bloques.json"
    draft.write_text(_draft(("vano-0001", "left", _block("PUERTA-A"))).model_dump_json())

    result = apply_block_draft(folder, "salidas/borrador_bloques.json")

    assert load_project(folder) == result.project
    assert load_project(folder).openings[0].block_id == "blq-0001"


@pytest.mark.parametrize(
    ("content", "message"),
    [(None, "No existe el borrador"), ('{"assignments": []}', "no es un borrador de bloques")],
)
def test_apply_rejects_a_missing_or_invalid_draft(
    tmp_path: Path, content: str | None, message: str
) -> None:
    folder = open_project(tmp_path / "casa").folder
    before = (folder / "modelo.json").read_text(encoding="utf-8")
    draft = folder / "salidas" / "borrador_bloques.json"
    if content is not None:
        draft.write_text(content)
    with pytest.raises(BlocksError, match=message):
        apply_block_draft(folder, draft)
    assert (folder / "modelo.json").read_text(encoding="utf-8") == before


def test_side_and_block_changes_show_up_between_versions() -> None:
    first = assign_blocks(_apto(), _draft(("vano-0001", "left", _block("PUERTA-A")))).project
    flipped = assign_blocks(first, _draft(("vano-0001", "right", _block("PUERTA-A")))).project
    assert compare_versions(_apto(), first).openings_modified == ["vano-0001"]
    assert compare_versions(first, flipped).openings_modified == ["vano-0001"]


def test_a_rebuild_drops_the_blocks_but_keeps_their_ids_retired() -> None:
    with_blocks = assign_blocks(_apto(), _draft(("vano-0001", "left", _block("PUERTA-A")))).project
    drawing = read_drawing(GOLDEN_DIR / "apto_2hab" / "input.dxf")
    rebuilt = build_model(drawing, {"A-MURO": "walls"}, base=with_blocks).project
    assert rebuilt.blocks == [] and all(o.block_id is None for o in rebuilt.openings)
    assert rebuilt.next_ids["blq"] == 2
