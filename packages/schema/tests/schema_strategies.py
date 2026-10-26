"""Estrategias hypothesis que generan entidades y proyectos válidos."""

import math
from typing import Literal, get_args

from archimind_schema import (
    Annotation,
    Block,
    LayerRole,
    Level,
    Opening,
    Point2D,
    Project,
    Space,
    SpacePolygon,
    Wall,
    new_id,
    wall_length,
)
from hypothesis import strategies as st

coords = st.floats(min_value=-500, max_value=500, allow_nan=False, allow_infinity=False)
sizes = st.floats(min_value=0.5, max_value=50, allow_nan=False, allow_infinity=False)
fractions = st.floats(min_value=0.05, max_value=0.95, allow_nan=False, allow_infinity=False)
heights = st.floats(min_value=0.5, max_value=10, allow_nan=False, allow_infinity=False)


@st.composite
def rectangles(draw: st.DrawFn) -> SpacePolygon:
    """Rectángulo, opcionalmente con un hueco rectangular estrictamente interior."""
    x, y, w, h = draw(coords), draw(coords), draw(sizes), draw(sizes)
    exterior = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
    holes: list[list[Point2D]] = []
    if draw(st.booleans()):
        fx, fy = draw(st.floats(0.1, 0.4)), draw(st.floats(0.1, 0.4))
        hx0, hy0, hx1, hy1 = x + w * fx, y + h * fy, x + w * (1 - fx), y + h * (1 - fy)
        holes.append([(hx0, hy0), (hx1, hy0), (hx1, hy1), (hx0, hy1)])
    return SpacePolygon(exterior=exterior, holes=holes)


@st.composite
def stars(draw: st.DrawFn) -> SpacePolygon:
    """Polígono estrellado: radios variables sobre ángulos crecientes, siempre simple."""
    n = draw(st.integers(3, 12))
    cx, cy = draw(coords), draw(coords)
    exterior = []
    for k in range(n):
        angle = 2 * math.pi * (k + draw(st.floats(-0.3, 0.3))) / n
        radius = draw(sizes)
        exterior.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
    return SpacePolygon(exterior=exterior)


space_polygons = st.one_of(rectangles(), stars())


@st.composite
def wall_axes(draw: st.DrawFn) -> list[Point2D]:
    """Polilínea de 1 a 3 tramos, cada uno de al menos 0.5 m."""
    x, y = draw(coords), draw(coords)
    axis = [(x, y)]
    for _ in range(draw(st.integers(1, 3))):
        angle = draw(st.floats(0, 2 * math.pi))
        length = draw(sizes)
        x, y = x + length * math.cos(angle), y + length * math.sin(angle)
        axis.append((x, y))
    return axis


thicknesses = st.sampled_from([0.10, 0.12, 0.15, 0.20, 0.25])


@st.composite
def projects(draw: st.DrawFn) -> Project:
    """Proyecto coherente cuyos IDs salen de new_id, como en el uso real."""
    project = Project(
        id="proyecto-prueba",
        name=draw(st.text(max_size=20)),
        scale_confirmed=draw(st.booleans()),
        source_files=draw(st.lists(st.text(max_size=10), max_size=3)),
        layer_mapping=draw(
            st.dictionaries(st.text(max_size=8), st.sampled_from(get_args(LayerRole)), max_size=3)
        ),
    )
    for _ in range(draw(st.integers(1, 3))):
        project.levels.append(
            Level(
                id=new_id(project, "niv"),
                name=draw(st.text(max_size=10)),
                elevation=draw(st.floats(-10, 100)),
                default_height=draw(heights),
            )
        )
    level_ids = st.sampled_from([level.id for level in project.levels])
    for _ in range(draw(st.integers(0, 4))):
        wall = Wall(
            id=new_id(project, "muro"),
            level_id=draw(level_ids),
            axis=draw(wall_axes()),
            thickness=draw(thicknesses),
            height=draw(st.none() | heights),
            source_layer=draw(st.none() | st.text(max_size=10)),
        )
        project.walls.append(wall)
        for _ in range(draw(st.integers(0, 2))):
            width = wall_length(wall) * draw(st.floats(0.05, 0.5))
            kind: Literal["door", "window", "void"] = draw(
                st.sampled_from(["door", "window", "void"])
            )
            height = draw(heights)
            block = None
            if kind in ("door", "window") and draw(st.booleans()):
                block = Block(
                    id=new_id(project, "blq"),
                    name=draw(st.text(min_size=1, max_size=20)),
                    kind=kind,
                    width=width,
                    height=height,
                    parameters={"type": draw(st.text(max_size=10)), "width": width},
                )
                project.blocks.append(block)
            project.openings.append(
                Opening(
                    id=new_id(project, "vano"),
                    wall_id=wall.id,
                    kind=kind,
                    offset=(wall_length(wall) - width) * draw(fractions),
                    width=width,
                    height=height,
                    sill_height=draw(st.floats(0, 1.5)),
                    block_id=block.id if block else None,
                    block_side=draw(st.sampled_from(["left", "right"])) if block else None,
                )
            )
    for _ in range(draw(st.integers(0, 4))):
        project.spaces.append(
            Space(
                id=new_id(project, "esp"),
                level_id=draw(level_ids),
                name=draw(st.text(max_size=10)),
                polygon=draw(space_polygons),
                category=draw(
                    st.sampled_from(["useful", "balcony", "circulation", "service", "technical"])
                ),
            )
        )
    for _ in range(draw(st.integers(0, 3))):
        project.annotations.append(
            Annotation(
                text=draw(st.text(max_size=10)),
                position=(draw(coords), draw(coords)),
                kind=draw(st.sampled_from(["dimension", "level", "label"])),
            )
        )
    # Las listas se llenaron tras construir el proyecto: se valida el conjunto al final.
    return Project.model_validate(project.model_dump())
