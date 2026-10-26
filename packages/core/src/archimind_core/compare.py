"""Diferencias entre dos versiones del modelo de un proyecto, emparejadas por ID.

Los IDs son estables: el mismo ID es el mismo elemento en las dos versiones.
"""

import math
from dataclasses import dataclass

from archimind_schema import LENGTH_TOL, Opening, Project, Wall, space_area

from archimind_core.quantities import PRELIMINARY_LABEL

AREA_CHANGE_TOL = 0.005


@dataclass(frozen=True)
class SpaceChange:
    id: str
    name: str
    area_before: float
    area_after: float
    relative_change: float


@dataclass(frozen=True)
class VersionDiff:
    """Lo que cambia de `model_a` a `model_b`. Las listas de muros y vanos son IDs, ordenados.
    `preliminary` si alguna de las dos versiones no tiene la escala confirmada."""

    spaces_changed: list[SpaceChange]
    walls_added: list[str]
    walls_removed: list[str]
    walls_moved: list[str]
    openings_modified: list[str]
    preliminary: bool
    label: str | None


def compare_versions(model_a: Project, model_b: Project) -> VersionDiff:
    walls_a = {w.id: w for w in model_a.walls}
    walls_b = {w.id: w for w in model_b.walls}
    openings_a = {o.id: o for o in model_a.openings}
    openings_b = {o.id: o for o in model_b.openings}
    preliminary = not (model_a.scale_confirmed and model_b.scale_confirmed)
    return VersionDiff(
        spaces_changed=_space_changes(model_a, model_b),
        walls_added=sorted(walls_b.keys() - walls_a.keys()),
        walls_removed=sorted(walls_a.keys() - walls_b.keys()),
        walls_moved=sorted(
            wall_id
            for wall_id in walls_a.keys() & walls_b.keys()
            if _wall_moved(walls_a[wall_id], walls_b[wall_id])
        ),
        openings_modified=sorted(
            opening_id
            for opening_id in openings_a.keys() & openings_b.keys()
            if _opening_modified(openings_a[opening_id], openings_b[opening_id])
        ),
        preliminary=preliminary,
        label=PRELIMINARY_LABEL if preliminary else None,
    )


def _space_changes(model_a: Project, model_b: Project) -> list[SpaceChange]:
    spaces_b = {s.id: s for s in model_b.spaces}
    changes = []
    for before in sorted(model_a.spaces, key=lambda s: s.id):
        after = spaces_b.get(before.id)
        if after is None:
            continue
        area_before, area_after = space_area(before), space_area(after)
        relative = (area_after - area_before) / area_before
        if abs(relative) > AREA_CHANGE_TOL:
            changes.append(SpaceChange(after.id, after.name, area_before, area_after, relative))
    return changes


def _wall_moved(a: Wall, b: Wall) -> bool:
    if len(a.axis) != len(b.axis) or abs(a.thickness - b.thickness) > LENGTH_TOL:
        return True
    return any(math.dist(p, q) > LENGTH_TOL for p, q in zip(a.axis, b.axis, strict=True))


def _opening_modified(a: Opening, b: Opening) -> bool:
    labels = ("wall_id", "kind", "block_id", "block_side")
    if any(getattr(a, name) != getattr(b, name) for name in labels):
        return True
    return any(
        abs(getattr(a, name) - getattr(b, name)) > LENGTH_TOL
        for name in ("offset", "width", "height", "sill_height")
    )
