"""Aplica al modelo el borrador de carpintería que entrega archimind-bloques.

Core pone los IDs `blq-`: los vanos con la misma carpintería (mismo nombre de bloque) comparten
uno, y los bloques que ningún vano usa se quitan del modelo; su ID queda retirado.
"""

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from archimind_schema import LENGTH_TOL, Block, BlocksDraft, Project, new_id, save_project
from pydantic import ValidationError

from archimind_core.project import load_existing, project_folder

DRAFT_PATH = "salidas/borrador_bloques.json"
_KINDS = {"door": "una puerta", "window": "una ventana", "void": "un vano sin tipo"}


class BlocksError(Exception):
    """El borrador no se puede aplicar; el mensaje está pensado para el usuario final."""


@dataclass(frozen=True)
class AssignedBlock:
    opening_id: str
    block_id: str
    block_name: str
    new: bool  # el bloque no estaba en el modelo


@dataclass(frozen=True)
class BlocksAssignment:
    project: Project
    assigned: list[AssignedBlock]
    removed: list[str]  # bloques que quedaron sin uso


def assign_blocks(project: Project, draft: BlocksDraft) -> BlocksAssignment:
    """Una copia del modelo con la carpintería del borrador en sus vanos. Comprueba todo el
    borrador antes de cambiar nada: si algo no calza con el modelo, no aplica ninguna parte."""
    _check(project, draft)
    result = project.model_copy(deep=True)
    openings = {opening.id: opening for opening in result.openings}
    by_name = {block.name: block for block in result.blocks}
    assigned = []
    for assignment in draft.assignments:
        definition = assignment.block
        block = by_name.get(definition.name)
        new = block is None
        if block is None:
            block = Block(id=new_id(result, "blq"), **definition.model_dump())
            result.blocks.append(block)
            by_name[block.name] = block
        opening = openings[assignment.opening_id]
        opening.block_id, opening.block_side = block.id, assignment.side
        opening.kind = block.kind  # un vano sin tipo adopta el de su carpintería
        assigned.append(AssignedBlock(opening.id, block.id, block.name, new))
    used = {opening.block_id for opening in result.openings}
    removed = [block.id for block in result.blocks if block.id not in used]
    result.blocks = [block for block in result.blocks if block.id in used]
    return BlocksAssignment(Project.model_validate(result.model_dump()), assigned, removed)


def apply_block_draft(project_path: str | Path, draft_path: str | Path) -> BlocksAssignment:
    """Lee el borrador (una ruta relativa se toma desde la carpeta), lo aplica y guarda el
    modelo. Si el borrador no es válido o no calza, no escribe nada."""
    folder = project_folder(project_path)
    project = load_existing(folder)
    source = Path(draft_path).expanduser()
    if not source.is_absolute():
        source = folder / source
    try:
        draft = BlocksDraft.model_validate_json(source.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise BlocksError(
            f"No existe el borrador {source}: créalo con insertar_bloques_en_plano de "
            "archimind-bloques."
        ) from None
    except ValidationError as exc:
        raise BlocksError(f"{source.name} no es un borrador de bloques válido: {exc}") from exc
    assignment = assign_blocks(project, draft)
    save_project(assignment.project, folder)
    return assignment


def _check(project: Project, draft: BlocksDraft) -> None:
    openings = {opening.id: opening for opening in project.openings}
    problems = []
    repeated = [
        opening_id
        for opening_id, n in Counter(a.opening_id for a in draft.assignments).items()
        if n > 1
    ]
    if repeated:
        problems.append(f"el borrador asigna dos bloques a {', '.join(repeated)}")
    for assignment in draft.assignments:
        opening = openings.get(assignment.opening_id)
        block = assignment.block
        if opening is None:
            problems.append(f"el vano {assignment.opening_id} no existe en el modelo")
        elif opening.kind not in (block.kind, "void"):
            problems.append(
                f"{opening.id} es {_KINDS[opening.kind]} y su bloque, {_KINDS[block.kind]}"
            )
        elif (
            abs(opening.width - block.width) > LENGTH_TOL
            or abs(opening.height - block.height) > LENGTH_TOL
        ):
            problems.append(
                f"{opening.id} mide {opening.width:.3f} × {opening.height:.3f} m y su bloque "
                f"{block.width:.3f} × {block.height:.3f} m"
            )
    if problems:
        raise BlocksError(
            "El borrador no calza con el modelo actual, que cambió desde que se creó: "
            + "; ".join(problems)
            + ". Vuelve a ejecutar insertar_bloques_en_plano de archimind-bloques."
        )
