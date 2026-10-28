"""Líneas de corte que core propone y que el puente de Rhino dibuja.

Viajan en `salidas/cortes.json`: el usuario elige un corte por su nombre y las coordenadas no
pasan por el LLM.
"""

from pydantic import BaseModel, ConfigDict, Field, model_validator

from archimind_schema.models import LENGTH_TOL, Point2D

CUTS_FILENAME = "cortes.json"


class CutLine(BaseModel):
    """Una línea de corte en planta, de `start` a `end`, en metros. `name` es la clave con la que
    se elige (p. ej. "longitudinal"); `label` es el rótulo del plano (p. ej. "A-A")."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    name: str = Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    label: str = Field(min_length=1)
    start: Point2D
    end: Point2D
    description: str = ""

    @model_validator(mode="after")
    def _has_length(self) -> "CutLine":
        dx, dy = self.end[0] - self.start[0], self.end[1] - self.start[1]
        if (dx * dx + dy * dy) ** 0.5 <= LENGTH_TOL:
            raise ValueError("la línea de corte necesita dos puntos distintos")
        return self


class CutProposals(BaseModel):
    """Los cortes propuestos para la versión del modelo con ese SHA-256."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    base_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    cuts: list[CutLine]

    @model_validator(mode="after")
    def _unique_names(self) -> "CutProposals":
        names = [cut.name for cut in self.cuts]
        if len(names) != len(set(names)):
            raise ValueError("los nombres de los cortes se repiten")
        return self
