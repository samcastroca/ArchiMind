"""Modelo 3D del proyecto en un .3dm de Rhino, en metros, con rhino3dm y sin booleanas.

rhino3dm no resta sólidos, así que cada muro se arma por tramos a lo largo de su eje: machones de
altura completa entre los vanos, un dintel sobre cada vano y un antepecho bajo cada vano con
antepecho (las ventanas). Cada pieza es la banda de un tramo recto del eje (con ingletes en los
quiebres, como `wall_polygon`) cortada en perpendicular entre dos distancias, extruida entre dos
cotas: las piezas de un muro llenan su huella sin huecos ni solapes. Cada nivel lleva una
losa de piso bajo su cota, con el contorno de sus espacios y sus muros.

Los stubs de rhino3dm 8.35 no coinciden con la extensión: no declaran el constructor de
PolylineCurve desde una Polyline ni el argumento de atributos de Add*, y dan por solo lectura
propiedades que se pueden asignar. Los `type: ignore` marcan esas llamadas; las firmas se
comprobaron en tiempo de ejecución y las pruebas releen el archivo.
"""

import math
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import rhino3dm
from archimind_schema import (
    LENGTH_TOL,
    Point2D,
    Project,
    Wall,
    validate,
    wall_height,
    wall_length,
    wall_polygon,
)
from shapely import Polygon, set_precision, unary_union
from shapely.geometry.polygon import orient

from archimind_core.export_dxf import ExportError, require_confirmed_scale
from archimind_core.heights import MissingHeight, missing_heights
from archimind_core.quantities import corner_patches

PieceKind = Literal["machon", "dintel", "antepecho", "losa"]
LAYERS: dict[PieceKind, tuple[str, tuple[int, int, int, int]]] = {
    "machon": ("Machones", (170, 170, 170, 255)),
    "dintel": ("Dinteles", (200, 120, 60, 255)),
    "antepecho": ("Antepechos", (90, 140, 200, 255)),
    "losa": ("Losas", (120, 120, 120, 255)),
}
PIECE_NAMES: dict[PieceKind, str] = {
    "machon": "machón",
    "dintel": "dintel",
    "antepecho": "antepecho",
    "losa": "losa",
}
ID_KEY = "archimind_id"
# Rejilla a la que se llevan las huellas antes de pasarlas a rhino3dm: la unión de shapely deja
# vértices que difieren en 1e-17 y rhino3dm no extruye una curva con tramos de longitud nula.
GRID_M = 1e-6


class HeightsMissing(Exception):
    """Faltan alturas para construir el 3D: no se suponen, se piden al usuario."""

    def __init__(self, missing: list[MissingHeight]) -> None:
        super().__init__(f"faltan alturas en {len(missing)} niveles")
        self.missing = missing


@dataclass(frozen=True)
class Piece:
    """Un prisma: `footprint` extruido de `z0` a `z1`. `owner_id` es el muro (machón), el vano
    (dintel y antepecho) o el nivel (losa)."""

    kind: PieceKind
    owner_id: str
    footprint: Polygon
    z0: float
    z1: float

    @property
    def volume(self) -> float:
        return float(self.footprint.area) * (self.z1 - self.z0)


@dataclass(frozen=True)
class Build3dResult:
    path: Path
    counts: dict[PieceKind, int]
    slab_thickness: float


def wall_pieces(project: Project, wall: Wall) -> list[Piece]:
    """Los tramos macizos del muro, de su inicio a su final."""
    z = _elevations(project)[wall.level_id]
    height = wall_height(project, wall)
    length = wall_length(wall)
    openings = sorted((o for o in project.openings if o.wall_id == wall.id), key=lambda o: o.offset)

    pieces = []
    cursor = 0.0
    for opening in openings:
        start = min(max(opening.offset, 0.0), length)
        end = min(opening.offset + opening.width, length)
        if start - cursor > LENGTH_TOL:
            pieces += _pieces("machon", wall.id, wall, cursor, start, z, z + height)
        if end - start > LENGTH_TOL:
            sill = min(opening.sill_height, height)
            top = min(opening.sill_height + opening.height, height)
            if height - top > LENGTH_TOL:
                pieces += _pieces("dintel", opening.id, wall, start, end, z + top, z + height)
            if sill > LENGTH_TOL:
                pieces += _pieces("antepecho", opening.id, wall, start, end, z, z + sill)
        cursor = max(cursor, end)
    if length - cursor > LENGTH_TOL:
        pieces += _pieces("machon", wall.id, wall, cursor, length, z, z + height)
    return pieces


