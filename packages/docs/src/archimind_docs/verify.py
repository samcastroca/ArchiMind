"""Los números de un texto frente a las cifras verificadas del proyecto.

Un número del texto está verificado si alguna cifra de los datos, redondeada a los decimales
con que está escrito, da ese mismo número: «55,25», «55.2», «55.3» y «55» valen para 55.25.
También valen los números que aparecen en los textos de los datos (nombres de espacios,
normas, claves). Se acepta coma o punto decimal y punto o coma de miles («1.234,56»); un número
ambiguo como «1.234» vale con cualquiera de sus dos lecturas. Todo lo demás (años, fechas,
escalas como 1:50) se rechaza: si no está en los datos, no está verificado.
"""

import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
CONTEXT_CHARS = 30
EPS = 1e-9

Reading = tuple[float, int]  # (valor, decimales escritos)


@dataclass(frozen=True)
class Unverified:
    text: str
    context: str


def readings(token: str) -> list[Reading]:
    """Las lecturas posibles de un número escrito."""
    separators = [c for c in token if c in ".,"]
    if not separators:
        return [(float(token), 0)]
    if len(set(separators)) == 2:
        decimal = separators[-1]
        thousands = "," if decimal == "." else "."
        whole = token.rpartition(decimal)[0]
        # Un solo separador decimal y miles de tres cifras; «1.5,2.5» o «1,23.5» no se leen.
        if decimal in whole or not all(len(g) == 3 for g in whole.split(thousands)[1:]):
            return []
        return [_decimal(token.replace(thousands, ""), decimal)]
    separator = separators[0]
    groups = token.split(separator)
    as_thousands = (float(token.replace(separator, "")), 0)
    if len(groups) > 2:
        return [as_thousands] if all(len(g) == 3 for g in groups[1:]) else []
    if len(groups[1]) == 3:
        return [_decimal(token, separator), as_thousands]
    return [_decimal(token, separator)]


def data_numbers(data: Any) -> list[float]:
    """Todos los números de los datos: los valores numéricos y los que aparecen en sus
    textos."""
    return sorted(set(_walk(data)))


def unverified_numbers(text: str, data: Any) -> list[Unverified]:
    numbers = data_numbers(data)
    found = []
    for match in NUMBER.finditer(text):
        if not any(_matches(reading, numbers) for reading in readings(match.group())):
            start = max(0, match.start() - CONTEXT_CHARS)
            context = " ".join(text[start : match.end() + CONTEXT_CHARS].split())
            found.append(Unverified(match.group(), context))
    return found


def _decimal(token: str, separator: str) -> Reading:
    whole, fraction = token.split(separator)
    return float(f"{whole}.{fraction}"), len(fraction)


def _matches(reading: Reading, numbers: list[float]) -> bool:
    """Si alguna cifra queda a media unidad del último decimal escrito, o menos: en un empate
    («55.25» escrito con un decimal) valen las dos formas de redondear, 55.2 y 55.3."""
    value, decimals = reading
    half = 0.5 * 10**-decimals
    return any(abs(n - value) <= half + EPS for n in numbers)


def _walk(value: Any) -> Iterator[float]:
    if isinstance(value, bool) or value is None:
        return
    if isinstance(value, int | float):
        yield float(value)
    elif isinstance(value, str):
        for match in NUMBER.finditer(value):
            for number, _ in readings(match.group()):
                yield number
    elif isinstance(value, dict):
        for item in value.values():
            yield from _walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk(item)
