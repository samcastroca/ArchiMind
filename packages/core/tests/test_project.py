import shutil
from pathlib import Path

import ezdxf
import pytest
from archimind_core import (
    DrawingError,
    MappingError,
    ProjectError,
    active_drawing,
    apply_mapping,
    import_drawing,
    open_project,
    proposals_to_mapping,
    propose_mapping,
    recent_versions,
)
from archimind_schema import (
    Level,
    Opening,
    Project,
    Space,
    Wall,
    load_project,
    save_project,
)
from golden import GOLDEN_DIR, assert_matches_golden


def _plan(folder: Path, case: str = "apto_2hab", name: str = "plano.dxf") -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    return Path(shutil.copy(GOLDEN_DIR / case / "input.dxf", folder / name))


def _imported(tmp_path: Path, case: str = "apto_2hab") -> Path:
    folder = open_project(tmp_path / "casa").folder
    import_drawing(folder, _plan(tmp_path / "fuera", case))
    return folder


# --- Abrir -----------------------------------------------------------------------------


def test_open_creates_the_whole_folder(tmp_path: Path) -> None:
    opened = open_project(tmp_path / "obras" / "casa")
    folder = opened.folder
    assert opened.created
    assert opened.project.id == opened.project.name == "casa"
    assert not opened.project.scale_confirmed
    assert (folder / "modelo.json").is_file()
    assert (folder / "salidas").is_dir()
    assert (folder / ".gitignore").read_text(encoding="utf-8") == "salidas/\n"
    assert (folder / ".git").exists()
    assert recent_versions(folder) == []


def test_open_keeps_an_existing_model(tmp_path: Path) -> None:
    folder = open_project(tmp_path / "casa").folder
    project = load_project(folder)
    project.name = "Casa de campo"
    save_project(project, folder)

    opened = open_project(folder)

    assert not opened.created
    assert opened.project.name == "Casa de campo"


def test_open_rejects_a_file(tmp_path: Path) -> None:
    (tmp_path / "casa").write_text("no soy una carpeta", encoding="utf-8")
    with pytest.raises(ProjectError, match="no es una carpeta"):
        open_project(tmp_path / "casa")


def test_operations_need_an_open_project(tmp_path: Path) -> None:
    with pytest.raises(ProjectError, match="ábrelo primero con abrir_proyecto"):
        import_drawing(tmp_path, _plan(tmp_path))


# --- Importar --------------------------------------------------------------------------


def test_import_copies_the_plan_and_makes_it_active(tmp_path: Path) -> None:
    folder = _imported(tmp_path)
    assert (folder / "planos" / "plano.dxf").is_file()
    assert load_project(folder).source_files == ["planos/plano.dxf"]
    assert active_drawing(folder).path == folder / "planos" / "plano.dxf"


def test_reimporting_moves_the_plan_to_the_end(tmp_path: Path) -> None:
    folder = _imported(tmp_path)
    import_drawing(folder, _plan(tmp_path / "fuera", "en_l", "otro.dxf"))
    drawing = import_drawing(folder, "planos/plano.dxf")  # relativa a la carpeta del proyecto
    assert drawing.path == folder / "planos" / "plano.dxf"
    assert load_project(folder).source_files == ["planos/otro.dxf", "planos/plano.dxf"]


def test_an_unreadable_plan_leaves_no_trace(tmp_path: Path) -> None:
    folder = open_project(tmp_path / "casa").folder
    pdf = tmp_path / "plano.pdf"
    pdf.write_bytes(b"%PDF-1.7")
    with pytest.raises(DrawingError, match="formato no admitido"):
        import_drawing(folder, pdf)
    assert not (folder / "planos").exists()
    assert load_project(folder).source_files == []


def test_active_drawing_needs_an_imported_plan(tmp_path: Path) -> None:
    folder = open_project(tmp_path / "casa").folder
    with pytest.raises(ProjectError, match="importar_plano"):
        active_drawing(folder)


# --- Aplicar el mapeo ------------------------------------------------------------------


def test_apply_mapping_rebuilds_the_model(tmp_path: Path) -> None:
    folder = _imported(tmp_path)
    drawing = active_drawing(folder)

    result = apply_mapping(folder, drawing, proposals_to_mapping(propose_mapping(drawing)))

    project = load_project(folder)
    assert project == result.project
    assert project.id == project.name == "casa"
    assert project.source_files == ["planos/plano.dxf"]
    assert project.layer_mapping["A-MURO"] == "walls"
    assert project.scale_confirmed
    assert_matches_golden(project, "apto_2hab")


def test_rebuilding_never_reuses_ids(tmp_path: Path) -> None:
    folder = _imported(tmp_path)
    drawing = active_drawing(folder)
    mapping = proposals_to_mapping(propose_mapping(drawing))

    first = apply_mapping(folder, drawing, mapping).project
    second = apply_mapping(folder, drawing, mapping).project

    assert len(second.walls) == len(first.walls)
    assert _ids(first).isdisjoint(_ids(second))


def _ids(project: Project) -> set[str]:
    groups: list[list[Level] | list[Wall] | list[Opening] | list[Space]] = [
        project.levels,
        project.walls,
        project.openings,
        project.spaces,
    ]
    return {entity.id for group in groups for entity in group}


@pytest.mark.parametrize(
    ("mapping", "message"),
    [
        ({"A-MURO": "muros"}, "Roles no válidos: A-MURO → muros"),
        ({"NO-EXISTE": "walls"}, "no están en plano.dxf: NO-EXISTE"),
    ],
)
def test_rejects_bad_mappings_without_writing(
    tmp_path: Path, mapping: dict[str, str], message: str
) -> None:
    folder = _imported(tmp_path)
    before = load_project(folder)
    with pytest.raises(MappingError, match=message):
        apply_mapping(folder, active_drawing(folder), mapping)
    assert load_project(folder) == before


def test_unconfirmed_scale_carries_into_the_model(tmp_path: Path) -> None:
    doc = ezdxf.readfile(GOLDEN_DIR / "milimetros" / "input.dxf")
    doc.header["$INSUNITS"] = 0
    doc.saveas(tmp_path / "plano.dxf")
    folder = open_project(tmp_path / "casa").folder
    drawing = import_drawing(folder, tmp_path / "plano.dxf")
    apply_mapping(folder, drawing, {"A-MURO": "walls"})
    assert not load_project(folder).scale_confirmed
