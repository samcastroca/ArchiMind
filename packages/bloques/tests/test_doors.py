"""Medidas exactas de las puertas con el perfil de prueba: F 0.05, D 0.08, O 0.03."""

import pytest
from archimind_bloques import (
    Arc,
    Carpentry,
    DoubleSwingDoor,
    Pen,
    Polyline,
    SlidingDoor,
    SwingDoor,
    generate,
)
from archimind_bloques.params import Hand, Side
from carpentry_cases import EXAMPLES, PROFILE, TOL, solid


def _swing_door(hand: Hand, swing: Side) -> Carpentry:
    return generate(
        SwingDoor(
            width=0.90,
            height=2.10,
            leaf_thickness=0.04,
            hand=hand,
            swing=swing,
            wall_thickness=0.15,
            profile=PROFILE,
        )
    )


def _arcs(carpentry: Carpentry) -> list[Arc]:
    return [s for s in carpentry.plan if isinstance(s, Arc)]


def test_swing_door_frame() -> None:
    door = generate(EXAMPLES["puerta_batiente"])
    assert solid(door, "marco jamba inicial").min == pytest.approx((0, -0.04, 0), abs=TOL)
    assert solid(door, "marco jamba inicial").max == pytest.approx((0.05, 0.04, 2.10), abs=TOL)
    assert solid(door, "marco jamba final").min == pytest.approx((0.85, -0.04, 0), abs=TOL)
    assert solid(door, "marco cabezal").min == pytest.approx((0.05, -0.04, 2.05), abs=TOL)
    assert solid(door, "marco cabezal").max == pytest.approx((0.85, 0.04, 2.10), abs=TOL)
    assert door.kind == "door" and door.panes == ()


def test_swing_door_left_in() -> None:
    """Abre adentro (+y), bisagras a la izquierda de quien mira desde adentro: en x = 0.85."""
    door = _swing_door("left", "in")
    leaf = solid(door, "hoja")
    assert leaf.min == pytest.approx((0.05, 0.0, 0), abs=TOL)
    assert leaf.max == pytest.approx((0.85, 0.04, 2.05), abs=TOL)
    (arc,) = _arcs(door)
    assert arc.center == pytest.approx((0.85, 0.04), abs=TOL)
    assert arc.radius == pytest.approx(0.80, abs=TOL)
    assert (arc.start_angle, arc.end_angle) == pytest.approx((90, 180), abs=TOL)
    # La hoja abierta a 90°: de la bisagra hacia adentro, con su espesor hacia el vano.
    open_leaf = next(s for s in door.plan if isinstance(s, Polyline) and s.pen is Pen.SEEN)
    xs, ys = [p[0] for p in open_leaf.points], [p[1] for p in open_leaf.points]
    assert (min(xs), max(xs)) == pytest.approx((0.81, 0.85), abs=TOL)
    assert (min(ys), max(ys)) == pytest.approx((0.04, 0.84), abs=TOL)


@pytest.mark.parametrize(
    ("hand", "swing", "hinge_x", "face_y"),
    [
        ("left", "in", 0.85, 0.04),
        ("right", "in", 0.05, 0.04),
        ("left", "out", 0.05, -0.04),
        ("right", "out", 0.85, -0.04),
    ],
)
def test_swing_door_hands(hand: Hand, swing: Side, hinge_x: float, face_y: float) -> None:
    """Mirando desde el lado al que abre, bisagras a la izquierda = izquierda (EN 12519)."""
    door = _swing_door(hand, swing)
    (arc,) = _arcs(door)
    assert arc.center == pytest.approx((hinge_x, face_y), abs=TOL)
    # En el alzado, el vértice del triángulo de apertura está en las bisagras.
    marks = [s for s in door.elevation if isinstance(s, Polyline) and s.pen is not Pen.SEEN]
    assert [s.points[1] for s in marks] == [pytest.approx((hinge_x, 1.025), abs=TOL)] * 2


@pytest.mark.parametrize(("swing", "pen"), [("in", Pen.HIDDEN), ("out", Pen.THIN)])
def test_the_swing_triangle_is_dashed_when_it_opens_away(swing: Side, pen: Pen) -> None:
    """El alzado se ve desde afuera: lo que abre adentro se aleja de quien mira."""
    door = _swing_door("left", swing)
    marks = [s for s in door.elevation if s.pen in (Pen.THIN, Pen.HIDDEN)]
    assert len(marks) == 2 and {s.pen for s in marks} == {pen}


def test_double_swing_door() -> None:
    door = generate(EXAMPLES["puerta_batiente_doble"])
    assert isinstance(door.params, DoubleSwingDoor)
    first, second = solid(door, "hoja 1"), solid(door, "hoja 2")
    assert first.min == pytest.approx((0.05, -0.04, 0), abs=TOL)
    assert first.max == pytest.approx((0.80, 0.0, 2.05), abs=TOL)
    assert second.min == pytest.approx((0.80, -0.04, 0), abs=TOL)
    assert second.max == pytest.approx((1.55, 0.0, 2.05), abs=TOL)
    arcs = _arcs(door)
    assert [a.center for a in arcs] == [
        pytest.approx((0.05, -0.04), abs=TOL),
        pytest.approx((1.55, -0.04), abs=TOL),
    ]
    assert [a.radius for a in arcs] == pytest.approx([0.75, 0.75], abs=TOL)


def test_sliding_door() -> None:
    door = generate(EXAMPLES["puerta_corrediza"])
    leaf = solid(door, "hoja")
    # Vano libre 0.80 más el traslape a cada lado; sobre la cara de adentro del muro.
    assert leaf.min == pytest.approx((0.02, 0.075, 0), abs=TOL)
    assert leaf.max == pytest.approx((0.88, 0.115, 2.08), abs=TOL)
    # Corre por detrás del muro para quien mira el alzado desde afuera.
    (outline,) = [s for s in door.elevation if s.pen is Pen.HIDDEN]
    assert isinstance(outline, Polyline) and outline.closed


def _shaft(strokes: tuple[Polyline | Arc, ...]) -> tuple[tuple[float, float], ...]:
    """El asta de la flecha: el único trazo fino de dos puntos."""
    (shaft,) = [
        s for s in strokes if isinstance(s, Polyline) and s.pen is Pen.THIN and len(s.points) == 2
    ]
    return shaft.points


@pytest.mark.parametrize(
    ("hand", "side", "toward", "y0"),
    [
        ("left", "in", 1, 0.075),
        ("right", "in", -1, 0.075),
        ("left", "out", -1, -0.115),
        ("right", "out", 1, -0.115),
    ],
)
def test_sliding_door_hands(hand: Hand, side: Side, toward: int, y0: float) -> None:
    """Mirando desde la cara por la que corre, izquierda = corre hacia la izquierda."""
    door = generate(
        SlidingDoor(
            width=0.90,
            height=2.10,
            leaf_thickness=0.04,
            hand=hand,
            side=side,
            wall_thickness=0.15,
            profile=PROFILE,
        )
    )
    assert solid(door, "hoja").min[1] == pytest.approx(y0, abs=TOL)
    for strokes in (door.plan, door.elevation):
        (x0, _), (x1, _) = _shaft(strokes)
        assert (x1 - x0) * toward > 0
