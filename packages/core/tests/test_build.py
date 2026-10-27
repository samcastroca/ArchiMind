import math
import tempfile
from collections.abc import Callable
from pathlib import Path

import ezdxf
import pytest
from archimind_core import (
    BuildResult,
    BuildStageError,
    MappingError,
    ViewChoiceNeeded,
    ViewError,
    build_model,
    proposals_to_mapping,
    propose_mapping,
    read_drawing,
)
from archimind_core.layer_roles import Segment
from archimind_core.walls import wall_material
from archimind_schema import (
    Annotation,
    Level,
    Opening,
    Point2D,
    Project,
    Space,
    SpacePolygon,
    Wall,
    new_id,
    space_area,
)
from cases import CASES, STANDARD, expected_project
from dxf_writer import write_dxf
from ezdxf.document import Drawing as DXFDocument
from ezdxf.entities import LWPolyline
from golden import GOLDEN_DIR, assert_matches, assert_matches_golden
from hypothesis import example, given, settings
from hypothesis import strategies as st
from shapely import LineString, MultiPolygon, Polygon, affinity

MAPPING = {
    "A-MURO": "walls",
    "A-PUERTA": "doors",
    "A-VENTANA": "windows",
    "A-TEXTO": "text",
    "A-COTA": "dimensions",
}


def _build_case(case: str) -> BuildResult:
    drawing = read_drawing(GOLDEN_DIR / case / "input.dxf")
    mapping = proposals_to_mapping(propose_mapping(drawing))
    return build_model(drawing, mapping, view=CASES[case].view)


def _codes(result: BuildResult) -> list[str]:
    return sorted(p.code for p in result.problems)


@pytest.mark.parametrize("case", sorted(CASES))
def test_golden_case_is_rebuilt(case: str) -> None:
    result = _build_case(case)
    assert_matches_golden(result.project, case)
    # Lo que el DXF dibuja además del modelo se avisa: la otra vista y sus sombreados.
    extra = ["sombreado_en_capa_de_muros", "vista_elegida"] if CASES[case].extras else []
    assert _codes(result) == sorted(["valores_por_defecto", *extra])


def test_project_carries_scale_mapping_and_source() -> None:
    project = _build_case("milimetros").project
    assert project.scale_confirmed
    assert project.source_files == ["input.dxf"]
    assert project.layer_mapping["A-MURO"] == "walls"
    # Las medidas en mm llegan en metros.
    assert {round(w.thickness, 3) for w in project.walls} == {0.10, 0.12, 0.20}


def test_base_keeps_identity_sources_and_id_counters() -> None:
    base = Project(id="casa", name="Casa", scale_confirmed=False, source_files=["a.dxf"])
    base.next_ids["muro"] = 50
    drawing = read_drawing(GOLDEN_DIR / "rect_simple" / "input.dxf")

    project = build_model(drawing, MAPPING, base=base).project

    assert (project.id, project.name, project.source_files) == ("casa", "Casa", ["a.dxf"])
    assert project.scale_confirmed  # la escala es la del plano, no la de la base
    assert all(int(w.id.split("-")[1]) >= 50 for w in project.walls)
    assert base.next_ids["muro"] == 50  # la base no se toca


# --- Planos generados -------------------------------------------------------------------


def _build(
    project: Project,
    mapping: dict[str, str] = MAPPING,
    edit: Callable[[DXFDocument], None] | None = None,
) -> BuildResult:
    """Dibuja el modelo con el escritor de los fixtures, lo retoca y lo reconstruye."""
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "plano.dxf"
        write_dxf(project, [], STANDARD, path)
        if edit is not None:
            doc = ezdxf.readfile(path)
            edit(doc)
            doc.saveas(path)
        return build_model(read_drawing(path), mapping)


def _project() -> tuple[Project, str]:
    project = Project(id="p", name="p", scale_confirmed=True)
    level_id = new_id(project, "niv")
    project.levels.append(Level(id=level_id, name="Planta baja", elevation=0, default_height=2.6))
    return project, level_id


