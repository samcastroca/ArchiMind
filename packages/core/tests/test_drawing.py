from pathlib import Path

import pytest
from archimind_core import DrawingError, read_drawing
from cases import CASES
from ezdxf.addons import odafc
from golden import GOLDEN_DIR


@pytest.mark.parametrize("case", sorted(CASES))
def test_reads_every_golden_dxf(case: str) -> None:
    drawing = read_drawing(GOLDEN_DIR / case / "input.dxf")
    assert len(drawing.doc.modelspace()) > 0
    assert drawing.units.confirmed


def test_dwg_without_oda_explains_how_to_continue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(odafc, "is_installed", lambda: False)
    dwg = tmp_path / "plano.dwg"
    dwg.write_bytes(b"AC1032")
    with pytest.raises(DrawingError) as error:
        read_drawing(dwg)
    message = str(error.value)
    assert "ODA File Converter" in message
    assert "DXF" in message


def test_missing_file_is_reported(tmp_path: Path) -> None:
    with pytest.raises(DrawingError, match="No existe"):
        read_drawing(tmp_path / "nada.dxf")


def test_unknown_extension_is_reported(tmp_path: Path) -> None:
    pdf = tmp_path / "plano.pdf"
    pdf.write_bytes(b"%PDF")
    with pytest.raises(DrawingError, match="formato no admitido"):
        read_drawing(pdf)


def test_garbage_dxf_is_reported(tmp_path: Path) -> None:
    broken = tmp_path / "roto.dxf"
    broken.write_text("esto no es un DXF", encoding="utf-8")
    with pytest.raises(DrawingError):
        read_drawing(broken)
