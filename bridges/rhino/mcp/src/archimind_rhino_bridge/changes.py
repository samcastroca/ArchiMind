"""Lo que cambió en Rhino respecto del modelo que se cargó, como un `EditsDraft`.

Cada objeto llega como lo devuelve el puente: su `archimind_id`, su nombre y sus caras planas como
bucles de puntos en metros (el exterior primero). Una entidad se reconoce por su ID, no por la
capa. Se compara siempre contra el modelo cargado (el que guarda el .3dm), no contra el actual:
así los cambios hechos después en ArchiMind no se leen como ediciones de Rhino.

- Un muro recto se lee de la huella de su prisma, que tiene que seguir siendo un rectángulo: el
  eje va por el medio, a lo largo, y conserva el sentido del original; el espesor es el ancho y la
  altura, la del prisma. Un muro de varios tramos solo se compara: Rhino no lo edita.
- Un vano se lee en su muro (el nuevo, si el muro cambió): offset y ancho a lo largo del eje,
  antepecho y alto del prisma. Si quedó fuera del muro, conserva su posición en él.
- Un espacio se lee de su cara horizontal, con sus huecos, y su nombre del nombre del objeto (uno
  vacío o igual al ID no lo renombra).
- Los IDs que ya no están en Rhino se borran, y con un muro, sus vanos.
- Lo dibujado sin `archimind_id` en una subcapa ArchiMind es nuevo, con un `ref` temporal
  (`nuevo-N`) al que core pone un ID: en Muros, un prisma rectangular a la cota de un nivel; en
  Vanos, un prisma sobre un muro recto (existente o nuevo), sin tipo (`void`); en Espacios, una
  superficie plana, con el nombre del objeto.

Lo que cambia menos que la tolerancia (0.001 m) no cuenta; lo que no se puede leer queda igual y
se avisa.
"""

import math
from dataclasses import dataclass
from typing import Any

from archimind_schema import (
    ANGLE_TOL_DEG,
    LENGTH_TOL,
    EditsDraft,
    Level,
    NewOpening,
    NewSpace,
    NewWall,
    Opening,
    OpeningEdit,
    Point2D,
    Project,
    Space,
    SpaceEdit,
    SpacePolygon,
    Wall,
    WallEdit,
    opening_polygon,
    wall_height,
    wall_length,
    wall_polygon,
)
from shapely import Polygon
from shapely.geometry.polygon import orient

# Las medidas leídas se guardan al micrómetro: el ruido de coma flotante no llega al modelo.
DECIMALS = 6
_SIN_TOL = math.sin(math.radians(ANGLE_TOL_DEG))
NEW_SPACE_NAME = "Espacio nuevo"

Record = dict[str, Any]


@dataclass(frozen=True)
class Changes:
    draft: EditsDraft | None
    lines: list[str]  # una por entidad modificada, nueva o borrada, sin coordenadas
    notes: list[str]  # lo que no entra en el borrador y por qué


@dataclass(frozen=True)
class _Prism:
    footprint: Polygon
    z0: float
    z1: float


@dataclass(frozen=True)
class _Line:
    """Eje recto y espesor de un muro, el leído o el del modelo."""

    start: Point2D
    end: Point2D
    thickness: float


class _Refs:
    """Los `ref` temporales de las entidades nuevas: nuevo-1, nuevo-2…"""

    def __init__(self) -> None:
        self.count = 0

    def next(self) -> str:
        self.count += 1
        return f"nuevo-{self.count}"


