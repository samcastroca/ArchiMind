"""Qué se dibuja y desde dónde: las piezas del modelo, la cámara y los planos de recorte.

Las piezas son las del 3D de core (`model_pieces`): machones, dinteles y antepechos de cada
muro, con los vanos abiertos, y una losa por nivel. La explosión las separa en altura: cada
nivel sube `separacion` sobre el anterior y sus muros, `separacion` sobre su losa. Todo en
metros; Y+ es el norte.
"""

import math
from collections.abc import Sequence
from dataclasses import replace
from typing import Any, Literal

from archimind_core import Piece, model_pieces
from archimind_schema import Point2D, Project
from shapely import set_precision
from shapely.geometry.polygon import orient

IsoView = Literal["iso_ne", "iso_no", "iso_se", "iso_so"]
Side = Literal["izquierda", "derecha"]
Vector = tuple[float, float, float]

# Desde qué cuadrante mira cada isométrica: (signo de x, signo de y), con Y+ al norte.
ISO_FROM: dict[IsoView, tuple[int, int]] = {
    "iso_ne": (1, 1),
    "iso_no": (-1, 1),
    "iso_se": (1, -1),
    "iso_so": (-1, -1),
}
VIEW_NAMES: dict[IsoView, str] = {
    "iso_ne": "isométrica desde el noreste",
    "iso_no": "isométrica desde el noroeste",
    "iso_se": "isométrica desde el sureste",
    "iso_so": "isométrica desde el suroeste",
}
# Como en build_3d: rhino3dm y RhinoCommon no extruyen tramos de longitud nula.
GRID_M = 1e-6
# Margen del encuadre alrededor de la esfera que contiene las piezas.
FRAME_MARGIN_M = 1.0


class ViewError(Exception):
    """No hay nada que dibujar con esa vista; el mensaje está pensado para el usuario final."""


def drawing_pieces(
    project: Project, exploded: bool, separation: float, slab_thickness: float
) -> list[Piece]:
    """Las piezas del 3D, separadas si `exploded`. Se niega como `model_pieces`."""
    pieces = model_pieces(project, slab_thickness)
    if not exploded:
        return pieces
    ranks = {
        level.id: rank
        for rank, level in enumerate(sorted(project.levels, key=lambda lv: (lv.elevation, lv.id)))
    }
    level_of = {wall.id: wall.level_id for wall in project.walls}
    level_of |= {o.id: level_of[o.wall_id] for o in project.openings}
    moved = []
    for piece in pieces:
        if piece.kind == "losa":
            lift = 2 * ranks[piece.owner_id] * separation
        else:
            lift = (2 * ranks[level_of[piece.owner_id]] + 1) * separation
        moved.append(replace(piece, z0=piece.z0 + lift, z1=piece.z1 + lift))
    return moved


def solids_payload(pieces: Sequence[Piece]) -> list[dict[str, Any]]:
    """Las piezas como las recibe `hidden_lines`: el contorno antihorario, los huecos en sentido
    horario y sin repetir el primer punto."""
    solids = []
    for piece in pieces:
        footprint = orient(set_precision(piece.footprint, GRID_M), sign=1.0)
        solids.append(
            {
                "footprint": [list(p) for p in footprint.exterior.coords[:-1]],
                "holes": [[list(p) for p in hole.coords[:-1]] for hole in footprint.interiors],
                "z0": piece.z0,
                "z1": piece.z1,
            }
        )
    return solids


def iso_camera(view: IsoView, pieces: Sequence[Piece]) -> dict[str, Any]:
    """Isométrica: mira hacia abajo a 35.26°, desde el cuadrante de la vista."""
    sx, sy = ISO_FROM[view]
    return _camera(_unit((-sx, -sy, -1.0)), pieces)


def cut_camera(start: Point2D, end: Point2D, side: Side, pieces: Sequence[Piece]) -> dict[str, Any]:
    """Alzado paralelo al corte, mirando en horizontal hacia `side` del recorrido inicio → fin."""
    lx, ly = looking(start, end, side)
    return _camera((lx, ly, 0.0), pieces)


def looking(start: Point2D, end: Point2D, side: Side) -> Point2D:
    """La dirección en planta hacia la que mira el corte: la normal izquierda del recorrido o la
    derecha."""
    length = math.dist(start, end)
    tx, ty = (end[0] - start[0]) / length, (end[1] - start[1]) / length
    return (-ty, tx) if side == "izquierda" else (ty, -tx)


def cut_planes(start: Point2D, end: Point2D, side: Side, depth: float) -> list[dict[str, Any]]:
    """El plano del corte y el del fondo. HiddenLineDrawing recorta el semiespacio hacia el que
    apunta la normal (McNeel, discourse.mcneel.com/t/215626: el plano de un ClippingPlane se
    invierte antes de pasarlo, y la profundidad es un segundo plano con la normal opuesta): el
    del corte apunta hacia atrás y quita lo que queda detrás de la línea; el del fondo apunta
    hacia adelante y quita lo que está más allá de `depth`."""
    lx, ly = looking(start, end, side)
    return [
        {"origin": [start[0], start[1], 0.0], "normal": [-lx, -ly, 0.0]},
        {"origin": [start[0] + depth * lx, start[1] + depth * ly, 0.0], "normal": [lx, ly, 0.0]},
    ]


def default_depth(pieces: Sequence[Piece], start: Point2D, end: Point2D, side: Side) -> float:
    """Hasta el punto más lejano del edificio del lado que mira el corte."""
    lx, ly = looking(start, end, side)
    reach = max(
        (x - start[0]) * lx + (y - start[1]) * ly
        for piece in pieces
        for x, y in piece.footprint.exterior.coords
    )
    if reach <= 0:
        raise ViewError(
            f"Mirando hacia la {side} de la línea de corte no hay nada del edificio: prueba "
            "mirando hacia el otro lado."
        )
    return float(reach)


def _camera(direction: Vector, pieces: Sequence[Piece]) -> dict[str, Any]:
    """Cámara paralela que encuadra todas las piezas: centrada en ellas y alejada lo suficiente
    para que el plano cercano no corte nada. El «arriba» es la vertical proyectada en la vista."""
    xs = [x for p in pieces for x, _ in p.footprint.exterior.coords]
    ys = [y for p in pieces for _, y in p.footprint.exterior.coords]
    zs = [z for p in pieces for z in (p.z0, p.z1)]
    center = ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, (min(zs) + max(zs)) / 2)
    radius = math.dist((min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))) / 2
    radius += FRAME_MARGIN_M
    distance = 3 * radius
    dot = direction[2]
    up = _unit((-dot * direction[0], -dot * direction[1], 1.0 - dot * direction[2]))
    location = tuple(c - distance * d for c, d in zip(center, direction, strict=True))
    return {
        "location": list(location),
        "direction": list(direction),
        "up": list(up),
        "frustum": [-radius, radius, -radius, radius, distance - radius, distance + radius],
    }


def _unit(v: Vector) -> Vector:
    length = math.sqrt(sum(c * c for c in v))
    return (v[0] / length, v[1] / length, v[2] / length)
