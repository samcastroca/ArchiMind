"""Lectura y escritura atómica de `modelo.json` en la carpeta del proyecto."""

import os
import tempfile
from pathlib import Path

from archimind_schema.models import Project

MODEL_FILENAME = "modelo.json"


def load_project(path: str | Path) -> Project:
    model_file = Path(path) / MODEL_FILENAME
    if not model_file.is_file():
        raise FileNotFoundError(f"No se encontró {MODEL_FILENAME} en la carpeta {path}")
    return Project.model_validate_json(model_file.read_text(encoding="utf-8"))


def save_project(project: Project, path: str | Path) -> Path:
    """Escribe en un temporal de la misma carpeta y lo renombra: nunca queda un archivo a medias."""
    folder = Path(path)
    folder.mkdir(parents=True, exist_ok=True)
    model_file = folder / MODEL_FILENAME
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=folder, prefix=".modelo-", suffix=".tmp", delete=False
    ) as tmp:
        tmp_path = Path(tmp.name)
        try:
            tmp.write(project.model_dump_json(indent=2))
            tmp.flush()
            os.fsync(tmp.fileno())
        except BaseException:
            tmp.close()
            tmp_path.unlink(missing_ok=True)
            raise
    try:
        os.replace(tmp_path, model_file)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise
    return model_file