def read_changes(base: Project, objects: list[Record], base_sha256: str) -> Changes:
    entities: list[Wall | Opening | Space] = [*base.walls, *base.openings, *base.spaces]
    known = {entity.id for entity in entities}
    notes: list[str] = []
    found: dict[str, list[Record]] = {}
    untagged: dict[str, list[Record]] = {}  # por subcapa
    for record in objects:
        tag = record.get("id")
        if not tag:
            layer = str(record.get("layer", "")).rsplit("::", 1)[-1]
            untagged.setdefault(layer, []).append(record)
        elif tag not in known:
            notes.append(f"{tag}: ese archimind_id no está en el modelo cargado; se ignora.")
        else:
            found.setdefault(tag, []).append(record)
    present: dict[str, Record | None] = {}
    for tag, records in found.items():
        present[tag] = records[0] if len(records) == 1 else None
        if len(records) > 1:
            notes.append(
                f"{tag} está {len(records)} veces en Rhino (¿una copia?): se deja igual. Borra la "
                "copia o quítale el archimind_id."
            )

    elevations = {level.id: level.elevation for level in base.levels}
    lines: list[str] = []
    refs = _Refs()
    deleted = [entity.id for entity in entities if entity.id not in present]
    deleted_walls = {wall_id for wall_id in deleted if wall_id.startswith("muro-")}

    wall_edits: list[WallEdit] = []
    lines_by_wall: dict[str, _Line] = {}
    for wall in base.walls:
        if len(wall.axis) == 2:
            lines_by_wall[wall.id] = _Line(wall.axis[0], wall.axis[-1], wall.thickness)
        wall_record = present.get(wall.id)
        if wall_record is None:
            continue
        result = _read_wall(base, wall, wall_record, elevations[wall.level_id], notes)
        if result is not None:
            edit, line, description = result
            lines_by_wall[wall.id] = line
            wall_edits.append(edit)
            lines.append(description)

    new_walls: list[NewWall] = []
    wall_levels = {wall.id: wall.level_id for wall in base.walls}
    for record in untagged.get("Muros", []):
        new_wall = _read_new_wall(base.levels, record, refs, notes)
        if new_wall is not None:
            new_walls.append(new_wall[0])
            lines_by_wall[new_wall[0].ref] = new_wall[1]
            wall_levels[new_wall[0].ref] = new_wall[0].level_id
            lines.append(new_wall[2])

    opening_edits: list[OpeningEdit] = []
    walls = {wall.id: wall for wall in base.walls}
    for opening in base.openings:
        if opening.wall_id in deleted_walls:
            if opening.id not in deleted:
                deleted.append(opening.id)
                if opening.id in present:
                    notes.append(f"{opening.id} se borra con su muro {opening.wall_id}.")
            continue
        opening_record = present.get(opening.id)
        if opening_record is None:
            continue
        wall = walls[opening.wall_id]
        opening_result = _read_opening(
            wall,
            opening,
            lines_by_wall.get(wall.id),
            opening_record,
            elevations[wall.level_id],
            notes,
        )
        if opening_result is not None:
            opening_edits.append(opening_result[0])
            lines.append(opening_result[1])

    new_openings: list[NewOpening] = []
    hosts = {key: line for key, line in lines_by_wall.items() if key not in deleted_walls}
    for record in untagged.get("Vanos", []):
        new_opening = _read_new_opening(record, hosts, wall_levels, elevations, refs, notes)
        if new_opening is not None:
            new_openings.append(new_opening[0])
            lines.append(new_opening[1])

    space_edits: list[SpaceEdit] = []
    for space in base.spaces:
        space_record = present.get(space.id)
        if space_record is None:
            continue
        space_result = _read_space(space, space_record, elevations[space.level_id], notes)
        if space_result is not None:
            space_edits.append(space_result[0])
            lines.append(space_result[1])

    new_spaces: list[NewSpace] = []
    for record in untagged.get("Espacios", []):
        new_space = _read_new_space(base.levels, record, refs, notes)
        if new_space is not None:
            new_spaces.append(new_space[0])
            lines.append(new_space[1])

    for entity_id in deleted:
        wall_id = next((o.wall_id for o in base.openings if o.id == entity_id), None)
        lines.append(
            f"{entity_id}: borrado con su muro {wall_id}"
            if wall_id in deleted_walls
            else f"{entity_id}: borrado"
        )

    draft = None
    if wall_edits or opening_edits or space_edits or deleted or refs.count:
        draft = EditsDraft(
            source="rhino",
            base_sha256=base_sha256,
            walls=wall_edits,
            openings=opening_edits,
            spaces=space_edits,
            deleted=deleted,
            new_walls=new_walls,
            new_openings=new_openings,
            new_spaces=new_spaces,
        )
    return Changes(draft, lines, notes)


# --- Muros ------------------------------------------------------------------------------------


