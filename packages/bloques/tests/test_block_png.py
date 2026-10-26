"""Salidas de cada tipo para revisión visual, en tests/output/bloques/ (ignorada por git).

Además del PNG quedan el DXF, el SVG y el .3dm, para abrirlos en AutoCAD o Rhino (ver
PRUEBA_MANUAL.md).
"""

from pathlib import Path

import pytest
from archimind_bloques import export_3dm, export_dxf, export_svg, generate, render_png
from carpentry_cases import EXAMPLES

OUTPUT = Path(__file__).resolve().parents[3] / "tests" / "output" / "bloques"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


@pytest.mark.parametrize("case", sorted(EXAMPLES))
def test_renders_each_type_for_review(case: str) -> None:
    carpentry = generate(EXAMPLES[case])
    png = render_png(carpentry, OUTPUT / f"{case}.png")
    assert png.read_bytes().startswith(PNG_SIGNATURE)
    for export, suffix in ((export_dxf, ".dxf"), (export_svg, ".svg"), (export_3dm, ".3dm")):
        assert export(carpentry, OUTPUT / f"{case}{suffix}").stat().st_size > 0
