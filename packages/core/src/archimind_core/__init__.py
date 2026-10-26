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
from archimind_core.history import (
    HistoryError,
    Version,
    commit,
    init_repo,
    load_version,
    recent_versions,
)
from archimind_core.inventory import LayerSummary, layer_inventory
from archimind_core.layer_roles import LayerProposal, propose_mapping
from archimind_core.layer_rules import DEFAULT_RULES_PATH, LayerRules, LayerRulesError, load_rules
from archimind_core.mapping import MappingError, proposals_to_mapping
from archimind_core.project import (
    OpenedProject,
    ProjectError,
    active_drawing,
    apply_mapping,
    import_drawing,
    load_existing,
    open_project,
    outputs_dir,
    project_folder,
)
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
from archimind_core.scale import ScaleConfirmation, ScaleError, confirm_scale, rescale
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
    "HistoryError",
    "LayerProposal",
    "LayerRules",
    "LayerRulesError",
    "LayerSummary",
    "MappingError",
    "OpenedProject",
    "OpeningCount",
    "OpeningCounts",
    "ProjectError",
    "QuantitiesError",
    "ScaleConfirmation",
    "ScaleError",
    "SpaceArea",
    "SpaceChange",
    "Version",
    "VersionDiff",
    "WallQuantities",
    "active_drawing",
    "apply_mapping",
    "area_table",
    "build_model",
    "commit",
    "compare_versions",
    "confirm_scale",
    "detect_units",
    "export_area_table_csv",
    "import_drawing",
    "init_repo",
    "layer_inventory",
    "load_build_rules",
    "load_existing",
    "load_rules",
    "load_version",
    "open_project",
    "opening_counts",
    "outputs_dir",
    "project_folder",
    "proposals_to_mapping",
    "propose_mapping",
    "read_drawing",
    "recent_versions",
    "rescale",
    "wall_quantities",
]
