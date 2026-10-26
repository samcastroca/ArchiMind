"""Espacios: las caras que dejan los muros una vez cerrados sus vanos, con el nombre del texto
que cae dentro."""

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
)
from shapely import Point, Polygon, polygonize, set_precision, unary_union
from shapely.geometry.base import BaseGeometry

from archimind_core.build_rules import BuildRules
from archimind_core.extract import Label

UNNAMED = "Espacio sin nombre"
# Rejilla a la que se ajusta el cerramiento para que las caras salgan sin restos numéricos.
GRID = LENGTH_TOL / 100


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
    closed = closed_walls(project, material)
    faces = [
        face
        for face in polygonize([closed.boundary]).geoms
        if face.area >= rules.min_space_area_m2 and not closed.contains(face.representative_point())
    ]
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


def _polygon(face: Polygon) -> SpacePolygon:
    return SpacePolygon(
        exterior=_ring(face.exterior.coords), holes=[_ring(r.coords) for r in face.interiors]
    )


def _ring(coords: Sequence[Point2D]) -> list[Point2D]:
    """Sin el punto de cierre repetido: el modelo cierra los anillos implícitamente."""
    return [(x, y) for x, y in list(coords)[:-1]]


def _warning(code: str, message: str, ids: list[str] | None = None) -> Problem:
    return Problem(code=code, severity="warning", ids=ids or [], message=message)
