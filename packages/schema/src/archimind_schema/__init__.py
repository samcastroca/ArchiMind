"""Modelo semántico del plano (Pydantic v2) y sus validadores."""

from archimind_schema.geometry import space_area, wall_height, wall_length, wall_polygon
from archimind_schema.ids import new_id
from archimind_schema.io import MODEL_FILENAME, load_project, save_project
from archimind_schema.models import (
    ANGLE_TOL_DEG,
    ID_PREFIXES,
    LENGTH_TOL,
    WALL_THICKNESSES,
    Annotation,
    Level,
    Opening,
    Point2D,
    Project,
    Space,
    SpacePolygon,
    Wall,
)
from archimind_schema.validation import Problem, validate

__all__ = [
    "ANGLE_TOL_DEG",
    "ID_PREFIXES",
    "LENGTH_TOL",
    "MODEL_FILENAME",
    "WALL_THICKNESSES",
    "Annotation",
    "Level",
    "Opening",
    "Point2D",
    "Problem",
    "Project",
    "Space",
    "SpacePolygon",
    "Wall",
    "load_project",
    "new_id",
    "save_project",
    "space_area",
    "validate",
    "wall_height",
    "wall_length",
    "wall_polygon",
]
