"""Parámetros de cada tipo de carpintería, validados contra su perfil del catálogo.

Medidas en metros. `width` y `height` son los del vano; `wall_thickness`, el espesor del muro
donde va. Cada modelo da el ancho y el alto de su hoja (`leaf_width`, `leaf_height`): son las
únicas fórmulas de las hojas, y las usan tanto la validación como los generadores.

- `hand`, la mano: mirando desde el lado hacia el que se mueve la hoja, bisagras a la izquierda
  es "left" (EN 12519). En la puerta corrediza, "left" es que corre hacia la izquierda vista
  desde la cara por la que corre.
- `swing`: hacia dónde abre la batiente, "in" (adentro, +y del bloque) u "out" (afuera, −y).
- `side`: la cara del muro por la que corre la puerta corrediza, "in" u "out".
"""

import math
from abc import abstractmethod
from typing import Annotated, ClassVar, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from archimind_bloques.catalog import TYPE_NAMES, CarpentryType, Profile

# Margen numérico de las comparaciones con los límites; no es una tolerancia geométrica.
EPS = 1e-9

Hand = Literal["left", "right"]
Side = Literal["in", "out"]


def side_sign(side: Side) -> int:
    """+1 adentro (+y del bloque), −1 afuera."""
    return 1 if side == "in" else -1


def hand_sign(hand: Hand, side: Side) -> int:
    """Hacia qué extremo del vano queda la izquierda de quien mira desde `side`: +1 es x = ancho.

    Desde adentro (+y) se mira hacia −y y la izquierda es +x; desde afuera, al revés."""
    return (1 if hand == "left" else -1) * side_sign(side)


