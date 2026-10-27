"""Fallos inesperados de la reconstrucción: en qué etapa ocurrieron y sobre qué elemento."""

from collections.abc import Iterator
from contextlib import contextmanager


class BuildStageError(Exception):
    """Una etapa de la reconstrucción falló por un error no previsto. El mensaje es para el
    usuario; la excepción original queda encadenada para el log."""

    def __init__(self, stage: str, cause: Exception) -> None:
        self.stage = stage
        where = "; ".join(getattr(cause, "__notes__", []))
        super().__init__(
            f"La reconstrucción falló en la etapa de {stage}"
            + (f", en {where}" if where else "")
            + f": {type(cause).__name__}: {cause}"
        )


@contextmanager
def stage(name: str) -> Iterator[None]:
    """Convierte cualquier excepción de la etapa en BuildStageError."""
    try:
        yield
    except Exception as exc:
        raise BuildStageError(name, exc) from exc


@contextmanager
def about(element: str) -> Iterator[None]:
    """Anota en la excepción el elemento que se estaba procesando; los niveles anidados se
    leen del más concreto al más general."""
    try:
        yield
    except Exception as exc:
        exc.add_note(element)
        raise
