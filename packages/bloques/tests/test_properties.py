"""Propiedades de los generadores con parámetros válidos por construcción: se parte de una hoja
dentro de los límites del perfil y se despeja el vano con las fórmulas de cada tipo."""

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
    block_name,
    generate,
)
from archimind_bloques.params import Hand, Side
from carpentry_cases import PROFILE, TOL, extents, sash_span, solids_extents
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

FACE, DEPTH, OVERLAP = PROFILE.frame.face, PROFILE.frame.depth, PROFILE.overlap
LEAF_WIDTHS = st.floats(PROFILE.sash_width.min, PROFILE.sash_width.max)
LEAF_HEIGHTS = st.floats(PROFILE.sash_height.min, PROFILE.sash_height.max)
WALLS = st.floats(DEPTH, 0.40)
SILLS = st.floats(0, 2)
HANDS: st.SearchStrategy[Hand] = st.sampled_from(["left", "right"])
SIDES: st.SearchStrategy[Side] = st.sampled_from(["in", "out"])
KINDS = ("swing", "double", "sliding_door", "sliding", "fixed", "awning")


@st.composite
def carpentry_params(draw: st.DrawFn, kinds: tuple[str, ...] = KINDS) -> CarpentryParams:
    a, b, wall = draw(LEAF_WIDTHS), draw(LEAF_HEIGHTS), draw(WALLS)
    common: dict[str, Any] = {"wall_thickness": wall, "profile": PROFILE}
    kind = draw(st.sampled_from(kinds))
    if kind == "swing":
        thickness = draw(st.floats(0.01, DEPTH))
        return SwingDoor(
            width=a + 2 * FACE,
            height=b + FACE,
            leaf_thickness=thickness,
            hand=draw(HANDS),
            swing=draw(SIDES),
            **common,
        )
    if kind == "double":
        thickness = draw(st.floats(0.01, DEPTH))
        return DoubleSwingDoor(
            width=2 * a + 2 * FACE,
            height=b + FACE,
            leaf_thickness=thickness,
            swing=draw(SIDES),
            **common,
        )
    if kind == "sliding_door":
        return SlidingDoor(
            width=a + 2 * FACE - 2 * OVERLAP,
            height=b + FACE - OVERLAP,
            leaf_thickness=draw(st.floats(0.01, 0.08)),
            hand=draw(HANDS),
            side=draw(SIDES),
            **common,
        )
    sill = draw(SILLS)
    if kind == "sliding":
        leaves = draw(st.integers(2, 4))
        overlaps = 1 if leaves == 2 else 2
        return SlidingWindow(
            width=leaves * a - overlaps * OVERLAP + 2 * FACE,
            height=b + 2 * FACE,
            sill_height=sill,
            leaves=leaves,
            **common,
        )
    window = FixedWindow if kind == "fixed" else AwningWindow
    return window(width=a + 2 * FACE, height=b + 2 * FACE, sill_height=sill, **common)


def _span(params: CarpentryParams) -> tuple[float, float, float, float]:
    """(x0, z0, x1, z1) esperados del alzado y de los sólidos."""
    match params:
        case SlidingDoor():
            return (
                min(0, FACE - OVERLAP),
                0,
                max(params.width, params.width - FACE + OVERLAP),
                params.height,
            )
        case SwingDoor() | DoubleSwingDoor():
            return 0, 0, params.width, params.height
        case _:
            bottom = params.sill_height
            return 0, bottom, params.width, bottom + params.height


@given(carpentry_params())
def test_the_plan_spans_the_opening(params: CarpentryParams) -> None:
    x0, _, x1, _ = _span(params)
    xmin, ymin, xmax, ymax = extents(generate(params).plan)
    assert (xmin, xmax) == pytest.approx((x0, x1), abs=TOL)
    if not isinstance(params, SwingDoor | DoubleSwingDoor | SlidingDoor):
        # La ventana llena el hueco del muro: sus caras van en ±espesor/2.
        half = params.wall_thickness / 2
        assert (ymin, ymax) == pytest.approx((-half, half), abs=TOL)


