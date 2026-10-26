"""Servidor MCP archimind-core: único escritor del modelo semántico de un proyecto."""

from archimind_core.drawing import Drawing, DrawingError, read_drawing
from archimind_core.inventory import LayerSummary, layer_inventory
from archimind_core.layer_roles import LayerProposal, propose_mapping
from archimind_core.layer_rules import DEFAULT_RULES_PATH, LayerRules, LayerRulesError, load_rules
from archimind_core.mapping import MappingError, apply_mapping, proposals_to_mapping
from archimind_core.units import DrawingUnits, detect_units

__all__ = [
    "DEFAULT_RULES_PATH",
    "Drawing",
    "DrawingError",
    "DrawingUnits",
    "LayerProposal",
    "LayerRules",
    "LayerRulesError",
    "LayerSummary",
    "MappingError",
    "apply_mapping",
    "detect_units",
    "layer_inventory",
    "load_rules",
    "proposals_to_mapping",
    "propose_mapping",
    "read_drawing",
]
