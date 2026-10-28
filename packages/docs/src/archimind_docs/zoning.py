"""COS y CUS del proyecto en un lote.

- COS (coeficiente de ocupación del suelo): la huella construida del nivel más bajo dividida
  por el área del lote.
- CUS (coeficiente de utilización del suelo): la suma de las áreas construidas de todos los
  niveles dividida por el área del lote.

El área construida de cada nivel es la de `area_table` de core sobre ese nivel solo: el
contorno exterior de sus espacios (sin balcones) y de sus muros.
"""

from dataclasses import dataclass

from archimind_core.quantities import area_table
from archimind_schema import Project

from archimind_docs.errors import DocsError


@dataclass(frozen=True)
class LevelArea:
    name: str
    built_area: float


@dataclass(frozen=True)
class Coefficients:
    lot_area: float
    levels: list[LevelArea]  # del más bajo al más alto
    footprint: float
    total_built: float
    cos: float
    cus: float
    preliminary: bool


def coefficients(project: Project, lot_area: float) -> Coefficients:
    if lot_area <= 0:
        raise DocsError("El área del lote debe ser mayor que 0 m².")
    levels = sorted(project.levels, key=lambda lv: (lv.elevation, lv.id))
    areas = [LevelArea(level.name, _built_area(project, level.id)) for level in levels]
    areas = [a for a in areas if a.built_area > 0]
    if not areas:
        raise DocsError(
            f"El modelo de {project.name} no tiene área construida: reconstrúyelo con "
            "aplicar_mapeo de archimind-core."
        )
    footprint = areas[0].built_area
    total = sum(a.built_area for a in areas)
    return Coefficients(
        lot_area,
        areas,
        footprint,
        total,
        footprint / lot_area,
        total / lot_area,
        not project.scale_confirmed,
    )


def _built_area(project: Project, level_id: str) -> float:
    walls = [w for w in project.walls if w.level_id == level_id]
    wall_ids = {w.id for w in walls}
    level_only = project.model_copy(
        update={
            "walls": walls,
            "openings": [o for o in project.openings if o.wall_id in wall_ids],
            "spaces": [s for s in project.spaces if s.level_id == level_id],
        }
    )
    return area_table(level_only).built_area
