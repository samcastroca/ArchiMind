"""Presupuesto preliminar: cada partida del modelo por el precio de su APU.

Una partida sin cantidad, sin fila en `budget_items`, con un APU que no está en `unit_prices` o
en otra unidad queda «sin precio» con el motivo: no se estima ni suma. Cada línea con precio
lleva la fecha y la fuente del APU.
"""

import csv
from dataclasses import dataclass
from pathlib import Path

from archimind_docs.database import BudgetItem, UnitPrice
from archimind_docs.items import ModelItem

# Unidades que se escriben de varias formas: todas se comparan como la de la derecha.
UNIT_ALIASES = {"m²": "m2", "m³": "m3", "und": "un", "u": "un", "unidad": "un", "ml": "m"}
CSV_HEADER = (
    "partida",
    "descripcion",
    "unidad",
    "cantidad",
    "codigo_apu",
    "precio_unitario",
    "subtotal",
    "fecha_precio",
    "fuente_precio",
    "sin_precio",
)


@dataclass(frozen=True)
class BudgetLine:
    item: ModelItem
    apu: UnitPrice | None
    subtotal: float | None
    missing: str | None  # por qué no tiene precio


@dataclass(frozen=True)
class Budget:
    lines: list[BudgetLine]
    total: float  # solo las partidas con precio
    preliminary_scale: bool

    @property
    def priced(self) -> list[BudgetLine]:
        return [line for line in self.lines if line.subtotal is not None]

    @property
    def unpriced(self) -> list[BudgetLine]:
        return [line for line in self.lines if line.subtotal is None]


def same_unit(a: str, b: str) -> bool:
    def plain(unit: str) -> str:
        text = unit.strip().casefold().replace(" ", "").rstrip(".")
        return UNIT_ALIASES.get(text, text)

    return plain(a) == plain(b)


def preliminary_budget(
    items: list[ModelItem],
    budget_rows: dict[str, BudgetItem],
    prices: dict[str, UnitPrice],
    scale_confirmed: bool,
) -> Budget:
    lines = [_line(item, budget_rows, prices) for item in items]
    total = sum(line.subtotal for line in lines if line.subtotal is not None)
    return Budget(lines, total, not scale_confirmed)


def export_budget_csv(budget: Budget, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(CSV_HEADER)
        for line in budget.lines:
            apu = line.apu
            writer.writerow(
                [
                    line.item.key,
                    line.item.description,
                    line.item.unit,
                    "" if line.item.quantity is None else f"{line.item.quantity:.2f}",
                    apu.codigo if apu else "",
                    f"{apu.precio:.2f}" if apu else "",
                    "" if line.subtotal is None else f"{line.subtotal:.2f}",
                    apu.fecha.isoformat() if apu else "",
                    apu.fuente if apu else "",
                    line.missing or "",
                ]
            )
        writer.writerow(
            ["TOTAL de las partidas con precio", "", "", "", "", "", f"{budget.total:.2f}"]
        )
    return path


def _line(
    item: ModelItem, budget_rows: dict[str, BudgetItem], prices: dict[str, UnitPrice]
) -> BudgetLine:
    if item.quantity is None:
        return BudgetLine(item, None, None, item.missing)
    row = budget_rows.get(item.key)
    if row is None:
        return BudgetLine(item, None, None, "la partida no está en budget_items")
    apu = prices.get(row.codigo_apu)
    if apu is None:
        return BudgetLine(item, None, None, f"el APU {row.codigo_apu} no está en unit_prices")
    if not same_unit(apu.unidad, item.unit):
        return BudgetLine(
            item,
            apu,
            None,
            f"el APU {apu.codigo} está en {apu.unidad} y la partida en {item.unit}",
        )
    return BudgetLine(item, apu, item.quantity * apu.precio, None)