def _wall(project: Project, level_id: str, a: Point2D, b: Point2D, t: float) -> str:
    wall_id = new_id(project, "muro")
    project.walls.append(
        Wall(id=wall_id, level_id=level_id, axis=[a, b], thickness=t, source_layer="A-MURO")
    )
    return wall_id


def _opening(project: Project, wall_id: str, kind: str, offset: float, width: float) -> None:
    project.openings.append(
        Opening.model_validate(
            {
                "id": new_id(project, "vano"),
                "wall_id": wall_id,
                "kind": kind,
                "offset": offset,
                "width": width,
                "height": 2.1,
                "sill_height": 0.0,
            }
        )
    )


def _space(project: Project, level_id: str, name: str, polygon: Polygon) -> None:
    project.spaces.append(
        Space(
            id=new_id(project, "esp"),
            level_id=level_id,
            name=name,
            polygon=SpacePolygon(exterior=list(polygon.exterior.coords)[:-1]),
            category="useful",
        )
    )
    point = polygon.representative_point()
    project.annotations.append(Annotation(text=name, position=(point.x, point.y), kind="label"))


def _room(
    width: float = 4.0,
    depth: float = 3.0,
    t: float = 0.15,
    door: tuple[str, float, float] | None = ("door", 1.6, 0.9),
    label: bool = True,
) -> Project:
    """Habitación de `width` × `depth` libres con un vano en el muro sur."""
    project, level_id = _project()
    h = t / 2
    corners = [(-h, -h), (width + h, -h), (width + h, depth + h), (-h, depth + h)]
    ids = [
        _wall(project, level_id, a, b, t)
        for a, b in zip(corners, corners[1:] + corners[:1], strict=True)
    ]
    if door is not None:
        _opening(project, ids[0], *door)
    if label:
        _space(
            project, level_id, "Estudio", Polygon([(0, 0), (width, 0), (width, depth), (0, depth)])
        )
    return project


def _transformed(project: Project, angle: float, dx: float, dy: float) -> Project:
    def move(points: list[Point2D]) -> list[Point2D]:
        line = affinity.translate(affinity.rotate(LineString(points), angle, (0, 0)), dx, dy)
        return [(x, y) for x, y in line.coords]

    moved = project.model_copy(deep=True)
    for wall in moved.walls:
        wall.axis = move(wall.axis)
    for space in moved.spaces:
        space.polygon.exterior = move(space.polygon.exterior)
    for note in moved.annotations:
        note.position = move([note.position, note.position])[0]
    return Project.model_validate(moved.model_dump())


@settings(max_examples=25, deadline=None)
@given(
    t=st.sampled_from([0.10, 0.12, 0.15, 0.20, 0.25]),
    width=st.floats(2.5, 8.0),
    depth=st.floats(2.5, 8.0),
    door_width=st.floats(0.6, 1.2),
    door_at=st.floats(0, 1),
    angle=st.floats(0, 360),
    dx=st.floats(-1000, 1000),
    dy=st.floats(-1000, 1000),
)
def test_rotated_room_with_a_door_is_rebuilt(
    t: float,
    width: float,
    depth: float,
    door_width: float,
    door_at: float,
    angle: float,
    dx: float,
    dy: float,
) -> None:
    # La puerta cae en cualquier punto de la cara interior, hasta tocar la esquina.
    offset = t / 2 + door_at * (width - door_width)
    room = _room(width, depth, t, ("door", offset, door_width))
    expected = _transformed(room, angle, dx, dy)
    result = _build(expected)
    assert_matches(result.project, expected)
    assert _codes(result) == ["valores_por_defecto"]


