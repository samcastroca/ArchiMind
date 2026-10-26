"""Entidades del modelo semántico. Unidades internas: metros."""

import math
import re
from collections.abc import Iterable
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

LENGTH_TOL = 0.001
ANGLE_TOL_DEG = 0.5
ID_PREFIXES = ("niv", "muro", "vano", "esp", "blq")
WALL_THICKNESSES = (0.10, 0.12, 0.15, 0.20, 0.25)
# Qué representa una capa del plano; "mixed" si mezcla roles y no se puede asignar uno solo.
LayerRole = Literal[
    "walls", "doors", "windows", "text", "dimensions", "axes", "furniture", "ignore", "mixed"
]

Point2D = tuple[float, float]


def id_pattern(prefix: str) -> re.Pattern[str]:
    return re.compile(rf"^{prefix}-\d{{4,}}$")


_ANY_ID = id_pattern("(?:" + "|".join(ID_PREFIXES) + ")")


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Level(_Model):
    id: str
    name: str
    elevation: float
    default_height: float = Field(gt=0)


class Wall(_Model):
    id: str
    level_id: str
    axis: list[Point2D] = Field(min_length=2)
    thickness: float
    height: float | None = Field(default=None, gt=0)
    source_layer: str | None = None

    @model_validator(mode="after")
    def _segments_have_length(self) -> "Wall":
        for a, b in zip(self.axis, self.axis[1:], strict=False):
            if math.dist(a, b) < LENGTH_TOL:
                raise ValueError(f"el eje del muro {self.id} tiene un tramo de longitud nula")
        return self


class Opening(_Model):
    id: str
    wall_id: str
    kind: Literal["door", "window", "void"]
    offset: float = Field(ge=0)
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    sill_height: float = Field(ge=0)
    block_id: str | None = None


class SpacePolygon(_Model):
    exterior: list[Point2D] = Field(min_length=3)
    holes: list[list[Point2D]] = Field(default_factory=list)


class Space(_Model):
    id: str
    level_id: str
    name: str
    polygon: SpacePolygon
    category: Literal["useful", "balcony", "circulation", "service", "technical"]


class Annotation(_Model):
    text: str
    position: Point2D
    kind: Literal["dimension", "level", "label"]


def _id_number(entity_id: str) -> int:
    return int(entity_id.rsplit("-", 1)[1])


class Project(_Model):
    id: str = Field(min_length=1)
    name: str
    units: Literal["m"] = "m"
    scale_confirmed: bool
    source_files: list[str] = Field(default_factory=list)
    layer_mapping: dict[str, LayerRole] = Field(default_factory=dict)
    levels: list[Level] = Field(default_factory=list)
    walls: list[Wall] = Field(default_factory=list)
    openings: list[Opening] = Field(default_factory=list)
    spaces: list[Space] = Field(default_factory=list)
    annotations: list[Annotation] = Field(default_factory=list)
    next_ids: dict[str, int] = Field(default_factory=lambda: dict.fromkeys(ID_PREFIXES, 1))

    @model_validator(mode="after")
    def _check_next_ids(self) -> "Project":
        """Solo la estructura: las reglas semánticas las reporta `validate`."""
        if set(self.next_ids) != set(ID_PREFIXES):
            raise ValueError(f"next_ids debe tener exactamente los prefijos {list(ID_PREFIXES)}")
        for entity_id in self._used_ids():
            prefix = entity_id.rsplit("-", 1)[0]
            if _id_number(entity_id) >= self.next_ids[prefix]:
                raise ValueError(
                    f"el contador de '{prefix}' ({self.next_ids[prefix]}) no supera el ID "
                    f"existente {entity_id}"
                )
        return self

    def _used_ids(self) -> list[str]:
        """IDs bien formados en uso; los mal formados los reporta `validate`."""
        entities: Iterable[Level | Wall | Opening | Space] = [
            *self.levels,
            *self.walls,
            *self.openings,
            *self.spaces,
        ]
        ids = [entity.id for entity in entities]
        ids += [o.block_id for o in self.openings if o.block_id is not None]
        return [entity_id for entity_id in ids if _ANY_ID.match(entity_id)]
