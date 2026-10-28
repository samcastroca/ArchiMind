"""Verificación de los números de la memoria y la ficha PDF."""

import re
from pathlib import Path

import pytest
from archimind_core import define_heights
from archimind_docs.items import model_items
from archimind_docs.memory import memory_data
from archimind_docs.sheet import build_sheet
from archimind_docs.verify import readings, unverified_numbers
from cases import apto_2hab
from hypothesis import given
from hypothesis import strategies as st

DATA = {
    "areas": {"util": 55.25, "construida": 1234.567},
    "conteos": {"puertas": 4, "confirmada": True},
    "materiales": [{"norma": "NTC 4026", "descripcion": "Bloque"}],
    "partidas": [{"partida": "puerta-0.90x2.10"}],
}


def _rejected(text: str) -> list[str]:
    return [u.text for u in unverified_numbers(text, DATA)]


@pytest.mark.parametrize(
    "text",
    [
        "El área útil es de 55,25 m², unos 55 m² o 55.3 m².",
        "La construida suma 1.234,57 m² (1234,6 m²; 1,234.567 m²).",
        "Tiene 4 puertas de 0,90 × 2,10 m y bloque NTC 4026.",
    ],
)
def test_figures_from_the_data_pass_however_they_are_written(text: str) -> None:
    assert _rejected(text) == []


@pytest.mark.parametrize(
    ("text", "rejected"),
    [
        ("El área útil es de 56 m².", ["56"]),
        # El 1 de 1:50 pasa: 0.90 redondeado a enteros da 1.
        ("Diseñado en 2026 a escala 1:50.", ["2026", "50"]),
        ("Tiene 3 puertas.", ["3"]),
        ("Útil: 55,26 m².", ["55,26"]),
        ("Del 27.10.2026.", ["27.10.2026"]),
    ],
)
def test_figures_not_in_the_data_are_rejected(text: str, rejected: list[str]) -> None:
    assert _rejected(text) == rejected


def test_a_rejection_says_where_the_number_is() -> None:
    (item,) = unverified_numbers("La vivienda, construida en 2026, tiene 4 puertas.", DATA)
    assert item.text == "2026" and "construida en 2026, tiene 4" in item.context


def test_readings_of_ambiguous_numbers() -> None:
    assert readings("1.234") == [(1.234, 3), (1234.0, 0)]
    assert readings("1,5") == [(1.5, 1)]
    assert readings("1.234.567") == [(1234567.0, 0)]
    assert readings("1.234,5") == [(1234.5, 1)]


@given(
    value=st.decimals(min_value=0, max_value=99999, places=2).map(float),
    decimals=st.integers(0, 2),
    comma=st.booleans(),
)
def test_any_rounding_of_a_figure_passes_and_a_changed_one_does_not(
    value: float, decimals: int, comma: bool
) -> None:
    data = {"x": value}
    written = f"{round(value, decimals):.{decimals}f}"
    if comma:
        written = written.replace(".", ",")
    assert unverified_numbers(f"Mide {written} m.", data) == []
    changed = round(value, decimals) + 10 ** (-decimals) * 7
    assert unverified_numbers(f"Mide {changed:.{decimals}f} m.", data) != []


def test_the_sheet_is_a_pdf(tmp_path: Path) -> None:
    project, _ = apto_2hab()
    project = define_heights(project, {project.levels[0].id: 2.6}, None).project
    data = memory_data(project, model_items(project), [])
    memory = "Vivienda de dos habitaciones con baño.\n\nÁrea útil: 55,25 m² — «ñandú» ✓."
    path = build_sheet(project, data, memory, tmp_path / "ficha.pdf")
    content = path.read_bytes()
    assert content.startswith(b"%PDF")
    assert len(re.findall(rb"/Type /Page\b", content)) >= 1
    assert b"DejaVuSans" in content


def test_an_unconfirmed_scale_marks_every_page(tmp_path: Path) -> None:
    project, _ = apto_2hab()
    project.scale_confirmed = False
    data = memory_data(project, model_items(project), [])
    long_memory = "\n\n".join(["Texto de la memoria sin cifras. " * 20] * 12)
    path = build_sheet(project, data, long_memory, tmp_path / "ficha.pdf")
    assert len(re.findall(rb"/Type /Page\b", path.read_bytes())) >= 2
