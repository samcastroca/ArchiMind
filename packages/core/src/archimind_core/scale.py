"""Confirmación de la escala del modelo y su recálculo a partir de una medida real.

Lo que se mide en el plano (ejes, espesores, vanos, espacios, anotaciones) se escala; lo que
sale de `build_rules.yaml` (alturas, antepechos, elevaciones) no.
"""

import math
from dataclasses import dataclass

from archimind_schema import Point2D, Project, SpacePolygon, wall_length
from pydantic import ValidationError

MAX_LISTED_WALLS = 10


class ScaleError(Exception):
    """La escala no se puede confirmar; el mensaje está pensado para el usuario final."""


@dataclass(frozen=True)
class ScaleConfirmation:
    """El modelo con la escala confirmada. `factor` es 1 si solo se confirmaron las unidades;
    `changed` es False si ya estaba confirmada y no hubo nada que hacer. `measured_length` es lo
    que medía el muro de referencia antes de escalar."""

    project: Project
    factor: float
    changed: bool
    measured_length: float | None = None


def rescale(project: Project, factor: float) -> Project:
    """Una copia del modelo con lo medido en el plano multiplicado por `factor`."""
    if not (math.isfinite(factor) and factor > 0):
        raise ScaleError(f"El factor de escala debe ser un número mayor que 0, no {factor}")

    def point(p: Point2D) -> Point2D:
        return (p[0] * factor, p[1] * factor)

    scaled = project.model_copy(deep=True)
    for wall in scaled.walls:
        wall.axis = [point(p) for p in wall.axis]
        wall.thickness *= factor
    for opening in scaled.openings:
        opening.offset *= factor
        opening.width *= factor
    for space in scaled.spaces:
        space.polygon = SpacePolygon(
            exterior=[point(p) for p in space.polygon.exterior],
            holes=[[point(p) for p in hole] for hole in space.polygon.holes],
        )
    for annotation in scaled.annotations:
        annotation.position = point(annotation.position)
    try:
        return Project.model_validate(scaled.model_dump())
    except ValidationError as exc:
        raise ScaleError(f"Con el factor {factor:.6g} el modelo deja de ser válido: {exc}") from exc


def confirm_scale(
    project: Project, wall_id: str | None = None, real_length: float | None = None
) -> ScaleConfirmation:
    """Sin argumentos, confirma las unidades con las que se leyó el plano. Con `wall_id` y
    `real_length` (metros, a lo largo del eje), escala el modelo para que ese muro mida eso."""
    if (wall_id is None) != (real_length is None):
        raise ScaleError(
            "Para recalcular la escala hacen falta muro_id y longitud_real juntos; sin ninguno "
            "de los dos se confirman las unidades detectadas."
        )
    if not project.walls:
        raise ScaleError(
            "El modelo aún no tiene muros: aplica el mapeo de capas con aplicar_mapeo antes de "
            "confirmar la escala."
        )
    if wall_id is None or real_length is None:
        if project.scale_confirmed:
            return ScaleConfirmation(project, 1.0, changed=False)
        return ScaleConfirmation(project.model_copy(update={"scale_confirmed": True}), 1.0, True)

    walls = {wall.id: wall for wall in project.walls}
    if wall_id not in walls:
        listed = sorted(walls)[:MAX_LISTED_WALLS]
        more = f" y {len(walls) - len(listed)} más" if len(walls) > len(listed) else ""
        raise ScaleError(
            f"No existe el muro {wall_id}. Los muros del modelo son {', '.join(listed)}{more}."
        )
    if not (math.isfinite(real_length) and real_length > 0):
        raise ScaleError(f"La longitud real debe ser mayor que 0 m, no {real_length}")
    measured = wall_length(walls[wall_id])
    scaled = rescale(project, real_length / measured)
    scaled.scale_confirmed = True
    return ScaleConfirmation(scaled, real_length / measured, True, measured)
