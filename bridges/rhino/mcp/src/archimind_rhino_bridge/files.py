"""La carpeta del proyecto vista desde el puente: el modelo, el .3dm y el borrador.

El puente nunca escribe `modelo.json`: lee su texto tal cual (su SHA-256 identifica la versión que
se cargó en Rhino) y deja sus salidas en `salidas/`.
"""

import hashlib
from dataclasses import dataclass
from pathlib import Path

import rhino3dm
from archimind_schema import LENGTH_TOL, MODEL_FILENAME, EditsDraft, Project
from pydantic import ValidationError

OUTPUTS_DIR = "salidas"
DRAFT_NAME = "borrador_rhino.json"
# Así lo renombra archimind-core cuando lo aplica al modelo.
APPLIED_NAME = "borrador_rhino.aplicado.json"


class ProjectError(Exception):
    """La carpeta no es un proyecto utilizable; el mensaje está pensado para el usuario final."""


@dataclass(frozen=True)
class ProjectModel:
    folder: Path
    project: Project
    text: str  # modelo.json tal cual, el que se guarda en el .3dm como base
    sha256: str


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_model(project_path: str | Path) -> ProjectModel:
    folder = Path(project_path).expanduser().resolve()
    model_file = folder / MODEL_FILENAME
    if not model_file.is_file():
        raise ProjectError(
            f"No hay un proyecto en {folder}: ábrelo con abrir_proyecto de archimind-core."
        )
    text = model_file.read_text(encoding="utf-8")
    try:
        project = Project.model_validate_json(text)
    except ValidationError as exc:
        raise ProjectError(f"El {MODEL_FILENAME} de {folder} no es válido: {exc}") from exc
    return ProjectModel(folder, project, text, sha256(text))


def outputs_dir(folder: Path) -> Path:
    path = folder / OUTPUTS_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def rhino_file(folder: Path) -> Path:
    return folder / OUTPUTS_DIR / f"{folder.name}.3dm"


def draft_file(folder: Path) -> Path:
    return folder / OUTPUTS_DIR / DRAFT_NAME


def applied_draft(folder: Path) -> EditsDraft | None:
    """El último borrador que core aplicó al modelo, si hay uno legible."""
    path = folder / OUTPUTS_DIR / APPLIED_NAME
    try:
        return EditsDraft.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError):
        return None


def create_empty_3dm(path: Path) -> Path:
    """Un .3dm vacío en metros y con la tolerancia del modelo, para que Rhino lo abra."""
    model = rhino3dm.File3dm()
    # Los stubs de rhino3dm dan por solo lectura propiedades que se pueden asignar.
    model.Settings.ModelUnitSystem = rhino3dm.UnitSystem.Meters  # type: ignore[misc]
    model.Settings.ModelAbsoluteTolerance = LENGTH_TOL  # type: ignore[misc]
    path.parent.mkdir(parents=True, exist_ok=True)
    if not model.Write(str(path), 0):
        raise OSError(f"rhino3dm no pudo escribir {path}")
    return path


def write_draft(folder: Path, draft: EditsDraft | None) -> Path | None:
    """Escribe el borrador; sin cambios, quita uno anterior para que no se aplique por error."""
    path = draft_file(folder)
    if draft is None:
        path.unlink(missing_ok=True)
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(draft.model_dump_json(indent=2), encoding="utf-8")
    return path
