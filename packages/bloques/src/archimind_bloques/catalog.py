"""Catálogo de perfiles de carpintería (catalog.yaml): medidas y límites de cada perfil."""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

# Fuera de src/: sirve en el workspace editable, no dentro de un wheel.
DEFAULT_CATALOG_PATH = Path(__file__).resolve().parents[2] / "catalog.yaml"

CarpentryType = Literal[
    "swing_door",
    "double_swing_door",
    "sliding_door",
    "sliding_window",
    "fixed_window",
    "awning_window",
]
TYPE_NAMES: dict[CarpentryType, str] = {
    "swing_door": "puerta batiente",
    "double_swing_door": "puerta batiente doble",
    "sliding_door": "puerta corrediza",
    "sliding_window": "ventana corrediza",
    "fixed_window": "ventana fija",
    "awning_window": "ventana proyectante",
}


class CatalogError(Exception):
    """El catálogo no existe, no es válido o no tiene el perfil pedido; el mensaje está pensado
    para el usuario."""


class _Catalog(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class Section(_Catalog):
    """Sección de un perfil: ancho visto en alzado y fondo en planta."""

    face: float = Field(gt=0)
    depth: float = Field(gt=0)


class Range(_Catalog):
    min: float = Field(gt=0)
    max: float = Field(gt=0)

    @model_validator(mode="after")
    def _ordered(self) -> "Range":
        if self.min > self.max:
            raise ValueError(f"el mínimo ({self.min}) supera al máximo ({self.max})")
        return self


class Profile(_Catalog):
    name: str = Field(min_length=1)
    types: tuple[CarpentryType, ...] = Field(min_length=1)
    frame: Section
    sash: Section
    overlap: float = Field(ge=0)
    glass: float = Field(gt=0)
    sash_width: Range
    sash_height: Range

    @model_validator(mode="after")
    def _consistent(self) -> "Profile":
        """Que toda hoja admitida tenga lugar para su vidrio y quepa en el marco."""
        if self.sash.depth > self.frame.depth:
            raise ValueError(
                f"la hoja ({self.sash.depth} m de fondo) no cabe en el marco "
                f"({self.frame.depth} m de fondo)"
            )
        if self.glass > self.sash.depth:
            raise ValueError(
                f"el vidrio ({self.glass} m) es más grueso que la hoja ({self.sash.depth} m)"
            )
        for label, limits in (("ancho", self.sash_width), ("alto", self.sash_height)):
            if limits.min <= 2 * self.sash.face:
                raise ValueError(
                    f"el {label} mínimo de hoja ({limits.min} m) no deja lugar al vidrio entre "
                    f"dos montantes de {self.sash.face} m"
                )
        return self


class Catalog(_Catalog):
    profiles: dict[str, Profile] = Field(min_length=1)

    def profile(self, key: str) -> Profile:
        try:
            return self.profiles[key]
        except KeyError:
            available = ", ".join(sorted(self.profiles))
            raise CatalogError(
                f"El catálogo no tiene el perfil «{key}». Los disponibles son: {available}."
            ) from None


def load_catalog(path: str | Path = DEFAULT_CATALOG_PATH) -> Catalog:
    source = Path(path)
    try:
        data = yaml.safe_load(source.read_text(encoding="utf-8"))
    except OSError as exc:
        raise CatalogError(f"No se pudo leer el catálogo {source}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise CatalogError(f"{source.name} no es un YAML válido: {exc}") from exc
    try:
        return Catalog.model_validate(data)
    except ValidationError as exc:
        raise CatalogError(f"{source.name} tiene perfiles inválidos: {exc}") from exc
