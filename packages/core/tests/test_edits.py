"""apply_edits / apply_edits_draft: el borrador de Rhino aplicado al modelo."""

import hashlib
import math
from pathlib import Path
from typing import Any

import pytest
from archimind_core.edits import APPLIED_SUFFIX, EditsError, apply_edits, apply_edits_draft
from archimind_schema import (
    MODEL_FILENAME,
    Block,
    EditsDraft,
    Point2D,
    Project,
    Wall,
    load_project,
    save_project,
    space_area,
)
from golden import load_expected
from hypothesis import given, settings
from hypothesis import strategies as st

SHA = "0" * 64
TOL = 1e-3


def _draft(**changes: Any) -> EditsDraft:
    return EditsDraft.model_validate({"source": "rhino", "base_sha256": SHA, **changes})


def _apto() -> Project:
    return load_expected("apto_2hab")


def _wall(project: Project, start: Point2D, end: Point2D) -> Wall:
    return next(
        w
        for w in project.walls
        if math.dist(w.axis[0], start) < TOL and math.dist(w.axis[-1], end) < TOL
    )


def _areas(project: Project) -> dict[str, float]:
    return {space.name: round(space_area(space), 3) for space in project.spaces}


def _partition(project: Project) -> Wall:
    """El tabique de 0.10 entre las dos habitaciones."""
    return _wall(project, (0, 3.6), (3.5, 3.6))


def _wall_edit(wall: Wall, **changes: Any) -> dict[str, Any]:
    return {"id": wall.id, "axis": wall.axis, "thickness": wall.thickness, "height": None} | changes


# --- Muros ------------------------------------------------------------------------------------


def test_moving_a_partition_moves_the_rooms_beside_it() -> None:
    apto = _apto()
    wall = _partition(apto)
    result = apply_edits(apto, _draft(walls=[_wall_edit(wall, axis=[(0, 3.8), (3.5, 3.8)])]))
    assert _wall(result.project, (0, 3.8), (3.5, 3.8)).id == wall.id
    after, before = _areas(result.project), _areas(apto)
    assert after["Habitación 1"] == pytest.approx(8.517, abs=TOL)
    assert after["Habitación 2"] == pytest.approx(12.191, abs=TOL)
    assert after["Baño"] == before["Baño"]
    assert after["Sala-comedor-cocina"] == before["Sala-comedor-cocina"]
    assert [s.id for s in result.project.spaces] == [s.id for s in apto.spaces]
    assert not [p for p in result.problems if p.code.startswith(("espacio_", "contorno_"))]
    assert _partition(apto).axis == [(0, 3.6), (3.5, 3.6)]  # el original no cambia


def test_a_thicker_wall_shrinks_the_rooms_beside_it() -> None:
    apto = _apto()
    wall = _partition(apto)
    result = apply_edits(apto, _draft(walls=[_wall_edit(wall, thickness=0.2)]))
    after = _areas(result.project)
    assert _partition(result.project).thickness == 0.2
    assert after["Habitación 1"] == pytest.approx(9.185 - 0.05 * 3.34, abs=TOL)
    assert after["Habitación 2"] == pytest.approx(11.523 - 0.05 * 3.34, abs=TOL)


def test_a_new_wall_splits_a_room() -> None:
    apto = _apto()
    new_wall = {"ref": "nuevo-1", "level_id": "niv-0001", "axis": [(5.5, 0), (5.5, 4.8)]}
    result = apply_edits(apto, _draft(new_walls=[new_wall | {"thickness": 0.1}]))
    wall_id = result.new_ids["nuevo-1"]
    assert wall_id not in {w.id for w in apto.walls}
    assert result.project.next_ids["muro"] == apto.next_ids["muro"] + 1
    after = _areas(result.project)
    assert after["Sala-comedor-cocina"] == pytest.approx(2.85 * 6.3, abs=TOL)
    assert after["Espacio sin nombre 1"] == pytest.approx(1.89 * 4.65, abs=TOL)
    assert [p.code for p in result.problems if p.code == "espacio_nuevo"] == ["espacio_nuevo"]


