"""Servidor MCP archimind-core: único escritor del modelo semántico de un proyecto."""

from archimind_core.build import BuildResult, build_model
from archimind_core.build_rules import (
    DEFAULT_BUILD_RULES_PATH,
    BuildRules,
    BuildRulesError,
    load_build_rules,
)
from archimind_core.compare import AREA_CHANGE_TOL, SpaceChange, VersionDiff, compare_versions
from archimind_core.drawing import Drawing, DrawingError, read_drawing
from archimind_core.inventory import LayerSummary, layer_inventory
from archimind_core.layer_roles import LayerProposal, propose_mapping
from archimind_core.layer_rules import DEFAULT_RULES_PATH, LayerRules, LayerRulesError, load_rules
from archimind_core.mapping import MappingError, apply_mapping, proposals_to_mapping
from archimind_core.quantities import (
    PRELIMINARY_LABEL,
    AreaTable,
    OpeningCount,
    OpeningCounts,
    QuantitiesError,
    SpaceArea,
    WallQuantities,
    area_table,
    export_area_table_csv,
    opening_counts,
    wall_quantities,
)
from archimind_core.units import DrawingUnits, detect_units

__all__ = [
    "AREA_CHANGE_TOL",
    "DEFAULT_BUILD_RULES_PATH",
    "DEFAULT_RULES_PATH",
    "PRELIMINARY_LABEL",
    "AreaTable",
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
    "OpeningCount",
    "OpeningCounts",
    "QuantitiesError",
    "SpaceArea",
    "SpaceChange",
    "VersionDiff",
    "WallQuantities",
    "apply_mapping",
    "area_table",
    "build_model",
    "compare_versions",
    "detect_units",
    "export_area_table_csv",
    "layer_inventory",
    "load_build_rules",
    "load_rules",
    "opening_counts",
    "proposals_to_mapping",
    "propose_mapping",
    "read_drawing",
    "wall_quantities",
]