@given(carpentry_params())
def test_the_elevation_spans_the_opening(params: CarpentryParams) -> None:
    xmin, ymin, xmax, ymax = extents(generate(params).elevation)
    x0, z0, x1, z1 = _span(params)
    if isinstance(params, SlidingDoor):
        z1 = max(z1, params.leaf_height)
    assert (xmin, ymin, xmax, ymax) == pytest.approx((x0, z0, x1, z1), abs=TOL)


@given(carpentry_params())
def test_the_solids_fill_the_frame(params: CarpentryParams) -> None:
    carpentry = generate(params)
    xmin, ymin, zmin, xmax, ymax, zmax = solids_extents(carpentry.solids)
    x0, z0, x1, z1 = _span(params)
    if isinstance(params, SlidingDoor):
        z1 = max(z1, params.leaf_height)
    assert (xmin, zmin, xmax, zmax) == pytest.approx((x0, z0, x1, z1), abs=TOL)
    if isinstance(params, SlidingDoor):
        outer = params.wall_thickness / 2 + params.leaf_thickness
        expected = (-DEPTH / 2, outer) if params.side == "in" else (-outer, DEPTH / 2)
        assert (ymin, ymax) == pytest.approx(expected, abs=TOL)
    else:
        assert (ymin, ymax) == pytest.approx((-DEPTH / 2, DEPTH / 2), abs=TOL)
    for piece in carpentry.solids:
        assert all(piece.max[i] - piece.min[i] > 0 for i in range(3)), piece.name
    names = [p.name for p in carpentry.solids] + [p.name for p in carpentry.panes]
    assert len(set(names)) == len(names)


@given(carpentry_params())
def test_panes_sit_inside_the_frame(params: CarpentryParams) -> None:
    _, z0, _, z1 = _span(params)
    for pane in generate(params).panes:
        assert FACE - TOL <= pane.x0 < pane.x1 <= params.width - FACE + TOL
        assert z0 + FACE - TOL <= pane.z0 < pane.z1 <= z1 - FACE + TOL
        assert -DEPTH / 2 <= pane.y <= DEPTH / 2


@given(carpentry_params(kinds=("sliding",)))
def test_sliding_leaves_cover_the_clear_opening(params: CarpentryParams) -> None:
    assert isinstance(params, SlidingWindow)
    window = generate(params)
    spans = [sash_span(window, n) for n in range(1, params.leaves + 1)]
    assert spans[0][0] == pytest.approx(FACE, abs=TOL)
    assert spans[-1][3] == pytest.approx(params.width - FACE, abs=TOL)
    rails, rail_depth = params.leaf_rails, PROFILE.sash.depth
    for i in range(params.leaves - 1):
        overlap = spans[i][3] - spans[i + 1][0]
        # Entre rieles distintos traslapan; en el mismo riel (las centrales de 4) van a tope.
        assert overlap == pytest.approx(OVERLAP if rails[i] != rails[i + 1] else 0, abs=TOL)
    for span, rail in zip(spans, rails, strict=True):
        assert span[1] == pytest.approx(-params.rails * rail_depth / 2 + rail * rail_depth, abs=TOL)
        assert span[4] - span[1] == pytest.approx(rail_depth, abs=TOL)


@given(carpentry_params())
def test_generation_is_deterministic(params: CarpentryParams) -> None:
    assert generate(params) == generate(params)
    assert block_name(params) == generate(params).name


@given(carpentry_params())
def test_just_below_the_minimum_width_is_rejected(params: CarpentryParams) -> None:
    """El ancho mínimo que da el mensaje se acepta, y dos milímetros menos no."""
    leaf_min = PROFILE.sash_width.min
    minimum = params.width + (leaf_min - params.leaf_width) * params.leaf_count
    data = params.model_dump()
    with pytest.raises(ValidationError, match="El ancho mínimo es"):
        type(params).model_validate({**data, "width": minimum - 0.002})
    accepted = type(params).model_validate({**data, "width": round(minimum + 0.0005, 3)})
    assert accepted.leaf_width >= leaf_min
