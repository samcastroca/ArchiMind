"""El SVG va a escala 1:20 y cada pluma conserva su grosor en mm."""

import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from archimind_bloques import export_svg, generate
from carpentry_cases import EXAMPLES


@pytest.mark.parametrize("case", ["puerta_batiente", "ventana_corrediza_4h"])
def test_the_svg_is_at_1_20_with_real_lineweights(tmp_path: Path, case: str) -> None:
    params = EXAMPLES[case]
    path = export_svg(generate(params), tmp_path / "salidas" / "bloque.svg")

    root = ET.parse(path).getroot()
    assert root.tag == "{http://www.w3.org/2000/svg}svg"
    # Ancho del vano a 1:20 (50 mm por metro) más 10 mm de margen a cada lado.
    width_mm = float(root.attrib["width"].removesuffix("mm"))
    assert width_mm == pytest.approx(params.width * 50 + 20, abs=0.1)
    view_width = float(root.attrib["viewBox"].split()[2])
    strokes = re.findall(r"stroke-width:\s*([\d.]+)", path.read_text(encoding="utf-8"))
    widths_mm = {round(float(s) * width_mm / view_width, 2) for s in strokes}
    assert widths_mm == {0.35, 0.25, 0.13}
