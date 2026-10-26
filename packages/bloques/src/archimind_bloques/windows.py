"""Generadores de ventanas: corrediza de 2 a 4 hojas, fija y proyectante.

El marco son dos jambas, un cabezal y un travesaño inferior del perfil, centrados en el eje del
muro; las hojas, cuatro piezas del perfil de hoja alrededor de su vidrio.

- Planta: las jambas cortadas en trazo grueso, cada hoja en su riel con su vidrio, el
  travesaño inferior visto y las caras del vano (y = ±espesor/2), que dan las tres o más líneas
  paralelas que el importador de core reconoce como ventana.
- Alzado, visto desde afuera, desde el antepecho: el marco, las hojas y los vidrios. La
  corrediza lleva una flecha por hoja hacia donde puede correr; la proyectante, el triángulo de
  apertura con el vértice arriba, en las bisagras, continuo porque abre hacia quien mira.
- 3D: el marco y las hojas como piezas macizas y cada vidrio como una superficie en el centro
  del fondo de su hoja.
"""

from archimind_bloques.geometry import (
    Box,
    Carpentry,
    Pane,
    Pen,
    Stroke,
    arrow,
    box,
    line,
    rect,
)
from archimind_bloques.naming import block_name
from archimind_bloques.params import AwningWindow, FixedWindow, SlidingWindow


class _Drawing:
    """Lo que va acumulando un generador de ventana."""

    def __init__(self, params: SlidingWindow | FixedWindow | AwningWindow) -> None:
        self.params = params
        self.plan: list[Stroke] = []
        self.elevation: list[Stroke] = []
        self.solids: list[Box] = []
        self.panes: list[Pane] = []
        self._frame()

    @property
    def clear_bottom(self) -> float:
        return self.params.sill_height + self.params.profile.frame.face

    @property
    def clear_top(self) -> float:
        return self.clear_bottom + self.params.leaf_height

    def _frame(self) -> None:
        params = self.params
        face, half = params.profile.frame.face, params.profile.frame.depth / 2
        width, wall = params.width, params.wall_thickness / 2
        bottom, top = params.sill_height, params.sill_height + params.height
        self.plan += [
            rect(0, -half, face, half, Pen.CUT),
            rect(width - face, -half, width, half, Pen.CUT),
            line((face, -half), (width - face, -half), Pen.THIN),
            line((face, half), (width - face, half), Pen.THIN),
            line((0, -wall), (width, -wall), Pen.THIN),
            line((0, wall), (width, wall), Pen.THIN),
        ]
        self.elevation += [
            rect(0, bottom, width, top, Pen.SEEN),
            rect(face, self.clear_bottom, width - face, self.clear_top, Pen.SEEN),
        ]
        self.solids += [
            box("marco jamba inicial", "frame", (0, -half, bottom), (face, half, top)),
            box("marco jamba final", "frame", (width - face, -half, bottom), (width, half, top)),
            box("marco cabezal", "frame", (face, -half, top - face), (width - face, half, top)),
            box(
                "marco travesaño inferior",
                "frame",
                (face, -half, bottom),
                (width - face, half, bottom + face),
            ),
        ]

    def glass(self, name: str, y: float, x0: float, x1: float, z0: float, z1: float) -> None:
        """Vidrio en el plano y, de x0 a x1 y de z0 a z1."""
        half = self.params.profile.glass / 2
        self.plan.append(rect(x0, y - half, x1, y + half, Pen.THIN))
        self.elevation.append(rect(x0, z0, x1, z1, Pen.THIN))
        self.panes.append(Pane(name, y, x0, x1, z0, z1))

    def sash(self, name: str, x0: float, x1: float, y0: float, y1: float) -> None:
        """Hoja de x0 a x1 en el fondo y0..y1, a todo el alto libre del marco, con su vidrio."""
        face = self.params.profile.sash.face
        z0, z1 = self.clear_bottom, self.clear_top
        self.plan.append(rect(x0, y0, x1, y1, Pen.SEEN))
        self.elevation.append(rect(x0, z0, x1, z1, Pen.SEEN))
        inner0, inner1 = x0 + face, x1 - face
        self.solids += [
            box(f"{name} montante inicial", "sash", (x0, y0, z0), (inner0, y1, z1)),
            box(f"{name} montante final", "sash", (inner1, y0, z0), (x1, y1, z1)),
            box(f"{name} travesaño inferior", "sash", (inner0, y0, z0), (inner1, y1, z0 + face)),
            box(f"{name} travesaño superior", "sash", (inner0, y0, z1 - face), (inner1, y1, z1)),
        ]
        glass_name = name.replace("hoja", "vidrio", 1)
        self.glass(glass_name, (y0 + y1) / 2, inner0, inner1, z0 + face, z1 - face)

    def carpentry(self) -> Carpentry:
        return Carpentry(
            name=block_name(self.params),
            kind="window",
            params=self.params,
            plan=tuple(self.plan),
            elevation=tuple(self.elevation),
            solids=tuple(self.solids),
            panes=tuple(self.panes),
        )


def sliding_window(params: SlidingWindow) -> Carpentry:
    face, leaf = params.profile.frame.face, params.leaf_width
    rail = params.profile.sash.depth
    if params.leaves == 4:
        # Las centrales se encuentran a tope en el centro del vano.
        starts = [face, face + leaf - params.profile.overlap, params.width / 2]
        starts.append(params.width - face - leaf)
    else:
        starts = [face + i * (leaf - params.profile.overlap) for i in range(params.leaves)]

    drawing = _Drawing(params)
    rails = params.leaf_rails
    middle = (drawing.clear_bottom + drawing.clear_top) / 2
    for i, (start, rail_index) in enumerate(zip(starts, rails, strict=True)):
        y0 = -params.rails * rail / 2 + rail_index * rail
        drawing.sash(f"hoja {i + 1}", start, start + leaf, y0, y0 + rail)
        # Una hoja corre hacia cada vecina que va en otro riel.
        center = start + leaf / 2
        for toward, neighbour in ((-1, i - 1), (1, i + 1)):
            if 0 <= neighbour < params.leaves and rails[neighbour] != rail_index:
                drawing.elevation += arrow(
                    (center, middle), (center + toward * leaf / 4, middle), Pen.THIN
                )
    return drawing.carpentry()


def fixed_window(params: FixedWindow) -> Carpentry:
    face = params.profile.frame.face
    drawing = _Drawing(params)
    x1 = face + params.leaf_width
    drawing.glass("vidrio", 0, face, x1, drawing.clear_bottom, drawing.clear_top)
    return drawing.carpentry()


def awning_window(params: AwningWindow) -> Carpentry:
    face, half = params.profile.frame.face, params.profile.sash.depth / 2
    x0, x1 = face, face + params.leaf_width
    drawing = _Drawing(params)
    drawing.sash("hoja", x0, x1, -half, half)
    bottom, top = drawing.clear_bottom, drawing.clear_top
    drawing.elevation += [
        line((x0, bottom), (params.width / 2, top), Pen.THIN),
        line((x1, bottom), (params.width / 2, top), Pen.THIN),
    ]
    return drawing.carpentry()