@settings(max_examples=25, deadline=None)
@given(
    t=st.sampled_from([0.15, 0.20, 0.25]),
    lean=st.floats(-1.5, 1.5),
    at=st.floats(2.0, 4.0),
)
# Inclinaciones por debajo de la tolerancia angular: el tabique entra en el grupo de paralelos
# de los muros laterales, y cada par de caras debe medirse en su propio marco.
@example(t=0.15, lean=0.03125, at=2.0)
@example(t=0.15, lean=-0.03125, at=2.0)
def test_partition_meeting_both_walls_at_an_angle(t: float, lean: float, at: float) -> None:
    """Tabique de 0.10 de la cara sur a la norte, inclinado: dos uniones en T no rectas."""
    width, depth = 6.0, 4.0
    project, level_id = _project()
    h = t / 2
    corners = [(-h, -h), (width + h, -h), (width + h, depth + h), (-h, depth + h)]
    for a, b in zip(corners, corners[1:] + corners[:1], strict=True):
        _wall(project, level_id, a, b, t)
    _wall(project, level_id, (at, -h), (at + lean, depth + h), 0.10)
    partition = LineString([(at, -h), (at + lean, depth + h)]).buffer(0.05, cap_style="flat")
    rooms = Polygon([(0, 0), (width, 0), (width, depth), (0, depth)]).difference(partition)
    assert isinstance(rooms, MultiPolygon)
    for name, polygon in zip(
        ["Oeste", "Este"], sorted(rooms.geoms, key=lambda p: p.centroid.x), strict=True
    ):
        _space(project, level_id, name, polygon)
    result = _build(project)
    assert_matches(result.project, project)
    assert _codes(result) == ["valores_por_defecto"]


# --- Lo que no se resuelve de forma fiable ----------------------------------------------


def test_gap_without_symbol_is_a_void_with_warning() -> None:
    result = _build(_room(door=("void", 1.6, 0.9)))
    assert [o.kind for o in result.project.openings] == ["void"]
    assert "hueco_sin_simbolo" in _codes(result)
    assert len(result.project.spaces) == 1


def test_wide_gap_without_symbol_splits_the_wall() -> None:
    result = _build(_room(width=6.0, door=("void", 1.0, 3.5)))
    assert len(result.project.walls) == 5
    assert result.project.openings == []
    # Sin vano, el espacio queda abierto al exterior y su texto no cae en ninguno.
    assert result.project.spaces == []
    assert "texto_fuera_de_espacio" in _codes(result)


def test_door_drawn_over_a_continuous_wall_is_only_reported() -> None:
    def door_over_wall(doc: DXFDocument) -> None:
        msp = doc.modelspace()
        msp.add_line((1.6, 0), (1.6, 0.9), dxfattribs={"layer": "A-PUERTA"})
        msp.add_arc((1.6, 0), 0.9, 0, 90, dxfattribs={"layer": "A-PUERTA"})

    result = _build(_room(door=None), edit=door_over_wall)
    assert result.project.openings == []
    assert "simbolo_sin_hueco" in _codes(result)


def _door_block(doc: DXFDocument) -> None:
    block = doc.blocks.new("PUERTA_90")
    block.add_line((0, 0), (0, 0.9))
    block.add_arc((0, 0), 0.9, 0, 90)


def test_door_block_in_a_gap_types_the_opening() -> None:
    def block_in_gap(doc: DXFDocument) -> None:
        _door_block(doc)
        doc.modelspace().add_blockref("PUERTA_90", (1.525, 0), dxfattribs={"layer": "A-PUERTA"})

    result = _build(_room(door=("void", 1.6, 0.9)), edit=block_in_gap)
    assert [o.kind for o in result.project.openings] == ["door"]
    assert _codes(result) == ["valores_por_defecto"]


def test_door_block_without_gap_creates_the_opening_with_warning() -> None:
    def block_on_wall(doc: DXFDocument) -> None:
        _door_block(doc)
        doc.modelspace().add_blockref("PUERTA_90", (1.525, 0), dxfattribs={"layer": "0"})

    result = _build(_room(door=None), edit=block_on_wall)
    [opening] = result.project.openings
    assert opening.kind == "door"
    assert opening.width == pytest.approx(0.9, abs=0.01)
    assert "vano_sin_hueco" in _codes(result)


def test_door_block_away_from_walls_is_reported() -> None:
    def block_in_room(doc: DXFDocument) -> None:
        _door_block(doc)
        doc.modelspace().add_blockref("PUERTA_90", (2.0, 1.0), dxfattribs={"layer": "A-PUERTA"})

    result = _build(_room(door=None), edit=block_in_room)
    assert result.project.openings == []
    assert "simbolo_sin_muro" in _codes(result)


