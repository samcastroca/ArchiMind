"""fit_to_opening: la carpintería que calza en un vano del modelo.

El ancho, el alto y el antepecho son los del vano y el espesor, el de su muro: las medidas se
conservan tal cual. Las preferencias fijan el tipo, el perfil, las hojas, la mano o la apertura;
lo demás se elige y queda explicado en las notas:

- el tipo: puerta batiente y si no calza, batiente doble; ventana corrediza con las menos hojas
  que calcen, si no proyectante y si no fija;
- el lado de adentro y el recinto hacia el que abre (`site.locate`);
- la mano: las bisagras de la batiente en el borde del vano más cercano a un muro que corta la
  cara hacia la que abre (o al extremo del muro), para que la hoja abierta quede contra él; la
  corrediza corre hacia el lado con más muro libre.
"""

from dataclasses import dataclass
from typing import Any

from archimind_schema import AxisSide, Opening, Project, Wall
from pydantic import BaseModel, ConfigDict, Field

from archimind_bloques.catalog import TYPE_NAMES, CarpentryType, Catalog
from archimind_bloques.params import CarpentryParams, Hand, Side, side_sign
from archimind_bloques.resolve import KINDS, Choice, FitError, accepts, resolve
from archimind_bloques.site import Site, free_runs, locate

DEFAULT_TYPES: dict[str, tuple[CarpentryType, ...]] = {
    "door": ("swing_door", "double_swing_door"),
    "window": ("sliding_window", "awning_window", "fixed_window"),
}
PRELIMINARY_NOTE = "PRELIMINAR: escala sin confirmar; las medidas del vano pueden cambiar"
KIND_NAMES = {"door": "una puerta", "window": "una ventana", "void": "un vano sin tipo"}


