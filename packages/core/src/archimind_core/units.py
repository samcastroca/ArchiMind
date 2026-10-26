"""Unidades del dibujo: de $INSUNITS si las declara, inferidas por magnitudes si no."""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from archimind_schema import LENGTH_TOL, WALL_THICKNESSES
from ezdxf import bbox, units
from ezdxf.document import Drawing as DXFDocument

from archimind_core.inventory import linear_lengths, modelspace_entities

METRES = units.InsertUnits.Meters
CANDIDATES = (METRES, units.InsertUnits.Centimeters, units.InsertUnits.Millimeters)
# Extensión, en metros, que puede tener un plano de edificio; la típica desempata.
PLAUSIBLE_EXTENT_M = (2.0, 500.0)
TYPICAL_EXTENT_M = 20.0


@dataclass(frozen=True)
class DrawingUnits:
    name: str
    to_metres: float
    confirmed: bool
    source: Literal["insunits", "inferidas"]
    evidence: str


def detect_units(doc: DXFDocument) -> DrawingUnits:
    insunits = doc.units
    if insunits != units.InsertUnits.Unitless:
        try:
            factor = units.conversion_factor(units.InsertUnits(insunits), METRES)
        except ValueError:
            reason = f"$INSUNITS = {insunits} no es una unidad válida"
        else:
            name = units.unit_name(insunits)
            return DrawingUnits(name, factor, True, "insunits", f"$INSUNITS = {insunits} ({name})")
    else:
        reason = "el archivo no declara unidades ($INSUNITS)"
    entities = list(modelspace_entities(doc))
    lengths = [length for entity, _ in entities for length in linear_lengths(entity)]
    box = bbox.extents(entity for entity, _ in entities)
    extent = max(box.size.x, box.size.y) if box.has_data else 0.0
    inferred = infer_units(lengths, extent)
    return DrawingUnits(
        inferred.name,
        inferred.to_metres,
        False,
        "inferidas",
        f"{reason}; {inferred.evidence}",
    )


def infer_units(lengths: Sequence[float], extent: float) -> DrawingUnits:
    """Elige entre m, cm y mm por los tramos que, convertidos, dan un espesor de muro habitual.

    Un tramo de 150 sugiere milímetros (0.15 m). Solo compiten las unidades con las que el plano
    mide lo que un edificio; si ninguna explica tramos, gana la de extensión más típica.
    """
    if extent <= 0:
        return DrawingUnits("Meters", 1.0, False, "inferidas", "plano vacío: se suponen metros")

    def matches(factor: float) -> int:
        return sum(
            any(abs(length * factor - t) <= LENGTH_TOL for t in WALL_THICKNESSES)
            for length in lengths
        )

    def atypical(factor: float) -> float:
        return abs(math.log(extent * factor / TYPICAL_EXTENT_M))

    low, high = PLAUSIBLE_EXTENT_M
    factors = {unit: units.conversion_factor(unit, METRES) for unit in CANDIDATES}
    plausible = [unit for unit in CANDIDATES if low <= extent * factors[unit] <= high]
    pool = plausible or list(CANDIDATES)
    best = max(pool, key=lambda unit: (matches(factors[unit]), -atypical(factors[unit])))
    factor, name, count = factors[best], units.unit_name(best), matches(factors[best])
    size = f"el plano mide {extent * factor:.1f} m"
    if count:
        evidence = f"{count} tramos miden un espesor de muro habitual si son {name}; {size}"
    elif plausible:
        evidence = f"ningún tramo mide un espesor habitual; en {name} {size}"
    else:
        evidence = f"ninguna unidad da un tamaño de edificio; en {name} {size}"
    return DrawingUnits(name, factor, False, "inferidas", evidence)
