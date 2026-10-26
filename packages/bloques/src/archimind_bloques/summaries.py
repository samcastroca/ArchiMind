"""Textos de respuesta del servidor MCP: resúmenes cortos (menos de 50 líneas) y rutas.

Funciones puras sobre los resultados de la lógica del paquete. Todo número sale de los
parámetros, del vano o del catálogo; aquí solo se da formato.
"""

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from archimind_bloques.catalog import TYPE_NAMES, Catalog, Profile
from archimind_bloques.fit import Fit
from archimind_bloques.geometry import Carpentry
from archimind_bloques.insert import InsertResult
from archimind_bloques.params import CarpentryParams, SlidingWindow
from archimind_bloques.resolve import Resolution

MAX_LINES = 50
HANDS = {"left": "mano izquierda", "right": "mano derecha"}
SWINGS = {"in": "abre hacia adentro", "out": "abre hacia afuera"}
SIDES = {"in": "corre por la cara de adentro", "out": "corre por la cara de afuera"}
KINDS = {"door": "puerta", "window": "ventana", "void": "vano sin tipo"}


def catalog(items: Catalog, path: Path) -> str:
    defaults = items.defaults
    lines = [
        f"Catálogo de carpintería ({_count(len(items.profiles), 'perfil', 'perfiles')}): {path}"
    ]
    for key, profile in items.profiles.items():
        lines += _profile_lines(key, profile)
    lines.append(
        f"Por defecto: muro de {defaults.wall_thickness:.2f} m, antepecho de "
        f"{defaults.sill_height:.2f} m, puerta de {defaults.door_height:.2f} m y ventana de "
        f"{defaults.window_height:.2f} m de alto."
    )
    lines.append(
        "Sin perfil ni material, se usa el primero de esta lista que admite el tipo y calza."
    )
    return _text(_truncate(lines, MAX_LINES))


def created(resolution: Resolution, carpentry: Carpentry, paths: Sequence[Path]) -> str:
    lines = [f"Bloque {carpentry.name}", *_params_lines(resolution.params, resolution.profile_key)]
    lines += _notes(resolution.notes)
    lines.append("Archivos:")
    lines += [f"  {path}" for path in paths]
    return _text(lines)


def fitted(fit: Fit, carpentry: Carpentry, requested: dict[str, Any], opening_line: str) -> str:
    lines = [opening_line, f"Bloque {carpentry.name}"]
    lines += _params_lines(fit.params, fit.profile_key)
    lines += _notes(fit.notes)
    assignments = json.dumps({fit.opening_id: requested}, ensure_ascii=False)
    lines.append(f"Para insertarlo: insertar_bloques_en_plano con asignaciones = {assignments}")
    lines.append("No se escribió nada.")
    return _text(lines)


def inserted(result: InsertResult, folder: Path) -> str:
    plan = _relative(folder, result.plan)
    lines = [
        f"Carpintería insertada en {plan}: {_count(len(result.fits), 'vano nuevo', 'vanos nuevos')}"
        f" y {_count(len(result.kept), 'vano', 'vanos')} con el bloque que ya tenían en el modelo."
    ]
    if result.fits:
        lines.append("Vano → tipo, perfil, apertura · bloque:")
        lines += _truncate([f"  {_fit_line(fit, carpentry)}" for fit, carpentry in result.fits], 30)
    if result.kept:
        lines.append(f"Ya tenían bloque: {', '.join(result.kept)}.")
    lines += [f"Aviso: {warning}" for warning in result.warnings[:5]]
    if result.draft is not None:
        lines.append(
            f"Borrador: {_relative(folder, result.draft)}. El modelo no cambió: si el usuario está "
            "conforme con el DXF, guárdalo con asignar_bloques de archimind-core."
        )
    lines.append(
        "ajustar_bloque_a_vano explica cada elección; para cambiar una, vuelve a insertar ese "
        "vano con sus preferencias."
    )
    return _text(_truncate(lines, MAX_LINES))


def profile_added(key: str, items: Catalog, path: Path) -> str:
    return _text(
        [
            f"Perfil agregado a {path}:",
            *_profile_lines(key, items.profiles[key]),
            f"El catálogo tiene ahora {_count(len(items.profiles), 'perfil', 'perfiles')}.",
        ]
    )


def opening_line(fit: Fit, kind: str, width: float, height: float, wall_id: str) -> str:
    return f"{fit.opening_id}: {KINDS[kind]} de {width:.2f} × {height:.2f} m en {wall_id}"


def _params_lines(params: CarpentryParams, key: str) -> list[str]:
    profile = params.profile
    name = TYPE_NAMES[params.type]
    if isinstance(params, SlidingWindow):
        name += f" de {params.leaves} hojas"
    lines = [
        f"{name[:1].upper()}{name[1:]}, {params.width:.2f} × {params.height:.2f} m, perfil {key} "
        f"({profile.name})"
    ]
    leaf = f"{params.leaf_noun} de {params.leaf_width:.3f} × {params.leaf_height:.3f} m"
    details = [leaf[:1].upper() + leaf[1:]]
    data = params.model_dump()
    if "leaf_thickness" in data:
        details.append(f"hoja de {data['leaf_thickness']:.3f} m de espesor")
    if "hand" in data:
        details.append(HANDS[data["hand"]])
    if "swing" in data:
        details.append(SWINGS[data["swing"]])
    if "side" in data:
        details.append(SIDES[data["side"]])
    if "sill_height" in data:
        details.append(f"antepecho {data['sill_height']:.2f} m")
    details.append(f"muro de {params.wall_thickness:.2f} m")
    return [*lines, " · ".join(details)]


def _profile_lines(key: str, profile: Profile) -> list[str]:
    types = ", ".join(TYPE_NAMES[t] for t in profile.types)
    return [
        f"  {key}: {profile.name} ({profile.material}) — {types}",
        f"    marco {profile.frame.face:.3f} × {profile.frame.depth:.3f} m, hoja "
        f"{profile.sash.face:.3f} × {profile.sash.depth:.3f} m, traslape {profile.overlap:.3f} m, "
        f"vidrio {profile.glass:.3f} m; cada hoja de {profile.sash_width.min:.2f} a "
        f"{profile.sash_width.max:.2f} m de ancho y de {profile.sash_height.min:.2f} a "
        f"{profile.sash_height.max:.2f} m de alto",
    ]


def _fit_line(fit: Fit, carpentry: Carpentry) -> str:
    params = fit.params
    name = TYPE_NAMES[params.type]
    if isinstance(params, SlidingWindow):
        name += f" de {params.leaves} hojas"
    data = params.model_dump()
    opening = []
    if "hand" in data:
        opening.append(HANDS[data["hand"]])
    if fit.site.room is not None:
        opening.append(f"adentro {fit.site.room.name} ({fit.site.room.id})")
    if "swing" in data and data["swing"] == "out":
        opening.append("abre hacia afuera")
    return f"{fit.opening_id} → {name}, {fit.profile_key}, {', '.join(opening)} · {carpentry.name}"


def _notes(notes: Sequence[str]) -> list[str]:
    return ["Elegido o supuesto:", *(f"  - {note}" for note in notes)] if notes else []


def _relative(folder: Path, path: Path) -> str:
    return path.relative_to(folder).as_posix() if path.is_relative_to(folder) else str(path)


def _count(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


def _truncate(lines: Sequence[str], limit: int) -> list[str]:
    if len(lines) <= limit:
        return list(lines)
    return [*lines[: limit - 1], f"  … y {len(lines) - limit + 1} más"]


def _text(lines: Sequence[str]) -> str:
    return "\n".join(lines)
