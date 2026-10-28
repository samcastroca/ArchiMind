"""Modelo 3D por tramos. El volumen de cada muro es longitud × espesor × altura menos sus vanos.

El .3dm se relee con rhino3dm, que no calcula volúmenes: el de cada extrusión es el área de sus
perfiles por la longitud de su recorrido. Los stubs de rhino3dm 8.35 piden un argumento en
GetBoundingBox que la extensión no acepta y no declaran iterable la tabla de objetos.

El PNG axonométrico queda en tests/output/build_3d/ (ignorada por git) para revisión visual.
"""

import math
from pathlib import Path
from typing import Literal

import matplotlib

matplotlib.use("Agg")
import pytest
import rhino3dm
from archimind_core import (
    ExportError,
    HeightsMissing,
    Piece,
    build_3d,
    define_heights,
    slab_pieces,
    wall_pieces,
)
from archimind_core.build_3d import LAYERS
from archimind_schema import (
    WALL_THICKNESSES,
    Level,
    Opening,
    Project,
    Wall,
    new_id,
    wall_height,
    wall_length,
    wall_polygon,
)
from cases import expected_project
from hypothesis import given
from hypothesis import strategies as st
from matplotlib.figure import Figure
from mpl_toolkits.mplot3d.art3d import Poly3DCollection  # type: ignore[import-untyped]
from shapely import Polygon, unary_union

OUTPUT = Path(__file__).resolve().parents[3] / "tests" / "output" / "build_3d"
VOLUME_TOL = 0.005
SLAB = 0.15


def _expected_volume(project: Project, wall: Wall) -> float:
    height = wall_height(project, wall)
    openings = sum(
        o.width * wall.thickness * o.height for o in project.openings if o.wall_id == wall.id
    )
    return wall_length(wall) * wall.thickness * height - openings


@st.composite
def walls_with_openings(draw: st.DrawFn) -> Project:
    """Un muro recto o con un quiebre de 30° a 150°, con vanos que no se solapan y caben en él.

    Ningún vano entra en la esquina del quiebre (lo que el inglete interior retrocede): ahí su
    huella ya no es ancho × espesor, ni en el modelo ni en una obra."""
    height = draw(st.floats(2.2, 3.5))
    first = draw(st.floats(2.0, 10.0))
    thickness = draw(st.sampled_from(WALL_THICKNESSES))
    axis = [(0.0, 0.0), (first, 0.0)]
    corner = (first, first)  # tramo del eje que ocupa la esquina
    if draw(st.booleans()):
        turn = math.radians(draw(st.floats(30.0, 150.0)))
        setback = thickness / 2 * math.tan(turn / 2)
        corner = (first - setback, first + setback)
        second = draw(st.floats(2.0, 10.0))
        axis.append((first + second * math.cos(turn), second * math.sin(turn)))

    project = Project(id="p", name="p", scale_confirmed=True)
    level_id = new_id(project, "niv")
    project.levels.append(
        Level(
            id=level_id,
            name="PB",
            elevation=draw(st.floats(-3.0, 9.0)),
            default_height=height,
            height_confirmed=True,
        )
    )
    wall = Wall(
        id=new_id(project, "muro"),
        level_id=level_id,
        axis=axis,
        thickness=thickness,
    )
    project.walls.append(wall)

    widths = draw(st.lists(st.floats(0.4, 1.8), max_size=4))
    free = wall_length(wall) - sum(widths)
    if free <= 0:
        widths = []
        free = wall_length(wall)
    weights = draw(
        st.lists(st.floats(0.0, 1.0), min_size=len(widths) + 1, max_size=len(widths) + 1)
    )
    total = sum(weights) or 1.0
    cursor = 0.0
    for width, weight in zip(widths, weights, strict=False):
        cursor += free * weight / total
        if cursor < corner[1] and cursor + width > corner[0]:
            cursor += width
            continue
        kind: Literal["door", "window", "void"] = draw(st.sampled_from(["door", "window", "void"]))
        sill = draw(st.floats(0.3, 1.2)) if kind == "window" else 0.0
        project.openings.append(
            Opening(
                id=new_id(project, "vano"),
                wall_id=wall.id,
                kind=kind,
                offset=cursor,
                width=width,
                height=draw(st.floats(0.3, height - sill)),
                sill_height=sill,
            )
        )
        cursor += width
    return project


