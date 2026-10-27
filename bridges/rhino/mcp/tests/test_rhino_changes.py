"""read_changes: lo editado en Rhino respecto del modelo cargado."""

import math

import pytest
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
    return math.dist(a, b) < 1e-5


def _mid(a: tuple[float, float], b: tuple[float, float]) -> tuple[float, float]:
    return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)


def _box(x0: float, y0: float, x1: float, y1: float) -> list[tuple[float, float]]:
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


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


@settings(max_examples=80, deadline=None)
@given(
    st.floats(-20, 20),
    st.floats(-20, 20),
    st.floats(0.5, 10),
    st.floats(0.05, 0.4),
    st.floats(-math.pi, math.pi),
)
def test_a_new_rectangle_on_the_wall_layer_is_a_new_wall(
    cx: float, cy: float, length: float, thickness: float, angle: float
) -> None:
    house = _house()
    document = _loaded(house)
    u, n = (math.cos(angle), math.sin(angle)), (-math.sin(angle), math.cos(angle))
    ring = [
        (
            cx + u[0] * a * length / 2 + n[0] * b * thickness / 2,
            cy + u[1] * a * length / 2 + n[1] * b * thickness / 2,
        )
        for a, b in [(-1, -1), (1, -1), (1, 1), (-1, 1)]
    ]
    document.add_untagged("Muros", ring, 0.0, 2.6)
    result = _read(house, document)
    assert result.draft is not None
    (wall,) = result.draft.new_walls
    assert abs(math.dist(*wall.axis) - length) < 1e-5
    assert abs(wall.thickness - thickness) < 1e-5
    assert _close(_mid(*wall.axis), (cx, cy)) and wall.height is None
    assert wall.axis[0] <= wall.axis[1]  # de menor a mayor x


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


def test_unknown_and_broken_objects_are_warned() -> None:
    house = _house()
    document = _loaded(house)
    document.add_untagged()
    document.objects[-1].tag = "muro-0099"
    document.break_object("vano-0001")
    result = _read(house, document)
    assert result.draft is None
    assert len(result.notes) == 2
    assert "muro-0099: ese archimind_id no está en el modelo cargado" in result.notes[0]
    assert "vano-0001: no se pudo leer" in result.notes[1]


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


def test_a_renamed_space() -> None:
    house = _house()
    document = _loaded(house)
    document.rename("esp-0001", "Living")
    result = _read(house, document)
    assert result.draft is not None
    (edit,) = result.draft.spaces
    assert edit.name == "Living" and edit.polygon == house.spaces[0].polygon
    assert result.lines == ["esp-0001: renombrado «Estar» → «Living»"]


@pytest.mark.parametrize("name", ["esp-0001", "", "  ", None])
def test_a_name_that_is_the_id_or_empty_does_not_rename(name: str | None) -> None:
    """Los .3dm cargados antes de llevar el nombre del espacio tienen el ID como nombre."""
    house = _house()
    document = _loaded(house)
    document.get("esp-0001").name = name
    assert _read(house, document).draft is None


def test_a_renamed_and_reshaped_space() -> None:
    house = _house()
    document = _loaded(house)
    document.rename("esp-0001", "Living")
    document.transform("esp-0001", lambda p: (5.0, p[1]) if p[0] == 4 else p)
    result = _read(house, document)
    assert result.draft is not None
    assert result.lines == [
        "esp-0001: contorno, área 11.70 → 14.62 m², renombrado «Estar» → «Living»"
    ]


def test_a_new_wall() -> None:
    house = _house()
    document = _loaded(house)
    document.add_untagged("Muros", _box(1, 1, 1.1, 4), 0.0, 2.6)
    result = _read(house, document)
    assert result.draft is not None
    (wall,) = result.draft.new_walls
    assert wall.ref == "nuevo-1" and wall.level_id == "niv-0001"
    assert wall.axis == [(1.05, 1), (1.05, 4)] and wall.thickness == 0.1 and wall.height is None
    assert result.lines == ["nuevo muro nuevo-1: largo 3.00 m, espesor 0.100 m"]


def test_a_new_wall_with_its_own_height() -> None:
    house = _house()
    document = _loaded(house)
    document.add_untagged("Muros", _box(1, 1, 1.1, 4), 0.0, 3.0)
    result = _read(house, document)
    assert result.draft is not None and result.draft.new_walls[0].height == 3.0


def test_a_new_wall_off_every_level_is_warned() -> None:
    house = _house()
    document = _loaded(house)
    document.add_untagged("Muros", _box(1, 1, 1.1, 4), 1.0, 3.0)
    result = _read(house, document)
    assert result.draft is None
    assert result.notes == [
        "Muro nuevo a la cota 1.00 m: no está en ningún nivel; no entra en el borrador."
    ]


def test_a_new_window_in_an_existing_wall() -> None:
    house = _house()
    document = _loaded(house)
    document.add_untagged("Vanos", _box(2.5, -0.075, 3.3, 0.075), 0.9, 2.1)
    result = _read(house, document)
    assert result.draft is not None
    (opening,) = result.draft.new_openings
    assert (opening.wall, opening.kind) == ("muro-0001", "void")
    measures = (opening.offset, opening.width, opening.height, opening.sill_height)
    assert measures == (2.5, 0.8, 1.2, 0.9)
    assert result.lines == ["nuevo vano nuevo-1 en muro-0001: ancho 0.80 m, alto 1.20 m"]


def test_a_new_door_in_a_new_wall() -> None:
    house = _house()
    document = _loaded(house)
    document.add_untagged("Muros", _box(1, 1, 1.1, 4), 0.0, 2.6)
    document.add_untagged("Vanos", _box(1, 2, 1.1, 2.9), 0.0, 2.0)
    result = _read(house, document)
    assert result.draft is not None
    (opening,) = result.draft.new_openings
    assert opening.wall == "nuevo-1" and opening.ref == "nuevo-2"
    assert (opening.offset, opening.width) == (1.0, 0.9)


def test_a_new_opening_on_no_wall_is_warned() -> None:
    house = _house()
    document = _loaded(house)
    document.add_untagged("Vanos", _box(2, 1, 2.8, 1.15), 0.0, 2.0)
    result = _read(house, document)
    assert result.draft is None
    assert result.notes == [
        "Vano nuevo que no cae sobre ningún muro recto: no entra en el borrador."
    ]


def test_a_new_opening_is_not_placed_in_a_deleted_wall() -> None:
    house = _house()
    document = _loaded(house)
    document.delete("muro-0001")
    document.add_untagged("Vanos", _box(2.5, -0.075, 3.3, 0.075), 0.9, 2.1)
    result = _read(house, document)
    assert result.draft is not None and result.draft.new_openings == []


def test_new_spaces_with_and_without_a_name() -> None:
    house = _house()
    document = _loaded(house)
    document.add_untagged("Espacios", _box(0, 3.1, 2, 5), name="Depósito")
    document.add_untagged("Espacios", _box(2, 3.1, 4, 5))
    result = _read(house, document)
    assert result.draft is not None
    named, unnamed = result.draft.new_spaces
    assert (named.name, named.level_id, named.category) == ("Depósito", "niv-0001", "useful")
    assert unnamed.name == "Espacio nuevo 2"
    assert result.lines == [
        "nuevo espacio nuevo-1 «Depósito»: 3.80 m²",
        "nuevo espacio nuevo-2 «Espacio nuevo 2»: 3.80 m²",
    ]
