"""De un pedido a parámetros válidos: elige el tipo, el perfil y las hojas, y completa lo que falta.

Prueba los tipos en el orden dado y, para cada uno, los perfiles en el orden del catálogo (que es
el orden de preferencia), filtrados por la clave o el material pedidos; en la ventana corrediza
sin número de hojas, de 2 a 4. Devuelve la primera combinación que `params.py` acepta, o un
`FitError` con el motivo de cada intento. Todo número sale del pedido, del vano o del catálogo.
"""

import unicodedata
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, TypeAdapter, ValidationError

from archimind_bloques.catalog import TYPE_NAMES, CarpentryType, Catalog, Profile
from archimind_bloques.params import (
    AwningWindow,
    CarpentryParams,
    DoubleSwingDoor,
    FixedWindow,
    SlidingDoor,
    SlidingWindow,
    SwingDoor,
)

PARAM_CLASSES: dict[CarpentryType, type[BaseModel]] = {
    "swing_door": SwingDoor,
    "double_swing_door": DoubleSwingDoor,
    "sliding_door": SlidingDoor,
    "sliding_window": SlidingWindow,
    "fixed_window": FixedWindow,
    "awning_window": AwningWindow,
}
KINDS: dict[CarpentryType, Literal["door", "window"]] = {
    "swing_door": "door",
    "double_swing_door": "door",
    "sliding_door": "door",
    "sliding_window": "window",
    "fixed_window": "window",
    "awning_window": "window",
}
# Lo que cambia de un tipo a otro; las medidas del vano y el perfil los llevan todos.
OPTION_FIELDS = ("leaves", "hand", "swing", "side", "leaf_thickness", "sill_height")
MAX_REASONS = 8

_PARAMS: TypeAdapter[CarpentryParams] = TypeAdapter(CarpentryParams)


class FitError(Exception):
    """No hay carpintería que cumpla el pedido; el mensaje está pensado para el usuario."""


@dataclass(frozen=True)
class Choice:
    """Lo que el pedido fija del perfil y de las hojas; None deja elegir."""

    profile: str | None = None
    material: str | None = None
    leaves: int | None = None
    leaf_thickness: float | None = None


@dataclass(frozen=True)
class Resolution:
    params: CarpentryParams
    profile_key: str
    notes: tuple[str, ...]  # lo que se eligió o se supuso, en frases para el usuario


def accepts(carpentry_type: CarpentryType, field: str) -> bool:
    return field in PARAM_CLASSES[carpentry_type].model_fields


def resolve(
    types: Sequence[CarpentryType],
    fields: Callable[[CarpentryType], dict[str, Any]],
    choice: Choice,
    catalog: Catalog,
) -> Resolution:
    """`fields(tipo)` da las medidas y opciones ya decididas para ese tipo; aquí se añaden el
    perfil, el espesor de hoja y las hojas."""
    reasons: list[str] = []
    for carpentry_type in types:
        profiles = list(_profiles(catalog, carpentry_type, choice))
        if not profiles:
            reasons.append(f"ningún perfil{_material(choice)} admite {TYPE_NAMES[carpentry_type]}")
        for key, profile in profiles:
            for leaves in _leaf_counts(carpentry_type, choice):
                data = {"type": carpentry_type, "profile": profile, **fields(carpentry_type)}
                if leaves is not None:
                    data["leaves"] = leaves
                if accepts(carpentry_type, "leaf_thickness"):
                    thickness = choice.leaf_thickness
                    data["leaf_thickness"] = profile.sash.depth if thickness is None else thickness
                try:
                    params = _PARAMS.validate_python(data)
                except ValidationError as exc:
                    reasons.append(f"{_attempt(carpentry_type, profile, leaves)}: {_reason(exc)}")
                    continue
                return Resolution(params, key, tuple(_notes(params, key, choice)))
    unique = list(dict.fromkeys(reasons))
    if len(unique) > MAX_REASONS:
        unique = [*unique[: MAX_REASONS - 1], f"… y {len(unique) - MAX_REASONS + 1} intentos más"]
    raise FitError(
        "Ninguna carpintería del catálogo calza:\n" + "\n".join(f"- {r}" for r in unique)
    )


def _profiles(
    catalog: Catalog, carpentry_type: CarpentryType, choice: Choice
) -> Iterator[tuple[str, Profile]]:
    if choice.profile is not None:
        # El perfil pedido se prueba aunque no admita el tipo: params.py explica por qué no.
        yield choice.profile, catalog.profile(choice.profile)
        return
    if choice.material is not None:
        materials = {plain(p.material) for p in catalog.profiles.values()}
        if plain(choice.material) not in materials:
            raise FitError(
                f"El catálogo no tiene perfiles de {choice.material}. Los materiales disponibles "
                f"son: {', '.join(sorted(materials))}."
            )
    for key, profile in catalog.profiles.items():
        if carpentry_type not in profile.types:
            continue
        if choice.material is None or plain(profile.material) == plain(choice.material):
            yield key, profile


def _leaf_counts(carpentry_type: CarpentryType, choice: Choice) -> list[int | None]:
    if carpentry_type != "sliding_window":
        return [None]
    return [choice.leaves] if choice.leaves is not None else [2, 3, 4]


def _notes(params: CarpentryParams, key: str, choice: Choice) -> Iterator[str]:
    profile = params.profile
    if choice.profile is None:
        among = f"de {choice.material}" if choice.material is not None else "del catálogo"
        yield f"perfil {key} ({profile.name}): el primero {among} que admite el tipo y calza"
    if isinstance(params, SlidingWindow) and choice.leaves is None:
        yield f"{params.leaves} hojas: las menos que calzan con ese perfil"
    if accepts(params.type, "leaf_thickness") and choice.leaf_thickness is None:
        yield f"hoja de {profile.sash.depth:.3f} m de espesor: el fondo de hoja del perfil"


def _attempt(carpentry_type: CarpentryType, profile: Profile, leaves: int | None) -> str:
    leaves_text = f" de {leaves} hojas" if leaves is not None else ""
    return f"{TYPE_NAMES[carpentry_type]}{leaves_text} con «{profile.name}»"


def _reason(error: ValidationError) -> str:
    """El mensaje de params.py sin el prefijo de pydantic, o el campo y su problema."""
    first = error.errors()[0]
    message = str(first["msg"]).removeprefix("Value error, ")
    location = ".".join(str(part) for part in first["loc"][1:])  # sin el tipo de la unión
    return f"{location}: {message}" if location else message


def _material(choice: Choice) -> str:
    return f" de {choice.material}" if choice.material is not None else ""


def plain(text: str) -> str:
    """Sin mayúsculas ni tildes: «Aluminio» y «aluminio» son el mismo material."""
    decomposed = unicodedata.normalize("NFD", text.strip().casefold())
    return "".join(c for c in decomposed if not unicodedata.combining(c))
