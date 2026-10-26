"""crear_bloque: de un pedido suelto a parámetros válidos, con el catálogo de prueba.

«prueba» (aluminio) admite todos los tipos: marco 0.05 × 0.08, hoja 0.04 × 0.025, traslape
0.03, hojas de 0.30 a 1.20. «estrecho» (pvc) solo corredizas y fijas, con marco de 0.06 de fondo.
"""

import re

import pytest
from archimind_bloques import CatalogError, SlidingWindow, SwingDoor
from archimind_bloques.create import BlockRequest, create_block
from archimind_bloques.resolve import FitError
from carpentry_cases import CATALOG


def test_the_example_of_the_tool_description() -> None:
    """«ventana corrediza de aluminio de 3 hojas de 2.40 × 1.50»."""
    request = BlockRequest(width=2.40, height=1.50, leaves=3, material="aluminio")

    resolution = create_block("sliding_window", request, CATALOG)

    params = resolution.params
    assert isinstance(params, SlidingWindow)
    assert (params.width, params.height, params.leaves) == (2.40, 1.50, 3)
    assert resolution.profile_key == "prueba"
    assert params.wall_thickness == CATALOG.defaults.wall_thickness
    assert params.sill_height == CATALOG.defaults.sill_height
    assert "muro de 0.15 m de espesor, el del catálogo" in resolution.notes
    assert "antepecho de 0.90 m, el del catálogo" in resolution.notes
    assert any("el primero de aluminio" in note for note in resolution.notes)


def test_what_the_request_does_not_say_comes_from_the_catalog() -> None:
    resolution = create_block("swing_door", BlockRequest(width=0.90), CATALOG)

    params = resolution.params
    assert isinstance(params, SwingDoor)
    assert params.height == CATALOG.defaults.door_height
    assert (params.hand, params.swing) == ("left", "in")
    assert params.leaf_thickness == CATALOG.profile("prueba").sash.depth
    assert "alto de 2.10 m, el del catálogo" in resolution.notes
    assert any("mano izquierda" in note for note in resolution.notes)
    assert any("el fondo de hoja del perfil" in note for note in resolution.notes)


def test_what_the_request_says_is_kept() -> None:
    request = BlockRequest(
        width=0.85,
        height=2.05,
        hand="right",
        swing="out",
        wall_thickness=0.20,
        leaf_thickness=0.045,
        profile="prueba",
    )
    resolution = create_block("swing_door", request, CATALOG)
    params = resolution.params
    assert isinstance(params, SwingDoor)
    assert (params.width, params.height, params.wall_thickness) == (0.85, 2.05, 0.20)
    assert (params.hand, params.swing, params.leaf_thickness) == ("right", "out", 0.045)
    assert not any("catálogo" in note or "defecto" in note for note in resolution.notes)


def test_the_fewest_leaves_that_fit() -> None:
    resolution = create_block("sliding_window", BlockRequest(width=3.00), CATALOG)
    assert isinstance(resolution.params, SlidingWindow)
    assert resolution.params.leaves == 3  # con 2, cada hoja mediría 1.465 m
    assert "3 hojas: las menos que calzan con ese perfil" in resolution.notes


@pytest.mark.parametrize(("material", "profile"), [("PVC", "estrecho"), ("Aluminio", "prueba")])
def test_material_ignores_case(material: str, profile: str) -> None:
    request = BlockRequest(width=1.00, material=material)
    assert create_block("fixed_window", request, CATALOG).profile_key == profile


def test_without_profile_nor_material_the_catalog_order_decides() -> None:
    assert create_block("fixed_window", BlockRequest(width=1.0), CATALOG).profile_key == "prueba"


def _fails(message: str) -> pytest.RaisesExc[FitError]:
    return pytest.raises(FitError, match=re.escape(message))


def test_an_unknown_material_lists_the_available_ones() -> None:
    with _fails("El catálogo no tiene perfiles de bronce. Los materiales disponibles son: "):
        create_block("fixed_window", BlockRequest(width=1.0, material="bronce"), CATALOG)


def test_an_unknown_profile() -> None:
    with pytest.raises(CatalogError, match="no tiene el perfil «pvc»"):
        create_block("fixed_window", BlockRequest(width=1.0, profile="pvc"), CATALOG)


def test_an_option_of_another_type_is_rejected() -> None:
    with _fails("leaves no se aplica a una puerta batiente"):
        create_block("swing_door", BlockRequest(width=0.9, leaves=2), CATALOG)
    with _fails("hand no se aplica a una ventana fija"):
        create_block("fixed_window", BlockRequest(width=1, hand="left"), CATALOG)
    with _fails("swing, sill_height no se aplica a una puerta corrediza"):
        create_block("sliding_door", BlockRequest(width=1, swing="in", sill_height=1), CATALOG)


def test_nothing_fits_explains_each_attempt() -> None:
    request = BlockRequest(width=2.0, leaves=3, material="pvc")
    with _fails(
        "- ventana corrediza de 3 hojas con «Perfil estrecho»: Una ventana corrediza de 3 hojas "
        "necesita 3 rieles"
    ):
        create_block("sliding_window", request, CATALOG)


def test_a_profile_that_does_not_admit_the_type() -> None:
    with _fails("El perfil «Perfil estrecho» no admite puerta batiente doble"):
        create_block("double_swing_door", BlockRequest(width=1.6, profile="estrecho"), CATALOG)
    with _fails("ningún perfil de pvc admite puerta batiente"):
        create_block("swing_door", BlockRequest(width=0.9, material="pvc"), CATALOG)


def test_a_too_wide_leaf_gives_the_limit() -> None:
    with _fails("El ancho máximo es 1.30 m"):
        create_block("swing_door", BlockRequest(width=2.0), CATALOG)
