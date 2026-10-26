"""Punto de entrada de los generadores: parámetros validados → carpintería."""

from typing import assert_never

from archimind_bloques.doors import double_swing_door, sliding_door, swing_door
from archimind_bloques.geometry import Carpentry
from archimind_bloques.params import (
    AwningWindow,
    CarpentryParams,
    DoubleSwingDoor,
    FixedWindow,
    SlidingDoor,
    SlidingWindow,
    SwingDoor,
)
from archimind_bloques.windows import awning_window, fixed_window, sliding_window


def generate(params: CarpentryParams) -> Carpentry:
    """Determinista: los mismos parámetros dan siempre la misma carpintería."""
    match params:
        case SwingDoor():
            return swing_door(params)
        case DoubleSwingDoor():
            return double_swing_door(params)
        case SlidingDoor():
            return sliding_door(params)
        case SlidingWindow():
            return sliding_window(params)
        case FixedWindow():
            return fixed_window(params)
        case AwningWindow():
            return awning_window(params)
        case _:
            assert_never(params)
