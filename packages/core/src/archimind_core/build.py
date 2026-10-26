"""Reconstrucción del modelo semántico desde un plano y su mapeo de capas."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from archimind_schema import Level, Problem, Project, Wall, new_id, validate
from shapely import unary_union

from archimind_core.build_rules import BuildRules, load_build_rules
from archimind_core.extract import extract
from archimind_core.layer_rules import LayerRules, load_rules
from archimind_core.mapping import validate_roles
from archimind_core.openings import place_openings
from archimind_core.spaces import place_spaces
from archimind_core.walls import Gap, reconstruct_walls

if TYPE_CHECKING:
    from archimind_core.drawing import Drawing


@dataclass(frozen=True)
class BuildResult:
    """El modelo reconstruido y todos sus problemas: los avisos de la reconstrucción y los de
    `validate`."""

    project: Project
    problems: list[Problem]


def build_model(
    drawing: "Drawing",
    mapping: Mapping[str, str],
    rules: BuildRules | None = None,
    layer_rules: LayerRules | None = None,
    base: Project | None = None,
) -> BuildResult:
    """Muros, vanos y espacios del plano según el rol de cada capa. No escribe nada.

    Lo que el plano no transmite (alturas, categoría de los espacios, el nivel) sale de
    `build_rules.yaml` y se declara en el aviso `valores_por_defecto`.

    Con `base`, el modelo reconstruido conserva su identidad, sus fuentes y sus contadores de
    IDs: los elementos nuevos nunca reutilizan un ID retirado.
    """
    validate_roles(mapping)
    rules = rules or load_build_rules()
    content = extract(drawing, mapping, layer_rules or load_rules())
    if base is None:
        project = Project(
            id=drawing.path.stem,
            name=drawing.path.stem,
            scale_confirmed=drawing.units.confirmed,
            source_files=[drawing.path.name],
        )
    else:
        project = Project(
            id=base.id,
            name=base.name,
            scale_confirmed=drawing.units.confirmed,
            source_files=list(base.source_files),
            next_ids=dict(base.next_ids),
        )
    level = Level(
        id=new_id(project, "niv"),
        name=rules.level.name,
        elevation=rules.level.elevation,
        default_height=rules.level.default_height,
    )
    project.levels.append(level)

    warnings: list[Problem] = []
    if not any(role == "walls" for role in mapping.values()):
        warnings.append(_warning("sin_capa_de_muros", "ninguna capa tiene el rol de muros"))
    for layer in sorted(content.mixed_layers):
        warnings.append(
            _warning(
                "capa_mixta_ignorada",
                f"la capa {layer!r} mezcla roles y no se usa: asignarle un rol para leerla",
            )
        )

    symbols = unary_union([*content.symbols["door"], *content.symbols["window"]])
    reconstructed = reconstruct_walls(content, symbols, rules)
    warnings += reconstructed.warnings
    gaps: dict[str, list[Gap]] = {}
    for draft in reconstructed.walls:
        wall = Wall(
            id=new_id(project, "muro"),
            level_id=level.id,
            axis=[draft.start, draft.end],
            thickness=draft.thickness,
            source_layer=draft.layer,
        )
        project.walls.append(wall)
        gaps[wall.id] = draft.gaps
    warnings += place_openings(project, gaps, content, rules)
    warnings += place_spaces(project, reconstructed.material, content.labels, rules)
    warnings += _defaults(project, rules)
    # Revalida el conjunto (contadores de IDs incluidos); los roles ya se comprobaron.
    project = Project.model_validate({**project.model_dump(), "layer_mapping": dict(mapping)})
    return BuildResult(project, [*warnings, *validate(project)])


def _defaults(project: Project, rules: BuildRules) -> list[Problem]:
    level = rules.level
    used = [
        f"nivel «{level.name}» a {level.elevation:.2f} m con altura {level.default_height:.2f} m"
    ]
    for kind in sorted({o.kind for o in project.openings}):
        defaults = rules.openings[kind]
        used.append(
            f"vanos {kind}: altura {defaults.height:.2f} m, antepecho {defaults.sill_height:.2f} m"
        )
    if project.spaces:
        used.append(f"categoría de los espacios: {rules.space_category}")
    return [
        _warning(
            "valores_por_defecto",
            "el plano no transmite estos datos y se usan los valores por defecto: "
            + "; ".join(used),
        )
    ]


def _warning(code: str, message: str) -> Problem:
    return Problem(code=code, severity="warning", ids=[], message=message)
