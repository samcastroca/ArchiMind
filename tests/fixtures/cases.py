"""Casos golden: el modelo semántico esperado de cada plano, escrito a mano.

Es la verdad de referencia. El DXF de cada caso se dibuja a partir de este modelo; nunca se
deriva de un importador. Un muro es un tramo recto continuo de eje: no se parte en las uniones
en T. Los espacios van por las caras interiores de los muros.
"""

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from archimind_schema import (
    Annotation,
    Level,
    Opening,
    Point2D,
    Project,
    Space,
    SpacePolygon,
    Wall,
    new_id,
)
from dxf_writer import Dimension, DrawStyle, Layers
from ezdxf import units
from ezdxf.layouts import Modelspace

SpaceCategory = Literal["useful", "balcony", "circulation", "service", "technical"]
DOOR_HEIGHT = 2.10
WINDOW_HEIGHT, WINDOW_SILL = 1.20, 0.90


@dataclass
class _Builder:
    """Ayuda a escribir el modelo: los IDs salen de new_id como en el uso real."""

    name: str
    wall_layer: str
    project: Project = field(init=False)
    level_id: str = field(init=False)

    def __post_init__(self) -> None:
        self.project = Project(id=self.name, name=self.name, scale_confirmed=True)
        self.level_id = new_id(self.project, "niv")
        self.project.levels.append(
            Level(id=self.level_id, name="Planta baja", elevation=0.0, default_height=2.60)
        )

    def wall(self, start: Point2D, end: Point2D, thickness: float) -> str:
        wall_id = new_id(self.project, "muro")
        self.project.walls.append(
            Wall(
                id=wall_id,
                level_id=self.level_id,
                axis=[start, end],
                thickness=thickness,
                source_layer=self.wall_layer,
            )
        )
        return wall_id

    def door(self, wall_id: str, offset: float, width: float) -> None:
        self._opening(wall_id, "door", offset, width, DOOR_HEIGHT, 0.0)

    def window(
        self,
        wall_id: str,
        offset: float,
        width: float,
        height: float = WINDOW_HEIGHT,
        sill: float = WINDOW_SILL,
    ) -> None:
        self._opening(wall_id, "window", offset, width, height, sill)

    def _opening(
        self,
        wall_id: str,
        kind: Literal["door", "window"],
        offset: float,
        width: float,
        height: float,
        sill: float,
    ) -> None:
        self.project.openings.append(
            Opening(
                id=new_id(self.project, "vano"),
                wall_id=wall_id,
                kind=kind,
                offset=offset,
                width=width,
                height=height,
                sill_height=sill,
            )
        )

    def space(
        self, name: str, exterior: list[Point2D], category: SpaceCategory, label_at: Point2D
    ) -> None:
        self.project.spaces.append(
            Space(
                id=new_id(self.project, "esp"),
                level_id=self.level_id,
                name=name,
                polygon=SpacePolygon(exterior=exterior),
                category=category,
            )
        )
        self.project.annotations.append(Annotation(text=name, position=label_at, kind="label"))

    def dimensions(self, dimensions: list[Dimension]) -> list[Dimension]:
        for dim in dimensions:
            length = math.dist(dim.p1, dim.p2)
            text = f"{length:.2f}"
            self.project.annotations.append(
                Annotation(text=text, position=dim.base, kind="dimension")
            )
        return dimensions


Model = tuple[Project, list[Dimension]]


def rect_simple() -> Model:
    """Un espacio interior de 4 × 3 m, muros de 0.15 y una puerta de 0.90 centrada."""
    b = _Builder("rect_simple", "A-MURO")
    bottom = b.wall((-0.075, -0.075), (4.075, -0.075), 0.15)
    b.wall((4.075, -0.075), (4.075, 3.075), 0.15)
    b.wall((4.075, 3.075), (-0.075, 3.075), 0.15)
    b.wall((-0.075, 3.075), (-0.075, -0.075), 0.15)
    b.door(bottom, offset=1.625, width=0.90)  # x de 1.55 a 2.45
    b.space("Estudio", [(0, 0), (4, 0), (4, 3), (0, 3)], "useful", (2.0, 1.5))
    dims = b.dimensions(
        [
            Dimension((-0.15, -0.15), (4.15, -0.15), (2.075, -0.8)),
            Dimension((4.15, -0.15), (4.15, 3.15), (4.8, 1.5), angle=90),
        ]
    )
    return b.project, dims


