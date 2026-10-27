"""read_changes: lo editado en Rhino respecto del modelo cargado."""

import math

from archimind_rhino_bridge.changes import Changes, read_changes
from archimind_rhino_bridge.scene import scene
from archimind_schema import (
    Level,
    Opening,
    Project,
    Space,
    SpacePolygon,
    Wall,
    new_id,
    validate,
    wall_length,
)
from fake_rhino import FakeDocument
from hypothesis import given, settings
from hypothesis import strategies as st
from schema_strategies import projects

SHA = "0" * 64
TOL = 1e-6


def _house() -> Project:
    """Un muro recto de 4 m con una puerta y un recinto al lado."""
    project = Project(id="casa", name="casa", scale_confirmed=True)
    level = Level(id=new_id(project, "niv"), name="PB", elevation=0.0, default_height=2.6)
    wall = Wall(
        id=new_id(project, "muro"), level_id=level.id, axis=[(0, 0), (4, 0)], thickness=0.15
    )
    door = Opening(
        id=new_id(project, "vano"),
        wall_id=wall.id,
        kind="door",
        offset=1.0,
        width=0.9,
        height=2.1,
        sill_height=0.0,
    )
    room = Space(
        id=new_id(project, "esp"),
        level_id=level.id,
        name="Estar",
        category="useful",
        polygon=SpacePolygon(exterior=[(0, 0.075), (4, 0.075), (4, 3), (0, 3)]),
    )
    project.levels, project.walls = [level], [wall]
    project.openings, project.spaces = [door], [room]
    return Project.model_validate(project.model_dump())


def _loaded(project: Project) -> FakeDocument:
    document = FakeDocument()
    document.load_model_layers("C:/casa", SHA, project.model_dump_json(), scene(project))
    return document


def _read(project: Project, document: FakeDocument) -> Changes:
    return read_changes(project, document.read_tagged_objects()["objects"], SHA)


def _close(a: tuple[float, float], b: tuple[float, float]) -> bool:
    return math.dist(a, b) < 1e-6


# --- Propiedades ------------------------------------------------------------------------------


@settings(max_examples=60, deadline=None)
@given(projects())
def test_what_was_loaded_reads_back_unchanged(project: Project) -> None:
    result = _read(project, _loaded(project))
    assert result.draft is None and result.notes == [] and result.lines == []


@settings(max_examples=60, deadline=None)
@given(
    projects(),
    st.floats(-50, 50),
    st.floats(-50, 50),
    st.floats(-math.radians(80), math.radians(80)),
)
def test_moving_everything_rigidly_moves_the_straight_walls(
    project: Project, dx: float, dy: float, angle: float
) -> None:
    document = _loaded(project)
    cos, sin = math.cos(angle), math.sin(angle)

    def motion(p: tuple[float, float]) -> tuple[float, float]:
        return (p[0] * cos - p[1] * sin + dx, p[0] * sin + p[1] * cos + dy)

    for obj in document.objects:
        document.transform(str(obj.tag), motion)
    result = _read(project, document)
    edits = {edit.id: edit for edit in result.draft.walls} if result.draft else {}
    moved = math.hypot(dx, dy) > 0.01 or abs(angle) > 0.01
    for wall in project.walls:
        if len(wall.axis) > 2:
            assert wall.id not in edits
            continue
        if not moved:
            continue
        edit = edits[wall.id]
        assert _close(edit.axis[0], motion(wall.axis[0]))
        assert _close(edit.axis[1], motion(wall.axis[1]))
        assert abs(edit.thickness - wall.thickness) < TOL and edit.height == wall.height
    # Los vanos se movieron con su muro: siguen en el mismo lugar del muro.
    assert result.draft is None or result.draft.openings == []
    assert result.draft is None or result.draft.deleted == []


@settings(max_examples=40, deadline=None)
@given(projects(), st.data())
def test_deleting_a_wall_deletes_its_openings(project: Project, data: st.DataObject) -> None:
    if not project.walls:
        return
    wall = data.draw(st.sampled_from(project.walls))
    document = _loaded(project)
    document.delete(wall.id)
    result = _read(project, document)
    assert result.draft is not None
    own = {o.id for o in project.openings if o.wall_id == wall.id}
    assert set(result.draft.deleted) == {wall.id} | own
    assert len(result.notes) == len(own)  # «se borra con su muro»


@settings(max_examples=40, deadline=None)
@given(projects(), st.data(), st.floats(-0.5, 0.5))
def test_sliding_an_opening_along_its_wall_changes_its_offset(
    project: Project, data: st.DataObject, delta: float
) -> None:
    walls = {w.id: w for w in project.walls}
    straight = [o for o in project.openings if len(walls[o.wall_id].axis) == 2]
    if not straight:
        return
    opening = data.draw(st.sampled_from(straight))
    wall = walls[opening.wall_id]
    if not 0 <= opening.offset + delta <= wall_length(wall) - opening.width or abs(delta) < 0.01:
        return
    (x0, y0), (x1, y1) = wall.axis
    length = wall_length(wall)
    document = _loaded(project)
    document.transform(
        opening.id,
        lambda p: (p[0] + (x1 - x0) / length * delta, p[1] + (y1 - y0) / length * delta),
    )
    result = _read(project, document)
    assert result.draft is not None
    (edit,) = result.draft.openings
    assert edit.id == opening.id and abs(edit.offset - (opening.offset + delta)) < 1e-5
    assert abs(edit.width - opening.width) < 1e-5