def test_deleting_a_wall_deletes_its_door_and_merges_the_rooms() -> None:
    apto = _apto()
    bath_south = _wall(apto, (3.5, 4.8), (5.5, 4.8))
    door = next(o for o in apto.openings if o.wall_id == bath_south.id)
    result = apply_edits(apto, _draft(deleted=[bath_south.id]))
    assert door.id not in {o.id for o in result.project.openings}
    assert "Baño" not in _areas(result.project)
    (removed,) = [p for p in result.problems if p.code == "espacio_quitado"]
    assert "se unió al de" in removed.message and "Sala-comedor-cocina" in removed.message


# --- Vanos y espacios ---------------------------------------------------------------------------


def test_a_moved_and_resized_door_keeps_the_spaces() -> None:
    apto = _apto()
    spine = _wall(apto, (3.5, 0), (3.5, 6.5))
    door = next(o for o in apto.openings if o.wall_id == spine.id)
    edit = {"id": door.id, "offset": 2.0, "width": 0.9, "height": 2.1, "sill_height": 0}
    result = apply_edits(apto, _draft(openings=[edit]))
    moved = next(o for o in result.project.openings if o.id == door.id)
    assert (moved.offset, moved.width, moved.wall_id) == (2.0, 0.9, spine.id)
    assert result.project.spaces == apto.spaces


def test_a_new_door_in_a_new_wall() -> None:
    apto = _apto()
    new_wall = {"ref": "nuevo-1", "level_id": "niv-0001", "axis": [(5.5, 0), (5.5, 4.8)]}
    door = {"ref": "nuevo-2", "wall": "nuevo-1", "offset": 2, "width": 0.8, "height": 2.0}
    draft = _draft(
        new_walls=[new_wall | {"thickness": 0.1}], new_openings=[door | {"sill_height": 0}]
    )
    result = apply_edits(apto, draft)
    opening = next(o for o in result.project.openings if o.id == result.new_ids["nuevo-2"])
    assert opening.wall_id == result.new_ids["nuevo-1"] and opening.kind == "void"


def test_a_renamed_space() -> None:
    apto = _apto()
    space = apto.spaces[0]
    edit = {"id": space.id, "polygon": space.polygon.model_dump(), "name": "Estudio"}
    result = apply_edits(apto, _draft(spaces=[edit]))
    assert result.renamed == [(space.id, space.name, "Estudio")]
    assert result.project.spaces[0].name == "Estudio"
    assert result.project.spaces[0].polygon == space.polygon


def test_a_new_space() -> None:
    apto = _apto()
    terrace = {"exterior": [(9, 0), (11, 0), (11, 2), (9, 2)]}
    new = {"ref": "nuevo-1", "level_id": "niv-0001", "name": "Terraza", "polygon": terrace}
    result = apply_edits(apto, _draft(new_spaces=[new | {"category": "balcony"}]))
    space = result.project.spaces[-1]
    assert (space.id, space.name, space.category) == (
        result.new_ids["nuevo-1"],
        "Terraza",
        "balcony",
    )


def test_a_deleted_door_retires_its_unused_block() -> None:
    apto = _apto()
    door = next(o for o in apto.openings if o.kind == "door")
    block = Block(
        id="blq-0001", name="P-90", kind="door", width=door.width, height=door.height, parameters={}
    )
    apto.blocks = [block]
    apto.next_ids["blq"] = 2
    door.block_id, door.block_side = block.id, "left"
    result = apply_edits(Project.model_validate(apto.model_dump()), _draft(deleted=[door.id]))
    assert result.removed_blocks == ["blq-0001"] and result.project.blocks == []


# --- Rechazos ---------------------------------------------------------------------------------


def test_errors_in_the_result_apply_nothing() -> None:
    apto = _apto()
    window = next(o for o in apto.openings if o.kind == "window" and o.offset == 1.0)
    edit = {"id": window.id, "offset": 5.8, "width": 1.5, "height": 1.2, "sill_height": 0.9}
    with pytest.raises(EditsError, match="No se aplicó nada") as raised:
        apply_edits(apto, _draft(openings=[edit]))
    assert "leer_cambios" in str(raised.value)
    assert next(o for o in apto.openings if o.id == window.id).offset == 1.0