def apto_2hab(wall_layer: str = "A-MURO") -> Model:
    """Apartamento de 8.50 × 6.50 m a ejes (55.25 m²): dos habitaciones, baño y cocina abierta.

    Exteriores de 0.20; tabique de 0.12 en x=3.5; tabiques de 0.10 entre habitaciones y en el
    baño.
    """
    b = _Builder("apto_2hab", wall_layer)
    south = b.wall((0, 0), (8.5, 0), 0.20)
    east = b.wall((8.5, 0), (8.5, 6.5), 0.20)
    north = b.wall((8.5, 6.5), (0, 6.5), 0.20)
    b.wall((0, 6.5), (0, 0), 0.20)
    spine = b.wall((3.5, 0), (3.5, 6.5), 0.12)
    b.wall((0, 3.6), (3.5, 3.6), 0.10)
    bath_south = b.wall((3.5, 4.8), (5.5, 4.8), 0.10)
    b.wall((5.5, 4.8), (5.5, 6.5), 0.10)

    b.door(south, offset=6.0, width=0.90)  # entrada
    b.window(south, offset=1.0, width=1.5)  # habitación 2
    b.window(east, offset=1.5, width=2.0)  # sala
    b.window(north, offset=0.8, width=1.5)  # cocina, x de 7.7 a 6.2
    b.window(north, offset=3.7, width=0.6, height=0.60, sill=1.50)  # baño, x de 4.8 a 4.2
    b.window(north, offset=6.0, width=1.5)  # habitación 1, x de 2.5 a 1.0
    b.door(spine, offset=2.6, width=0.80)  # habitación 2
    b.door(spine, offset=3.75, width=0.80)  # habitación 1
    b.door(bath_south, offset=1.1, width=0.70)  # baño, x de 4.6 a 5.3

    b.space(
        "Habitación 1",
        [(0.10, 3.65), (3.44, 3.65), (3.44, 6.40), (0.10, 6.40)],
        "useful",
        (1.77, 5.0),
    )
    b.space(
        "Habitación 2",
        [(0.10, 0.10), (3.44, 0.10), (3.44, 3.55), (0.10, 3.55)],
        "useful",
        (1.77, 1.8),
    )
    b.space(
        "Baño",
        [(3.56, 4.85), (5.45, 4.85), (5.45, 6.40), (3.56, 6.40)],
        "service",
        (4.0, 6.0),
    )
    b.space(
        "Sala-comedor-cocina",
        [(3.56, 0.10), (8.40, 0.10), (8.40, 6.40), (5.55, 6.40), (5.55, 4.75), (3.56, 4.75)],
        "useful",
        (6.0, 2.5),
    )
    dims = b.dimensions(
        [
            Dimension((-0.10, -0.10), (8.60, -0.10), (4.25, -0.9)),
            Dimension((8.60, -0.10), (8.60, 6.60), (9.4, 3.25), angle=90),
        ]
    )
    return b.project, dims