def slab_pieces(project: Project, thickness: float) -> list[Piece]:
    """Por nivel, la losa bajo su cota: la unión de sus espacios y las huellas de sus muros,
    con las esquinas en L rellenas. Lo que queda encerrado sin espacio ni muro es un hueco."""
    shapes: dict[str, list[Polygon]] = defaultdict(list)
    for space in project.spaces:
        shapes[space.level_id].append(Polygon(space.polygon.exterior, space.polygon.holes))
    walls_by_level: dict[str, list[Wall]] = defaultdict(list)
    for wall in project.walls:
        walls_by_level[wall.level_id].append(wall)
    for level_id, walls in walls_by_level.items():
        shapes[level_id] += [wall_polygon(w) for w in walls]
        shapes[level_id] += corner_patches(walls)

    elevations = _elevations(project)
    pieces = []
    for level_id, polygons in shapes.items():
        union = unary_union(polygons)
        z = elevations[level_id]
        for part in getattr(union, "geoms", [union]):
            if isinstance(part, Polygon) and not part.is_empty:
                pieces.append(Piece("losa", level_id, part, z - thickness, z))
    return pieces


def build_3d(project: Project, path: str | Path, slab_thickness: float) -> Build3dResult:
    """Escribe el .3dm con las piezas de `model_pieces`; si se niega, no escribe nada."""
    pieces = model_pieces(project, slab_thickness)
    target = _write(pieces, Path(path))
    return Build3dResult(target, dict(Counter(p.kind for p in pieces)), slab_thickness)


def model_pieces(project: Project, slab_thickness: float) -> list[Piece]:
    """Los tramos macizos de todos los muros y las losas. Se niega si la escala no está
    confirmada, si el modelo tiene errores o si faltan alturas (`HeightsMissing`, con la
    lista)."""
    require_confirmed_scale(project)
    errors = [p for p in validate(project) if p.severity == "error"]
    if errors:
        listed = "; ".join(f"{p.code}: {p.message}" for p in errors[:5])
        more = f" (y {len(errors) - 5} más)" if len(errors) > 5 else ""
        raise ExportError(
            f"El modelo tiene {len(errors)} errores y no se construye en 3D: {listed}{more}. "
            "Revísalos con validar_modelo."
        )
    missing = missing_heights(project)
    if missing:
        raise HeightsMissing(missing)

    pieces = [piece for wall in project.walls for piece in wall_pieces(project, wall)]
    return pieces + slab_pieces(project, slab_thickness)


def _elevations(project: Project) -> dict[str, float]:
    return {level.id: level.elevation for level in project.levels}


def _pieces(
    kind: PieceKind, owner_id: str, wall: Wall, start: float, end: float, z0: float, z1: float
) -> list[Piece]:
    """El tramo del eje entre `start` y `end`, una pieza por cada tramo recto que toca: la
    banda del tramo recto (con ingletes en los quiebres) cortada en perpendicular. Las piezas de
    un muro lo llenan sin huecos ni solapes, aunque un corte caiga junto a un quiebre."""
    pieces = []
    cursor = 0.0
    for a, b, band in _bands(wall):
        length = math.dist(a, b)
        lo, hi = max(start, cursor) - cursor, min(end, cursor + length) - cursor
        if hi - lo > LENGTH_TOL:
            footprint = band.intersection(_slice(a, b, lo, hi, length + wall.thickness * 100))
            if isinstance(footprint, Polygon) and not footprint.is_empty:
                pieces.append(Piece(kind, owner_id, footprint, z0, z1))
        cursor += length
    return pieces


