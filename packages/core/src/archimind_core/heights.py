"""Alturas de los muros: las que confirma el usuario por nivel o por espacio, y las que faltan.

Un muro mide `wall.height` o, si no la tiene, el `default_height` de su nivel. Este último sale de
`build_rules.yaml` al importar y no cuenta como medida hasta que se confirma (`height_confirmed`).
"""

import math
from collections.abc import Collection
from dataclasses import dataclass

from archimind_schema import LENGTH_TOL, Project, Wall, wall_height, wall_polygon
from shapely import Polygon

# Borde mínimo que un muro comparte con un espacio para delimitarlo: el umbral de «unión
# abierta» de validate. Menos es tocar en una esquina.
MIN_SHARED_EDGE = 0.05


class HeightsError(Exception):
    """Las alturas no se pueden aplicar; el mensaje está pensado para el usuario final."""


@dataclass(frozen=True)
class MissingHeight:
    """Un nivel con la altura sin confirmar y sus muros sin altura propia."""

    level_id: str
    level_name: str
    default_height: float
    wall_ids: list[str]


@dataclass(frozen=True)
class HeightsResult:
    """El modelo con las alturas aplicadas. `walls` es muro → altura nueva por espacio;
    `kept_walls` son los muros con altura propia de los niveles confirmados, que la conservan."""

    project: Project
    levels: dict[str, float]
    walls: dict[str, float]
    kept_walls: list[str]
    warnings: list[str]


def missing_heights(project: Project) -> list[MissingHeight]:
    missing = []
    for level in project.levels:
        if level.height_confirmed:
            continue
        walls = [w.id for w in project.walls if w.level_id == level.id and w.height is None]
        if walls:
            missing.append(MissingHeight(level.id, level.name, level.default_height, walls))
    return missing


def define_heights(
    project: Project,
    by_level: dict[str, float] | None = None,
    by_space: dict[str, float] | None = None,
) -> HeightsResult:
    """Una copia del modelo con las alturas aplicadas: primero las de nivel, después las de
    espacio. Comprueba todo antes de devolver nada."""
    by_level, by_space = by_level or {}, by_space or {}
    if not by_level and not by_space:
        raise HeightsError("Indica las alturas por_nivel ({niv-…: m}) o por_espacio ({esp-…: m}).")
    _check_values({**by_level, **by_space})
    levels = {level.id: level for level in project.levels}
    spaces = {space.id: space for space in project.spaces}
    _check_ids("nivel", by_level, levels)
    _check_ids("espacio", by_space, spaces)

    result = project.model_copy(deep=True)
    for level in result.levels:
        if level.id in by_level:
            level.default_height = by_level[level.id]
            level.height_confirmed = True
    kept = [w.id for w in result.walls if w.level_id in by_level and w.height is not None]

    # La altura de cada espacio: la pedida o, si no, la de su nivel confirmado.
    confirmed = {
        level.id: level.default_height for level in result.levels if level.height_confirmed
    }
    space_heights = {s.id: by_space.get(s.id, confirmed.get(s.level_id)) for s in result.spaces}
    polygons = {s.id: Polygon(s.polygon.exterior, s.polygon.holes) for s in result.spaces}

    def bounded(wall: Wall) -> list[str]:
        return [
            s.id
            for s in result.spaces
            if s.level_id == wall.level_id and _bounds(wall, polygons[s.id])
        ]

    walls: dict[str, float] = {}
    warnings = []
    for space_id in by_space:
        around = [w for w in result.walls if space_id in bounded(w)]
        if not around:
            warnings.append(f"{space_id} no tiene muros que lo delimiten: no cambió ninguno")
        for wall in around:
            if wall.id in walls:
                continue
            # Un muro entre espacios de alturas distintas llega hasta el más alto.
            sides = sorted((h, s) for s in bounded(wall) if (h := space_heights[s]) is not None)
            (low, low_id), (high, high_id) = sides[0], sides[-1]
            if high - low > LENGTH_TOL:
                source = "" if high_id in by_space else ", la de su nivel"
                warnings.append(
                    f"{wall.id} separa {high_id} ({high:.2f} m{source}) de {low_id} "
                    f"({low:.2f} m): queda con {high:.2f} m"
                )
            wall.height = walls[wall.id] = high

    _check_openings_fit(result)
    return HeightsResult(
        project=result,
        levels=dict(by_level),
        walls=walls,
        kept_walls=kept,
        warnings=warnings,
    )


def _bounds(wall: Wall, space: Polygon) -> bool:
    footprint = wall_polygon(wall).buffer(LENGTH_TOL)
    return float(space.boundary.intersection(footprint).length) > MIN_SHARED_EDGE


def _check_values(heights: dict[str, float]) -> None:
    bad = [f"{key}: {h}" for key, h in heights.items() if not (math.isfinite(h) and h > 0)]
    if bad:
        raise HeightsError(f"Las alturas deben ser mayores que 0 m ({', '.join(bad)}).")


def _check_ids(kind: str, given: dict[str, float], known: Collection[str]) -> None:
    unknown = [key for key in given if key not in known]
    if unknown:
        raise HeightsError(
            f"No existen en el modelo: {', '.join(unknown)}. Los IDs de {kind} salen de "
            "listar_modelo y del resumen del proyecto."
        )


def _check_openings_fit(project: Project) -> None:
    walls = {wall.id: wall for wall in project.walls}
    too_tall = []
    for opening in project.openings:
        wall = walls[opening.wall_id]
        top, height = opening.sill_height + opening.height, wall_height(project, wall)
        if top > height + LENGTH_TOL:
            too_tall.append(f"{opening.id} llega a {top:.2f} m y {wall.id} mide {height:.2f} m")
    if too_tall:
        raise HeightsError(
            "Con esas alturas hay vanos más altos que su muro; no se aplicó nada: "
            + "; ".join(too_tall)
        )