class _Params(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    type: CarpentryType
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    wall_thickness: float = Field(gt=0)
    profile: Profile

    leaf_noun: ClassVar[str] = "la hoja"

    @property
    def leaf_count(self) -> int:
        return 1

    @property
    @abstractmethod
    def leaf_width(self) -> float: ...

    @property
    @abstractmethod
    def leaf_height(self) -> float: ...

    def description(self) -> str:
        return f"una {TYPE_NAMES[self.type]}"

    @model_validator(mode="after")
    def _fits(self) -> Self:
        profile = self.profile
        if self.type not in profile.types:
            accepted = ", ".join(TYPE_NAMES[t] for t in profile.types)
            raise ValueError(
                f"El perfil «{profile.name}» no admite {TYPE_NAMES[self.type]}; admite: {accepted}."
            )
        if profile.frame.depth > self.wall_thickness + EPS:
            raise ValueError(
                f"El marco del perfil «{profile.name}» tiene {_metres(profile.frame.depth)} de "
                f"fondo y no cabe en un muro de {_metres(self.wall_thickness)}."
            )
        self._check_type_rules()
        self._check_leaf_width()
        self._check_leaf_height()
        return self

    def _check_type_rules(self) -> None:
        """Reglas propias de cada tipo, antes de las medidas de la hoja."""

    def _width_hint(self, too_wide: bool) -> str:
        return ""

    def _check_leaf_width(self) -> None:
        limits, leaf = self.profile.sash_width, self.leaf_width
        what = _capitalized(self.description())
        # El ancho de la hoja crece 1/leaf_count por cada metro de vano.
        if leaf < limits.min - EPS:
            minimum = _ceil_mm(self.width + (limits.min - leaf) * self.leaf_count)
            raise ValueError(
                f"{what} no cabe en {_metres(self.width)} con el perfil «{self.profile.name}»: "
                f"{self.leaf_noun} mediría {_metres(leaf)} de ancho y el perfil exige al menos "
                f"{_metres(limits.min)}. El ancho mínimo es {_metres(minimum)}."
                + self._width_hint(too_wide=False)
            )
        if leaf > limits.max + EPS:
            maximum = _floor_mm(self.width - (leaf - limits.max) * self.leaf_count)
            raise ValueError(
                f"{what} de {_metres(self.width)} excede el perfil «{self.profile.name}»: "
                f"{self.leaf_noun} mediría {_metres(leaf)} de ancho y el perfil admite como máximo "
                f"{_metres(limits.max)}. El ancho máximo es {_metres(maximum)}."
                + self._width_hint(too_wide=True)
            )

    def _check_leaf_height(self) -> None:
        limits, leaf = self.profile.sash_height, self.leaf_height
        what = _capitalized(self.description())
        # El alto de la hoja crece lo mismo que el del vano.
        if leaf < limits.min - EPS:
            raise ValueError(
                f"{what} de {_metres(self.height)} de alto no cabe con el perfil "
                f"«{self.profile.name}»: {self.leaf_noun} mediría {_metres(leaf)} de alto y el "
                f"perfil exige al menos {_metres(limits.min)}. El alto mínimo es "
                f"{_metres(_ceil_mm(self.height + limits.min - leaf))}."
            )
        if leaf > limits.max + EPS:
            raise ValueError(
                f"{what} de {_metres(self.height)} de alto excede el perfil "
                f"«{self.profile.name}»: {self.leaf_noun} mediría {_metres(leaf)} de alto y el "
                f"perfil admite como máximo {_metres(limits.max)}. El alto máximo es "
                f"{_metres(_floor_mm(self.height - (leaf - limits.max)))}."
            )


class _Door(_Params):
    leaf_thickness: float = Field(gt=0)


class _SwingingDoor(_Door):
    swing: Side

    @property
    def leaf_height(self) -> float:
        return self.height - self.profile.frame.face

    def _check_type_rules(self) -> None:
        depth = self.profile.frame.depth
        if self.leaf_thickness > depth + EPS:
            raise ValueError(
                f"La hoja de {_metres(self.leaf_thickness)} de espesor no cabe en el marco del "
                f"perfil «{self.profile.name}», de {_metres(depth)} de fondo."
            )


class SwingDoor(_SwingingDoor):
    """Puerta batiente de una hoja: la hoja llena el vano libre entre las jambas del marco."""

    type: Literal["swing_door"] = "swing_door"
    hand: Hand

    @property
    def leaf_width(self) -> float:
        return self.width - 2 * self.profile.frame.face


class DoubleSwingDoor(_SwingingDoor):
    """Puerta batiente de dos hojas iguales, con las bisagras en las dos jambas."""

    type: Literal["double_swing_door"] = "double_swing_door"

    leaf_noun: ClassVar[str] = "cada hoja"

    @property
    def leaf_count(self) -> int:
        return 2

    @property
    def leaf_width(self) -> float:
        return (self.width - 2 * self.profile.frame.face) / 2


class SlidingDoor(_Door):
    """Puerta corrediza sobrepuesta a una cara del muro: la hoja sobrepasa el vano libre en el
    traslape del perfil a cada lado y por arriba."""

    type: Literal["sliding_door"] = "sliding_door"
    hand: Hand
    side: Side

    @property
    def leaf_width(self) -> float:
        return self.width - 2 * self.profile.frame.face + 2 * self.profile.overlap

    @property
    def leaf_height(self) -> float:
        return self.height - self.profile.frame.face + self.profile.overlap


class _Window(_Params):
    sill_height: float = Field(ge=0)

    @property
    def leaf_height(self) -> float:
        return self.height - 2 * self.profile.frame.face


class SlidingWindow(_Window):
    """Ventana corrediza de 2 a 4 hojas iguales.

    Con 2 hojas hay 2 rieles y un traslape; con 3, 3 rieles y dos traslapes; con 4, 2 rieles:
    las dos hojas laterales van en el riel exterior y las dos centrales en el interior, se
    encuentran a tope en el centro y traslapan con las laterales.
    """

    type: Literal["sliding_window"] = "sliding_window"
    leaves: int

    leaf_noun: ClassVar[str] = "cada hoja"

    @property
    def leaf_count(self) -> int:
        return self.leaves

    @property
    def rails(self) -> int:
        return 3 if self.leaves == 3 else 2

    @property
    def overlaps(self) -> int:
        return 1 if self.leaves == 2 else 2

    @property
    def leaf_rails(self) -> tuple[int, ...]:
        """Riel de cada hoja, de x = 0 a x = ancho; el riel 0 es el exterior."""
        return {2: (0, 1), 3: (0, 1, 2), 4: (0, 1, 1, 0)}[self.leaves]

    @property
    def leaf_width(self) -> float:
        clear = self.width - 2 * self.profile.frame.face
        return (clear + self.overlaps * self.profile.overlap) / self.leaves

    def description(self) -> str:
        return f"una ventana corrediza de {self.leaves} hojas"

    def _check_type_rules(self) -> None:
        if self.leaves not in (2, 3, 4):
            raise ValueError(
                f"Una ventana corrediza tiene de 2 a 4 hojas; se pidieron {self.leaves}."
            )
        rail, depth = self.profile.sash.depth, self.profile.frame.depth
        if self.rails * rail > depth + EPS:
            raise ValueError(
                f"Una ventana corrediza de {self.leaves} hojas necesita {self.rails} rieles de "
                f"{_metres(rail)} ({_metres(self.rails * rail)}) y el marco del perfil "
                f"«{self.profile.name}» tiene {_metres(depth)} de fondo. Usa 2 o 4 hojas u otro "
                "perfil."
            )

    def _width_hint(self, too_wide: bool) -> str:
        if too_wide and self.leaves < 4:
            return " También puedes usar más hojas."
        if not too_wide and self.leaves > 2:
            return " También puedes usar menos hojas."
        return ""


class FixedWindow(_Window):
    """Ventana fija: un paño de vidrio en el marco, sin hoja."""

    type: Literal["fixed_window"] = "fixed_window"

    leaf_noun: ClassVar[str] = "el paño"

    @property
    def leaf_width(self) -> float:
        return self.width - 2 * self.profile.frame.face


class AwningWindow(_Window):
    """Ventana proyectante: una hoja con bisagra arriba que abre hacia afuera."""

    type: Literal["awning_window"] = "awning_window"

    @property
    def leaf_width(self) -> float:
        return self.width - 2 * self.profile.frame.face


CarpentryParams = Annotated[
    SwingDoor | DoubleSwingDoor | SlidingDoor | SlidingWindow | FixedWindow | AwningWindow,
    Field(discriminator="type"),
]


def _metres(value: float) -> str:
    """Una medida para los mensajes, al milímetro: 0.6 → «0.60 m», 0.145 → «0.145 m»."""
    text = f"{value:.3f}"
    return f"{text[:-1] if text.endswith('0') else text} m"


def _capitalized(text: str) -> str:
    return text[:1].upper() + text[1:]


def _ceil_mm(value: float) -> float:
    return math.ceil(value * 1000 - 1e-6) / 1000


def _floor_mm(value: float) -> float:
    return math.floor(value * 1000 + 1e-6) / 1000