def test_axis_polyline_with_width_gives_walls() -> None:
    expected = _room(door=None)

    def axis_instead_of_outline(doc: DXFDocument) -> None:
        msp = doc.modelspace()
        for entity in [e for e in msp if e.dxf.layer == "A-MURO"]:
            msp.delete_entity(entity)
        axis = [wall.axis[0] for wall in expected.walls] + [expected.walls[0].axis[0]]
        msp.add_lwpolyline(axis, dxfattribs={"layer": "A-MURO", "const_width": 0.15})

    result = _build(expected, edit=axis_instead_of_outline)
    assert_matches(result.project, expected)


def test_open_line_without_width_is_reported() -> None:
    def stray_line(doc: DXFDocument) -> None:
        doc.modelspace().add_lwpolyline([(1, 1), (2, 1)], dxfattribs={"layer": "A-MURO"})

    result = _build(_room(), edit=stray_line)
    assert "linea_de_muro_sin_interpretar" in _codes(result)
    assert len(result.project.walls) == 4


def test_space_names_from_its_texts() -> None:
    def two_texts(doc: DXFDocument) -> None:
        doc.modelspace().add_text("Taller", dxfattribs={"layer": "A-TEXTO", "insert": (1, 1)})

    result = _build(_room(), edit=two_texts)
    assert [s.name for s in result.project.spaces] == ["Estudio / Taller"]
    assert "espacio_varios_nombres" in _codes(result)

    result = _build(_room(label=False))
    assert [s.name for s in result.project.spaces] == ["Espacio sin nombre 1"]
    assert "espacio_sin_nombre" in _codes(result)


def test_mixed_layer_is_ignored_with_warning() -> None:
    result = _build(_room(), mapping={**MAPPING, "A-PUERTA": "mixed"})
    assert "capa_mixta_ignorada" in _codes(result)
    assert [o.kind for o in result.project.openings] == ["void"]


def test_rejects_unknown_roles() -> None:
    drawing = read_drawing(GOLDEN_DIR / "rect_simple" / "input.dxf")
    with pytest.raises(MappingError, match="Roles no válidos"):
        build_model(drawing, {"A-MURO": "paredes"})


def test_expected_projects_rebuild_from_their_own_drawing() -> None:
    """El escritor y el reconstructor son inversos en los casos: sin cambiar nada."""
    project = expected_project("en_l")
    assert_matches(_build(project).project, project)


# --- Vistas, sombreados, limpieza y fallos ----------------------------------------------------


def test_plan_and_elevation_are_not_mixed() -> None:
    drawing = read_drawing(GOLDEN_DIR / "planta_y_alzado" / "input.dxf")
    with pytest.raises(ViewChoiceNeeded) as choice:
        build_model(drawing, MAPPING)
    plan, elevation = choice.value.views
    assert (plan.number, elevation.number) == (1, 2)
    assert plan.bounds == pytest.approx((-0.15, -0.15, 4.15, 3.15))
    assert elevation.bounds == pytest.approx((14.0, 0.0, 19.44, 2.8))
    with pytest.raises(ViewError, match="vistas de 1 a 2"):
        build_model(drawing, MAPPING, view=3)


def test_single_view_needs_no_choice() -> None:
    drawing = read_drawing(GOLDEN_DIR / "rect_simple" / "input.dxf")
    assert len(build_model(drawing, MAPPING, view=1).project.walls) == 4
    with pytest.raises(ViewError, match="una sola vista"):
        build_model(drawing, MAPPING, view=2)


def test_hatches_on_wall_layer_are_counted_not_used() -> None:
    result = _build_case("planta_y_alzado")
    [hatches] = [p for p in result.problems if p.code == "sombreado_en_capa_de_muros"]
    assert "'A-MURO' tiene 2 sombreados" in hatches.message
    assert "HATCH" not in str([p.message for p in result.problems if p is not hatches])


