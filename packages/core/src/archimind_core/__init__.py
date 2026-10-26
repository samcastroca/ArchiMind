"""Servidor MCP archimind-core: único escritor del modelo semántico de un proyecto."""

from archimind_core.build import BuildResult, build_model
from archimind_core.build_rules import (
    DEFAULT_BUILD_RULES_PATH,
    BuildRules,
    BuildRulesError,
    load_build_rules,
)
from archimind_core.drawing import Drawing, DrawingError, read_drawing
from archimind_core.inventory import LayerSummary, layer_inventory
from archimind_core.layer_roles import LayerProposal, propose_mapping
from archimind_core.layer_rules import DEFAULT_RULES_PATH, LayerRules, LayerRulesError, load_rules
from archimind_core.mapping import MappingError, apply_mapping, proposals_to_mapping
from archimind_core.units import DrawingUnits, detect_units

__all__ = [
    "DEFAULT_BUILD_RULES_PATH",
    "DEFAULT_RULES_PATH",
    "BuildResult",
    "BuildRules",
    "BuildRulesError",
    "Drawing",
    "DrawingError",
    "DrawingUnits",
    "LayerProposal",
    "LayerRules",
    "LayerRulesError",
    "LayerSummary",
    "MappingError",
    "apply_mapping",
    "build_model",
    "detect_units",
    "layer_inventory",
    "load_build_rules",
    "load_rules",
    "proposals_to_mapping",
    "propose_mapping",
    "read_drawing",
]
