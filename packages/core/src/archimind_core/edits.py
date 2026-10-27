"""Aplica al modelo el borrador de ediciones que entrega el puente de Rhino (`EditsDraft`).

El borrador se hizo sobre una versión del modelo (`base_sha256`): si `modelo.json` cambió desde
entonces, se rechaza entero. Core pone los IDs de lo nuevo (los `ref` `nuevo-N` del borrador),
quita los vanos de los muros borrados y los bloques que quedan sin uso, y, si cambiaron los
muros, recalcula los espacios con `recompute_spaces`. Si el modelo resultante tiene errores de
`validate`, no se aplica nada.
"""

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

from archimind_schema import (
    MODEL_FILENAME,
    EditsDraft,
    Opening,
    Problem,
    Project,
    Space,
    Wall,
    new_id,
    save_project,
    validate,
)
from pydantic import ValidationError

from archimind_core.build_rules import BuildRules, load_build_rules
from archimind_core.project import load_existing, project_folder
from archimind_core.spaces import recompute_spaces

DRAFT_PATH = "salidas/borrador_rhino.json"
# El borrador aplicado se renombra así: rhino-bridge lo reconoce y no lo vuelve a ofrecer.
APPLIED_SUFFIX = ".aplicado.json"
MAX_ERRORS = 8


class EditsError(Exception):
    """El borrador no se puede aplicar; el mensaje está pensado para el usuario final."""


@dataclass(frozen=True)
class EditsResult:
    project: Project
    new_ids: dict[str, str]  # ref del borrador → ID nuevo
    renamed: list[tuple[str, str, str]]  # (ID, nombre anterior, nombre nuevo)
    removed_blocks: list[str]
    problems: list[Problem]  # avisos del recálculo y de `validate`; nunca errores


def apply_edits(
    project: Project, draft: EditsDraft, rules: BuildRules | None = None
) -> EditsResult:
    """Una copia del modelo con el borrador aplicado. Comprueba todo antes: si algo no calza con
    el modelo o el resultado no es válido, lanza EditsError y no aplica ninguna parte."""
    _check(project, draft)
    result = project.model_copy(deep=True)
    walls = {wall.id: wall for wall in result.walls}
    openings = {opening.id: opening for opening in result.openings}
    spaces = {space.id: space for space in result.spaces}
    for wall_edit in draft.walls:
        wall = walls[wall_edit.id]
        wall.axis, wall.thickness = list(wall_edit.axis), wall_edit.thickness
        wall.height = wall_edit.height
    for opening_edit in draft.openings:
        opening = openings[opening_edit.id]
        opening.offset, opening.width = opening_edit.offset, opening_edit.width
        opening.height, opening.sill_height = opening_edit.height, opening_edit.sill_height
    renamed, reshaped = [], set()
    for space_edit in draft.spaces:
        space = spaces[space_edit.id]
        if space.name != space_edit.name:
            renamed.append((space.id, space.name, space_edit.name))
            space.name = space_edit.name
        if space.polygon != space_edit.polygon:
            reshaped.add(space.id)
            space.polygon = space_edit.polygon.model_copy(deep=True)

    deleted = set(draft.deleted)
    deleted |= {o.id for o in result.openings if o.wall_id in deleted}
    result.walls = [w for w in result.walls if w.id not in deleted]
    result.openings = [o for o in result.openings if o.id not in deleted]
    result.spaces = [s for s in result.spaces if s.id not in deleted]

    new_ids: dict[str, str] = {}
    for new_wall in draft.new_walls:
        wall_id = new_ids[new_wall.ref] = new_id(result, "muro")
        result.walls.append(
            Wall(
                id=wall_id,
                level_id=new_wall.level_id,
                axis=list(new_wall.axis),
                thickness=new_wall.thickness,
                height=new_wall.height,
            )
        )
    for new_opening in draft.new_openings:
        opening_id = new_ids[new_opening.ref] = new_id(result, "vano")
        result.openings.append(
            Opening(
                id=opening_id,
                wall_id=new_ids.get(new_opening.wall, new_opening.wall),
                kind=new_opening.kind,
                offset=new_opening.offset,
                width=new_opening.width,
                height=new_opening.height,
                sill_height=new_opening.sill_height,
            )
        )
    for new_space in draft.new_spaces:
        space_id = new_ids[new_space.ref] = new_id(result, "esp")
        result.spaces.append(
            Space(
                id=space_id,
                level_id=new_space.level_id,
                name=new_space.name,
                polygon=new_space.polygon,
                category=new_space.category,
            )
        )

    used = {opening.block_id for opening in result.openings}
    removed_blocks = [block.id for block in result.blocks if block.id not in used]
    result.blocks = [block for block in result.blocks if block.id in used]

    problems: list[Problem] = []
    walls_changed = draft.walls or draft.new_walls or any(i.startswith("muro-") for i in deleted)
    if walls_changed:
        problems += recompute_spaces(result, rules or load_build_rules(), reshaped)
    try:
        result = Project.model_validate(result.model_dump())
    except ValidationError as exc:
        raise EditsError(f"El borrador deja el modelo con datos no válidos: {exc}") from exc
    found = validate(result)
    errors = [p for p in found if p.severity == "error"]
    if errors:
        listed = "; ".join(p.message for p in errors[:MAX_ERRORS])
        more = f" y {len(errors) - MAX_ERRORS} más" if len(errors) > MAX_ERRORS else ""
        raise EditsError(
            f"No se aplicó nada: con estos cambios el modelo tendría {len(errors)} error(es): "
            f"{listed}{more}. Corrígelo en Rhino y vuelve a leer los cambios con leer_cambios."
        )
    return EditsResult(result, new_ids, renamed, removed_blocks, [*problems, *found])


