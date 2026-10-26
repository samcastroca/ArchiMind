"""Vista en planta del modelo, renderizada a PNG con matplotlib.

Se trabaja con `Figure` directamente, sin pyplot: no hay backend global ni estado entre llamadas.
"""

from pathlib import Path

from archimind_schema import Project, opening_polygon, space_area, wall_polygon
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.patches import Patch, PathPatch
from matplotlib.path import Path as MplPath
from shapely import Polygon, affinity

from archimind_core.quantities import PRELIMINARY_LABEL

WALL_COLOR, OPENING_COLOR = "#2f6fd6", "#f08a24"
SPACE_COLORS = ["#7fc97f", "#beaed4", "#fdc086", "#ffff99", "#80b1d3", "#fb8072", "#b3de69"]


def draw_model(ax: Axes, project: Project, k: float = 1.0) -> list[Patch]:
    """Dibuja los espacios rellenos con su nombre y su área, los muros en azul y los vanos en
    naranja. `k` lleva los metros del modelo a las unidades de los ejes. Devuelve la leyenda."""
    for i, space in enumerate(project.spaces):
        polygon = Polygon(space.polygon.exterior, space.polygon.holes)
        _fill(ax, polygon, k, SPACE_COLORS[i % len(SPACE_COLORS)], 0.45)
        point = polygon.representative_point()
        area = f"{space_area(space):.2f} m²" + ("" if project.scale_confirmed else " (prelim.)")
        ax.annotate(
            f"{space.name}\n{area}",
            (point.x * k, point.y * k),
            ha="center",
            va="center",
            fontsize=9,
            bbox={"boxstyle": "round", "fc": "white", "ec": "none", "alpha": 0.8},
        )
    walls = {wall.id: wall for wall in project.walls}
    for wall in project.walls:
        _fill(ax, wall_polygon(wall), k, WALL_COLOR, 0.55)
    for opening in project.openings:
        # Un vano sobre un muro inexistente lo reporta validate; aquí no se dibuja.
        if opening.wall_id in walls:
            _fill(ax, opening_polygon(walls[opening.wall_id], opening), k, OPENING_COLOR, 0.85)
    return [
        Patch(color=WALL_COLOR, alpha=0.55, label=f"{len(project.walls)} muros"),
        Patch(color=OPENING_COLOR, alpha=0.85, label=f"{len(project.openings)} vanos"),
        Patch(color=SPACE_COLORS[0], alpha=0.45, label=f"{len(project.spaces)} espacios"),
    ]


def render_model(project: Project, png_path: str | Path, dpi: int = 150) -> Path:
    """Planta del modelo en metros, con el nombre del proyecto y la marca PRELIMINAR si la escala
    no está confirmada."""
    fig = Figure(figsize=(10, 10))
    ax = fig.add_axes((0.02, 0.06, 0.96, 0.88))
    legend = draw_model(ax, project)
    if not project.walls and not project.spaces:
        ax.text(0.5, 0.5, "El modelo aún no tiene muros ni espacios", ha="center", va="center")
    ax.set_aspect("equal")
    ax.autoscale_view()
    ax.set_axis_off()
    title = project.name if project.scale_confirmed else f"{project.name} · {PRELIMINARY_LABEL}"
    fig.text(0.01, 0.98, title, va="top", fontsize=12)
    fig.legend(handles=legend, loc="lower left", ncols=3, frameon=False)
    target = Path(png_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(target, dpi=dpi)
    return target


def _fill(ax: Axes, polygon: Polygon, k: float, color: str, alpha: float) -> None:
    scaled = affinity.scale(polygon, k, k, origin=(0, 0))
    for part in getattr(scaled, "geoms", [scaled]):
        rings = [part.exterior, *part.interiors]
        path = MplPath.make_compound_path(*(MplPath(list(r.coords), closed=True) for r in rings))
        ax.add_patch(PathPatch(path, facecolor=color, edgecolor=color, alpha=alpha, lw=0.5))
