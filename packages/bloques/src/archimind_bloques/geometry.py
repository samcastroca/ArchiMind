"""Primitivas que producen los generadores, en metros y en los ejes locales del bloque.

Planta: x a lo largo del muro (el vano va de 0 al ancho), y perpendicular (+y adentro) y el
origen en el borde del vano sobre el eje del muro. Alzado: visto desde afuera, x igual que en la
planta e y = altura sobre el piso. 3D: x e y como en la planta, z = altura sobre el piso.
"""

import math
from dataclasses import dataclass
from enum import Enum
from typing import Literal

from archimind_bloques.params import CarpentryParams

Point = tuple[float, float]
Point3 = tuple[float, float, float]


class Pen(Enum):
    """Jerarquía de trazo: lo cortado, lo visto, lo fino y lo oculto."""

    CUT = "cut"
    SEEN = "seen"
    THIN = "thin"
    HIDDEN = "hidden"


@dataclass(frozen=True)
class Polyline:
    points: tuple[Point, ...]
    pen: Pen
    closed: bool = False


@dataclass(frozen=True)
class Arc:
    """Arco antihorario de `start_angle` a `end_angle`, en grados."""

    center: Point
    radius: float
    start_angle: float
    end_angle: float
    pen: Pen


Stroke = Polyline | Arc


@dataclass(frozen=True)
class Box:
    """Pieza maciza alineada con los ejes: un tramo de marco o de hoja."""

    name: str
    part: Literal["frame", "sash"]
    min: Point3
    max: Point3


@dataclass(frozen=True)
class Pane:
    """Vidrio: un rectángulo en el plano y = cte."""

    name: str
    y: float
    x0: float
    x1: float
    z0: float
    z1: float


@dataclass(frozen=True)
class Carpentry:
    name: str
    kind: Literal["door", "window"]
    params: CarpentryParams
    plan: tuple[Stroke, ...]
    elevation: tuple[Stroke, ...]
    solids: tuple[Box, ...]
    panes: tuple[Pane, ...]


def line(a: Point, b: Point, pen: Pen) -> Polyline:
    return Polyline((a, b), pen)


def rect(x0: float, y0: float, x1: float, y1: float, pen: Pen) -> Polyline:
    """Rectángulo cerrado; acepta las esquinas en cualquier orden."""
    xa, xb = sorted((x0, x1))
    ya, yb = sorted((y0, y1))
    return Polyline(((xa, ya), (xb, ya), (xb, yb), (xa, yb)), pen, closed=True)


def arrow(start: Point, end: Point, pen: Pen) -> tuple[Polyline, Polyline]:
    """Flecha de `start` a `end`: el asta y la punta, de un quinto del largo."""
    (x0, y0), (x1, y1) = start, end
    angle = math.atan2(y1 - y0, x1 - x0)
    head = math.dist(start, end) / 5
    tips = [
        (x1 - head * math.cos(angle + turn), y1 - head * math.sin(angle + turn))
        for turn in (math.pi / 6, -math.pi / 6)
    ]
    return line(start, end, pen), Polyline((tips[0], end, tips[1]), pen)


def quarter_arc(center: Point, start: Point, end: Point, pen: Pen) -> Arc:
    """El arco de 90° con centro `center` que va de `start` a `end`, en cualquier sentido."""
    a = math.degrees(math.atan2(start[1] - center[1], start[0] - center[0])) % 360
    b = math.degrees(math.atan2(end[1] - center[1], end[0] - center[0])) % 360
    radius = math.dist(center, start)
    if math.isclose((b - a) % 360, 90):
        return Arc(center, radius, a, b, pen)
    return Arc(center, radius, b, a, pen)


def box(name: str, part: Literal["frame", "sash"], a: Point3, b: Point3) -> Box:
    """Caja entre dos esquinas opuestas cualesquiera."""
    lo = (min(a[0], b[0]), min(a[1], b[1]), min(a[2], b[2]))
    hi = (max(a[0], b[0]), max(a[1], b[1]), max(a[2], b[2]))
    return Box(name, part, lo, hi)