@given(walls_with_openings())
def test_wall_volume_is_the_wall_minus_its_openings(project: Project) -> None:
    [wall] = project.walls
    pieces = wall_pieces(project, wall)
    volume = sum(p.volume for p in pieces)
    assert volume == pytest.approx(_expected_volume(project, wall), rel=VOLUME_TOL)

    elevation = project.levels[0].elevation
    top = elevation + wall_height(project, wall)
    assert all(elevation - 1e-9 <= p.z0 < p.z1 <= top + 1e-9 for p in pieces)
    owners = {wall.id} | {o.id for o in project.openings}
    assert {p.owner_id for p in pieces} <= owners
    # Antepecho solo bajo los vanos con antepecho; dintel solo si el vano no llega arriba. Un
    # vano que cruza un quiebre tiene una pieza de cada una por tramo recto.
    for opening in project.openings:
        kinds = {p.kind for p in pieces if p.owner_id == opening.id}
        expected = set()
        if opening.sill_height + opening.height < wall_height(project, wall) - 0.001:
            expected.add("dintel")
        if opening.sill_height > 0.001:
            expected.add("antepecho")
        assert kinds == expected


@given(walls_with_openings())
def test_the_pieces_of_a_solid_wall_fill_its_footprint(project: Project) -> None:
    [wall] = project.walls
    project.openings.clear()
    pieces = wall_pieces(project, wall)
    union = unary_union([p.footprint for p in pieces])
    assert sum(p.footprint.area for p in pieces) == pytest.approx(wall_polygon(wall).area)
    assert union.symmetric_difference(wall_polygon(wall)).area < 1e-9


def _apto() -> Project:
    project = expected_project("apto_2hab")
    return define_heights(project, by_level={project.levels[0].id: 2.60}).project


def _profile_area(curve: rhino3dm.Curve) -> float:
    assert isinstance(curve, rhino3dm.PolylineCurve)
    points = [curve.Point(i) for i in range(curve.PointCount)]
    return float(abs(Polygon([(p.X, p.Y) for p in points]).area))


def _volume(extrusion: rhino3dm.Extrusion) -> float:
    outer = _profile_area(extrusion.Profile3d(0, 0.0))
    holes = sum(
        _profile_area(extrusion.Profile3d(i, 0.0)) for i in range(1, extrusion.ProfileCount)
    )
    start, end = extrusion.PathStart, extrusion.PathEnd
    return (outer - holes) * math.dist((start.X, start.Y, start.Z), (end.X, end.Y, end.Z))


def test_the_3dm_has_closed_solids_with_their_ids(tmp_path: Path) -> None:
    project = _apto()
    result = build_3d(project, tmp_path / "apto-3d.3dm", SLAB)
    model = rhino3dm.File3dm.Read(str(result.path))
    assert model.Settings.ModelUnitSystem == rhino3dm.UnitSystem.Meters

    layer_names = [model.Layers[i].Name for i in range(len(model.Layers))]
    assert layer_names == [name for name, _ in LAYERS.values()]
    ids = {w.id for w in project.walls} | {o.id for o in project.openings}
    ids |= {level.id for level in project.levels}
    volumes: dict[str, float] = {}
    slab_z: list[tuple[float, float]] = []
    for obj in model.Objects:  # type: ignore[attr-defined]
        extrusion = obj.Geometry
        assert isinstance(extrusion, rhino3dm.Extrusion) and extrusion.IsSolid
        owner = obj.Attributes.GetUserString("archimind_id")
        assert owner in ids, obj.Attributes.Name
        layer = layer_names[obj.Attributes.LayerIndex]
        volumes[layer] = volumes.get(layer, 0.0) + _volume(extrusion)
        if layer == "Losas":
            box = extrusion.GetBoundingBox()  # type: ignore[call-arg]
            slab_z.append((box.Min.Z, box.Max.Z))
    assert sum(result.counts.values()) == len(model.Objects)  # type: ignore[arg-type]

    walls = volumes["Machones"] + volumes["Dinteles"] + volumes["Antepechos"]
    expected = sum(_expected_volume(project, wall) for wall in project.walls)
    assert walls == pytest.approx(expected, rel=VOLUME_TOL)
    slab_area = sum(p.footprint.area for p in slab_pieces(project, SLAB))
    assert volumes["Losas"] == pytest.approx(slab_area * SLAB, rel=1e-6)
    # El apartamento mide 8.70 × 6.70 m por fuera de los muros: una sola losa, sin huecos.
    assert slab_area == pytest.approx(8.7 * 6.7, rel=VOLUME_TOL)
    assert slab_z == [pytest.approx((-SLAB, 0.0))]


