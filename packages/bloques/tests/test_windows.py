"""Medidas exactas de las ventanas con el perfil de prueba: F 0.05, D 0.08, S 0.04, Sd 0.025,
O 0.03."""

import pytest
from archimind_bloques import Carpentry, Pen, Polyline, generate
from carpentry_cases import EXAMPLES, TOL, sash_span, solid, solids_extents


def _arrows(carpentry: Carpentry) -> list[int]:
    """Sentido en x de cada flecha del alzado: sus astas son los trazos finos de dos puntos."""
    return [
        1 if s.points[1][0] > s.points[0][0] else -1
        for s in carpentry.elevation
        if isinstance(s, Polyline) and s.pen is Pen.THIN and len(s.points) == 2
    ]


def test_window_frame_from_the_sill() -> None:
    window = generate(EXAMPLES["ventana_fija"])  # 1.00 x 1.00 con antepecho 1.00
    assert solid(window, "marco jamba inicial").min == pytest.approx((0, -0.04, 1.00), abs=TOL)
    assert solid(window, "marco jamba final").max == pytest.approx((1.00, 0.04, 2.00), abs=TOL)
    assert solid(window, "marco cabezal").min == pytest.approx((0.05, -0.04, 1.95), abs=TOL)
    bottom = solid(window, "marco travesaño inferior")
    assert bottom.min == pytest.approx((0.05, -0.04, 1.00), abs=TOL)
    assert bottom.max == pytest.approx((0.95, 0.04, 1.05), abs=TOL)
    assert window.kind == "window"


def test_window_plan_draws_the_faces_of_the_opening() -> None:
    window = generate(EXAMPLES["ventana_fija"])
    lines = [
        tuple(c for point in s.points for c in point)
        for s in window.plan
        if isinstance(s, Polyline) and len(s.points) == 2
    ]
    for y in (-0.075, 0.075):
        assert any(line == pytest.approx((0.0, y, 1.0, y), abs=TOL) for line in lines)


def test_fixed_window_pane() -> None:
    (pane,) = generate(EXAMPLES["ventana_fija"]).panes
    assert (pane.x0, pane.x1, pane.z0, pane.z1, pane.y) == pytest.approx(
        (0.05, 0.95, 1.05, 1.95, 0.0), abs=TOL
    )


def test_two_sliding_leaves() -> None:
    window = generate(EXAMPLES["ventana_corrediza_2h"])  # 1.20: hojas de (1.10 + 0.03) / 2
    assert sash_span(window, 1) == pytest.approx((0.05, -0.025, 0.95, 0.615, 0.0, 2.05), abs=TOL)
    assert sash_span(window, 2) == pytest.approx((0.585, 0.0, 0.95, 1.15, 0.025, 2.05), abs=TOL)
    assert _arrows(window) == [1, -1]


def test_three_sliding_leaves_on_three_rails() -> None:
    window = generate(EXAMPLES["ventana_corrediza_3h"])  # 1.54: hojas de (1.44 + 0.06) / 3
    assert sash_span(window, 1) == pytest.approx(
        (0.05, -0.0375, 0.95, 0.55, -0.0125, 2.05), abs=TOL
    )
    assert sash_span(window, 2) == pytest.approx((0.52, -0.0125, 0.95, 1.02, 0.0125, 2.05), abs=TOL)
    assert sash_span(window, 3) == pytest.approx((0.99, 0.0125, 0.95, 1.49, 0.0375, 2.05), abs=TOL)
    # La central corre hacia los dos lados.
    assert _arrows(window) == [1, -1, 1, -1]


def test_four_sliding_leaves_meet_in_the_middle() -> None:
    window = generate(EXAMPLES["ventana_corrediza_4h"])  # 2.00: hojas de (1.90 + 0.06) / 4
    spans = [sash_span(window, n) for n in (1, 2, 3, 4)]
    assert [(s[0], s[3]) for s in spans] == [
        pytest.approx((0.05, 0.54), abs=TOL),
        pytest.approx((0.51, 1.00), abs=TOL),
        pytest.approx((1.00, 1.49), abs=TOL),
        pytest.approx((1.46, 1.95), abs=TOL),
    ]
    # Laterales en el riel exterior (−y), centrales en el interior.
    assert [s[1] for s in spans] == pytest.approx([-0.025, 0.0, 0.0, -0.025], abs=TOL)
    assert _arrows(window) == [1, -1, 1, -1]


def test_sliding_leaf_members_and_glass() -> None:
    window = generate(EXAMPLES["ventana_corrediza_4h"])
    stile = solid(window, "hoja 1 montante inicial")
    assert stile.min == pytest.approx((0.05, -0.025, 0.95), abs=TOL)
    assert stile.max == pytest.approx((0.09, 0.0, 2.05), abs=TOL)
    rail = solid(window, "hoja 1 travesaño superior")
    assert rail.min == pytest.approx((0.09, -0.025, 2.01), abs=TOL)
    assert rail.max == pytest.approx((0.50, 0.0, 2.05), abs=TOL)
    glass = next(p for p in window.panes if p.name == "vidrio 1")
    assert (glass.x0, glass.x1, glass.z0, glass.z1, glass.y) == pytest.approx(
        (0.09, 0.50, 0.99, 2.01, -0.0125), abs=TOL
    )
    assert len(window.panes) == 4 and len(window.solids) == 4 + 4 * 4


def test_awning_window() -> None:
    window = generate(EXAMPLES["ventana_proyectante"])  # 0.80 x 0.60 con antepecho 1.50
    sash = tuple(b for b in window.solids if b.part == "sash")
    assert len(sash) == 4
    assert solids_extents(sash) == pytest.approx((0.05, -0.0125, 1.55, 0.75, 0.0125, 2.05), abs=TOL)
    (glass,) = window.panes
    assert (glass.x0, glass.x1, glass.z0, glass.z1) == pytest.approx(
        (0.09, 0.71, 1.59, 2.01), abs=TOL
    )
    # Triángulo de apertura con el vértice arriba, continuo: abre hacia quien mira desde afuera.
    marks = [
        s
        for s in window.elevation
        if isinstance(s, Polyline) and s.pen is Pen.THIN and len(s.points) == 2
    ]
    assert [s.points[1] for s in marks] == [pytest.approx((0.40, 2.05), abs=TOL)] * 2