def _read_wall(
    project: Project, wall: Wall, record: Record, elevation: float, notes: list[str]
) -> tuple[WallEdit, _Line, str] | None:
    prism = _prism(record)
    if isinstance(prism, str):
        notes.append(f"{wall.id}: no se pudo leer ({prism}); se deja igual.")
        return None
    if abs(prism.z0 - elevation) > LENGTH_TOL:
        notes.append(
            f"{wall.id} se movió en vertical: el modelo no guarda la cota de cada muro y se ignora."
        )
    base_height = wall_height(project, wall)
    if len(wall.axis) > 2:
        if (
            _distance(prism.footprint, _outline(wall_polygon(wall))) > LENGTH_TOL
            or abs(prism.z1 - prism.z0 - base_height) > LENGTH_TOL
        ):
            notes.append(
                f"{wall.id} tiene un eje de varios tramos: en Rhino solo se editan muros rectos; "
                "se deja igual."
            )
        return None
    corners = _rectangle(prism.footprint)
    if corners is None:
        notes.append(f"{wall.id}: su huella ya no es un rectángulo; se deja igual.")
        return None
    start, end = wall.axis[0], wall.axis[-1]
    line = _wall_line(corners, (start, end), wall_length(wall) >= wall.thickness)
    height = prism.z1 - prism.z0
    moved = max(math.dist(line.start, start), math.dist(line.end, end))
    changes = []
    if moved > LENGTH_TOL:
        old, new = wall_length(wall), math.dist(line.start, line.end)
        changes.append(
            f"largo {old:.2f} → {new:.2f} m"
            if abs(new - old) > LENGTH_TOL
            else f"movido {moved:.2f} m"
        )
    if abs(line.thickness - wall.thickness) > LENGTH_TOL:
        changes.append(f"espesor {wall.thickness:.3f} → {line.thickness:.3f} m")
    if abs(height - base_height) > LENGTH_TOL:
        changes.append(f"alto {base_height:.2f} → {height:.2f} m")
    if not changes:
        return None
    edit = WallEdit(
        id=wall.id,
        axis=[_point(line.start), _point(line.end)],
        thickness=_round(line.thickness),
        height=wall.height if abs(height - base_height) <= LENGTH_TOL else _round(height),
    )
    return edit, line, f"{wall.id}: {', '.join(changes)}"


def _read_new_wall(
    levels: list[Level], record: Record, refs: _Refs, notes: list[str]
) -> tuple[NewWall, _Line, str] | None:
    prism = _prism(record)
    if isinstance(prism, str):
        notes.append(f"Objeto nuevo en Muros: no se pudo leer ({prism}); no entra en el borrador.")
        return None
    level = _level_at(levels, prism.z0)
    if level is None:
        notes.append(
            f"Muro nuevo a la cota {prism.z0:.2f} m: no está en ningún nivel; no entra en el "
            "borrador."
        )
        return None
    corners = _rectangle(prism.footprint)
    if corners is None:
        notes.append("Muro nuevo cuya huella no es un rectángulo: no entra en el borrador.")
        return None
    line = _wall_line(corners, None)
    height = prism.z1 - prism.z0
    ref = refs.next()
    edit = NewWall(
        ref=ref,
        level_id=level.id,
        axis=[_point(line.start), _point(line.end)],
        thickness=_round(line.thickness),
        height=None if abs(height - level.default_height) <= LENGTH_TOL else _round(height),
    )
    length = math.dist(line.start, line.end)
    return edit, line, f"nuevo muro {ref}: largo {length:.2f} m, espesor {line.thickness:.3f} m"


def _wall_line(
    corners: list[Point2D], original: tuple[Point2D, Point2D] | None, along_long: bool = True
) -> _Line:
    """El eje por el medio del rectángulo, a lo largo del lado largo (o del corto, si el muro del
    modelo es más corto que su espesor), con el sentido del eje `original`; sin original (un muro
    nuevo), de menor a mayor x y luego y."""
    a, b, c, d = corners
    first, second = math.dist(a, b), math.dist(b, c)
    direction = _unit(*original) if original else None
    if direction is not None and abs(first - second) <= LENGTH_TOL:
        along_first = abs(_dot(_unit(a, b), direction)) >= abs(_dot(_unit(b, c), direction))
    else:
        along_first = (first > second) == along_long
    if along_first:  # el eje es paralelo a ab: une los lados da y bc
        start, end, thickness = _mid(d, a), _mid(b, c), second
    else:
        start, end, thickness = _mid(a, b), _mid(c, d), first
    if original is None or direction is None:
        if _point(end) < _point(start):
            start, end = end, start
        return _Line(start, end, thickness)
    alignment = _dot(_unit(start, end), direction)
    if alignment < 0 or (
        alignment == 0 and math.dist(end, original[0]) < math.dist(start, original[0])
    ):
        start, end = end, start
    return _Line(start, end, thickness)


