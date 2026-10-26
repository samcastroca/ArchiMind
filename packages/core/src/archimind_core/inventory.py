"""Inventario por capa del espacio modelo, con los bloques explotados solo para el análisis."""

import math
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ezdxf.document import Drawing as DXFDocument
from ezdxf.entities import Arc, DXFGraphic, Insert, Line, LWPolyline, MText, Polyline, Text

if TYPE_CHECKING:
    from archimind_core.drawing import Drawing

MAX_SAMPLE_TEXTS = 5


@dataclass(frozen=True)
class LayerSummary:
    """Lo que hay en una capa. Las longitudes van en metros; `preliminary` si la escala no está
    confirmada."""

    layer: str
    entity_counts: dict[str, int]
    line_length_m: float
    blocks: dict[str, int]
    sample_texts: list[str] = field(default_factory=list)
    preliminary: bool = False


def modelspace_entities(doc: DXFDocument) -> Iterator[tuple[DXFGraphic, str]]:
    """Cada entidad del espacio modelo con su capa efectiva; los layouts de papel se ignoran.

    Los INSERT aparecen ellos mismos y luego su contenido, recursivamente, como entidades
    virtuales: el documento no se modifica. Lo que dentro de un bloque está en la capa "0" toma
    la capa del INSERT que lo contiene, como en CAD.
    """
    yield from _flatten(doc.modelspace(), None)


def _flatten(
    entities: Iterable[DXFGraphic], parent_layer: str | None
) -> Iterator[tuple[DXFGraphic, str]]:
    for entity in entities:
        layer = entity.dxf.layer
        if parent_layer is not None and layer == "0":
            layer = parent_layer
        yield entity, layer
        if isinstance(entity, Insert):
            yield from _flatten(entity.virtual_entities(), layer)


def linear_pieces(entity: DXFGraphic) -> list[DXFGraphic]:
    """Tramos (LINE y, por los bulges, ARC) de una LINE o polilínea; [] para el resto."""
    if isinstance(entity, Line):
        return [entity]
    if isinstance(entity, LWPolyline):
        return list(entity.virtual_entities())
    if isinstance(entity, Polyline) and (entity.is_2d_polyline or entity.is_3d_polyline):
        return list(entity.virtual_entities())
    return []


def linear_lengths(entity: DXFGraphic) -> list[float]:
    """Longitud de cada tramo de una LINE o polilínea, en unidades del dibujo; [] para el resto.

    Los tramos con bulge de una polilínea cuentan con la longitud de su arco.
    """
    return [length for piece in linear_pieces(entity) if (length := piece_length(piece)) > 0]


def piece_length(piece: DXFGraphic) -> float:
    if isinstance(piece, Line):
        return math.dist(piece.dxf.start, piece.dxf.end)
    if isinstance(piece, Arc):
        span = (piece.dxf.end_angle - piece.dxf.start_angle) % 360
        return float(piece.dxf.radius) * math.radians(span)
    return 0.0


def _plain_text(entity: Text | MText) -> str:
    if isinstance(entity, MText):
        # Con split=False, MText.plain_text siempre devuelve str.
        return str(entity.plain_text(split=False)).strip()
    return entity.plain_text().strip()


def layer_inventory(drawing: "Drawing") -> list[LayerSummary]:
    """Resumen por capa del espacio modelo, ordenado por nombre de capa."""
    counts: dict[str, Counter[str]] = {}
    lengths: defaultdict[str, float] = defaultdict(float)
    blocks: dict[str, Counter[str]] = {}
    texts: dict[str, list[str]] = {}
    for entity, layer in modelspace_entities(drawing.doc):
        counts.setdefault(layer, Counter())[entity.dxftype()] += 1
        lengths[layer] += sum(linear_lengths(entity))
        if isinstance(entity, Insert):
            blocks.setdefault(layer, Counter())[entity.dxf.name] += 1
        if isinstance(entity, Text | MText):
            samples = texts.setdefault(layer, [])
            text = _plain_text(entity)
            if text and text not in samples and len(samples) < MAX_SAMPLE_TEXTS:
                samples.append(text)
    return [
        LayerSummary(
            layer=layer,
            entity_counts=dict(sorted(counts[layer].items())),
            line_length_m=lengths[layer] * drawing.units.to_metres,
            blocks=dict(sorted(blocks.get(layer, Counter()).items())),
            sample_texts=texts.get(layer, []),
            preliminary=not drawing.units.confirmed,
        )
        for layer in sorted(counts)
    ]
