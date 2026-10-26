from pathlib import Path

import pytest
from archimind_bloques import DEFAULT_CATALOG_PATH, CatalogError, load_catalog
from carpentry_cases import CATALOG

VALID_PROFILE = """
profiles:
  p:
    name: P
    types: [fixed_window]
    frame: {face: 0.05, depth: 0.08}
    sash: {face: 0.04, depth: 0.025}
    overlap: 0.03
    glass: 0.006
    sash_width: {min: 0.30, max: 1.20}
    sash_height: {min: 0.30, max: 2.40}
"""


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "catalog.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_the_real_catalog_loads_with_its_three_profiles() -> None:
    catalog = load_catalog()
    assert DEFAULT_CATALOG_PATH.name == "catalog.yaml"
    assert set(catalog.profiles) == {"aluminio_liviano", "aluminio_pesado", "madera"}


def test_looks_up_a_profile_by_key() -> None:
    assert CATALOG.profile("prueba").name == "Perfil de prueba"


def test_an_unknown_profile_lists_the_available_ones() -> None:
    with pytest.raises(
        CatalogError, match="no tiene el perfil «pvc». Los disponibles son: estrecho, prueba."
    ):
        CATALOG.profile("pvc")


def test_a_missing_file_is_reported(tmp_path: Path) -> None:
    with pytest.raises(CatalogError, match="No se pudo leer el catálogo"):
        load_catalog(tmp_path / "no_existe.yaml")


def test_invalid_yaml_is_reported(tmp_path: Path) -> None:
    with pytest.raises(CatalogError, match="no es un YAML válido"):
        load_catalog(_write(tmp_path, "profiles: [a: b"))


def test_a_valid_profile_loads(tmp_path: Path) -> None:
    assert load_catalog(_write(tmp_path, VALID_PROFILE)).profile("p").types == ("fixed_window",)


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ("depth: 0.025}", "depth: 0.09}", "no cabe en el marco"),
        ("glass: 0.006", "glass: 0.03", "es más grueso que la hoja"),
        ("sash_width: {min: 0.30", "sash_width: {min: 0.08", "no deja lugar al vidrio"),
        ("sash_height: {min: 0.30", "sash_height: {min: 2.50", "supera al máximo"),
        ("types: [fixed_window]", "types: [garage_door]", "types"),
    ],
)
def test_inconsistent_profiles_are_rejected(
    tmp_path: Path, old: str, new: str, message: str
) -> None:
    with pytest.raises(CatalogError, match=message):
        load_catalog(_write(tmp_path, VALID_PROFILE.replace(old, new)))
