"""Espacios: las caras que dejan los muros una vez cerrados sus vanos, con el nombre del texto
que cae dentro. Cuando cambian los muros del modelo, `recompute_spaces` vuelve a sacar las caras
y cada una hereda el espacio que ocupaba."""

import re
from collections.abc import Sequence

from archimind_schema import (
    LENGTH_TOL,
    Point2D,
    Problem,
    Project,
    Space,
    SpacePolygon,
    new_id,
    opening_polygon,
    wall_polygon,
)
from shapely import Point, Polygon, polygonize, set_precision, unary_union
from shapely.geometry.base import BaseGeometry

from archimind_core.build_rules import BuildRules
from archimind_core.extract import Label
from archimind_core.quantities import corner_patches

UNNAMED = "Espacio sin nombre"
# Una cara hereda un espacio si comparten al menos esta fracción de la menor de las dos.
MIN_SHARED = 0.5
# Rejilla a la que se ajusta el cerramiento para que las caras salgan sin restos numéricos.
GRID = LENGTH_TOL / 100
# Ruido numérico del recálculo (medido: ≈1e-6 m). Una cara más cerca que esto de su espacio es
# el mismo contorno; un muro movido aunque sea 1 mm ya cambia el contorno.
SAME_CONTOUR = LENGTH_TOL / 10


def closed_walls(project: Project, material: BaseGeometry) -> BaseGeometry:
    """El material de los muros con cada vano tapado por su huella, alargada 1 mm a cada lado
    para que se suelde con las jambas: sus lados sobre las caras son las líneas virtuales."""
    walls = {wall.id: wall for wall in project.walls}
    patches = []
    for opening in project.openings:
        wall = walls[opening.wall_id]
        widened = opening.model_copy(
            update={
                "offset": max(0.0, opening.offset - LENGTH_TOL),
                "width": opening.width + 2 * LENGTH_TOL,
            }
        )
        patches.append(opening_polygon(wall, widened))
    return set_precision(unary_union([material, *patches]), GRID)


def place_spaces(
    project: Project,
    material: BaseGeometry,
    labels: Sequence[Label],
    rules: BuildRules,
) -> list[Problem]:
    """Añade al proyecto los espacios y devuelve los avisos.

    Las caras se obtienen con polygonize del contorno de los muros cerrados; las que caen dentro
    del material son muros y las de área despreciable, restos. El exterior no forma cara.
    """
    faces = _faces(project, material, rules.min_space_area_m2)
    faces.sort(key=lambda f: (-f.representative_point().y, f.representative_point().x))
    warnings: list[Problem] = []
    placed: set[int] = set()
    unnamed = 0
    for face in faces:
        inside = [i for i, label in enumerate(labels) if face.contains(Point(label.position))]
        placed.update(inside)
        names = list(dict.fromkeys(labels[i].text for i in inside))
        space_id = new_id(project, "esp")
        if not names:
            unnamed += 1
            name = f"{UNNAMED} {unnamed}"
            warnings.append(
                _warning(
                    "espacio_sin_nombre",
                    f"el espacio {space_id} ({face.area:.2f} m²) no contiene ningún texto: se "
                    f"llama «{name}»",
                    [space_id],
                )
            )
        else:
            name = " / ".join(names)
            if len(names) > 1:
                warnings.append(
                    _warning(
                        "espacio_varios_nombres",
                        f"el espacio {space_id} contiene varios textos ({', '.join(names)}): se "
                        f"llama «{name}»",
                        [space_id],
                    )
                )
        project.spaces.append(
            Space(
                id=space_id,
                level_id=project.levels[0].id,
                name=name,
                polygon=_polygon(face),
                category=rules.space_category,
            )
        )
    for i, label in enumerate(labels):
        if i not in placed:
            warnings.append(
                _warning(
                    "texto_fuera_de_espacio",
                    f"el texto «{label.text}» en ({label.position[0]:.2f}, "
                    f"{label.position[1]:.2f}) no cae en ningún espacio cerrado: puede faltar un "
                    "muro o un vano",
                )
            )
    return warnings