@settings(max_examples=25, deadline=None)
@given(t=st.floats(0.10, 0.50), course=st.floats(0.05, 0.50))
def test_pieces_inside_another_wall_are_dropped(t: float, course: float) -> None:
    """Las hiladas de una pilastra se emparejan como tramos que caben enteros en la huella de la
    pilastra: la unión los deja sin longitud y se descartan sin romper la reconstrucción."""

    def pilaster(doc: DXFDocument) -> None:
        msp = doc.modelspace()
        attribs = {"layer": "A-MURO"}
        msp.add_lwpolyline([(6, 0), (6 + t, 0), (6 + t, 3), (6, 3)], close=True, dxfattribs=attribs)
        for i in range(1, math.ceil(3 / course)):
            msp.add_lwpolyline([(6, i * course), (6 + t, i * course)], dxfattribs=attribs)

    result = _build(_room(), edit=pilaster)
    assert [s.name for s in result.project.spaces] == ["Estudio"]


def test_repeated_lines_and_vertices_change_nothing() -> None:
    expected = _room()

    def messy(doc: DXFDocument) -> None:
        msp = doc.modelspace()
        for entity in list(msp.query('LWPOLYLINE[layer=="A-MURO"]')):
            assert isinstance(entity, LWPolyline)
            points = list(entity.get_points("xy"))
            msp.add_lwpolyline(points, close=True, dxfattribs={"layer": "A-MURO"})
            entity.set_points([points[0], *points], format="xy")

    assert_matches(_build(expected, edit=messy).project, expected)


def test_arc_on_wall_layer_closes_the_outline(tmp_path: Path) -> None:
    """Un muro curvo (tramo con bulge) se aproxima con tramos rectos: el contorno cierra y el
    espacio llega hasta la curva."""
    bulge = 0.25
    doc = ezdxf.new("R2010", units=ezdxf.units.M)
    msp = doc.modelspace()
    for h in (0.0, 0.15):
        ring = [(-h, -h, 0), (4 + h, -h, 0), (4 + h, 3 + h, bulge), (-h, 3 + h, 0)]
        msp.add_lwpolyline(ring, format="xyb", close=True, dxfattribs={"layer": "A-MURO"})
    msp.add_text("Ábside", dxfattribs={"layer": "A-TEXTO", "insert": (2.0, 1.5)})
    doc.saveas(tmp_path / "curvo.dxf")

    result = build_model(read_drawing(tmp_path / "curvo.dxf"), MAPPING)
    angle = 4 * math.atan(bulge)
    radius = 2 / math.sin(angle / 2)
    segment = radius**2 / 2 * (angle - math.sin(angle))
    [space] = result.project.spaces
    assert space.name == "Ábside"
    assert space_area(space) == pytest.approx(12 + segment, rel=1e-3)
    assert "entidad_de_muro_no_soportada" not in _codes(result)


def test_self_crossing_outline_is_repaired() -> None:
    bowtie = [(0.0, 0.0), (2.0, 2.0), (2.0, 0.0), (0.0, 2.0)]
    segments = [Segment(a, b) for a, b in zip(bowtie, bowtie[1:] + bowtie[:1], strict=True)]
    material, open_segments = wall_material(segments)
    assert open_segments == []
    assert material.area == pytest.approx(2.0)


def test_unexpected_failure_names_the_stage(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(*_: object) -> None:
        raise ZeroDivisionError("division by zero")

    monkeypatch.setattr("archimind_core.build.reconstruct_walls", broken)
    drawing = read_drawing(GOLDEN_DIR / "rect_simple" / "input.dxf")
    with pytest.raises(BuildStageError, match="etapa de muros: ZeroDivisionError") as error:
        build_model(drawing, MAPPING)
    assert error.value.stage == "muros"


def test_unexpected_failure_names_the_entity(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(*_: object) -> None:
        raise ValueError("geometría imposible")

    monkeypatch.setattr("archimind_core.extract._add_wall", broken)
    drawing = read_drawing(GOLDEN_DIR / "rect_simple" / "input.dxf")
    with pytest.raises(BuildStageError) as error:
        build_model(drawing, MAPPING)
    message = str(error.value)
    assert "etapa de lectura del plano, en la entidad LWPOLYLINE #" in message
    assert "de la capa 'A-MURO': ValueError: geometría imposible" in message
