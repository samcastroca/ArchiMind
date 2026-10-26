"""Historial del proyecto con git: cada cambio del modelo es una versión.

El repositorio vive en la carpeta del proyecto. Se versionan `modelo.json`, los planos importados
y `.gitignore`; `salidas/` se regenera y queda fuera.
"""

import subprocess
from dataclasses import dataclass
from pathlib import Path

from archimind_schema import MODEL_FILENAME, Project
from pydantic import ValidationError

PLANS_DIR = "planos"
OUTPUTS_DIR = "salidas"
GITIGNORE = ".gitignore"
TRACKED = (MODEL_FILENAME, PLANS_DIR, GITIGNORE)
# Las versiones las firma la herramienta: no depende de la configuración global de git.
AUTHOR = ("-c", "user.name=ArchiMind", "-c", "user.email=archimind@localhost")


class HistoryError(Exception):
    """El historial no se puede leer o escribir; el mensaje está pensado para el usuario final."""


@dataclass(frozen=True)
class Version:
    hash: str
    date: str
    message: str


def init_repo(folder: str | Path) -> bool:
    """Crea el repositorio si la carpeta no tiene uno propio; devuelve si lo creó.

    Mira `.git` en la carpeta misma, no hacia arriba: un proyecto dentro de otro repositorio
    tiene igualmente su propio historial.
    """
    folder = Path(folder)
    if (folder / ".git").exists():
        return False
    _git(folder, "init", "-b", "main")
    return True


def commit(folder: str | Path, message: str) -> str | None:
    """Versiona lo que cambió y devuelve el hash corto; `None` si no había nada que versionar."""
    folder = Path(folder)
    present = [name for name in TRACKED if (folder / name).exists()]
    if present:
        _git(folder, "add", "--all", "--", *present)
    if _git(folder, "diff", "--cached", "--quiet", check=False).returncode == 0:
        return None
    _git(folder, "commit", "--quiet", "--message", message)
    return _git(folder, "rev-parse", "--short", "HEAD").stdout.strip()


def recent_versions(folder: str | Path, limit: int = 5) -> list[Version]:
    """Las últimas versiones, de la más reciente a la más antigua."""
    folder = Path(folder)
    if _git(folder, "rev-parse", "--verify", "--quiet", "HEAD", check=False).returncode != 0:
        return []
    output = _git(folder, "log", f"--max-count={limit}", "--format=%h%x1f%cs%x1f%s").stdout
    return [Version(*line.split("\x1f", 2)) for line in output.splitlines()]


def load_version(folder: str | Path, version: str) -> Project:
    """El modelo tal como quedó en `version`: un hash o una referencia como HEAD o HEAD~1."""
    folder = Path(folder)
    if not version or version.startswith("-"):
        raise HistoryError(f"'{version}' no es una versión válida. {_recent_hint(folder)}")
    result = _git(folder, "show", f"{version}:{MODEL_FILENAME}", check=False)
    if result.returncode != 0:
        raise HistoryError(f"La versión '{version}' no existe. {_recent_hint(folder)}")
    try:
        return Project.model_validate_json(result.stdout)
    except ValidationError as exc:
        raise HistoryError(f"El modelo de la versión '{version}' no es válido: {exc}") from exc


def _recent_hint(folder: Path) -> str:
    versions = recent_versions(folder)
    if not versions:
        return "El proyecto aún no tiene versiones."
    listed = "; ".join(f"{v.hash} ({v.date}) {v.message}" for v in versions)
    return f"Versiones recientes: {listed}"


def _git(folder: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            ["git", "-C", str(folder), *AUTHOR, *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
    except FileNotFoundError as exc:
        raise HistoryError(
            "git no está instalado o no está en el PATH; hace falta para versionar el proyecto "
            "(https://git-scm.com/downloads)."
        ) from exc
    if check and result.returncode != 0:
        raise HistoryError(f"git {args[0]} falló en {folder}: {result.stderr.strip()}")
    return result
