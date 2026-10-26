import tempfile
from pathlib import Path

import pytest
from archimind_schema import MODEL_FILENAME, Project, load_project, save_project
from hypothesis import given
from schema_strategies import projects


@given(projects())
def test_ida_y_vuelta_json_sin_perdida(project: Project) -> None:
    with tempfile.TemporaryDirectory() as folder:
        save_project(project, folder)
        assert load_project(folder) == project
        assert [p.name for p in Path(folder).iterdir()] == [MODEL_FILENAME]


def test_guardar_sobrescribe_el_modelo_anterior(tmp_path: Path) -> None:
    save_project(Project(id="p", name="primero", scale_confirmed=False), tmp_path)
    save_project(Project(id="p", name="segundo", scale_confirmed=True), tmp_path)
    assert load_project(tmp_path).name == "segundo"


def test_cargar_sin_modelo_da_error_claro(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match=MODEL_FILENAME):
        load_project(tmp_path)
