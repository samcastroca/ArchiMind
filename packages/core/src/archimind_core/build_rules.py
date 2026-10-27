"""Umbrales y valores por defecto de la reconstrucción del modelo (config/build_rules.yaml)."""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

# Fuera de src/: sirve en el workspace editable, no dentro de un wheel.
DEFAULT_BUILD_RULES_PATH = Path(__file__).resolve().parents[2] / "config" / "build_rules.yaml"

OpeningKind = Literal["door", "window", "void"]
SpaceCategory = Literal["useful", "balcony", "circulation", "service", "technical"]


class BuildRulesError(Exception):
    """El archivo de reglas no existe o no es válido; el mensaje está pensado para el usuario."""


class _Rules(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class LevelDefaults(_Rules):
    name: str
    elevation: float
    default_height: float = Field(gt=0)


class OpeningDefaults(_Rules):
    height: float = Field(gt=0)
    sill_height: float = Field(ge=0)


class BuildRules(_Rules):
    min_thickness_m: float = Field(gt=0)
    max_thickness_m: float = Field(gt=0)
    material_share: float = Field(gt=0, le=1)
    joint_slack_m: float = Field(ge=0)
    max_void_width_m: float = Field(gt=0)
    symbol_search_m: float = Field(ge=0)
    min_space_area_m2: float = Field(ge=0)
    view_gap_m: float = Field(gt=0)
    level: LevelDefaults
    openings: dict[OpeningKind, OpeningDefaults]
    space_category: SpaceCategory


def load_build_rules(path: str | Path = DEFAULT_BUILD_RULES_PATH) -> BuildRules:
    source = Path(path)
    try:
        data = yaml.safe_load(source.read_text(encoding="utf-8"))
    except OSError as exc:
        raise BuildRulesError(f"No se pudo leer el archivo de reglas {source}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise BuildRulesError(f"{source.name} no es un YAML válido: {exc}") from exc
    try:
        rules = BuildRules.model_validate(data)
    except ValidationError as exc:
        raise BuildRulesError(f"{source.name} tiene reglas inválidas: {exc}") from exc
    missing = {"door", "window", "void"} - set(rules.openings)
    if missing:
        raise BuildRulesError(
            f"{source.name}: faltan los valores por defecto de los vanos {sorted(missing)}"
        )
    return rules