def test_slabs_keep_the_holes_inside_the_walls() -> None:
    """Un patio encerrado por muros y sin espacio queda como hueco de la losa."""
    project = expected_project("rect_simple")
    project.spaces.clear()
    [slab] = slab_pieces(project, SLAB)
    assert len(slab.footprint.interiors) == 1
    assert slab.footprint.area == pytest.approx(4.3 * 3.3 - 4.0 * 3.0)


def test_missing_heights_build_nothing(tmp_path: Path) -> None:
    target = tmp_path / "apto-3d.3dm"
    with pytest.raises(HeightsMissing) as raised:
        build_3d(expected_project("apto_2hab"), target, SLAB)
    assert [m.default_height for m in raised.value.missing] == [2.60]
    assert not target.exists()


def test_an_unconfirmed_scale_builds_nothing(tmp_path: Path) -> None:
    project = _apto().model_copy(update={"scale_confirmed": False})
    target = tmp_path / "apto-3d.3dm"
    with pytest.raises(ExportError, match="confirma la escala"):
        build_3d(project, target, SLAB)
    assert not target.exists()


COLORS = {"machon": "#bbbbbb", "dintel": "#d08040", "antepecho": "#5a8cc8", "losa": "#808080"}


def _render(pieces: list[Piece], png: Path) -> None:
    """Axonometría de los prismas para revisarla a ojo."""
    figure = Figure(figsize=(9, 7))
    ax = figure.add_subplot(projection="3d")
    for piece in pieces:
        ring = list(piece.footprint.exterior.coords)[:-1]
        faces = [[(x, y, piece.z0) for x, y in ring], [(x, y, piece.z1) for x, y in ring]]
        for (x0, y0), (x1, y1) in zip(ring, ring[1:] + ring[:1], strict=True):
            faces.append(
                [(x0, y0, piece.z0), (x1, y1, piece.z0), (x1, y1, piece.z1), (x0, y0, piece.z1)]
            )
        ax.add_collection3d(
            Poly3DCollection(
                faces, facecolor=COLORS[piece.kind], edgecolor="#333333", linewidth=0.2
            )
        )
    xs = [x for p in pieces for x, _ in p.footprint.exterior.coords]
    ys = [y for p in pieces for _, y in p.footprint.exterior.coords]
    ax.set_xlim(min(xs), max(xs))
    ax.set_ylim(min(ys), max(ys))
    ax.set_zlim(min(p.z0 for p in pieces), max(p.z1 for p in pieces))
    ax.set_box_aspect((max(xs) - min(xs), max(ys) - min(ys), max(p.z1 for p in pieces) + SLAB))
    ax.view_init(elev=35, azim=-60)
    ax.set_axis_off()
    png.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(png, dpi=150, bbox_inches="tight")


def test_render_for_visual_review() -> None:
    project = _apto()
    pieces = [p for wall in project.walls for p in wall_pieces(project, wall)]
    pieces += slab_pieces(project, SLAB)
    png = OUTPUT / "apto_2hab.png"
    _render(pieces, png)
    assert png.read_bytes().startswith(b"\x89PNG")
