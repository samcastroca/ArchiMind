"""Operaciones sobre la carpeta de un proyecto: abrirla, importar planos y aplicar el mapeo.

La carpeta tiene `modelo.json`, los planos importados en `planos/`, las salidas regenerables en
`salidas/` y su propio repositorio git. El plano activo es el último de `source_files`.
"""

import shutil
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path

from archimind_schema import MODEL_FILENAME, Project, load_project, save_project
from pydantic import ValidationError

from archimind_core.build import BuildResult, build_model
from archimind_core.drawing import Drawing, read_drawing
from archimind_core.history import GITIGNORE, OUTPUTS_DIR, PLANS_DIR, init_repo
from archimind_core.inventory import modelspace_entities
from archimind_core.mapping import MappingError, validate_roles


class ProjectError(Exception):
    """La carpeta no es un proyecto utilizable; el mensaje está pensado para el usuario final."""


@dataclass(frozen=True)
class OpenedProject:
    folder: Path
    project: Project
    created: bool


def project_folder(project_path: str | Path) -> Path:
    return Path(project_path).expanduser().resolve()


def open_project(project_path: str | Path) -> OpenedProject:
    """Crea lo que falte de la carpeta: ella misma, `modelo.json`, `salidas/`, `.gitignore` y el
    repositorio. `created` dice si el modelo es nuevo."""
    folder = project_folder(project_path)
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except (FileExistsError, NotADirectoryError) as exc:
        raise ProjectError(f"{folder} existe y no es una carpeta") from exc
    created = not (folder / MODEL_FILENAME).is_file()
    if created:
        save_project(Project(id=folder.name, name=folder.name, scale_confirmed=False), folder)
    (folder / OUTPUTS_DIR).mkdir(exist_ok=True)
    gitignore = folder / GITIGNORE
    if not gitignore.is_file():
        gitignore.write_text(f"{OUTPUTS_DIR}/\n", encoding="utf-8")
    init_repo(folder)
    return OpenedProject(folder, load_existing(folder), created)


def load_existing(project_path: str | Path) -> Project:
    folder = project_folder(project_path)
    try:
        return load_project(folder)
    except FileNotFoundError as exc:
        raise ProjectError(
            f"No hay un proyecto en {folder}: ábrelo primero con abrir_proyecto."
        ) from exc
    except ValidationError as exc:
        raise ProjectError(f"El {MODEL_FILENAME} de {folder} no es válido: {exc}") from exc


def outputs_dir(project_path: str | Path) -> Path:
    folder = project_folder(project_path)
    load_existing(folder)
    (folder / OUTPUTS_DIR).mkdir(exist_ok=True)
    return folder / OUTPUTS_DIR


def import_drawing(project_path: str | Path, file_path: str | Path) -> Drawing:
    """Copia el plano a `planos/` y lo deja como plano activo. No toca el resto del modelo.

    Una ruta relativa se lee desde la carpeta del proyecto. El plano se lee antes de copiarlo:
    uno ilegible no deja rastro.
    """
    folder = project_folder(project_path)
    project = load_existing(folder)
    source = Path(file_path).expanduser()
    if not source.is_absolute():
        source = folder / source
    drawing = read_drawing(source)
    target = folder / PLANS_DIR / source.name
    if source.resolve() != target.resolve():
        target.parent.mkdir(exist_ok=True)
        shutil.copy2(source, target)
    name = target.relative_to(folder).as_posix()
    project.source_files = [f for f in project.source_files if f != name] + [name]
    save_project(project, folder)
    return replace(drawing, path=target)


def active_drawing(project_path: str | Path) -> Drawing:
    folder = project_folder(project_path)
    project = load_existing(folder)
    if not project.source_files:
        raise ProjectError(
            f"El proyecto {project.name} aún no tiene planos: impórtalo con importar_plano."
        )
    return read_drawing(folder / project.source_files[-1])


def apply_mapping(
    project_path: str | Path, drawing: Drawing, mapping: Mapping[str, str]
) -> BuildResult:
    """Guarda el mapeo de capas y reconstruye el modelo del proyecto desde el plano.

    El modelo reconstruido conserva el nombre, las fuentes y los contadores de IDs del proyecto:
    sus muros, vanos y espacios reciben IDs nuevos. La escala vuelve a ser la del plano. Si el
    mapeo no es válido, no escribe nada.
    """
    validate_roles(mapping)
    layers = {layer for _, layer in modelspace_entities(drawing.doc)}
    unknown = sorted(set(mapping) - layers)
    if unknown:
        raise MappingError(f"Estas capas no están en {drawing.path.name}: {', '.join(unknown)}")
    folder = project_folder(project_path)
    project = load_existing(folder)
    source = _source_name(drawing.path, folder)
    if source not in project.source_files:
        project.source_files.append(source)
    result = build_model(drawing, mapping, base=project)
    save_project(result.project, folder)
    return result


def _source_name(plan: Path, folder: Path) -> str:
    """Ruta del plano relativa a la carpeta del proyecto si está dentro; si no, absoluta."""
    resolved = plan.resolve()
    if resolved.is_relative_to(folder):
        return resolved.relative_to(folder).as_posix()
    return str(resolved)
