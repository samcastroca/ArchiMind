"""Presupuesto preliminar: cantidades del modelo por APU, sin estimar lo que no tiene precio."""

import csv
from datetime import date
from pathlib import Path

import pytest
from archimind_docs.budget import export_budget_csv, preliminary_budget, same_unit
from archimind_docs.database import BudgetItem, UnitPrice
from archimind_docs.items import MISSING_HEIGHT, ModelItem

ITEMS = [
    ModelItem("muro-0.15", "Muro", "m2", 40.0),
    ModelItem("muro-0.20", "Muro", "m2", None, MISSING_HEIGHT),
    ModelItem("puerta-0.90x2.10", "Puerta", "un", 3.0),
    ModelItem("ventana-1.50x1.20", "Ventana", "un", 2.0),
    ModelItem("piso-util", "Piso", "m2", 50.0),
]


def _price(code: str, unit: str, price: float) -> UnitPrice:
    return UnitPrice(
        codigo=code,
        descripcion=code,
        unidad=unit,
        precio=price,
        fecha=date(2026, 9, 1),
        fuente="Lista septiembre",
    )


ROWS = {
    "muro-0.15": BudgetItem(partida="muro-0.15", codigo_apu="A-MURO"),
    "muro-0.20": BudgetItem(partida="muro-0.20", codigo_apu="A-MURO"),
    "puerta-0.90x2.10": BudgetItem(partida="puerta-0.90x2.10", codigo_apu="A-PUERTA"),
    "piso-util": BudgetItem(partida="piso-util", codigo_apu="A-PISO"),
}
PRICES = {
    "A-MURO": _price("A-MURO", "m²", 85.5),
    "A-PUERTA": _price("A-PUERTA", "und", 350),
    "A-PISO": _price("A-PISO", "un", 20),
}


def test_only_items_with_a_price_add_up() -> None:
    budget = preliminary_budget(ITEMS, ROWS, PRICES, scale_confirmed=True)
    assert budget.total == pytest.approx(40 * 85.5 + 3 * 350)
    reasons = {line.item.key: line.missing for line in budget.unpriced}
    assert reasons == {
        "muro-0.20": MISSING_HEIGHT,
        "ventana-1.50x1.20": "la partida no está en budget_items",
        "piso-util": "el APU A-PISO está en un y la partida en m2",
    }
    assert not budget.preliminary_scale


def test_a_missing_unit_price_is_never_estimated() -> None:
    budget = preliminary_budget(ITEMS[:1], ROWS, {}, scale_confirmed=False)
    (line,) = budget.lines
    assert (line.subtotal, line.missing) == (None, "el APU A-MURO no está en unit_prices")
    assert budget.total == 0 and budget.preliminary_scale


@pytest.mark.parametrize(
    ("a", "b"), [("m²", "m2"), ("M2", "m2"), ("und", "un"), ("U.", "un"), ("ml", "m")]
)
def test_units_written_differently_are_the_same(a: str, b: str) -> None:
    assert same_unit(a, b)


def test_m2_is_not_m3() -> None:
    assert not same_unit("m2", "m3")


def test_the_csv_has_date_and_source_of_each_price(tmp_path: Path) -> None:
    budget = preliminary_budget(ITEMS, ROWS, PRICES, scale_confirmed=True)
    path = export_budget_csv(budget, tmp_path / "presupuesto.csv")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    wall = next(r for r in rows if r["partida"] == "muro-0.15")
    assert (wall["subtotal"], wall["fecha_precio"], wall["fuente_precio"]) == (
        "3420.00",
        "2026-09-01",
        "Lista septiembre",
    )
    assert next(r for r in rows if r["partida"] == "muro-0.20")["sin_precio"] == MISSING_HEIGHT
    assert rows[-1]["partida"] == "TOTAL de las partidas con precio"
    assert rows[-1]["subtotal"] == "4470.00"