# --- Vanos ------------------------------------------------------------------------------------


def _read_opening(
    wall: Wall,
    opening: Opening,
    line: _Line | None,
    record: Record,
    elevation: float,
    notes: list[str],
) -> tuple[OpeningEdit, str] | None:
    prism = _prism(record)
    if isinstance(prism, str):
        notes.append(f"{opening.id}: no se pudo leer ({prism}); se deja igual.")
        return None
    if line is None:  # muro de varios tramos: solo se compara
        if (
            _distance(prism.footprint, _outline(opening_polygon(wall, opening))) > LENGTH_TOL
            or abs(prism.z0 - elevation - opening.sill_height) > LENGTH_TOL
            or abs(prism.z1 - prism.z0 - opening.height) > LENGTH_TOL
        ):
            notes.append(
                f"{opening.id} está en un muro de varios tramos: en Rhino solo se editan los vanos "
                "de muros rectos; se deja igual."
            )
        return None
    corners = _rectangle(prism.footprint)
    if corners is None:
        notes.append(f"{opening.id}: su huella ya no es un rectángulo; se deja igual.")
        return None
    placed = _place(corners, line)
    if placed is None:
        notes.append(
            f"{opening.id} ya no está sobre su muro {wall.id} en Rhino: conserva su posición en "
            "el muro."
        )
        return None
    offset, width, _ = placed
    sill, height = prism.z0 - elevation, prism.z1 - prism.z0
    changes = []
    if abs(offset - opening.offset) > LENGTH_TOL:
        changes.append(f"desplazado {abs(offset - opening.offset):.2f} m en el muro")
    if abs(width - opening.width) > LENGTH_TOL:
        changes.append(f"ancho {opening.width:.2f} → {width:.2f} m")
    if abs(height - opening.height) > LENGTH_TOL:
        changes.append(f"alto {opening.height:.2f} → {height:.2f} m")
    if abs(sill - opening.sill_height) > LENGTH_TOL:
        changes.append(f"antepecho {opening.sill_height:.2f} → {sill:.2f} m")
    if not changes:
        return None
    edit = OpeningEdit(
        id=opening.id,
        offset=_round(max(offset, 0.0)),
        width=_round(width),
        height=_round(height),
        sill_height=_round(max(sill, 0.0)),
    )
    return edit, f"{opening.id}: {', '.join(changes)}"


def _read_new_opening(
    record: Record,
    hosts: dict[str, _Line],
    wall_levels: dict[str, str],
    elevations: dict[str, float],
    refs: _Refs,
    notes: list[str],
) -> tuple[NewOpening, str] | None:
    """Un vano nuevo va en el muro recto sobre el que cae; si cae en varios, en el más centrado."""
    prism = _prism(record)
    if isinstance(prism, str):
        notes.append(f"Objeto nuevo en Vanos: no se pudo leer ({prism}); no entra en el borrador.")
        return None
    corners = _rectangle(prism.footprint)
    if corners is None:
        notes.append("Vano nuevo cuya huella no es un rectángulo: no entra en el borrador.")
        return None
    candidates = []
    for wall_id, line in hosts.items():
        placed = _place(corners, line)
        if placed is not None:
            candidates.append((abs(placed[2]), wall_id, placed))
    if not candidates:
        notes.append("Vano nuevo que no cae sobre ningún muro recto: no entra en el borrador.")
        return None
    _, wall_id, (offset, width, _) = min(candidates)
    sill, height = prism.z0 - elevations[wall_levels[wall_id]], prism.z1 - prism.z0
    if sill < -LENGTH_TOL:
        notes.append(f"Vano nuevo en {wall_id} que empieza bajo el piso: no entra en el borrador.")
        return None
    ref = refs.next()
    edit = NewOpening(
        ref=ref,
        wall=wall_id,
        offset=_round(max(offset, 0.0)),
        width=_round(width),
        height=_round(height),
        sill_height=_round(max(sill, 0.0)),
    )
    return edit, f"nuevo vano {ref} en {wall_id}: ancho {width:.2f} m, alto {height:.2f} m"


