"""Las partidas del modelo y los materiales asignados a ellas y a la carpintería.

Cada partida tiene una clave fija, la que se usa en la tabla `budget_items` de la base para
darle un APU y un material:

- `muro-<espesor>` (p. ej. `muro-0.15`), en m²: una cara de cada muro, su longitud de eje por
  su altura menos los vanos. Si al muro le falta la altura (nivel sin confirmar y sin altura
  propia), la partida queda sin cantidad: no se supone.
- `puerta-<ancho>x<alto>`, `ventana-…` y `vano-…` (p. ej. `puerta-0.90x2.10`), en unidades.
- `piso-<categoría>` (`piso-util`, `piso-balcon`, `piso-circulacion`, `piso-servicio`,
  `piso-tecnico`), en m²: la suma de las áreas de los espacios de esa categoría.
"""

from collections import defaultdict
from dataclasses import dataclass

from archimind_core.heights import missing_heights
from archimind_core.quantities import opening_counts
from archimind_schema import Project, space_area, wall_height, wall_length

from archimind_docs.database import BudgetItem, Material

UNIT_AREA, UNIT_COUNT = "m2", "un"
OPENING_KEYS = {"door": "puerta", "window": "ventana", "void": "vano"}
OPENING_NAMES = {"door": "Puerta", "window": "Ventana", "void": "Vano libre"}
FLOOR_KEYS = {
    "useful": "util",
    "balcony": "balcon",
    "circulation": "circulacion",
    "service": "servicio",
    "technical": "tecnico",
}
FLOOR_NAMES = {
    "useful": "útil",
    "balcony": "balcón",
    "circulation": "circulación",
    "service": "servicio",
    "technical": "técnico",
}
MISSING_HEIGHT = "faltan alturas: pídelas al usuario y aplícalas con definir_alturas"


@dataclass(frozen=True)
class ModelItem:
    """Una partida del modelo. Sin `quantity`, `missing` dice por qué."""

    key: str
    description: str
    unit: str
    quantity: float | None
    missing: str | None = None


@dataclass(frozen=True)
class AssignedMaterial:
    """Un material asignado: a una partida (por `budget_items`) o a la carpintería de un
    bloque. `code` es None en la carpintería; `note` dice si el código no está en la base."""

    source: str
    code: str | None
    description: str
    standard: str | None
    note: str | None = None


def model_items(project: Project) -> list[ModelItem]:
    return _wall_items(project) + _opening_items(project) + _floor_items(project)


def assigned_materials(
    project: Project,
    items: list[ModelItem],
    budget: dict[str, BudgetItem],
    materials: dict[str, Material],
) -> list[AssignedMaterial]:
    assigned = []
    for item in items:
        row = budget.get(item.key)
        if row is None or row.codigo_material is None:
            continue
        material = materials.get(row.codigo_material)
        if material is None:
            assigned.append(
                AssignedMaterial(
                    f"partida {item.key}",
                    row.codigo_material,
                    "",
                    None,
                    "el código no está en la tabla materials",
                )
            )
        else:
            source = f"partida {item.key}"
            assigned.append(
                AssignedMaterial(source, material.codigo, material.descripcion, material.norma)
            )
    for block in project.blocks:
        # Los parámetros de la carpintería de bloques: el perfil lleva su nombre y su material.
        profile = block.parameters.get("profile")
        if not isinstance(profile, dict) or not isinstance(profile.get("material"), str):
            continue
        name = profile.get("name")
        used = sum(1 for o in project.openings if o.block_id == block.id)
        detail = f"perfil {name}, " if isinstance(name, str) else ""
        source = f"carpintería {block.name} ({detail}{used} vanos)"
        assigned.append(AssignedMaterial(source, None, str(profile["material"]), None))
    return assigned


def measure(value: float) -> str:
    """Una medida en metros para una clave: dos decimales, o tres si hacen falta."""
    return f"{value:.2f}" if abs(value * 100 - round(value * 100)) < 1e-6 else f"{value:.3f}"


def _wall_items(project: Project) -> list[ModelItem]:
    without_height = {wall_id for m in missing_heights(project) for wall_id in m.wall_ids}
    areas: dict[str, float] = defaultdict(float)
    missing: set[str] = set()
    for wall in project.walls:
        key = f"muro-{measure(round(wall.thickness, 3))}"
        if wall.id in without_height:
            missing.add(key)
            continue
        height = wall_height(project, wall)
        voids = sum(
            o.width * max(0.0, min(o.height, height - o.sill_height))
            for o in project.openings
            if o.wall_id == wall.id
        )
        areas[key] += wall_length(wall) * height - voids
    items = []
    for key in sorted(set(areas) | missing):
        description = f"Muro de {key.removeprefix('muro-')} m de espesor, una cara"
        if key in missing:
            items.append(ModelItem(key, description, UNIT_AREA, None, MISSING_HEIGHT))
        else:
            items.append(ModelItem(key, description, UNIT_AREA, areas[key]))
    return items


def _opening_items(project: Project) -> list[ModelItem]:
    return [
        ModelItem(
            f"{OPENING_KEYS[c.kind]}-{measure(c.width)}x{measure(c.height)}",
            f"{OPENING_NAMES[c.kind]} de {measure(c.width)} × {measure(c.height)} m",
            UNIT_COUNT,
            float(c.count),
        )
        for c in opening_counts(project).counts
    ]


def _floor_items(project: Project) -> list[ModelItem]:
    areas: dict[str, float] = defaultdict(float)
    for space in project.spaces:
        areas[space.category] += space_area(space)
    return [
        ModelItem(
            f"piso-{FLOOR_KEYS[category]}",
            f"Piso de los espacios de categoría {FLOOR_NAMES[category]}",
            UNIT_AREA,
            areas[category],
        )
        for category in FLOOR_KEYS
        if category in areas
    ]
