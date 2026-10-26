"""Entidades del modelo semántico. Unidades internas: metros."""

import math
import re
from collections.abc import Callable, Iterable
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator
from shapely import Polygon, is_valid_reason

from archimind_schema.geometry import wall_length

LENGTH_TOL = 0.001
ANGLE_TOL_DEG = 0.5
ID_PREFIXES = ("niv", "muro", "vano", "esp", "blq")

Point2D = tuple[float, float]


def _prefixed_id(prefix: str) -> Callable[[str], str]:
    pattern = re.compile(rf"^{prefix}-\d{{4,}}$")

    def check(value: str) -> str:
        if not pattern.match(value):
            raise ValueError(f"el ID '{value}' no tiene el formato '{prefix}-NNNN'")
        return value

    return check


LevelId = Annotated[str, AfterValidator(_prefixed_id("niv"))]
WallId = Annotated[str, AfterValidator(_prefixed_id("muro"))]
OpeningId = Annotated[str, AfterValidator(_prefixed_id("vano"))]
SpaceId = Annotated[str, AfterValidator(_prefixed_id("esp"))]
BlockId = Annotated[str, AfterValidator(_prefixed_id("blq"))]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Level(_Model):
    id: LevelId
    name: str
    elevation: float
    default_height: float = Field(gt=0)


class Wall(_Model):
    id: WallId
    level_id: LevelId
    axis: list[Point2D] = Field(min_length=2)
    thickness: float = Field(gt=0)
    height: float | None = Field(default=None, gt=0)
    source_layer: str | None = None

    @model_validator(mode="after")
    def _segments_have_length(self) -> "Wall":
        for a, b in zip(self.axis, self.axis[1:], strict=False):
            if math.dist(a, b) < LENGTH_TOL:
                raise ValueError(f"el eje del muro {self.id} tiene un tramo de longitud nula")
        return self


class Opening(_Model):
    id: OpeningId
    wall_id: WallId
    kind: Literal["door", "window", "void"]
    offset: float = Field(ge=0)
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    sill_height: float = Field(ge=0)
    block_id: BlockId | None = None


class SpacePolygon(_Model):
    exterior: list[Point2D] = Field(min_length=3)
    holes: list[list[Point2D]] = Field(default_factory=list)

    @model_validator(mode="after")
    def _is_valid_polygon(self) -> "SpacePolygon":
        if any(len(hole) < 3 for hole in self.holes):
            raise ValueError("cada hueco del polígono necesita al menos 3 puntos")
        polygon = Polygon(self.exterior, self.holes)
        if not polygon.is_valid:
            raise ValueError(f"polígono no válido: {is_valid_reason(polygon)}")
        if polygon.area <= 0:
            raise ValueError("el polígono tiene área nula")
        return self


class Space(_Model):
    id: SpaceId
    level_id: LevelId
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
    layer_mapping: dict[str, str] = Field(default_factory=dict)
    levels: list[Level] = Field(default_factory=list)
    walls: list[Wall] = Field(default_factory=list)
    openings: list[Opening] = Field(default_factory=list)
    spaces: list[Space] = Field(default_factory=list)
    annotations: list[Annotation] = Field(default_factory=list)
    next_ids: dict[str, int] = Field(default_factory=lambda: dict.fromkeys(ID_PREFIXES, 1))

    @model_validator(mode="after")
    def _check_integrity(self) -> "Project":
        used = self._used_ids()
        self._check_next_ids(used)
        level_ids = {level.id for level in self.levels}
        walls = {wall.id: wall for wall in self.walls}
        located: list[Wall | Space] = [*self.walls, *self.spaces]
        for item in located:
            if item.level_id not in level_ids:
                raise ValueError(f"{item.id} apunta al nivel inexistente {item.level_id}")
        for opening in self.openings:
            wall = walls.get(opening.wall_id)
            if wall is None:
                raise ValueError(f"{opening.id} apunta al muro inexistente {opening.wall_id}")
            if opening.offset + opening.width > wall_length(wall) + LENGTH_TOL:
                raise ValueError(f"{opening.id} se sale de la longitud del muro {wall.id}")
        return self

    def _used_ids(self) -> list[str]:
        entities: Iterable[Level | Wall | Opening | Space] = [
            *self.levels,
            *self.walls,
            *self.openings,
            *self.spaces,
        ]
        ids = [entity.id for entity in entities]
        seen: set[str] = set()
        for entity_id in ids:
            if entity_id in seen:
                raise ValueError(f"el ID {entity_id} está repetido")
            seen.add(entity_id)
        ids += [o.block_id for o in self.openings if o.block_id is not None]
        return ids

    def _check_next_ids(self, used: list[str]) -> None:
        if set(self.next_ids) != set(ID_PREFIXES):
            raise ValueError(f"next_ids debe tener exactamente los prefijos {list(ID_PREFIXES)}")
        for entity_id in used:
            prefix = entity_id.rsplit("-", 1)[0]
            if _id_number(entity_id) >= self.next_ids[prefix]:
                raise ValueError(
                    f"el contador de '{prefix}' ({self.next_ids[prefix]}) no supera el ID "
                    f"existente {entity_id}"
                )
