import re
from typing import Any

import pytest
from archimind_bloques import (
    AwningWindow,
    CarpentryParams,
    DoubleSwingDoor,
    FixedWindow,
    SlidingDoor,
    SlidingWindow,
    SwingDoor,
)
from carpentry_cases import EXAMPLES, NARROW, PROFILE
from pydantic import TypeAdapter, ValidationError

WINDOW: dict[str, Any] = {"height": 1.20, "sill_height": 0.90, "wall_thickness": 0.15}
DOOR: dict[str, Any] = {"height": 2.10, "leaf_thickness": 0.04, "wall_thickness": 0.15}


def _rejects(message: str) -> pytest.RaisesExc[ValidationError]:
    return pytest.raises(ValidationError, match=re.escape(message))


def test_four_sliding_leaves_do_not_fit_in_60_cm() -> None:
    with _rejects(
        "Una ventana corrediza de 4 hojas no cabe en 0.60 m con el perfil «Perfil de prueba»: "
        "cada hoja mediría 0.14 m de ancho y el perfil exige al menos 0.30 m. El ancho mínimo "
        "es 1.24 m. También puedes usar menos hojas."
    ):
        SlidingWindow(width=0.60, leaves=4, profile=PROFILE, **WINDOW)


def test_the_minimum_width_of_the_message_is_accepted() -> None:
    window = SlidingWindow(width=1.24, leaves=4, profile=PROFILE, **WINDOW)
    assert window.leaf_width == pytest.approx(0.30)


def test_too_wide_sliding_leaves_suggest_more_leaves() -> None:
    with _rejects(
        "Una ventana corrediza de 2 hojas de 3.00 m excede el perfil «Perfil de prueba»: cada "
        "hoja mediría 1.465 m de ancho y el perfil admite como máximo 1.20 m. El ancho máximo "
        "es 2.47 m. También puedes usar más hojas."
    ):
        SlidingWindow(width=3.00, leaves=2, profile=PROFILE, **WINDOW)


def test_a_narrow_swing_door() -> None:
    with _rejects(
        "Una puerta batiente no cabe en 0.30 m con el perfil «Perfil de prueba»: la hoja "
        "mediría 0.20 m de ancho y el perfil exige al menos 0.30 m. El ancho mínimo es 0.40 m."
    ):
        SwingDoor(width=0.30, hand="left", swing="in", profile=PROFILE, **DOOR)


def test_a_narrow_double_door_counts_each_leaf() -> None:
    with _rejects(
        "cada hoja mediría 0.25 m de ancho y el perfil exige al menos 0.30 m. El ancho "
        "mínimo es 0.70 m."
    ):
        DoubleSwingDoor(width=0.60, swing="in", profile=PROFILE, **DOOR)


def test_a_wide_sliding_door_counts_the_overlaps() -> None:
    with _rejects(
        "la hoja mediría 1.26 m de ancho y el perfil admite como máximo 1.20 m. El "
        "ancho máximo es 1.24 m."
    ):
        SlidingDoor(width=1.30, hand="left", side="in", profile=PROFILE, **DOOR)


def test_a_fixed_window_names_its_pane() -> None:
    with _rejects("el paño mediría 0.20 m de ancho"):
        FixedWindow(width=0.30, profile=PROFILE, height=1.0, sill_height=1.0, wall_thickness=0.15)


def test_a_low_window() -> None:
    with _rejects(
        "Una ventana proyectante de 0.35 m de alto no cabe con el perfil «Perfil de prueba»: "
        "la hoja mediría 0.25 m de alto y el perfil exige al menos 0.30 m. El alto mínimo es "
        "0.40 m."
    ):
        AwningWindow(width=0.80, height=0.35, sill_height=1.0, wall_thickness=0.15, profile=PROFILE)


def test_a_tall_door() -> None:
    with _rejects(
        "la hoja mediría 2.45 m de alto y el perfil admite como máximo 2.40 m. El alto "
        "máximo es 2.45 m."
    ):
        SwingDoor(
            width=0.90,
            height=2.50,
            leaf_thickness=0.04,
            hand="left",
            swing="in",
            wall_thickness=0.15,
            profile=PROFILE,
        )


def test_the_frame_must_fit_in_the_wall() -> None:
    with _rejects(
        "El marco del perfil «Perfil de prueba» tiene 0.08 m de fondo y no cabe en un muro de "
        "0.06 m."
    ):
        FixedWindow(width=1.0, height=1.0, sill_height=1.0, wall_thickness=0.06, profile=PROFILE)
    assert FixedWindow(width=1.0, height=1.0, sill_height=1.0, wall_thickness=0.08, profile=PROFILE)


def test_the_leaf_must_fit_in_the_frame() -> None:
    with _rejects(
        "La hoja de 0.09 m de espesor no cabe en el marco del perfil «Perfil de prueba», de "
        "0.08 m de fondo."
    ):
        SwingDoor(
            width=0.90,
            height=2.10,
            leaf_thickness=0.09,
            hand="left",
            swing="in",
            wall_thickness=0.15,
            profile=PROFILE,
        )


def test_three_rails_need_a_deep_frame() -> None:
    with _rejects(
        "Una ventana corrediza de 3 hojas necesita 3 rieles de 0.025 m (0.075 m) y el marco del "
        "perfil «Perfil estrecho» tiene 0.06 m de fondo. Usa 2 o 4 hojas u otro perfil."
    ):
        SlidingWindow(width=1.50, leaves=3, profile=NARROW, **WINDOW)
    assert SlidingWindow(width=1.50, leaves=2, profile=NARROW, **WINDOW)


@pytest.mark.parametrize("leaves", [0, 1, 5])
def test_a_sliding_window_has_two_to_four_leaves(leaves: int) -> None:
    with _rejects(f"Una ventana corrediza tiene de 2 a 4 hojas; se pidieron {leaves}."):
        SlidingWindow(width=1.50, leaves=leaves, profile=PROFILE, **WINDOW)


def test_the_profile_must_accept_the_type() -> None:
    with _rejects(
        "El perfil «Perfil estrecho» no admite puerta batiente; admite: ventana corrediza, "
        "ventana fija."
    ):
        SwingDoor(width=0.90, hand="left", swing="in", profile=NARROW, **DOOR)


def test_fixed_and_awning_windows_have_no_leaves_parameter() -> None:
    with pytest.raises(ValidationError, match="leaves"):
        FixedWindow.model_validate({"width": 1.0, "leaves": 2, "profile": PROFILE, **WINDOW})


def test_the_union_is_discriminated_by_type() -> None:
    data = {"type": "awning_window", "width": 0.80, "profile": PROFILE.model_dump(), **WINDOW}
    params = TypeAdapter(CarpentryParams).validate_python(data)
    assert isinstance(params, AwningWindow)


def test_params_are_frozen() -> None:
    with pytest.raises(ValidationError):
        EXAMPLES["puerta_batiente"].width = 1.0