def _bands(wall: Wall) -> list[tuple[Point2D, Point2D, Polygon]]:
    """Cada tramo recto del eje con su banda: el espesor a cada lado, con los extremos en
    perpendicular al final del muro y en inglete en los quiebres, como `wall_polygon`."""
    axis = wall.axis
    normals = [_normal(a, b) for a, b in zip(axis, axis[1:], strict=False)]
    # Inglete en cada vértice: el vector que lleva del eje a la esquina de las dos caras.
    miters = [normals[0]]
    for n0, n1 in zip(normals, normals[1:], strict=False):
        dot = n0[0] * n1[0] + n0[1] * n1[1]
        miters.append(((n0[0] + n1[0]) / (1 + dot), (n0[1] + n1[1]) / (1 + dot)))
    miters.append(normals[-1])
    half = wall.thickness / 2
    bands = []
    for i, (a, b) in enumerate(zip(axis, axis[1:], strict=False)):
        ma, mb = miters[i], miters[i + 1]
        corners = [
            (a[0] + half * ma[0], a[1] + half * ma[1]),
            (b[0] + half * mb[0], b[1] + half * mb[1]),
            (b[0] - half * mb[0], b[1] - half * mb[1]),
            (a[0] - half * ma[0], a[1] - half * ma[1]),
        ]
        bands.append((a, b, Polygon(corners)))
    return bands


def _normal(a: Point2D, b: Point2D) -> Point2D:
    length = math.dist(a, b)
    return (-(b[1] - a[1]) / length, (b[0] - a[0]) / length)


def _slice(a: Point2D, b: Point2D, lo: float, hi: float, reach: float) -> Polygon:
    """La franja entre las perpendiculares al tramo a `lo` y `hi` de su inicio. En los extremos
    del tramo no corta: ahí manda el inglete de la banda."""
    length = math.dist(a, b)
    d = ((b[0] - a[0]) / length, (b[1] - a[1]) / length)
    n = (-d[1], d[0])
    lo = -reach if lo <= 0 else lo
    hi = length + reach if hi >= length else hi

    def at(s: float, w: float) -> Point2D:
        return (a[0] + s * d[0] + w * n[0], a[1] + s * d[1] + w * n[1])

    return Polygon([at(lo, -reach), at(hi, -reach), at(hi, reach), at(lo, reach)])


def _write(pieces: list[Piece], target: Path) -> Path:
    model = rhino3dm.File3dm()
    model.Settings.ModelUnitSystem = rhino3dm.UnitSystem.Meters  # type: ignore[misc]
    model.Settings.ModelAbsoluteTolerance = LENGTH_TOL  # type: ignore[misc]
    layers = {kind: model.Layers.AddLayer(name, color) for kind, (name, color) in LAYERS.items()}
    numbers: Counter[tuple[str, PieceKind]] = Counter()
    for piece in pieces:
        numbers[piece.owner_id, piece.kind] += 1
        name = f"{piece.owner_id} {PIECE_NAMES[piece.kind]} {numbers[piece.owner_id, piece.kind]}"
        model.Objects.AddExtrusion(  # type: ignore[call-arg]
            _extrusion(piece), _attributes(name, piece.owner_id, layers[piece.kind])
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    if not model.Write(str(target), 0):
        raise OSError(f"rhino3dm no pudo escribir {target}")
    return target


def _extrusion(piece: Piece) -> rhino3dm.Extrusion:
    """Extrusion.Create sube (+z) con el contorno exterior antihorario; los huecos son perfiles
    interiores en el mismo plano."""
    footprint = orient(set_precision(piece.footprint, GRID_M), sign=1.0)
    extrusion = rhino3dm.Extrusion.Create(
        _curve(footprint.exterior.coords, piece.z0), piece.z1 - piece.z0, True
    )
    if extrusion is None:
        raise OSError(f"rhino3dm no pudo extruir {piece.kind} de {piece.owner_id}")
    for hole in footprint.interiors:
        extrusion.AddInnerProfile(_curve(hole.coords, piece.z0))
    return extrusion


def _curve(coords: Iterable[Sequence[float]], z: float) -> rhino3dm.PolylineCurve:
    """Un anillo cerrado de shapely (el último punto repite el primero) como curva a la cota z."""
    polyline = rhino3dm.Polyline(0)
    for x, y in coords:
        polyline.Add(x, y, z)
    return rhino3dm.PolylineCurve(polyline)  # type: ignore[call-arg]


def _attributes(name: str, owner_id: str, layer_index: int) -> rhino3dm.ObjectAttributes:
    attributes = rhino3dm.ObjectAttributes()
    attributes.Name = name  # type: ignore[misc]
    attributes.LayerIndex = layer_index  # type: ignore[misc]
    attributes.SetUserString(ID_KEY, owner_id)
    return attributes
