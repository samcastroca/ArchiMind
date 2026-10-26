from pathlib import Path

import pytest
from archimind_bloques import DEFAULT_CATALOG_PATH, CatalogError, Profile, add_profile, load_catalog
from archimind_bloques.catalog import Range, Section
from carpentry_cases import CATALOG

VALID_PROFILE = """
defaults: {wall_thickness: 0.15, sill_height: 0.90, door_height: 2.10, window_height: 1.20}
profiles:
  p:
    name: P
    material: pvc
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


def test_the_real_catalog_has_materials_and_defaults() -> None:
    catalog = load_catalog()
    assert {p.material for p in catalog.profiles.values()} == {"aluminio", "madera"}
    assert catalog.defaults.wall_thickness > 0 and catalog.defaults.door_height > 0


def test_defaults_are_required(tmp_path: Path) -> None:
    text = VALID_PROFILE.split("\n", 2)[2]  # sin la línea de defaults
    with pytest.raises(CatalogError, match="defaults"):
        load_catalog(_write(tmp_path, text))


NEW_PROFILE = Profile(
    name="PVC serie 80",
    material="pvc",
    types=("sliding_window", "fixed_window"),
    frame=Section(face=0.06, depth=0.08),
    sash=Section(face=0.05, depth=0.03),
    overlap=0.03,
    glass=0.005,
    sash_width=Range(min=0.35, max=1.10),
    sash_height=Range(min=0.35, max=1.60),
)


def test_add_profile_appends_and_keeps_the_comments(tmp_path: Path) -> None:
    path = _write(tmp_path, "# Comentario del usuario.\n" + VALID_PROFILE)

    catalog = add_profile(path, "pvc_80", NEW_PROFILE)

    assert list(catalog.profiles) == ["p", "pvc_80"]
    assert load_catalog(path).profile("pvc_80") == NEW_PROFILE
    text = path.read_text(encoding="utf-8")
    assert text.startswith("# Comentario del usuario.\n")
    assert "  pvc_80:\n    name: PVC serie 80\n" in text
    assert "    frame: {face: 0.06, depth: 0.08}\n" in text


def test_add_profile_to_a_copy_of_the_real_catalog(tmp_path: Path) -> None:
    path = _write(tmp_path, DEFAULT_CATALOG_PATH.read_text(encoding="utf-8"))
    catalog = add_profile(path, "pvc_80", NEW_PROFILE)
    assert list(catalog.profiles)[-1] == "pvc_80"
    assert load_catalog(path).defaults == load_catalog().defaults


# Válido, pero con defaults después de profiles: un perfil agregado al final caería en defaults.
_DEFAULTS_LINE, _PROFILES = VALID_PROFILE.strip().split("\n", 1)
_PROFILES_FIRST = f"{_PROFILES}\n{_DEFAULTS_LINE}\n"


@pytest.mark.parametrize(
    ("key", "text", "message"),
    [
        ("p", VALID_PROFILE, r"ya tiene el perfil «p» \(P\)"),
        ("PVC 80", VALID_PROFILE, "minúsculas"),
        ("pvc_80", _PROFILES_FIRST, "profiles tiene que ser la última sección"),
    ],
)
def test_add_profile_leaves_the_file_untouched_on_error(
    tmp_path: Path, key: str, text: str, message: str
) -> None:
    path = _write(tmp_path, text)
    load_catalog(path)  # el archivo de partida es válido
    with pytest.raises(CatalogError, match=message):
        add_profile(path, key, NEW_PROFILE)
    assert path.read_text(encoding="utf-8") == text
