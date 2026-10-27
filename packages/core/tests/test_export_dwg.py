from pathlib import Path

import pytest
from archimind_core import DwgVersion, ExportError, export_dwg, layer_inventory, read_drawing
from cases import expected_project
from ezdxf.addons import odafc

needs_oda = pytest.mark.skipif(not odafc.is_installed(), reason="ODA File Converter no instalado")


@needs_oda
@pytest.mark.parametrize(("version", "dxfversion"), [("R2013", "AC1027"), ("R2018", "AC1032")])
def test_the_dwg_has_the_entities_and_lengths_of_the_dxf(
    tmp_path: Path, version: DwgVersion, dxfversion: str
) -> None:
    dwg = export_dwg(expected_project("apto_2hab"), tmp_path / "casa.dwg", version)

    from_dwg = read_drawing(dwg)  # un .dwg se lee con odafc.readfile
    from_dxf = read_drawing(dwg.with_suffix(".dxf"))
    assert from_dwg.doc.dxfversion == dxfversion
    dwg_layers = layer_inventory(from_dwg)
    dxf_layers = layer_inventory(from_dxf)
    assert {s.layer: s.entity_counts for s in dwg_layers} == {
        s.layer: s.entity_counts for s in dxf_layers
    }
    assert {s.layer: s.line_length_m for s in dwg_layers} == pytest.approx(
        {s.layer: s.line_length_m for s in dxf_layers}, abs=0.001
    )


def test_without_oda_nothing_is_written_and_the_dxf_is_offered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(odafc, "is_installed", lambda: False)
    with pytest.raises(ExportError) as error:
        export_dwg(expected_project("apto_2hab"), tmp_path / "casa.dwg")
    message = str(error.value)
    assert "ODA File Converter" in message and 'formato="dxf"' in message
    assert list(tmp_path.iterdir()) == []


def test_an_unconfirmed_scale_is_reported_before_the_missing_oda(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(odafc, "is_installed", lambda: False)
    project = expected_project("apto_2hab").model_copy(update={"scale_confirmed": False})
    with pytest.raises(ExportError, match="PRELIMINAR: escala sin confirmar"):
        export_dwg(project, tmp_path / "casa.dwg")


def test_converts_the_dxf_beside_it_to_the_requested_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[Path, Path, str]] = []

    def convert(source: Path, dest: Path, *, version: str) -> None:
        calls.append((source, dest, version))
        dest.write_bytes(b"AC1027")

    monkeypatch.setattr(odafc, "is_installed", lambda: True)
    monkeypatch.setattr(odafc, "convert", convert)
    target = tmp_path / "salidas" / "casa.dwg"

    assert export_dwg(expected_project("apto_2hab"), target, "R2013") == target
    assert calls == [(target.with_suffix(".dxf"), target, "R2013")]
    assert target.with_suffix(".dxf").is_file()


def _raises(source: Path, dest: Path, *, version: str) -> None:
    raise odafc.ODAFCError("archivo dañado")


def _writes_nothing(source: Path, dest: Path, *, version: str) -> None:
    pass


@pytest.mark.parametrize(
    ("convert", "expected"),
    [(_raises, "no pudo convertir casa.dxf"), (_writes_nothing, "no generó casa.dwg")],
)
def test_a_failed_conversion_is_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, convert: object, expected: str
) -> None:
    monkeypatch.setattr(odafc, "is_installed", lambda: True)
    monkeypatch.setattr(odafc, "convert", convert)
    target = tmp_path / "casa.dwg"
    target.write_bytes(b"de una exportacion anterior")
    with pytest.raises(ExportError, match=expected):
        export_dwg(expected_project("apto_2hab"), target)
    assert not target.exists()  # un DWG viejo no pasa por el nuevo