def _place(corners: list[Point2D], line: _Line) -> tuple[float, float, float] | None:
    """Offset y ancho a lo largo del eje, y distancia al eje, de un rectángulo que cae dentro del
    muro con sus lados paralelos al eje; None si no cae."""
    direction = _unit(line.start, line.end)
    normal = (-direction[1], direction[0])
    side = _unit(corners[0], corners[1])
    parallel = abs(_cross(side, direction)) <= _SIN_TOL or abs(_dot(side, direction)) <= _SIN_TOL
    along = [_dot(_sub(p, line.start), direction) for p in corners]
    across = sum(_dot(_sub(p, line.start), normal) for p in corners) / 4
    length = math.dist(line.start, line.end)
    offset, width = min(along), max(along) - min(along)
    if (
        not parallel
        or abs(across) > line.thickness / 2 + LENGTH_TOL
        or offset < -LENGTH_TOL
        or offset + width > length + LENGTH_TOL
    ):
        return None
    return offset, width, across


# --- Espacios ---------------------------------------------------------------------------------


def _read_space(
    space: Space, record: Record, elevation: float, notes: list[str]
) -> tuple[SpaceEdit, str] | None:
    face = _flat_face(record)
    if face is None:
        notes.append(f"{space.id}: no se pudo leer (no es una superficie plana); se deja igual.")
        return None
    if abs(face[0][0][2] - elevation) > LENGTH_TOL:
        notes.append(f"{space.id} se movió en vertical: la cota de un espacio es la de su nivel.")
    polygon = _face_polygon(face)
    if not polygon.is_valid:
        notes.append(f"{space.id}: su contorno no es un polígono válido; se deja igual.")
        return None
    before = Polygon(space.polygon.exterior, space.polygon.holes)
    name = record.get("name") or ""
    renamed = bool(name.strip()) and name not in (space.id, space.name)
    reshaped = _distance(polygon, before) > LENGTH_TOL
    if not (renamed or reshaped):
        return None
    changes = []
    if reshaped:
        changes.append(f"contorno, área {before.area:.2f} → {polygon.area:.2f} m²")
    if renamed:
        changes.append(f"renombrado «{space.name}» → «{name}»")
    edit = SpaceEdit(
        id=space.id,
        polygon=_space_polygon(polygon) if reshaped else space.polygon,
        name=name if renamed else space.name,
    )
    return edit, f"{space.id}: {', '.join(changes)}"


def _read_new_space(
    levels: list[Level], record: Record, refs: _Refs, notes: list[str]
) -> tuple[NewSpace, str] | None:
    face = _flat_face(record)
    if face is None:
        notes.append(
            "Objeto nuevo en Espacios que no es una superficie plana: no entra en el borrador."
        )
        return None
    level = _level_at(levels, face[0][0][2])
    if level is None:
        notes.append(
            f"Espacio nuevo a la cota {face[0][0][2]:.2f} m: no está en ningún nivel; no entra en "
            "el borrador."
        )
        return None
    polygon = _face_polygon(face)
    if not polygon.is_valid:
        notes.append(
            "Espacio nuevo cuyo contorno no es un polígono válido: no entra en el borrador."
        )
        return None
    ref = refs.next()
    name = (record.get("name") or "").strip() or f"{NEW_SPACE_NAME} {ref.removeprefix('nuevo-')}"
    edit = NewSpace(ref=ref, level_id=level.id, name=name, polygon=_space_polygon(polygon))
    return edit, f"nuevo espacio {ref} «{name}»: {polygon.area:.2f} m²"


def _flat_face(record: Record) -> list[list[list[float]]] | None:
    """La cara plana mayor del objeto, o None si no tiene ninguna."""
    faces: list[list[list[list[float]]]] = record.get("faces") or []
    flat = [face for face in faces if face and _flat(face)]
    if not flat:
        return None
    return max(flat, key=lambda f: Polygon(_ring(f[0])).area)