# --- Casos ------------------------------------------------------------------------------------


def test_moving_a_wall_alone_keeps_its_door_in_the_wall() -> None:
    house = _house()
    document = _loaded(house)
    document.move("muro-0001", 0, 0.5)
    result = _read(house, document)
    assert result.draft is not None
    (edit,) = result.draft.walls
    assert edit.axis == [(0, 0.5), (4, 0.5)] and edit.thickness == 0.15 and edit.height is None
    assert result.draft.openings == []
    assert result.lines == ["muro-0001: movido 0.50 m"]
    assert any("vano-0001 ya no está sobre su muro" in note for note in result.notes)


def test_stretching_a_wall_and_raising_it() -> None:
    house = _house()
    document = _loaded(house)
    document.transform("muro-0001", lambda p: (p[0] * 1.25, p[1]))
    document.set_top("muro-0001", 3.0)
    result = _read(house, document)
    assert result.draft is not None
    (edit,) = result.draft.walls
    assert edit.axis == [(0, 0), (5, 0)] and edit.height == 3.0
    assert result.lines == ["muro-0001: largo 4.00 → 5.00 m, alto 2.60 → 3.00 m"]


def test_a_thicker_wall() -> None:
    house = _house()
    document = _loaded(house)
    document.transform("muro-0001", lambda p: (p[0], p[1] * 2))
    result = _read(house, document)
    assert result.draft is not None
    assert result.draft.walls[0].thickness == 0.3
    assert result.lines == ["muro-0001: espesor 0.150 → 0.300 m"]


def test_a_wider_and_taller_door() -> None:
    house = _house()
    document = _loaded(house)
    document.transform("vano-0001", lambda p: (1.0 + (p[0] - 1.0) * 1.2, p[1]))
    document.set_top("vano-0001", 2.4)
    result = _read(house, document)
    assert result.draft is not None
    (edit,) = result.draft.openings
    assert (edit.offset, edit.width, edit.height, edit.sill_height) == (1.0, 1.08, 2.4, 0.0)


def test_a_space_with_another_outline() -> None:
    house = _house()
    document = _loaded(house)
    document.transform("esp-0001", lambda p: (5.0, p[1]) if p[0] == 4 else p)
    result = _read(house, document)
    assert result.draft is not None
    (edit,) = result.draft.spaces
    assert max(x for x, _ in edit.polygon.exterior) == 5.0
    assert result.lines == ["esp-0001: contorno, área 11.70 → 14.62 m²"]


def test_a_vertical_move_is_warned_and_ignored() -> None:
    house = _house()
    document = _loaded(house)
    document.move("muro-0001", 0, 0, 0.3)
    result = _read(house, document)
    assert result.draft is None
    assert any("se movió en vertical" in note for note in result.notes)


def test_a_copy_leaves_the_entity_as_is() -> None:
    house = _house()
    document = _loaded(house)
    document.duplicate("muro-0001")
    document.move("muro-0001", 1, 0)
    result = _read(house, document)
    assert result.draft is None
    assert any("está 2 veces en Rhino" in note for note in result.notes)


def test_untagged_unknown_and_broken_objects_are_warned() -> None:
    house = _house()
    document = _loaded(house)
    document.add_untagged()
    document.objects[-1].tag = "muro-0099"
    document.add_untagged("Espacios")
    document.break_object("vano-0001")
    result = _read(house, document)
    assert result.draft is None
    assert len(result.notes) == 3
    assert "muro-0099: ese archimind_id no está en el modelo cargado" in result.notes[0]
    assert "vano-0001: no se pudo leer" in result.notes[1]
    assert "1 objeto(s) sin archimind_id" in result.notes[2]


def test_a_footprint_that_is_no_longer_a_rectangle() -> None:
    house = _house()
    document = _loaded(house)
    document.transform("muro-0001", lambda p: (4.5, p[1]) if p == (4.0, 0.075) else p)
    result = _read(house, document)
    assert result.draft is None
    assert result.notes == ["muro-0001: su huella ya no es un rectángulo; se deja igual."]


def test_a_deleted_space() -> None:
    house = _house()
    document = _loaded(house)
    document.delete("esp-0001")
    result = _read(house, document)
    assert result.draft is not None and result.draft.deleted == ["esp-0001"]
    assert result.lines == ["esp-0001: borrado"]


def test_the_edited_model_stays_valid() -> None:
    """Lo que se lee de Rhino se puede llevar al modelo sin romperlo (lo hará core)."""
    house = _house()
    document = _loaded(house)
    document.move("muro-0001", 0, 0.5)
    document.move("vano-0001", 0.3, 0.5)
    result = _read(house, document)
    assert result.draft is not None
    edited = house.model_copy(deep=True)
    edited.walls[0].axis = result.draft.walls[0].axis
    edited.openings[0].offset = result.draft.openings[0].offset
    assert edited.openings[0].offset == 1.3
    assert not [p for p in validate(edited) if p.severity == "error"]
