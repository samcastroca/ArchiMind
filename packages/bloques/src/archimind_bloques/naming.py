"""Nombre de bloque determinista: legible y distinto para parámetros distintos."""

import hashlib
from typing import assert_never

from archimind_bloques.params import (
    AwningWindow,
    CarpentryParams,
    DoubleSwingDoor,
    FixedWindow,
    SlidingDoor,
    SlidingWindow,
    SwingDoor,
)

HANDS = {"left": "IZQ", "right": "DER"}
SIDES = {"in": "ADENTRO", "out": "AFUERA"}


def block_name(params: CarpentryParams) -> str:
    """P. ej. `PUERTA-BATIENTE-900x2100-IZQ-ADENTRO-3F2A1C`: tipo, medidas del vano en mm y lo
    que distingue al tipo, más un resumen de todos los parámetros (también el perfil), para que
    dos bloques distintos nunca compartan nombre. Lleva PUERTA o VENTANA, que es lo que el
    importador de core reconoce en los nombres de bloque."""
    size = f"{round(params.width * 1000)}x{round(params.height * 1000)}"
    match params:
        case SwingDoor():
            parts = ["PUERTA-BATIENTE", size, HANDS[params.hand], SIDES[params.swing]]
        case DoubleSwingDoor():
            parts = ["PUERTA-BATIENTE-DOBLE", size, SIDES[params.swing]]
        case SlidingDoor():
            parts = ["PUERTA-CORREDIZA", size, HANDS[params.hand], SIDES[params.side]]
        case SlidingWindow():
            parts = ["VENTANA-CORREDIZA", f"{params.leaves}H", size]
        case FixedWindow():
            parts = ["VENTANA-FIJA", size]
        case AwningWindow():
            parts = ["VENTANA-PROYECTANTE", size]
        case _:
            assert_never(params)
    digest = hashlib.sha1(params.model_dump_json().encode("utf-8")).hexdigest()[:6].upper()
    return "-".join([*parts, digest])