class Preferences(BaseModel):
    """Lo que el usuario pidió para un vano. Todo es opcional: las medidas salen del vano."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    type: CarpentryType | None = Field(
        default=None,
        description="Tipo de carpintería; sin él, el habitual para el vano (batiente en puertas, "
        "corrediza en ventanas). Obligatorio en un vano sin tipo.",
    )
    profile: str | None = Field(
        default=None, description="Clave de un perfil del catálogo (p. ej. madera)."
    )
    material: str | None = Field(
        default=None,
        description="Material (p. ej. aluminio): el primer perfil de ese material que calce.",
    )
    leaves: int | None = Field(
        default=None, description="Solo sliding_window: número de hojas, de 2 a 4."
    )
    hand: Hand | None = Field(
        default=None,
        description='Solo swing_door y sliding_door: "left" o "right" (EN 12519). Sin ella, las '
        "bisagras van hacia el muro más cercano y la corrediza corre hacia el lado con más muro.",
    )
    swing: Side | None = Field(
        default=None,
        description='Solo puertas batientes: "in" abre hacia el recinto de adentro (por defecto), '
        '"out" hacia el otro lado.',
    )
    side: Side | None = Field(
        default=None,
        description='Solo sliding_door: cara del muro por la que corre, "in" (por defecto) u '
        '"out".',
    )
    leaf_thickness: float | None = Field(
        default=None, gt=0, description="Solo puertas: espesor de la hoja, en metros."
    )
    opens_into: str | None = Field(
        default=None,
        description="ID del recinto (esp-) que queda adentro: hacia donde abre la puerta. Sin él, "
        "el interior en un muro exterior y, entre dos recintos, el que no es circulación o el más "
        "pequeño.",
    )


@dataclass(frozen=True)
class Fit:
    opening_id: str
    params: CarpentryParams
    profile_key: str
    site: Site
    notes: tuple[str, ...]


def fit_to_opening(
    project: Project, opening_id: str, preferences: Preferences, catalog: Catalog
) -> Fit:
    opening = _opening(project, opening_id)
    wall = _wall(project, opening)
    types = _candidates(opening, preferences)
    site = locate(project, wall, opening, preferences.opens_into)
    given = preferences.model_dump(exclude_none=True)
    hands = {
        t: _default_hand(t, project, wall, opening, site, given)
        for t in types
        if accepts(t, "hand")
    }

    def fields(carpentry_type: CarpentryType) -> dict[str, Any]:
        data: dict[str, Any] = {
            "width": opening.width,
            "height": opening.height,
            "wall_thickness": wall.thickness,
        }
        if accepts(carpentry_type, "sill_height"):
            data["sill_height"] = opening.sill_height
        for name in ("swing", "side"):
            if accepts(carpentry_type, name):
                data[name] = given.get(name, "in")
        if accepts(carpentry_type, "hand"):
            data["hand"] = given.get("hand", hands[carpentry_type][0])
        return data

    choice = Choice(
        preferences.profile, preferences.material, preferences.leaves, preferences.leaf_thickness
    )
    resolution = resolve(types, fields, choice, catalog)
    notes = [site.note, *resolution.notes]
    chosen = resolution.params.type
    if chosen in hands and preferences.hand is None:
        notes.append(hands[chosen][1])
    if not project.scale_confirmed:
        notes.append(PRELIMINARY_NOTE)
    return Fit(opening.id, resolution.params, resolution.profile_key, site, tuple(notes))


def _opening(project: Project, opening_id: str) -> Opening:
    for opening in project.openings:
        if opening.id == opening_id:
            return opening
    raise FitError(
        f"No existe el vano {opening_id}: los vanos los lista listar_modelo(que='vanos') de core."
    )


def _wall(project: Project, opening: Opening) -> Wall:
    for wall in project.walls:
        if wall.id == opening.wall_id:
            return wall
    raise FitError(
        f"El vano {opening.id} apunta al muro inexistente {opening.wall_id}: revisa el modelo con "
        "validar_modelo de core."
    )


def _candidates(opening: Opening, preferences: Preferences) -> list[CarpentryType]:
    if preferences.type is not None:
        kind = KINDS[preferences.type]
        if opening.kind not in (kind, "void"):
            raise FitError(
                f"{opening.id} es {KIND_NAMES[opening.kind]} y {TYPE_NAMES[preferences.type]} es "
                f"para {KIND_NAMES[kind]}."
            )
        types: tuple[CarpentryType, ...] = (preferences.type,)
    elif opening.kind == "void":
        raise FitError(
            f"{opening.id} es un vano sin tipo: indica type (p. ej. swing_door o sliding_window)."
        )
    else:
        types = DEFAULT_TYPES[opening.kind]
    options = ("leaves", "hand", "swing", "side", "leaf_thickness")
    given = [name for name in options if getattr(preferences, name) is not None]
    fitting = [t for t in types if all(accepts(t, name) for name in given)]
    if not fitting:
        names = ", ".join(TYPE_NAMES[t] for t in types)
        raise FitError(
            f"{', '.join(given)} no se aplica a {names}: quítalo o indica otro type para "
            f"{opening.id}."
        )
    return fitting


def _default_hand(
    carpentry_type: CarpentryType,
    project: Project,
    wall: Wall,
    opening: Opening,
    site: Site,
    given: dict[str, Any],
) -> tuple[Hand, str]:
    """La mano y su explicación, mirando la cara del muro hacia la que abre o por la que corre
    la hoja: la batiente lleva las bisagras hacia el muro más cercano; la corrediza corre hacia
    el lado con más muro libre."""
    sliding = carpentry_type == "sliding_door"
    face: Side = given.get("side", "in") if sliding else given.get("swing", "in")
    leaf_side = site.side if side_sign(face) > 0 else _OPPOSITE[site.side]
    before, after = free_runs(project, wall, opening, leaf_side)
    if sliding:
        toward_end = after.length >= before.length  # el final del eje
    else:
        toward_end = after.length < before.length
    run = after if toward_end else before
    # El +x del bloque va hacia el final del eje con adentro a la izquierda, al revés a la derecha.
    toward_plus_x = toward_end == (site.side == "left")
    hand: Hand = "left" if (1 if toward_plus_x else -1) * side_sign(face) > 0 else "right"
    target = run.wall_id or f"el {'final' if toward_end else 'inicio'} de {wall.id}"
    if sliding:
        note = f"corre hacia {target}, con {run.length:.2f} m de muro libre"
    else:
        note = (
            f"bisagras hacia {target}, a {run.length:.2f} m: la hoja abierta queda contra el muro"
        )
    hand_name = "izquierda" if hand == "left" else "derecha"
    return hand, f'mano {hand_name} ("{hand}"): {note}'


_OPPOSITE: dict[AxisSide, AxisSide] = {"left": "right", "right": "left"}
