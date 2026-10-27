"""Borradores que los demás servidores entregan a core, el único que escribe el modelo.

Viajan como archivos JSON en la carpeta del proyecto: así ninguna medida pasa por el LLM que
orquesta los servidores.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from archimind_schema.models import AxisSide, BlockDefinition, Point2D, SpacePolygon, id_pattern


class BlockAssignment(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    opening_id: str
    side: AxisSide
    block: BlockDefinition


class BlocksDraft(BaseModel):
    """La carpintería que archimind-bloques propone para unos vanos; core pone los IDs `blq-`."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    assignments: list[BlockAssignment] = Field(min_length=1)


class _Edit(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    id: str


class WallEdit(_Edit):
    """Los valores nuevos de un muro recto; `height` con la semántica de `Wall.height`."""

    axis: list[Point2D] = Field(min_length=2)
    thickness: float = Field(gt=0)
    height: float | None = Field(default=None, gt=0)


class OpeningEdit(_Edit):
    """Los valores nuevos de un vano en su mismo muro."""

    offset: float = Field(ge=0)
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    sill_height: float = Field(ge=0)


class SpaceEdit(_Edit):
    """El contorno y el nombre nuevos de un espacio."""

    polygon: SpacePolygon
    name: str


_NEW_REF = r"^nuevo-\d+$"


class _New(BaseModel):
    """Una entidad dibujada fuera de ArchiMind, sin ID: core le pone uno inédito. `ref` la
    identifica solo dentro del borrador."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    ref: str = Field(pattern=_NEW_REF)


class NewWall(_New):
    level_id: str
    axis: list[Point2D] = Field(min_length=2)
    thickness: float = Field(gt=0)
    height: float | None = Field(default=None, gt=0)


class NewOpening(_New):
    """Un vano nuevo en un muro: un `muro-` del modelo o el `ref` de un muro nuevo."""

    wall: str
    kind: Literal["door", "window", "void"] = "void"
    offset: float = Field(ge=0)
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    sill_height: float = Field(ge=0)


class NewSpace(_New):
    level_id: str
    name: str = Field(min_length=1)
    polygon: SpacePolygon
    category: Literal["useful", "balcony", "circulation", "service", "technical"] = "useful"


_EDIT_PREFIXES = {"walls": "muro", "openings": "vano", "spaces": "esp"}


class EditsDraft(BaseModel):
    """Ediciones de geometría hechas fuera de ArchiMind (en Rhino) sobre una versión del modelo:
    entidades modificadas, nuevas (sin ID) e IDs borrados. `base_sha256` es el SHA-256 de
    `modelo.json` tal como se cargó: si el modelo cambió desde entonces, core debe rechazar el
    borrador."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    source: Literal["rhino"]
    base_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    walls: list[WallEdit] = Field(default_factory=list)
    openings: list[OpeningEdit] = Field(default_factory=list)
    spaces: list[SpaceEdit] = Field(default_factory=list)
    deleted: list[str] = Field(default_factory=list)
    new_walls: list[NewWall] = Field(default_factory=list)
    new_openings: list[NewOpening] = Field(default_factory=list)
    new_spaces: list[NewSpace] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_ids(self) -> "EditsDraft":
        ids = [*(e.id for e in self.walls), *(e.id for e in self.openings)]
        ids += [*(e.id for e in self.spaces), *self.deleted]
        refs = [*(n.ref for n in self.new_walls), *(n.ref for n in self.new_openings)]
        refs += [n.ref for n in self.new_spaces]
        if not ids and not refs:
            raise ValueError("el borrador no tiene ningún cambio")
        repeated_refs = sorted({r for r in refs if refs.count(r) > 1})
        if repeated_refs:
            raise ValueError(f"refs repetidos en el borrador: {', '.join(repeated_refs)}")
        new_walls = {n.ref for n in self.new_walls}
        for opening in self.new_openings:
            if opening.wall.startswith("nuevo-"):
                if opening.wall not in new_walls:
                    raise ValueError(f"{opening.ref} está en {opening.wall}, que no es un muro")
            elif not id_pattern("muro").match(opening.wall):
                raise ValueError(f"{opening.ref}: {opening.wall} no es un muro")
            elif opening.wall in self.deleted:
                raise ValueError(f"{opening.ref} está en el muro borrado {opening.wall}")
        repeated = sorted({i for i in ids if ids.count(i) > 1})
        if repeated:
            raise ValueError(f"IDs repetidos en el borrador: {', '.join(repeated)}")
        for field, prefix in _EDIT_PREFIXES.items():
            for edit in getattr(self, field):
                if not id_pattern(prefix).match(edit.id):
                    raise ValueError(f"{edit.id} no es un ID {prefix}- válido en {field}")
        deletable = id_pattern("(?:muro|vano|esp)")
        bad = [i for i in self.deleted if not deletable.match(i)]
        if bad:
            raise ValueError(f"solo se borran muros, vanos y espacios: {', '.join(bad)}")
        return self
