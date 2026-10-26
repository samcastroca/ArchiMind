"""Bloques sueltos (crear_bloque): un pedido con sus medidas, sin un vano del modelo.

Lo que el pedido no dice sale del catálogo: el alto, el espesor del muro y el antepecho de
`defaults`, el espesor de hoja del perfil. La mano, la apertura y la cara por defecto son
"left" e "in". Cada supuesto queda en las notas.
"""

from dataclasses import replace
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from archimind_bloques.catalog import TYPE_NAMES, CarpentryType, Catalog
from archimind_bloques.params import Hand, Side
from archimind_bloques.resolve import (
    KINDS,
    OPTION_FIELDS,
    Choice,
    FitError,
    Resolution,
    accepts,
    resolve,
)

OPTION_DEFAULTS: dict[str, tuple[str, str]] = {
    "hand": ("left", 'mano izquierda ("left"), la de por defecto'),
    "swing": ("in", 'abre hacia adentro ("in"), lo de por defecto'),
    "side": ("in", 'corre por la cara de adentro del muro ("in"), lo de por defecto'),
}


class BlockRequest(BaseModel):
    """Las medidas y opciones de un bloque suelto. Solo `width` es obligatorio: lo que el
    usuario no dijo se omite y lo completa el catálogo."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    width: float = Field(gt=0, description="Ancho del vano, en metros (p. ej. 2.40).")
    height: float | None = Field(
        default=None,
        gt=0,
        description="Alto del vano, en metros. Si el usuario no lo dio, omítelo: se usa el del "
        "catálogo.",
    )
    profile: str | None = Field(
        default=None,
        description="Clave de un perfil del catálogo (p. ej. aluminio_pesado; ver "
        "listar_catalogo). Omítela para elegir por material o el primero que calce.",
    )
    material: str | None = Field(
        default=None,
        description="Material pedido (p. ej. aluminio, madera): se usa el primer perfil de ese "
        "material que calce.",
    )
    wall_thickness: float | None = Field(
        default=None, gt=0, description="Espesor del muro, en metros; sin él, el del catálogo."
    )
    sill_height: float | None = Field(
        default=None,
        ge=0,
        description="Solo ventanas: antepecho, en metros; sin él, el del catálogo.",
    )
    leaves: int | None = Field(
        default=None,
        description="Solo sliding_window: número de hojas, de 2 a 4; sin él, las menos que calzan.",
    )
    hand: Hand | None = Field(
        default=None,
        description='Solo swing_door y sliding_door: "left" o "right", mirando desde el lado '
        "hacia el que abre la hoja (EN 12519); en la corrediza, hacia dónde corre. Sin ella, "
        '"left".',
    )
    swing: Side | None = Field(
        default=None,
        description='Solo puertas batientes: "in" abre hacia adentro, "out" hacia afuera. Sin '
        'ella, "in".',
    )
    side: Side | None = Field(
        default=None,
        description='Solo sliding_door: la cara del muro por la que corre, "in" (adentro) u '
        '"out". Sin ella, "in".',
    )
    leaf_thickness: float | None = Field(
        default=None,
        gt=0,
        description="Solo puertas: espesor de la hoja, en metros; sin él, el fondo de hoja del "
        "perfil.",
    )


def create_block(
    carpentry_type: CarpentryType, request: BlockRequest, catalog: Catalog
) -> Resolution:
    given = request.model_dump(exclude_none=True)
    misplaced = [
        name for name in OPTION_FIELDS if name in given and not accepts(carpentry_type, name)
    ]
    if misplaced:
        raise FitError(
            f"{', '.join(misplaced)} no se aplica a una {TYPE_NAMES[carpentry_type]}: quítalo o "
            "elige otro tipo."
        )
    defaults = catalog.defaults
    notes: list[str] = []
    height = request.height
    if height is None:
        is_door = KINDS[carpentry_type] == "door"
        height = defaults.door_height if is_door else defaults.window_height
        notes.append(f"alto de {height:.2f} m, el del catálogo")
    wall = request.wall_thickness
    if wall is None:
        wall = defaults.wall_thickness
        notes.append(f"muro de {wall:.2f} m de espesor, el del catálogo")
    fields: dict[str, Any] = {"width": request.width, "height": height, "wall_thickness": wall}
    if accepts(carpentry_type, "sill_height"):
        fields["sill_height"] = given.get("sill_height", defaults.sill_height)
        if request.sill_height is None:
            notes.append(f"antepecho de {defaults.sill_height:.2f} m, el del catálogo")
    for name, (default, note) in OPTION_DEFAULTS.items():
        if accepts(carpentry_type, name):
            fields[name] = given.get(name, default)
            if name not in given:
                notes.append(note)
    choice = Choice(request.profile, request.material, request.leaves, request.leaf_thickness)
    resolution = resolve([carpentry_type], lambda _: fields, choice, catalog)
    return replace(resolution, notes=(*resolution.notes, *notes))
