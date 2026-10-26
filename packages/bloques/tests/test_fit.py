"""fit_to_opening sobre apto_2hab (el modelo esperado de tests/fixtures/cases.py) con el catálogo
de prueba.

Vanos: vano-0001 puerta de entrada 0.90 en muro-0001 (y = 0, de x = 0 a 8.5), a 6.0 m;
vano-0003 ventana 2.00; vano-0005 ventana 0.60 × 0.60 del baño; vano-0007 puerta 0.80 de la
Habitación 2 en muro-0005 (x = 3.5, de y = 0 a 6.5) a 2.6 m, cerca del tabique muro-0006
(y = 3.6); vano-0009 puerta 0.70 del baño en muro-0007.
"""

import math

import pytest
from archimind_bloques import Arc, AwningWindow, SlidingWindow, SwingDoor, generate
from archimind_bloques.fit import PRELIMINARY_NOTE, Fit, Preferences, fit_to_opening
from archimind_bloques.resolve import FitError
from archimind_bloques.site import insertion
from archimind_schema import Project
from carpentry_cases import CATALOG
from cases import expected_project
from hypothesis import given
from hypothesis import strategies as st

APTO = expected_project("apto_2hab")


def _fit(opening_id: str, project: Project = APTO, /, **preferences: object) -> Fit:
    return fit_to_opening(project, opening_id, Preferences.model_validate(preferences), CATALOG)


def _hinge(opening_id: str, **preferences: object) -> tuple[float, float]:
    """Las bisagras de la puerta (el centro de su arco), en coordenadas del modelo."""
    fit = _fit(opening_id, **preferences)
    (cx, cy), rotation = insertion(fit.site)
    (arc,) = [s for s in generate(fit.params).plan if isinstance(s, Arc)]
    a = math.radians(rotation)
    x, y = arc.center
    return cx + x * math.cos(a) - y * math.sin(a), cy + x * math.sin(a) + y * math.cos(a)


def test_a_door_keeps_the_measures_of_its_opening() -> None:
    fit = _fit("vano-0001")
    params = fit.params
    assert params.type == "swing_door"
    assert (params.width, params.height, params.wall_thickness) == (0.9, 2.1, 0.2)
    assert fit.profile_key == "prueba"
    assert fit.site.side == "left" and fit.site.room is not None
    assert fit.site.room.name == "Sala-comedor-cocina"


def test_a_window_takes_the_fewest_sliding_leaves_and_its_sill() -> None:
    params = _fit("vano-0003").params
    assert isinstance(params, SlidingWindow)
    assert (params.leaves, params.width, params.sill_height) == (2, 2.0, 0.9)


def test_a_window_too_narrow_to_slide_becomes_an_awning() -> None:
    params = _fit("vano-0005").params
    assert isinstance(params, AwningWindow)
    assert (params.width, params.height, params.sill_height) == (0.6, 0.6, 1.5)


def test_a_door_too_wide_for_one_leaf_becomes_double() -> None:
    project = APTO.model_copy(deep=True)
    project.openings[0].offset, project.openings[0].width = 5.0, 2.0
    assert _fit("vano-0001", project).params.type == "double_swing_door"


def test_the_hinges_go_to_the_nearest_wall() -> None:
    """vano-0007 va de y = 2.6 a 3.4; el tabique muro-0006 corta esa cara en y = 3.55."""
    x, y = _hinge("vano-0007")
    assert x < 3.5 and y > 3.3  # del lado del tabique, hacia la Habitación 2
    assert any("bisagras hacia muro-0006, a 0.15 m" in n for n in _fit("vano-0007").notes)


def test_an_explicit_hand_is_kept() -> None:
    _, y = _hinge("vano-0007", hand="right")
    fit = _fit("vano-0007", hand="right")
    assert isinstance(fit.params, SwingDoor) and fit.params.hand == "right"
    assert not any("mano" in n for n in fit.notes)
    assert (y > 3.0) != (_hinge("vano-0007")[1] > 3.0)


def test_opens_into_and_swing_out() -> None:
    into_living = _fit("vano-0009", opens_into="esp-0004")
    assert into_living.site.room is not None and into_living.site.room.id == "esp-0004"
    out = _fit("vano-0009", swing="out")
    assert isinstance(out.params, SwingDoor) and out.params.swing == "out"
    assert out.site.room is not None
    assert out.site.room.name == "Baño"  # adentro sigue siendo el baño; la hoja abre afuera


def test_a_sliding_door_runs_toward_the_longest_free_wall() -> None:
    fit = _fit("vano-0007", type="sliding_door")
    assert fit.params.type == "sliding_door"
    assert any("corre hacia muro-0001, con 2.50 m de muro libre" in n for n in fit.notes)


def test_preferences_choose_the_type_and_leaves() -> None:
    params = _fit("vano-0003", leaves=4).params
    assert isinstance(params, SlidingWindow) and params.leaves == 4
    assert _fit("vano-0005", type="fixed_window").params.type == "fixed_window"


def test_a_void_needs_a_type() -> None:
    project = APTO.model_copy(deep=True)
    project.openings[0].kind = "void"
    with pytest.raises(FitError, match="vano-0001 es un vano sin tipo: indica type"):
        _fit("vano-0001", project)
    assert _fit("vano-0001", project, type="sliding_door").params.type == "sliding_door"


@pytest.mark.parametrize(
    ("opening_id", "preferences", "message"),
    [
        ("vano-0099", {}, "No existe el vano vano-0099"),
        (
            "vano-0001",
            {"type": "fixed_window"},
            "vano-0001 es una puerta y ventana fija es para una ventana",
        ),
        ("vano-0003", {"hand": "left"}, "hand no se aplica a ventana corrediza"),
        ("vano-0001", {"leaves": 2}, "leaves no se aplica a puerta batiente"),
        ("vano-0001", {"material": "pvc"}, "ningún perfil de pvc admite puerta batiente"),
    ],
)
def test_errors_say_what_to_change(
    opening_id: str, preferences: dict[str, object], message: str
) -> None:
    with pytest.raises(FitError, match=message):
        _fit(opening_id, **preferences)


def test_an_unconfirmed_scale_marks_the_fit_as_preliminary() -> None:
    project = APTO.model_copy(update={"scale_confirmed": False})
    assert PRELIMINARY_NOTE in _fit("vano-0001", project).notes
    assert PRELIMINARY_NOTE not in _fit("vano-0001").notes


@given(width=st.floats(0.3, 2.6), height=st.floats(1.0, 2.6))
def test_a_fitted_door_always_measures_its_opening(width: float, height: float) -> None:
    project = APTO.model_copy(deep=True)
    project.openings[0].offset, project.openings[0].width = 4.0, width
    project.openings[0].height = height
    try:
        params = _fit("vano-0001", project).params
    except FitError as error:
        assert "Ninguna carpintería del catálogo calza" in str(error)
        return
    assert (params.width, params.height, params.wall_thickness) == (width, height, 0.2)