def test_unknown_ids_are_rejected() -> None:
    with pytest.raises(EditsError, match="muro-0099"):
        apply_edits(_apto(), _draft(deleted=["muro-0099"]))


# --- Desde la carpeta -------------------------------------------------------------------------


def _folder_with_draft(tmp_path: Path, sha: str | None = None, **changes: Any) -> Path:
    folder = tmp_path / "apto"
    save_project(_apto(), folder)
    text = (folder / MODEL_FILENAME).read_text(encoding="utf-8")
    base = sha or hashlib.sha256(text.encode("utf-8")).hexdigest()
    draft = EditsDraft.model_validate({"source": "rhino", "base_sha256": base, **changes})
    (folder / "salidas").mkdir()
    (folder / "salidas" / "borrador_rhino.json").write_text(draft.model_dump_json(), "utf-8")
    return folder


def test_applies_the_draft_and_marks_it_applied(tmp_path: Path) -> None:
    wall = _partition(_apto())
    folder = _folder_with_draft(tmp_path, walls=[_wall_edit(wall, axis=[(0, 3.8), (3.5, 3.8)])])
    before, draft, result = apply_edits_draft(folder)
    assert _partition(before).id == draft.walls[0].id
    assert load_project(folder) == result.project
    assert not (folder / "salidas" / "borrador_rhino.json").exists()
    assert (folder / "salidas" / f"borrador_rhino{APPLIED_SUFFIX}").is_file()
    with pytest.raises(EditsError, match="ya se aplicó"):
        apply_edits_draft(folder)


def test_a_draft_over_another_version_is_rejected(tmp_path: Path) -> None:
    folder = _folder_with_draft(tmp_path, sha="f" * 64, deleted=[_partition(_apto()).id])
    text = (folder / MODEL_FILENAME).read_text(encoding="utf-8")
    with pytest.raises(EditsError, match="El modelo cambió desde que se cargó en Rhino"):
        apply_edits_draft(folder)
    assert (folder / MODEL_FILENAME).read_text(encoding="utf-8") == text
    assert (folder / "salidas" / "borrador_rhino.json").is_file()


def test_a_missing_draft_says_how_to_make_it(tmp_path: Path) -> None:
    save_project(_apto(), tmp_path)
    with pytest.raises(EditsError, match="leer_cambios de rhino-bridge"):
        apply_edits_draft(tmp_path)


# --- Propiedades ------------------------------------------------------------------------------


@settings(max_examples=25, deadline=None)
@given(st.floats(-1.0, 1.0))
def test_moving_the_partition_trades_area_between_the_rooms(dy: float) -> None:
    apto = _apto()
    wall = _partition(apto)
    axis = [(0, 3.6 + dy), (3.5, 3.6 + dy)]
    result = apply_edits(apto, _draft(walls=[_wall_edit(wall, axis=axis)]))
    after, before = _areas(result.project), _areas(apto)
    shift = round(dy, 6) * 3.34
    assert after["Habitación 1"] == pytest.approx(before["Habitación 1"] - shift, abs=TOL)
    assert after["Habitación 2"] == pytest.approx(before["Habitación 2"] + shift, abs=TOL)
    assert sum(after.values()) == pytest.approx(sum(before.values()), abs=2 * TOL)


@settings(max_examples=25, deadline=None)
@given(st.floats(-0.05, 0.05))
def test_sliding_the_partition_along_itself_keeps_the_areas(dx: float) -> None:
    apto = _apto()
    wall = _partition(apto)
    axis = [(dx, 3.6), (3.5 + dx, 3.6)]
    result = apply_edits(apto, _draft(walls=[_wall_edit(wall, axis=axis)]))
    after, before = _areas(result.project), _areas(apto)
    assert after == pytest.approx(before, abs=TOL)
