"""scene: el modelo como objetos para las capas ArchiMind:: de Rhino."""

import archimind_bridge as bridge
from archimind_rhino_bridge.scene import scene
from archimind_schema import Level, Opening, Project, Space, SpacePolygon, Wall, new_id
from hypothesis import given, settings
from schema_strategies import projects


def test_walls_openings_and_spaces() -> None:
    project = Project(id="p", name="p", scale_confirmed=True)
    level = Level(id=new_id(project, "niv"), name="1", elevation=3.0, default_height=2.5)
    wall = Wall(id=new_id(project, "muro"), level_id=level.id, axis=[(0, 0), (4, 0)], thickness=0.2)
    window = Opening(
        id=new_id(project, "vano"),
        wall_id=wall.id,
        kind="window",
        offset=1,
        width=1.5,
        height=1.2,
        sill_height=0.9,
    )
    room = Space(
        id=new_id(project, "esp"),
        level_id=level.id,
        name="A",
        category="useful",
        polygon=SpacePolygon(exterior=[(0, 0), (4, 0), (4, 3)]),
    )
    project.levels, project.walls, project.openings = [level], [wall], [window]
    project.spaces = [room]

    muro, vano, esp = scene(project)
    assert muro["layer"] == "Muros" and muro["kind"] == "prism"
    assert sorted(map(tuple, muro["footprint"])) == [(0, -0.1), (0, 0.1), (4, -0.1), (4, 0.1)]
    assert (muro["z0"], muro["z1"]) == (3.0, 5.5)
    assert vano["layer"] == "Vanos"
    corners = sorted((round(x, 9), round(y, 9)) for x, y in vano["footprint"])
    assert corners == [(1, -0.1), (1, 0.1), (2.5, -0.1), (2.5, 0.1)]
    assert (vano["z0"], vano["z1"]) == (3.9, 5.1)
    assert esp == {
        "id": "esp-0001",
        "layer": "Espacios",
        "kind": "surface",
        "exterior": [[0, 0], [4, 0], [4, 3]],
        "holes": [],
        "z": 3.0,
    }


@settings(max_examples=50, deadline=None)
@given(projects())
def test_the_bridge_accepts_every_scene(project: Project) -> None:
    objects = scene(project)
    bridge.check_load("C:/p", "0" * 64, "{}", objects)
    assert len(objects) == len(project.walls) + len(project.openings) + len(project.spaces)
