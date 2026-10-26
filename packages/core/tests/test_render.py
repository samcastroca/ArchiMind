from pathlib import Path

import pytest
from archimind_core import render_model
from archimind_schema import Project
from cases import expected_project

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


@pytest.mark.parametrize("confirmed", [True, False])
def test_renders_the_model_to_png(tmp_path: Path, confirmed: bool) -> None:
    project = expected_project("apto_2hab").model_copy(update={"scale_confirmed": confirmed})
    path = render_model(project, tmp_path / "salidas" / "vista.png")
    assert path.read_bytes().startswith(PNG_SIGNATURE)


def test_renders_an_empty_model(tmp_path: Path) -> None:
    project = Project(id="p", name="p", scale_confirmed=False)
    assert render_model(project, tmp_path / "vista.png").read_bytes().startswith(PNG_SIGNATURE)
