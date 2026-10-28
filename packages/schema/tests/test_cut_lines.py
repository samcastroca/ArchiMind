"""Líneas de corte que core propone y el puente de Rhino dibuja."""

import pytest
from archimind_schema import CutLine, CutProposals
from pydantic import ValidationError

SHA = "a" * 64


def _cut(name: str = "longitudinal", end: tuple[float, float] = (10.0, 2.0)) -> CutLine:
    return CutLine(name=name, label="A-A", start=(-1.0, 2.0), end=end, description="Estar")


def test_round_trips_through_json() -> None:
    proposals = CutProposals(base_sha256=SHA, cuts=[_cut(), _cut("transversal")])
    assert CutProposals.model_validate_json(proposals.model_dump_json()) == proposals


def test_a_cut_needs_two_distinct_points() -> None:
    with pytest.raises(ValidationError, match="dos puntos distintos"):
        _cut(end=(-1.0, 2.0))


@pytest.mark.parametrize("name", ["", "Longitudinal", "corte A", "-a"])
def test_names_are_lowercase_keys(name: str) -> None:
    with pytest.raises(ValidationError):
        _cut(name)


def test_names_do_not_repeat() -> None:
    with pytest.raises(ValidationError, match="se repiten"):
        CutProposals(base_sha256=SHA, cuts=[_cut(), _cut()])