def en_l() -> Model:
    """Planta en L de 10 × 10 m a ejes, brazos de 4 m y un muro diagonal a 45°.

    El chaflán va de (6, 4) a (4, 6) y lleva la puerta de entrada del estar. Un tabique en y=5
    separa el estar del dormitorio y llega al punto medio del chaflán.
    """
    b = _Builder("en_l", "A-MURO")
    south = b.wall((0, 0), (10, 0), 0.20)
    b.wall((10, 0), (10, 4), 0.20)
    b.wall((10, 4), (6, 4), 0.20)
    diagonal = b.wall((6, 4), (4, 6), 0.20)
    b.wall((4, 6), (4, 10), 0.20)
    north = b.wall((4, 10), (0, 10), 0.20)
    west = b.wall((0, 10), (0, 0), 0.20)
    partition = b.wall((0, 5), (5, 5), 0.10)

    # En el tramo del chaflán que da al estar, lejos del tabique que llega a su punto medio.
    b.door(diagonal, offset=0.25, width=0.90)
    b.door(partition, offset=2.0, width=0.80)
    b.window(south, offset=7.0, width=2.0)
    b.window(north, offset=1.0, width=2.0)
    b.window(west, offset=7.0, width=1.5)

    # Cara interior del chaflán: la recta x + y = 10 desplazada 0.10 m hacia el interior.
    c = 10 - 0.10 * math.sqrt(2)
    b.space(
        "Estar",
        [
            (0.10, 0.10),
            (9.90, 0.10),
            (9.90, 3.90),
            (c - 3.90, 3.90),
            (c - 4.95, 4.95),
            (0.10, 4.95),
        ],
        "useful",
        (5.0, 2.0),
    )
    b.space(
        "Dormitorio",
        [(0.10, 5.05), (c - 5.05, 5.05), (3.90, c - 3.90), (3.90, 9.90), (0.10, 9.90)],
        "useful",
        (2.0, 7.5),
    )
    dims = b.dimensions(
        [
            Dimension((-0.10, -0.10), (10.10, -0.10), (5.05, -0.9)),
            Dimension((-0.10, -0.10), (-0.10, 10.10), (-0.9, 5.05), angle=90),
        ]
    )
    return b.project, dims


def elevation_beside(msp: Modelspace, layers: Layers) -> None:
    """Lo que un plano real añade en la capa de muros a la planta de rect_simple: sombreados de
    muro y, a 10 m a la derecha, un alzado. El alzado tiene la fachada y una pilastra de 0.44 m
    con hiladas cada 0.20 m: las hiladas se emparejan como tramos de muro de 0.44 m que caben
    enteros en la huella de la pilastra y, mezclados con la planta, quedaban sin longitud."""
    attribs = {"layer": layers.wall}
    # Relleno del muro izquierdo de la planta.
    msp.add_hatch(color=8, dxfattribs=attribs).paths.add_polyline_path(
        [(-0.15, -0.15), (0.0, -0.15), (0.0, 3.15), (-0.15, 3.15)]
    )
    msp.add_lwpolyline(
        [(14.0, 0.0), (18.0, 0.0), (18.0, 2.8), (14.0, 2.8)], close=True, dxfattribs=attribs
    )
    pilaster = [(19.0, 0.0), (19.44, 0.0), (19.44, 2.8), (19.0, 2.8)]
    msp.add_lwpolyline(pilaster, close=True, dxfattribs=attribs)
    msp.add_hatch(color=8, dxfattribs=attribs).paths.add_polyline_path(pilaster)
    for i in range(1, 14):
        msp.add_lwpolyline([(19.0, 0.2 * i), (19.44, 0.2 * i)], dxfattribs=attribs)


STANDARD = DrawStyle()
CHAOTIC_LAYERS = Layers(
    wall="0", door="Capa1", window="xx_tmp", text="nueva", dimension="DEFPOINTS_2"
)


@dataclass(frozen=True)
class Case:
    model: Callable[[], Model]
    style: DrawStyle
    # Lo que el DXF dibuja además del modelo, y entonces qué vista es la planta.
    extras: Callable[[Modelspace, Layers], None] | None = None
    view: int | None = None


CASES: dict[str, Case] = {
    "rect_simple": Case(rect_simple, STANDARD),
    "apto_2hab": Case(apto_2hab, STANDARD),
    "apto_capas_caoticas": Case(lambda: apto_2hab("0"), DrawStyle(layers=CHAOTIC_LAYERS)),
    "en_l": Case(en_l, STANDARD),
    "muros_linea_doble": Case(apto_2hab, DrawStyle(wall_entities="lines")),
    "milimetros": Case(apto_2hab, DrawStyle(unit_scale=1000, insunits=units.MM)),
    "planta_y_alzado": Case(rect_simple, STANDARD, extras=elevation_beside, view=1),
}


def expected_project(case: str) -> Project:
    project, _ = CASES[case].model()
    project.id = project.name = case
    return project
