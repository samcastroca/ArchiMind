"""Casos y utilidades comunes de las pruebas de archimind-bloques (en el pythonpath de pytest)."""

import math
from pathlib import Path

from archimind_bloques import (
    Arc,
    AwningWindow,
    Box,
    Carpentry,
    CarpentryParams,
    DoubleSwingDoor,
    FixedWindow,
    Polyline,
    SlidingDoor,
    SlidingWindow,
    Stroke,
    SwingDoor,
    load_catalog,
)

CATALOG = load_catalog(Path(__file__).with_name("catalog_prueba.yaml"))
PROFILE = CATALOG.profile("prueba")  # F 0.05, D 0.08, S 0.04, Sd 0.025, O 0.03
NARROW = CATALOG.profile("estrecho")
TOL = 0.001

EXAMPLES: dict[str, CarpentryParams] = {
    "puerta_batiente": SwingDoor(
        width=0.90,
        height=2.10,
        leaf_thickness=0.04,
        hand="left",
        swing="in",
        wall_thickness=0.15,
        profile=PROFILE,
    ),
    "puerta_batiente_doble": DoubleSwingDoor(
        width=1.60,
        height=2.10,
        leaf_thickness=0.04,
        swing="out",
        wall_thickness=0.15,
        profile=PROFILE,
    ),
    "puerta_corrediza": SlidingDoor(
        width=0.90,
        height=2.10,
        leaf_thickness=0.04,
        hand="left",
        side="in",
        wall_thickness=0.15,
        profile=PROFILE,
    ),
    "ventana_corrediza_2h": SlidingWindow(
        width=1.20, height=1.20, sill_height=0.90, leaves=2, wall_thickness=0.15, profile=PROFILE
    ),
    "ventana_corrediza_3h": SlidingWindow(
        width=1.54, height=1.20, sill_height=0.90, leaves=3, wall_thickness=0.15, profile=PROFILE
    ),
    "ventana_corrediza_4h": SlidingWindow(
        width=2.00, height=1.20, sill_height=0.90, leaves=4, wall_thickness=0.15, profile=PROFILE
    ),
    "ventana_fija": FixedWindow(
        width=1.00, height=1.00, sill_height=1.00, wall_thickness=0.15, profile=PROFILE
    ),
    "ventana_proyectante": AwningWindow(
        width=0.80, height=0.60, sill_height=1.50, wall_thickness=0.15, profile=PROFILE
    ),
}


def arc_points(arc: Arc) -> list[tuple[float, float]]:
    """Los extremos del arco y los puntos cardinales que recorre: bastan para su extensión."""
    sweep = (arc.end_angle - arc.start_angle) % 360
    angles = [arc.start_angle, arc.end_angle]
    angles += [q for q in (0, 90, 180, 270) if (q - arc.start_angle) % 360 <= sweep]
    return [
        (
            arc.center[0] + arc.radius * math.cos(math.radians(a)),
            arc.center[1] + arc.radius * math.sin(math.radians(a)),
        )
        for a in angles
    ]


def extents(strokes: tuple[Stroke, ...]) -> tuple[float, float, float, float]:
    """(xmin, ymin, xmax, ymax) de unos trazos."""
    points: list[tuple[float, float]] = []
    for stroke in strokes:
        match stroke:
            case Polyline():
                points += stroke.points
            case Arc():
                points += arc_points(stroke)
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


def solids_extents(boxes: tuple[Box, ...]) -> tuple[float, ...]:
    """(xmin, ymin, zmin, xmax, ymax, zmax) de unas piezas."""
    return (
        *(min(b.min[i] for b in boxes) for i in range(3)),
        *(max(b.max[i] for b in boxes) for i in range(3)),
    )


def solid(carpentry: Carpentry, name: str) -> Box:
    (found,) = [b for b in carpentry.solids if b.name == name]
    return found


def sash_span(carpentry: Carpentry, number: int) -> tuple[float, ...]:
    """(x0, y0, z0, x1, y1, z1) de la hoja `number`, unión de sus cuatro piezas."""
    prefix = f"hoja {number} "
    return solids_extents(tuple(b for b in carpentry.solids if b.name.startswith(prefix)))
