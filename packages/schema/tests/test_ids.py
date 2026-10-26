import tempfile

import pytest
from archimind_schema import ID_PREFIXES, Level, Project, load_project, new_id, save_project
from hypothesis import given
from hypothesis import strategies as st

operations = st.lists(
    st.one_of(
        st.just(("crear", 0)),
        st.tuples(st.just("borrar"), st.integers(0, 50)),
        st.just(("guardar_y_cargar", 0)),
    ),
    max_size=40,
)


@given(operations)
def test_ids_nunca_se_repiten_tras_borrar_y_crear(steps: list[tuple[str, int]]) -> None:
    project = Project(id="p", name="", scale_confirmed=False)
    issued: list[str] = []
    with tempfile.TemporaryDirectory() as folder:
        for action, index in steps:
            if action == "crear":
                level_id = new_id(project, "niv")
                issued.append(level_id)
                project.levels.append(Level(id=level_id, name="", elevation=0, default_height=3))
            elif action == "borrar" and project.levels:
                project.levels.pop(index % len(project.levels))
            elif action == "guardar_y_cargar":
                save_project(project, folder)
                project = load_project(folder)
    assert len(issued) == len(set(issued))


def test_formato_con_cuatro_digitos() -> None:
    project = Project(id="p", name="", scale_confirmed=False)
    assert [new_id(project, prefix) for prefix in ID_PREFIXES] == [
        "niv-0001",
        "muro-0001",
        "vano-0001",
        "esp-0001",
        "blq-0001",
    ]
    assert new_id(project, "muro") == "muro-0002"


def test_prefijo_desconocido() -> None:
    with pytest.raises(ValueError, match="prefijo desconocido"):
        new_id(Project(id="p", name="", scale_confirmed=False), "puerta")
