import shutil
from pathlib import Path

import pytest
from archimind_core import (
    MappingError,
    apply_mapping,
    proposals_to_mapping,
    propose_mapping,
    read_drawing,
)
from archimind_schema import Project, load_project, new_id, save_project
from golden import GOLDEN_DIR


def _drawing_in(folder: Path, case: str = "apto_2hab") -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    return Path(shutil.copy(GOLDEN_DIR / case / "input.dxf", folder / "plano.dxf"))


def test_creates_a_minimal_project_when_there_is_none(tmp_path: Path) -> None:
    folder = tmp_path / "casa"
    drawing = read_drawing(_drawing_in(folder))
    model_file = apply_mapping(folder, drawing, proposals_to_mapping(propose_mapping(drawing)))
    project = load_project(folder)
    assert model_file == folder.resolve() / "modelo.json"
    assert project.id == project.name == "casa"
    assert project.scale_confirmed
    assert project.source_files == ["plano.dxf"]
    assert project.layer_mapping["A-MURO"] == "walls"
    assert project.walls == []


def test_updates_an_existing_project_without_touching_the_rest(tmp_path: Path) -> None:
    folder = tmp_path / "casa"
    drawing = read_drawing(_drawing_in(folder))
    existing = Project(id="p", name="Casa", scale_confirmed=False, layer_mapping={"X": "ignore"})
    level_id = new_id(existing, "niv")
    save_project(existing, folder)

    apply_mapping(folder, drawing, {"A-MURO": "walls", "A-TEXTO": "text"})
    apply_mapping(folder, drawing, {"A-MURO": "walls", "A-COTA": "dimensions"})

    project = load_project(folder)
    assert project.layer_mapping == {"A-MURO": "walls", "A-COTA": "dimensions"}
    assert project.name == "Casa" and not project.scale_confirmed
    assert project.source_files == ["plano.dxf"]
    assert project.next_ids["niv"] == int(level_id.split("-")[1]) + 1


@pytest.mark.parametrize(
    ("mapping", "message"),
    [
        ({"A-MURO": "muros"}, "Roles no válidos: A-MURO → muros"),
        ({"NO-EXISTE": "walls"}, "no están en plano.dxf: NO-EXISTE"),
    ],
)
def test_rejects_bad_mappings(tmp_path: Path, mapping: dict[str, str], message: str) -> None:
    drawing = read_drawing(_drawing_in(tmp_path))
    with pytest.raises(MappingError, match=message):
        apply_mapping(tmp_path, drawing, mapping)
    assert not (tmp_path / "modelo.json").exists()


def test_unconfirmed_scale_carries_into_the_new_project(tmp_path: Path) -> None:
    import ezdxf

    doc = ezdxf.readfile(GOLDEN_DIR / "milimetros" / "input.dxf")
    doc.header["$INSUNITS"] = 0
    doc.saveas(tmp_path / "plano.dxf")
    drawing = read_drawing(tmp_path / "plano.dxf")
    apply_mapping(tmp_path, drawing, {"A-MURO": "walls"})
    assert not load_project(tmp_path).scale_confirmed
