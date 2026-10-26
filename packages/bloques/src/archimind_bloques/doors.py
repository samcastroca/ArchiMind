"""Generadores de puertas: batiente, batiente doble y corrediza.

El marco son dos jambas y un cabezal del perfil, centrados en el eje del muro; sin umbral.

- Planta: las jambas cortadas en trazo grueso. La batiente se dibuja abierta a 90°, con el
  arco que recorre su canto; la corrediza, cerrada sobre la cara del muro, con una flecha hacia
  donde abre.
- Alzado, visto desde afuera: el marco y las hojas. La batiente lleva el triángulo de apertura
  con el vértice en el lado de las bisagras, continuo si abre hacia quien mira (afuera) y
  discontinuo si abre adentro. La corrediza lleva una flecha, y su hoja va discontinua si corre
  por la cara de adentro, detrás del muro.
- 3D: el marco y las hojas cerradas, como piezas macizas.
"""

from archimind_bloques.geometry import (
    Box,
    Carpentry,
    Pen,
    Polyline,
    Stroke,
    arrow,
    box,
    line,
    quarter_arc,
    rect,
)
from archimind_bloques.naming import block_name
from archimind_bloques.params import (
    DoubleSwingDoor,
    SlidingDoor,
    SwingDoor,
    hand_sign,
    side_sign,
)


def swing_door(params: SwingDoor) -> Carpentry:
    face = params.profile.frame.face
    if hand_sign(params.hand, params.swing) > 0:
        return _swinging(params, [(params.width - face, -1)])
    return _swinging(params, [(face, 1)])


def double_swing_door(params: DoubleSwingDoor) -> Carpentry:
    face = params.profile.frame.face
    return _swinging(params, [(face, 1), (params.width - face, -1)])


def sliding_door(params: SlidingDoor) -> Carpentry:
    frame, overlap = params.profile.frame, params.profile.overlap
    width, leaf = params.width, params.leaf_width
    side = side_sign(params.side)
    toward = hand_sign(params.hand, params.side)
    x0 = frame.face - overlap
    x1 = x0 + leaf
    y0 = side * params.wall_thickness / 2
    y1 = y0 + side * params.leaf_thickness
    middle = (x0 + x1) / 2

    plan: list[Stroke] = [*_jambs_plan(params), rect(x0, y0, x1, y1, Pen.SEEN)]
    plan += arrow(
        (middle - toward * leaf / 4, y1 + side * leaf / 8),
        (middle + toward * leaf / 4, y1 + side * leaf / 8),
        Pen.THIN,
    )
    clear_top = params.height - frame.face
    inner = ((frame.face, 0), (frame.face, clear_top), (width - frame.face, clear_top))
    elevation: list[Stroke] = [
        *_frame_elevation(params),
        Polyline((*inner, (width - frame.face, 0)), Pen.SEEN),
        rect(x0, 0, x1, params.leaf_height, Pen.HIDDEN if side > 0 else Pen.SEEN),
    ]
    elevation += arrow(
        (middle - toward * leaf / 4, params.leaf_height / 2),
        (middle + toward * leaf / 4, params.leaf_height / 2),
        Pen.THIN,
    )
    leaf_box = box("hoja", "sash", (x0, y0, 0), (x1, y1, params.leaf_height))
    solids = [*_frame_solids(params), leaf_box]
    return Carpentry(
        name=block_name(params),
        kind="door",
        params=params,
        plan=tuple(plan),
        elevation=tuple(elevation),
        solids=tuple(solids),
        panes=(),
    )


def _swinging(params: SwingDoor | DoubleSwingDoor, leaves: list[tuple[float, int]]) -> Carpentry:
    """`leaves`: por hoja, la x de sus bisagras y hacia dónde queda su canto libre (±1 en x)."""
    side = side_sign(params.swing)
    face_y = side * params.profile.frame.depth / 2  # cara del marco del lado al que abre
    thickness, width, height = params.leaf_thickness, params.leaf_width, params.leaf_height
    # Quien mira el alzado está afuera: ve venir hacia sí la hoja que abre afuera.
    swing_pen = Pen.THIN if side < 0 else Pen.HIDDEN

    plan: list[Stroke] = list(_jambs_plan(params))
    elevation: list[Stroke] = list(_frame_elevation(params))
    solids: list[Box] = list(_frame_solids(params))
    for number, (hinge, toward) in enumerate(leaves, start=1):
        free = hinge + toward * width
        open_tip = (hinge, face_y + side * width)
        plan.append(rect(hinge, face_y, hinge + toward * thickness, open_tip[1], Pen.SEEN))
        plan.append(quarter_arc((hinge, face_y), (free, face_y), open_tip, Pen.THIN))
        elevation += [
            rect(hinge, 0, free, height, Pen.SEEN),
            line((free, 0), (hinge, height / 2), swing_pen),
            line((free, height), (hinge, height / 2), swing_pen),
        ]
        name = "hoja" if len(leaves) == 1 else f"hoja {number}"
        corner = (hinge, face_y - side * thickness, 0)
        solids.append(box(name, "sash", corner, (free, face_y, height)))
    return Carpentry(
        name=block_name(params),
        kind="door",
        params=params,
        plan=tuple(plan),
        elevation=tuple(elevation),
        solids=tuple(solids),
        panes=(),
    )


def _jambs_plan(params: SwingDoor | DoubleSwingDoor | SlidingDoor) -> list[Stroke]:
    face, half = params.profile.frame.face, params.profile.frame.depth / 2
    return [
        rect(0, -half, face, half, Pen.CUT),
        rect(params.width - face, -half, params.width, half, Pen.CUT),
    ]


def _frame_elevation(params: SwingDoor | DoubleSwingDoor | SlidingDoor) -> list[Stroke]:
    """Contorno exterior del marco, abierto abajo: la puerta no tiene umbral."""
    width, height = params.width, params.height
    return [Polyline(((0, 0), (0, height), (width, height), (width, 0)), Pen.SEEN)]


def _frame_solids(params: SwingDoor | DoubleSwingDoor | SlidingDoor) -> list[Box]:
    face, half = params.profile.frame.face, params.profile.frame.depth / 2
    width, height = params.width, params.height
    return [
        box("marco jamba inicial", "frame", (0, -half, 0), (face, half, height)),
        box("marco jamba final", "frame", (width - face, -half, 0), (width, half, height)),
        box("marco cabezal", "frame", (face, -half, height - face), (width - face, half, height)),
    ]
