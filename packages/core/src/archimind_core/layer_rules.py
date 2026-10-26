"""Reglas configurables para proponer el rol de cada capa (config/layer_rules.yaml)."""

import re
import unicodedata
from pathlib import Path

import yaml
from archimind_schema import LayerRole
from pydantic import BaseModel, ConfigDict, Field, ValidationError

# Fuera de src/: sirve en el workspace editable, no dentro de un wheel.
DEFAULT_RULES_PATH = Path(__file__).resolve().parents[2] / "config" / "layer_rules.yaml"


class LayerRulesError(Exception):
    """El archivo de reglas no existe o no es válido; el mensaje está pensado para el usuario."""


class _Rules(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Confidence(_Rules):
    agree: float = Field(ge=0, le=1)
    name_only: float = Field(ge=0, le=1)
    geometry_base: float = Field(ge=0, le=1)
    geometry_gain: float = Field(ge=0, le=1)
    conflict: float = Field(ge=0, le=1)
    mixed: float = Field(ge=0, le=1)
    none: float = Field(ge=0, le=1)


class LayerRules(_Rules):
    name_patterns: dict[LayerRole, list[str]]
    block_patterns: dict[LayerRole, list[str]]
    length_tolerance_m: float = Field(gt=0)
    angle_tolerance_deg: float = Field(gt=0)
    door_arc_span_deg: float = Field(gt=0, lt=360)
    door_arc_tolerance_deg: float = Field(gt=0)
    mixed_min_share: float = Field(gt=0, le=0.5)
    confidence: Confidence

    def name_matches(self, name: str) -> dict[LayerRole, str]:
        """Roles cuyo patrón coincide con alguna palabra del nombre de capa, con la palabra."""
        return _matches(self.name_patterns, name)

    def block_role(self, block_name: str) -> LayerRole | None:
        """Primer rol cuyo patrón coincide con el nombre del bloque."""
        return next(iter(_matches(self.block_patterns, block_name)), None)


def _words(name: str) -> list[str]:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return [word for word in re.split(r"[^A-Z0-9]+", ascii_name.upper()) if word]


def _matches(patterns: dict[LayerRole, list[str]], name: str) -> dict[LayerRole, str]:
    words = _words(name)
    found: dict[LayerRole, str] = {}
    for role, keywords in patterns.items():
        for keyword in keywords:
            word = next((w for w in words if w.startswith(keyword.upper())), None)
            if word is not None:
                found[role] = word
                break
    return found


def load_rules(path: str | Path = DEFAULT_RULES_PATH) -> LayerRules:
    source = Path(path)
    try:
        data = yaml.safe_load(source.read_text(encoding="utf-8"))
    except OSError as exc:
        raise LayerRulesError(f"No se pudo leer el archivo de reglas {source}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise LayerRulesError(f"{source.name} no es un YAML válido: {exc}") from exc
    try:
        return LayerRules.model_validate(data)
    except ValidationError as exc:
        raise LayerRulesError(f"{source.name} tiene reglas inválidas: {exc}") from exc
