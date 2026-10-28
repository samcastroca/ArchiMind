"""Estilos de los dibujos (config/estilos.yaml): grosor, color y tipo de línea de cada capa."""

from pathlib import Path
from typing import Literal

import yaml
from ezdxf.lldxf.const import VALID_DXF_LINEWEIGHTS
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

# Fuera de src/: sirve en el workspace editable, no dentro de un wheel.
DEFAULT_STYLES_PATH = Path(__file__).resolve().parents[2] / "config" / "estilos.yaml"
# Las capas que usan las herramientas: la axonometría y el corte.
REQUIRED_LAYERS = ("VISIBLES", "OCULTAS", "CORTADO", "PROYECTADO")

Linetype = Literal["CONTINUOUS", "DASHED", "HIDDEN", "CENTER", "DASHDOT"]


class StylesError(Exception):
    """El archivo de estilos no existe o no es válido; el mensaje está pensado para el usuario."""


class _Styles(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class LayerStyle(_Styles):
    lineweight_mm: float
    color: int = Field(ge=1, le=255)
    linetype: Linetype

    @field_validator("lineweight_mm")
    @classmethod
    def _standard(cls, value: float) -> float:
        hundredths = value * 100
        if (
            abs(hundredths - round(hundredths)) > 1e-6
            or round(hundredths) not in VALID_DXF_LINEWEIGHTS
        ):
            valid = ", ".join(f"{w / 100:.2f}" for w in VALID_DXF_LINEWEIGHTS if w > 0)
            raise ValueError(f"{value} mm no es un grosor de DXF; los válidos son {valid}")
        return value

    @property
    def lineweight(self) -> int:
        """En centésimas de mm, como lo guarda el DXF."""
        return round(self.lineweight_mm * 100)


class Styles(_Styles):
    layers: dict[str, LayerStyle]
    linetype_scale: float = Field(gt=0)
    svg_scale: float = Field(gt=0)
    exploded_gap_m: float = Field(gt=0)


def load_styles(path: str | Path = DEFAULT_STYLES_PATH) -> Styles:
    source = Path(path)
    try:
        data = yaml.safe_load(source.read_text(encoding="utf-8"))
    except OSError as exc:
        raise StylesError(f"No se pudo leer el archivo de estilos {source}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise StylesError(f"{source.name} no es un YAML válido: {exc}") from exc
    try:
        styles = Styles.model_validate(data)
    except ValidationError as exc:
        raise StylesError(f"{source.name} tiene estilos inválidos: {exc}") from exc
    missing = [layer for layer in REQUIRED_LAYERS if layer not in styles.layers]
    if missing:
        raise StylesError(f"{source.name}: faltan las capas {', '.join(missing)}.")
    return styles
