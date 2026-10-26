"""Del plano a primitivas en metros, separadas según el rol de la capa en el mapeo."""

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from archimind_schema import LENGTH_TOL, Point2D
from ezdxf import path
from ezdxf.entities import Arc, DXFGraphic, Insert, Line, LWPolyline, MText, Text
from shapely import LineString, MultiPoint, Point, Polygon
from shapely.geometry.base import BaseGeometry

from archimind_core.inventory import linear_pieces, plain_text
from archimind_core.layer_roles import Segment
from archimind_core.layer_rules import LayerRules

if TYPE_CHECKING:
    from archimind_core.drawing import Drawing

SymbolKind = Literal["door", "window"]
SYMBOL_ROLES: dict[str, SymbolKind] = {"doors": "door", "windows": "window"}


@dataclass(frozen=True)
class AxisLine:
    """Polilínea abierta de eje con ancho constante: el ancho es el espesor del muro."""

    points: list[Point2D]
    thickness: float
    layer: str


@dataclass(frozen=True)
class Label:
    text: str
    position: Point2D


@dataclass(frozen=True)
class BlockSymbol:
    """INSERT de puerta o ventana: su tipo y la envolvente convexa de lo que dibuja."""

    kind: SymbolKind
    name: str
    hull: Polygon


@dataclass
class PlanContent:
    wall_segments: dict[str, list[Segment]] = field(default_factory=dict)
    wall_axes: list[AxisLine] = field(default_factory=list)
    # Puertas y ventanas dibujadas con entidades sueltas, sin bloque.
    symbols: dict[SymbolKind, list[BaseGeometry]] = field(
        default_factory=lambda: {"door": [], "window": []}
    )
    blocks: list[BlockSymbol] = field(default_factory=list)
    labels: list[Label] = field(default_factory=list)
    mixed_layers: set[str] = field(default_factory=set)
    # Entidades de las capas de muros que no se interpretan, por tipo DXF.
    unsupported_walls: Counter[str] = field(default_factory=Counter)


def extract(drawing: "Drawing", mapping: Mapping[str, str], rules: LayerRules) -> PlanContent:
    """Recorre el espacio modelo con los bloques explotados (lo que está en la capa "0" de un
    bloque toma la capa del INSERT). Un INSERT es una puerta o ventana si lo es su capa o si su
    nombre de bloque lo indica; entonces no se explota en las demás capas."""
    k = drawing.units.to_metres
    content = PlanContent()

    def walk(entities: Iterable[DXFGraphic], parent_layer: str | None) -> None:
        for entity in entities:
            layer = entity.dxf.layer
            if parent_layer is not None and layer == "0":
                layer = parent_layer
            role = mapping.get(layer)
            if isinstance(entity, Insert):
                kind = SYMBOL_ROLES.get(role or "") or SYMBOL_ROLES.get(
                    rules.block_role(entity.dxf.name) or ""
                )
                if kind is None:
                    walk(entity.virtual_entities(), layer)
                else:
                    content.blocks.append(_block(entity, kind, k))
            elif role == "mixed":
                content.mixed_layers.add(layer)
            elif role == "walls":
                _add_wall(content, entity, layer, k)
            elif role in SYMBOL_ROLES:
                content.symbols[SYMBOL_ROLES[role]].extend(_shapes(entity, k))
            elif role == "text" and isinstance(entity, Text | MText):
                text = plain_text(entity)
                if text:
                    content.labels.append(Label(text, _text_position(entity, k)))

    walk(drawing.doc.modelspace(), None)
    return content


def _add_wall(content: PlanContent, entity: DXFGraphic, layer: str, k: float) -> None:
    if isinstance(entity, LWPolyline) and not entity.closed and entity.dxf.const_width > 0:
        points = [_round((x * k, y * k)) for x, y in entity.get_points("xy")]
        content.wall_axes.append(AxisLine(points, entity.dxf.const_width * k, layer))
        return
    pieces = linear_pieces(entity)
    if not pieces:
        content.unsupported_walls[entity.dxftype()] += 1
    for piece in pieces:
        if isinstance(piece, Line):
            start, end = piece.dxf.start, piece.dxf.end
            segment = Segment(_round((start.x * k, start.y * k)), _round((end.x * k, end.y * k)))
            # Hasta los lados diminutos hacen falta para que el contorno cierre.
            if segment.length > 0:
                content.wall_segments.setdefault(layer, []).append(segment)
        elif isinstance(piece, Arc):
            content.unsupported_walls["ARC"] += 1


def _round(point: Point2D) -> Point2D:
    """Redondeo a la micra: los extremos que coinciden en el dibujo coinciden exactamente."""
    return (round(point[0], 6), round(point[1], 6))


def _shapes(entity: DXFGraphic, k: float) -> list[BaseGeometry]:
    """La entidad aplanada a líneas, en metros; [] si no dibuja líneas."""
    try:
        points = [(p.x * k, p.y * k) for p in path.make_path(entity).flattening(LENGTH_TOL / k)]
    except TypeError:
        return []
    if len(points) < 2:
        return [Point(points[0])] if points else []
    return [LineString(points)]


def _block(insert: Insert, kind: SymbolKind, k: float) -> BlockSymbol:
    points: list[tuple[float, float]] = []

    def collect(entities: Iterable[DXFGraphic]) -> None:
        for entity in entities:
            if isinstance(entity, Insert):
                collect(entity.virtual_entities())
            else:
                for shape in _shapes(entity, k):
                    points.extend(shape.coords)

    collect(insert.virtual_entities())
    hull = MultiPoint(points).convex_hull
    if not isinstance(hull, Polygon):
        hull = hull.buffer(LENGTH_TOL)
    return BlockSymbol(kind, insert.dxf.name, hull)


def _text_position(entity: Text | MText, k: float) -> Point2D:
    location = entity.dxf.insert if isinstance(entity, MText) else entity.get_placement()[1]
    return (location.x * k, location.y * k)
