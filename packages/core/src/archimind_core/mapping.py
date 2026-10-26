"""Guarda el mapeo de capas a roles en el modelo del proyecto."""

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import TYPE_CHECKING, get_args

from archimind_schema import MODEL_FILENAME, LayerRole, Project, load_project, save_project

from archimind_core.inventory import modelspace_entities

if TYPE_CHECKING:
    from archimind_core.drawing import Drawing
    from archimind_core.layer_roles import LayerProposal

ROLES: tuple[str, ...] = get_args(LayerRole)


class MappingError(Exception):
    """El mapeo no se puede aplicar; el mensaje está pensado para el usuario final."""


def proposals_to_mapping(proposals: Iterable["LayerProposal"]) -> dict[str, LayerRole]:
    return {proposal.layer: proposal.role for proposal in proposals}


def validate_roles(mapping: Mapping[str, str]) -> None:
    """Lanza MappingError si algún rol del mapeo no es uno de los posibles."""
    invalid = sorted(f"{layer} → {role}" for layer, role in mapping.items() if role not in ROLES)
    if invalid:
        raise MappingError(
            f"Roles no válidos: {', '.join(invalid)}. Los roles posibles son {', '.join(ROLES)}"
        )


def apply_mapping(project_path: str | Path, drawing: "Drawing", mapping: Mapping[str, str]) -> Path:
    """Reemplaza el mapeo de capas del proyecto y devuelve la ruta de `modelo.json`.

    Si la carpeta aún no tiene modelo, crea uno mínimo: sin niveles ni muros, con el plano como
    fuente y la escala confirmada solo si el plano declara sus unidades.
    """
    validate_roles(mapping)
    layers = {layer for _, layer in modelspace_entities(drawing.doc)}
    unknown = sorted(set(mapping) - layers)
    if unknown:
        raise MappingError(f"Estas capas no están en {drawing.path.name}: {', '.join(unknown)}")
    folder = Path(project_path).resolve()
    source = _source_name(drawing.path, folder)
    if (folder / MODEL_FILENAME).is_file():
        project = load_project(folder)
        if source not in project.source_files:
            project.source_files.append(source)
    else:
        project = Project(
            id=folder.name,
            name=folder.name,
            scale_confirmed=drawing.units.confirmed,
            source_files=[source],
        )
    project = Project.model_validate({**project.model_dump(), "layer_mapping": dict(mapping)})
    return save_project(project, folder)


def _source_name(plan: Path, folder: Path) -> str:
    """Ruta del plano relativa a la carpeta del proyecto si está dentro; si no, absoluta."""
    resolved = plan.resolve()
    if resolved.is_relative_to(folder):
        return resolved.relative_to(folder).as_posix()
    return str(resolved)
