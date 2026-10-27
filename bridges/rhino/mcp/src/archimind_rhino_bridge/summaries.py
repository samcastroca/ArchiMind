"""Textos de respuesta de las herramientas: resúmenes cortos y rutas, nunca coordenadas."""

from pathlib import Path
from typing import Any

from archimind_rhino_bridge.changes import Changes

MAX_CHANGES = 25
MAX_NOTES = 10
# Subcapa → nombre en plural.
NAMES = {"Muros": "muros", "Vanos": "vanos", "Espacios": "espacios"}


def counts(per_layer: dict[str, int]) -> str:
    return ", ".join(f"{per_layer.get(layer, 0)} {name}" for layer, name in NAMES.items())


def status(sha256: str, folder: Path, info: dict[str, Any], same_project: bool) -> str:
    lines = [f"Rhino {info['rhino']}: el puente responde."]
    if info.get("in_command"):
        lines.append("Rhino está ejecutando un comando: las operaciones esperan a que termine.")
    document = info.get("document")
    if document is None:
        lines.append("Rhino no tiene ningún documento abierto.")
        return "\n".join(lines)
    name = document["path"] or document["name"] or "sin título"
    modified = ", con cambios sin guardar" if document["modified"] else ""
    lines.append(f"Documento: {name}{modified}; unidades {document['units']}.")
    archimind = info.get("archimind") or {}
    if not archimind.get("project"):
        lines.append(
            f"El documento no tiene las capas de ArchiMind: usa abrir_en_rhino con {folder}."
        )
    elif not same_project:
        lines.append(
            f"Las capas ArchiMind son de otro proyecto ({archimind['project']}): usa "
            f"abrir_en_rhino con {folder}."
        )
    else:
        lines.append(f"Capas ArchiMind de este proyecto: {counts(archimind['objects'])}.")
        if archimind.get("base_sha256") == sha256:
            lines.append("El modelo está al día con lo que se cargó en Rhino.")
        else:
            lines.append(
                "El modelo cambió desde que se cargó en Rhino: abrir_en_rhino recarga las capas."
            )
    return "\n".join(lines)


def opened(
    target: Path,
    loaded: dict[str, int] | None,
    kept: dict[str, int],
    discarded: list[str],
    foreign: str | None,
    preliminary: bool,
) -> str:
    lines = [f"Proyecto abierto en Rhino: {target}."]
    if loaded is None:
        lines.append(
            f"Las capas ArchiMind ya estaban al día con el modelo ({counts(kept)}): se conservan "
            "las ediciones hechas en Rhino."
        )
    else:
        lines.append(
            "Capas ArchiMind::Muros, ::Vanos y ::Espacios cargadas desde el modelo: "
            f"{counts(loaded)}."
        )
    if foreign:
        lines.append(f"Las capas que había eran de otro proyecto ({foreign}) y se reemplazaron.")
    if discarded:
        lines.append(f"Se descartaron {len(discarded)} cambio(s) sin leer de Rhino.")
    if preliminary:
        lines.append("PRELIMINAR: la escala del modelo no está confirmada.")
    lines.append(
        "Siguiente: edita en Rhino (cada objeto lleva su archimind_id) y luego usa leer_cambios."
    )
    return "\n".join(lines)


def pending(lines: list[str]) -> str:
    shown = "; ".join(lines[:5]) + (f" y {len(lines) - 5} más" if len(lines) > 5 else "")
    return (
        f"En Rhino hay cambios que aún no se leyeron y el modelo cambió desde que se cargaron: "
        f"{shown}. Guárdalos en un borrador con leer_cambios, o vuelve a llamar a abrir_en_rhino "
        "con descartar_cambios=True para perderlos."
    )


def changes(result: Changes, draft: Path | None, removed: bool, stale: bool) -> str:
    lines: list[str] = []
    if draft is None:
        lines.append("Sin cambios en Rhino respecto del modelo cargado: no hay borrador.")
        if removed:
            lines.append("Se quitó el borrador anterior, que ya no corresponde.")
    else:
        lines.append(f"{len(result.lines)} cambio(s) en Rhino respecto del modelo cargado:")
        lines += [f"- {line}" for line in result.lines[:MAX_CHANGES]]
        if len(result.lines) > MAX_CHANGES:
            lines.append(f"- … y {len(result.lines) - MAX_CHANGES} más (en el borrador).")
        lines.append(f"Borrador: {draft}. archimind-core todavía no aplica este borrador.")
    if stale:
        lines.append(
            "El modelo cambió desde que se cargó en Rhino: el borrador se refiere a la versión "
            "cargada."
        )
    if result.notes:
        lines.append("Avisos:")
        lines += [f"- {note}" for note in result.notes[:MAX_NOTES]]
        if len(result.notes) > MAX_NOTES:
            lines.append(f"- … y {len(result.notes) - MAX_NOTES} avisos más.")
    return "\n".join(lines)


def saved(path: Path) -> str:
    return f"Documento de Rhino guardado en {path}."
