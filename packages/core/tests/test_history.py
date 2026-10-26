from pathlib import Path

import pytest
from archimind_core import HistoryError, commit, init_repo, load_version, recent_versions
from archimind_schema import Project, save_project


def _repo(tmp_path: Path) -> Path:
    save_project(Project(id="casa", name="Casa", scale_confirmed=False), tmp_path)
    (tmp_path / ".gitignore").write_text("salidas/\n", encoding="utf-8")
    init_repo(tmp_path)
    return tmp_path


def _rename(folder: Path, name: str) -> None:
    project = Project.model_validate_json((folder / "modelo.json").read_text(encoding="utf-8"))
    project.name = name
    save_project(project, folder)


def test_init_is_idempotent(tmp_path: Path) -> None:
    assert init_repo(tmp_path)
    assert not init_repo(tmp_path)


def test_commit_versions_changes_and_skips_empty_ones(tmp_path: Path) -> None:
    folder = _repo(tmp_path)
    first = commit(folder, "Crea el proyecto")
    assert first is not None
    assert commit(folder, "Nada que versionar") is None

    _rename(folder, "Casa de campo")
    second = commit(folder, "Renombra el proyecto: año 2026, sin acentos perdidos")

    versions = recent_versions(folder)
    assert [v.hash for v in versions] == [second, first]
    assert versions[0].message == "Renombra el proyecto: año 2026, sin acentos perdidos"
    assert len(versions[0].date) == len("2026-10-26")


def test_outputs_are_not_versioned(tmp_path: Path) -> None:
    folder = _repo(tmp_path)
    commit(folder, "Crea el proyecto")
    (folder / "salidas").mkdir()
    (folder / "salidas" / "vista.png").write_bytes(b"png")
    (folder / "notas.txt").write_text("ajeno al modelo", encoding="utf-8")
    assert commit(folder, "No hay cambios del modelo") is None


def test_load_version_reads_an_earlier_model(tmp_path: Path) -> None:
    folder = _repo(tmp_path)
    first = commit(folder, "Crea el proyecto")
    _rename(folder, "Casa de campo")
    commit(folder, "Renombra")

    assert load_version(folder, "HEAD~1").name == "Casa"
    assert first is not None and load_version(folder, first).name == "Casa"
    assert load_version(folder, "HEAD").name == "Casa de campo"


@pytest.mark.parametrize("version", ["abc1234", "HEAD~5", "--output=x", ""])
def test_unknown_versions_list_the_recent_ones(tmp_path: Path, version: str) -> None:
    folder = _repo(tmp_path)
    commit(folder, "Crea el proyecto")
    with pytest.raises(HistoryError, match="Versiones recientes: .* Crea el proyecto"):
        load_version(folder, version)


def test_a_project_without_versions_says_so(tmp_path: Path) -> None:
    folder = _repo(tmp_path)
    assert recent_versions(folder) == []
    with pytest.raises(HistoryError, match="aún no tiene versiones"):
        load_version(folder, "HEAD")
