"""Dibuja un modelo semántico como plano DXF. Va del modelo al DXF, nunca al revés."""

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import ezdxf
from archimind_schema import Opening, Point2D, Project, Wall
from ezdxf import units
from ezdxf.enums import TextEntityAlignment
from ezdxf.layouts import Modelspace
from shapely import MultiLineString, MultiPolygon, Polygon, line_merge, unary_union

TEXT_HEIGHT = 0.20
# Lo que el vano se extiende más allá de las caras del muro, para que el recorte sea limpio.
CUT_MARGIN = 0.01
# Colores ACI por rol, solo para distinguir en la revisión visual.
LAYER_COLORS = {"wall": 7, "door": 1, "window": 5, "text": 3, "dimension": 8}


@dataclass(frozen=True)
class Layers:
    wall: str = "A-MURO"
    door: str = "A-PUERTA"
    window: str = "A-VENTANA"
    text: str = "A-TEXTO"
    dimension: str = "A-COTA"


@dataclass(frozen=True)
class Dimension:
    """Cota lineal entre p1 y p2, con la línea de cota pasando por `base`. En metros."""

    p1: Point2D
    p2: Point2D
    base: Point2D
    angle: float = 0.0


@dataclass(frozen=True)
class DrawStyle:
    layers: Layers = field(default_factory=Layers)
    unit_scale: float = 1.0
    insunits: int = units.M
    wall_entities: Literal["polyline", "lines"] = "polyline"


def write_dxf(
    project: Project, dimensions: list[Dimension], style: DrawStyle, path: str | Path
) -> None:
    doc = ezdxf.new("R2010", setup=True, units=style.insunits)
    for role, name in vars(style.layers).items():
        if name not in doc.layers:
            doc.layers.add(name, color=LAYER_COLORS[role])
    msp = doc.modelspace()
    draw = _Drawer(msp, style)
    draw.walls(project)
    walls = {wall.id: wall for wall in project.walls}
    for opening in project.openings:
        draw.opening(walls[opening.wall_id], opening)
    for annotation in project.annotations:
        if annotation.kind == "label":
            draw.label(annotation.text, annotation.position)
    for dimension in dimensions:
        draw.dimension(dimension)
    doc.saveas(Path(path))


def opening_rectangle(wall: Wall, opening: Opening, margin: float = 0.0) -> Polygon:
    (a, d, n) = _frame(wall)
    half = wall.thickness / 2 + margin
    s0, s1 = opening.offset, opening.offset + opening.width
    corners = [(s0, -half), (s1, -half), (s1, half), (s0, half)]
    return Polygon([_at(a, d, n, s, t) for s, t in corners])


def _frame(wall: Wall) -> tuple[Point2D, Point2D, Point2D]:
    """Origen, dirección unitaria y normal a la izquierda de un muro recto."""
    if len(wall.axis) != 2:
        raise ValueError(f"el dibujante solo admite muros rectos de 2 puntos ({wall.id})")
    (x0, y0), (x1, y1) = wall.axis
    length = math.dist(wall.axis[0], wall.axis[1])
    d = ((x1 - x0) / length, (y1 - y0) / length)
    return (x0, y0), d, (-d[1], d[0])


def _at(a: Point2D, d: Point2D, n: Point2D, s: float, t: float) -> Point2D:
    """Punto a distancia s a lo largo del eje y t hacia la normal."""
    return (a[0] + d[0] * s + n[0] * t, a[1] + d[1] * s + n[1] * t)


class _Drawer:
    def __init__(self, msp: Modelspace, style: DrawStyle) -> None:
        self.msp = msp
        self.style = style

    def _p(self, point: Point2D) -> tuple[float, float]:
        k = self.style.unit_scale
        return (round(point[0] * k, 6), round(point[1] * k, 6))

    def walls(self, project: Project) -> None:
        """Contorno de la unión de las huellas, recortada en los vanos.

        Los ejes conectados de igual espesor se unen antes de engrosar para que las esquinas
        salgan a inglete. Los extremos que quedan acaban en el eje de otro muro (uniones en T),
        dentro de su huella; en los casos no hay extremos libres.
        """
        by_thickness: dict[float, list[list[Point2D]]] = {}
        for wall in project.walls:
            by_thickness.setdefault(wall.thickness, []).append(wall.axis)
        footprints = [
            line_merge(MultiLineString(axes)).buffer(t / 2, cap_style="flat", join_style="mitre")
            for t, axes in by_thickness.items()
        ]
        walls = {wall.id: wall for wall in project.walls}
        cuts = [opening_rectangle(walls[o.wall_id], o, CUT_MARGIN) for o in project.openings]
        outline = unary_union(footprints).difference(unary_union(cuts))
        polygons = outline.geoms if isinstance(outline, MultiPolygon) else [outline]
        attribs = {"layer": self.style.layers.wall}
        for polygon in polygons:
            for ring in [polygon.exterior, *polygon.interiors]:
                points = [self._p(p) for p in ring.coords[:-1]]
                if self.style.wall_entities == "polyline":
                    self.msp.add_lwpolyline(points, close=True, dxfattribs=attribs)
                else:
                    for start, end in zip(points, points[1:] + points[:1], strict=True):
                        self.msp.add_line(start, end, dxfattribs=attribs)

    def opening(self, wall: Wall, opening: Opening) -> None:
        a, d, n = _frame(wall)
        s0, s1 = opening.offset, opening.offset + opening.width
        half = wall.thickness / 2
        if opening.kind == "door":
            # Hoja abierta 90° hacia la normal izquierda, con bisagra en s0 y su arco de giro.
            attribs = {"layer": self.style.layers.door}
            hinge = _at(a, d, n, s0, half)
            leaf_end = _at(a, d, n, s0, half + opening.width)
            self.msp.add_line(self._p(hinge), self._p(leaf_end), dxfattribs=attribs)
            start_angle = math.degrees(math.atan2(d[1], d[0]))
            self.msp.add_arc(
                self._p(hinge),
                opening.width * self.style.unit_scale,
                start_angle,
                start_angle + 90,
                dxfattribs=attribs,
            )
        elif opening.kind == "window":
            attribs = {"layer": self.style.layers.window}
            for t in (-half, 0.0, half):
                start, end = _at(a, d, n, s0, t), _at(a, d, n, s1, t)
                self.msp.add_line(self._p(start), self._p(end), dxfattribs=attribs)

    def label(self, text: str, position: Point2D) -> None:
        self.msp.add_text(
            text,
            height=TEXT_HEIGHT * self.style.unit_scale,
            dxfattribs={"layer": self.style.layers.text},
        ).set_placement(self._p(position), align=TextEntityAlignment.MIDDLE_CENTER)

    def dimension(self, dimension: Dimension) -> None:
        # EZ_M_100_H25_CM está pensado para metros a 1:100 y mide en cm: se mide en la unidad
        # del dibujo (dimlfac=1) y se escala el tamaño de flechas y texto con la unidad.
        metres = self.style.unit_scale == 1
        self.msp.add_linear_dim(
            base=self._p(dimension.base),
            p1=self._p(dimension.p1),
            p2=self._p(dimension.p2),
            angle=dimension.angle,
            dimstyle="EZ_M_100_H25_CM",
            override={
                "dimlfac": 1,
                "dimdec": 2 if metres else 0,
                "dimzin": 0,
                "dimscale": self.style.unit_scale,
            },
            dxfattribs={"layer": self.style.layers.dimension},
        ).render()