def apply_edits_draft(
    project_path: str | Path, draft_path: str | Path = DRAFT_PATH
) -> tuple[Project, EditsDraft, EditsResult]:
    """Lee el borrador (una ruta relativa se toma desde la carpeta), lo aplica, guarda el modelo
    y renombra el borrador a `*.aplicado.json`. Devuelve el modelo anterior, el borrador y el
    resultado. Si el borrador no es válido, no calza o el modelo cambió, no escribe nada."""
    folder = project_folder(project_path)
    project = load_existing(folder)
    source = Path(draft_path).expanduser()
    if not source.is_absolute():
        source = folder / source
    applied = source.with_name(source.name.removesuffix(".json") + APPLIED_SUFFIX)
    try:
        text = source.read_text(encoding="utf-8")
    except FileNotFoundError:
        if applied.is_file():
            raise EditsError(
                f"El borrador {source.name} ya se aplicó al modelo (quedó como {applied.name}). "
                "Para otros cambios, edita en Rhino y usa leer_cambios de rhino-bridge."
            ) from None
        raise EditsError(
            f"No existe el borrador {source}: créalo con leer_cambios de rhino-bridge."
        ) from None
    try:
        draft = EditsDraft.model_validate_json(text)
    except ValidationError as exc:
        raise EditsError(f"{source.name} no es un borrador de ediciones válido: {exc}") from exc
    current = (folder / MODEL_FILENAME).read_text(encoding="utf-8")
    if hashlib.sha256(current.encode("utf-8")).hexdigest() != draft.base_sha256:
        raise EditsError(
            "El modelo cambió desde que se cargó en Rhino, así que el borrador ya no corresponde "
            "y no se aplicó nada. Recarga el modelo con abrir_en_rhino de rhino-bridge "
            "(descartar_cambios=True) y repite la edición."
        )
    result = apply_edits(project, draft)
    save_project(result.project, folder)
    os.replace(source, applied)
    return project, draft, result


def _check(project: Project, draft: EditsDraft) -> None:
    known = {w.id for w in project.walls} | {o.id for o in project.openings}
    known |= {s.id for s in project.spaces}
    ids = [*(e.id for e in draft.walls), *(e.id for e in draft.openings)]
    ids += [*(e.id for e in draft.spaces), *draft.deleted]
    ids += [n.wall for n in draft.new_openings if not n.wall.startswith("nuevo-")]
    missing = sorted({entity_id for entity_id in ids if entity_id not in known})
    if missing:
        raise EditsError(
            f"El borrador menciona elementos que no están en el modelo ({', '.join(missing)}): "
            "no se aplicó nada. Vuelve a leer los cambios con leer_cambios."
        )