def recompute_spaces(project: Project, rules: BuildRules, edited: set[str]) -> list[Problem]:
    """Vuelve a sacar los espacios de los muros del modelo, por nivel, y devuelve los avisos.

    El material es la huella de los muros con las esquinas en L rellenas. Cada cara hereda ID,
    nombre y categoría del espacio actual con el que más área comparte (de mayor a menor
    solape, uno por cara); si la cara coincide con su contorno salvo ruido numérico
    (`SAME_CONTOUR`), este se conserva. Las caras sin espacio son espacios nuevos sin nombre;
    los espacios sin cara se quitan. `edited` son los espacios cuyo contorno se acaba de editar
    a mano: si el recálculo lo cambia, se avisa.
    """
    warnings: list[Problem] = []
    unnamed = _last_unnamed(project.spaces)
    spaces: list[Space] = []
    for level in project.levels:
        walls = [wall for wall in project.walls if wall.level_id == level.id]
        seeds = [space for space in project.spaces if space.level_id == level.id]
        if not walls:
            spaces += seeds
            continue
        ids = {wall.id for wall in walls}
        own = project.model_copy(
            update={"walls": walls, "openings": [o for o in project.openings if o.wall_id in ids]}
        )
        material = unary_union([*(wall_polygon(wall) for wall in walls), *corner_patches(walls)])
        faces = _faces(own, material, rules.min_space_area_m2)
        faces.sort(key=lambda f: (-f.representative_point().y, f.representative_point().x))
        shapes = {seed.id: Polygon(seed.polygon.exterior, seed.polygon.holes) for seed in seeds}
        claims = []
        for i, face in enumerate(faces):
            for seed in seeds:
                shared = face.intersection(shapes[seed.id]).area
                if shared >= MIN_SHARED * min(face.area, shapes[seed.id].area):
                    claims.append((shared, i, seed))
        claims.sort(key=lambda claim: -claim[0])
        owner: dict[int, Space] = {}
        for _, i, seed in claims:
            if i not in owner and seed.id not in {other.id for other in owner.values()}:
                owner[i] = seed
        for i, face in enumerate(faces):
            claimed = owner.get(i)
            if claimed is None:
                unnamed += 1
                space = Space(
                    id=new_id(project, "esp"),
                    level_id=level.id,
                    name=f"{UNNAMED} {unnamed}",
                    polygon=_polygon(face),
                    category=rules.space_category,
                )
                warnings.append(
                    _warning(
                        "espacio_nuevo",
                        f"los muros cierran un recinto nuevo de {face.area:.2f} m²: es el espacio "
                        f"{space.id} «{space.name}»",
                        [space.id],
                    )
                )
            elif face.boundary.hausdorff_distance(shapes[claimed.id].boundary) <= SAME_CONTOUR:
                space = claimed
            else:
                space = claimed.model_copy(update={"polygon": _polygon(face)})
                if claimed.id in edited:
                    warnings.append(
                        _warning(
                            "contorno_recalculado",
                            f"el contorno editado de {claimed.id} «{claimed.name}» se recalculó "
                            "con los muros nuevos",
                            [claimed.id],
                        )
                    )
            spaces.append(space)
        kept = {seed.id for seed in owner.values()}
        for seed in seeds:
            if seed.id in kept:
                continue
            shared, best = max(
                (
                    (faces[i].intersection(shapes[seed.id]).area, other)
                    for i, other in owner.items()
                ),
                key=lambda pair: pair[0],
                default=(0.0, None),
            )
            where = (
                f"su recinto se unió al de {best.id} «{best.name}»"
                if best is not None and shared > LENGTH_TOL**2
                else "los muros ya no lo cierran"
            )
            warnings.append(
                _warning("espacio_quitado", f"se quita {seed.id} «{seed.name}»: {where}", [seed.id])
            )
    spaces += [s for s in project.spaces if s.level_id not in {lvl.id for lvl in project.levels}]
    order = {space.id: i for i, space in enumerate(project.spaces)}
    project.spaces = sorted(spaces, key=lambda space: order.get(space.id, len(order)))
    return warnings


def _faces(project: Project, material: BaseGeometry, min_area: float) -> list[Polygon]:
    """Las caras que dejan los muros cerrados: ni dentro del material ni de área despreciable."""
    closed = closed_walls(project, material)
    return [
        face
        for face in polygonize([closed.boundary]).geoms
        if face.area >= min_area and not closed.contains(face.representative_point())
    ]


def _last_unnamed(spaces: Sequence[Space]) -> int:
    """El mayor N de los espacios «Espacio sin nombre N», para seguir la cuenta."""
    pattern = re.compile(rf"^{re.escape(UNNAMED)} (\d+)$")
    numbers = [int(m.group(1)) for space in spaces if (m := pattern.match(space.name))]
    return max(numbers, default=0)


def _polygon(face: Polygon) -> SpacePolygon:
    return SpacePolygon(
        exterior=_ring(face.exterior.coords), holes=[_ring(r.coords) for r in face.interiors]
    )


def _ring(coords: Sequence[Point2D]) -> list[Point2D]:
    """Sin el punto de cierre repetido: el modelo cierra los anillos implícitamente."""
    return [(x, y) for x, y in list(coords)[:-1]]


def _warning(code: str, message: str, ids: list[str] | None = None) -> Problem:
    return Problem(code=code, severity="warning", ids=ids or [], message=message)
