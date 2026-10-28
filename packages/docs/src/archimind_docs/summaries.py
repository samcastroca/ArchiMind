"""Textos de respuesta de las herramientas: resúmenes cortos y rutas. Todo número sale del
modelo o de la base; aquí solo se da formato."""

from collections.abc import Iterable
from pathlib import Path

from archimind_core.quantities import PRELIMINARY_LABEL

from archimind_docs.program import ProgramCheck
from archimind_docs.zoning import Coefficients

MAX_ROWS = 15


def memory_saved(path: Path, data_json: str, preliminary: bool) -> str:
    lines = [
        f"Cifras verificadas del proyecto (guardadas en {path}). Redacta la memoria solo con "
        "estos números, escritos con los mismos decimales o menos; generar_ficha_pdf rechaza "
        "cualquier otro."
    ]
    if preliminary:
        lines.append(f"{PRELIMINARY_LABEL}: dilo en la memoria.")
    lines.append(data_json)
    return "\n".join(lines)


def program(check: ProgramCheck) -> str:
    met = [m for m in check.matches if m.met]
    short = [m for m in check.matches if m.area is not None and not m.met]
    missing = [m for m in check.matches if m.area is None]
    verdict = "cumple" if not short and not missing else "no cumple"
    lines = [f"Programa de áreas: {verdict} ({len(met)} de {len(check.matches)} exigencias)."]
    if check.preliminary:
        lines.append(f"{PRELIMINARY_LABEL}: las áreas son preliminares.")
    if met:
        lines.append("Cumplen:")
        lines += _limit(
            f"  {m.row.espacio} ≥ {m.row.area_minima:.2f} m²: {m.space} con {m.area:.2f} m²"
            for m in met
        )
    if short:
        lines.append("No llegan al mínimo:")
        lines += _limit(
            f"  {m.row.espacio} ≥ {m.row.area_minima:.2f} m²: {m.space} con {m.area:.2f} m² "
            f"(faltan {m.row.area_minima - (m.area or 0):.2f} m²)"
            for m in short
        )
    if missing:
        lines.append("Faltan (ningún espacio con ese nombre):")
        lines += _limit(f"  {m.row.espacio} ≥ {m.row.area_minima:.2f} m²" for m in missing)
    if check.extra:
        lines.append("Espacios que el programa no pide:")
        lines += _limit(f"  {name} ({area:.2f} m²)" for name, area in check.extra)
    return "\n".join(lines)


def coefficients(result: Coefficients) -> str:
    lines = [
        f"Lote de {result.lot_area:.2f} m².",
        f"COS = {result.cos:.2f}: huella construida del nivel más bajo "
        f"({result.levels[0].name}, {result.footprint:.2f} m²) / área del lote.",
        f"CUS = {result.cus:.2f}: área construida de todos los niveles "
        f"({result.total_built:.2f} m²) / área del lote.",
    ]
    if len(result.levels) > 1:
        lines.append(
            "Por nivel: "
            + ", ".join(f"{lv.name} {lv.built_area:.2f} m²" for lv in result.levels)
            + "."
        )
    lines.append(
        "Área construida: el contorno exterior de los espacios (sin balcones) y de los muros "
        "de cada nivel, como en cuadro_de_areas."
    )
    if result.preliminary:
        lines.append(f"{PRELIMINARY_LABEL}: los coeficientes son preliminares.")
    return "\n".join(lines)


def _limit(lines: Iterable[str]) -> list[str]:
    items = list(lines)
    if len(items) <= MAX_ROWS:
        return items
    return [*items[: MAX_ROWS - 1], f"  … y {len(items) - MAX_ROWS + 1} más"]