def _face_polygon(face: list[list[list[float]]]) -> Polygon:
    return orient(Polygon(_ring(face[0]), [_ring(hole) for hole in face[1:]]), 1.0)


def _space_polygon(polygon: Polygon) -> SpacePolygon:
    return SpacePolygon(
        exterior=[_point(p) for p in polygon.exterior.coords[:-1]],
        holes=[[_point(p) for p in hole.coords[:-1]] for hole in polygon.interiors],
    )


# --- Geometría --------------------------------------------------------------------------------


def _level_at(levels: list[Level], z: float) -> Level | None:
    return next((level for level in levels if abs(level.elevation - z) <= LENGTH_TOL), None)


def _prism(record: Record) -> _Prism | str:
    """La huella y las cotas de un prisma vertical, o por qué no lo es."""
    faces = record.get("faces")
    if not faces:
        return "no es una extrusión ni una polisuperficie de caras planas"
    points = [p for face in faces for loop in face for p in loop]
    z0, z1 = min(p[2] for p in points), max(p[2] for p in points)
    if z1 - z0 <= LENGTH_TOL or any(
        min(abs(p[2] - z0), abs(p[2] - z1)) > LENGTH_TOL for p in points
    ):
        return "ya no es un prisma vertical"
    bottoms = [f for f in faces if f and _flat(f) and abs(f[0][0][2] - z0) <= LENGTH_TOL]
    tops = [f for f in faces if f and _flat(f) and abs(f[0][0][2] - z1) <= LENGTH_TOL]
    if not bottoms or not tops:
        return "le falta la cara de abajo o la de arriba"
    bottom = Polygon(_ring(max(bottoms, key=lambda f: Polygon(_ring(f[0])).area)[0]))
    top = Polygon(_ring(max(tops, key=lambda f: Polygon(_ring(f[0])).area)[0]))
    if not bottom.is_valid or _distance(bottom, top) > LENGTH_TOL:
        return "ya no es un prisma vertical"
    return _Prism(bottom, z0, z1)


def _rectangle(polygon: Polygon) -> list[Point2D] | None:
    """Las cuatro esquinas en orden si el polígono es un rectángulo (± 0.5° en cada esquina)."""
    simple = polygon.simplify(1e-6)
    corners = [(float(x), float(y)) for x, y in simple.exterior.coords[:-1]]
    if len(corners) != 4:
        return None
    for i in range(4):
        e1 = _unit(corners[i - 1], corners[i])
        e2 = _unit(corners[i], corners[(i + 1) % 4])
        if abs(_dot(e1, e2)) > _SIN_TOL:
            return None
    return corners


def _flat(face: list[list[list[float]]]) -> bool:
    z = face[0][0][2]
    return all(abs(p[2] - z) <= LENGTH_TOL for loop in face for p in loop)


def _ring(loop: list[list[float]]) -> list[Point2D]:
    points = [(p[0], p[1]) for p in loop]
    if len(points) > 1 and math.dist(points[0], points[-1]) <= 1e-9:
        points = points[:-1]
    return points


def _outline(polygon: Polygon) -> Polygon:
    """Solo el contorno exterior: el prisma de Rhino se extruye sin huecos (los tiene la huella
    de un muro de varios tramos que se cruza a sí mismo)."""
    return Polygon(polygon.exterior)


def _distance(a: Polygon, b: Polygon) -> float:
    return float(a.boundary.hausdorff_distance(b.boundary))


def _round(value: float) -> float:
    return round(value, DECIMALS)


def _point(p: tuple[float, ...] | Point2D) -> Point2D:
    return (_round(p[0]), _round(p[1]))


def _sub(a: Point2D, b: Point2D) -> Point2D:
    return (a[0] - b[0], a[1] - b[1])


def _unit(a: Point2D, b: Point2D) -> Point2D:
    dx, dy = _sub(b, a)
    norm = math.hypot(dx, dy)
    return (dx / norm, dy / norm) if norm else (0.0, 0.0)


def _dot(a: Point2D, b: Point2D) -> float:
    return a[0] * b[0] + a[1] * b[1]


def _cross(a: Point2D, b: Point2D) -> float:
    return a[0] * b[1] - a[1] * b[0]


def _mid(a: Point2D, b: Point2D) -> Point2D:
    return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
