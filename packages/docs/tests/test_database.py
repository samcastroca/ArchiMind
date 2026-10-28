"""La base de datos del usuario y la carga de CSV."""

import sqlite3
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from archimind_docs.database import (
    DATA_ENV,
    TABLES,
    area_program,
    budget_items,
    connect,
    database_path,
    materials,
    unit_prices,
)
from archimind_docs.importers import CsvImportError, import_csv, main

TEMPLATES = Path(__file__).resolve().parents[1] / "plantillas"


@pytest.fixture
def db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[sqlite3.Connection]:
    monkeypatch.setenv(DATA_ENV, str(tmp_path / "datos"))
    connection = connect()
    yield connection
    connection.close()


def _csv(tmp_path: Path, text: str, name: str = "datos.csv") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_the_database_lives_in_the_data_folder(db: sqlite3.Connection, tmp_path: Path) -> None:
    assert database_path() == tmp_path / "datos" / "archimind.sqlite3"
    assert database_path().is_file()


@pytest.mark.parametrize("table", list(TABLES))
def test_every_empty_template_imports(db: sqlite3.Connection, table: str) -> None:
    assert import_csv(db, table, TEMPLATES / f"{table}.csv") == 0


def test_prices_with_semicolons_decimal_commas_and_a_bom(
    db: sqlite3.Connection, tmp_path: Path
) -> None:
    path = tmp_path / "apu.csv"
    path.write_text(
        "codigo;descripcion;unidad;precio;fecha;fuente\n"
        "APU-01;Muro de bloque 0,15;m2;1.234,56;2026-09-01;Lista de precios septiembre\n"
        "\n"
        "APU-02;Puerta 0,90 × 2,10;un;350;2026-09-01;Proveedor\n",
        encoding="utf-8-sig",
    )
    assert import_csv(db, "unit_prices", path) == 2
    prices = unit_prices(db)
    assert prices["APU-01"].precio == pytest.approx(1234.56)
    assert prices["APU-01"].fecha == date(2026, 9, 1)
    assert prices["APU-02"].descripcion == "Puerta 0,90 × 2,10"


def test_a_bad_row_loads_nothing_and_says_where(db: sqlite3.Connection, tmp_path: Path) -> None:
    good = "M-01,NTC 4026,Bloque de concreto,un\n"
    path = _csv(tmp_path, "codigo,norma,descripcion,unidad\n" + good + "M-02,,Arena,m3\n")
    with pytest.raises(CsvImportError, match="Fila 3, norma"):
        import_csv(db, "materials", path)
    assert materials(db) == {}


def test_invalid_numbers_and_dates_are_reported(db: sqlite3.Connection, tmp_path: Path) -> None:
    path = _csv(
        tmp_path,
        "codigo,descripcion,unidad,precio,fecha,fuente\n"
        "A,Muro,m2,-3,2026-09-01,Lista\n"
        "B,Muro,m2,10,1 de septiembre,Lista\n",
    )
    with pytest.raises(CsvImportError) as raised:
        import_csv(db, "unit_prices", path)
    assert [p.split(":")[0] for p in raised.value.problems] == ["Fila 2, precio", "Fila 3, fecha"]


def test_a_dot_with_three_digits_is_ambiguous_and_rejected(
    db: sqlite3.Connection, tmp_path: Path
) -> None:
    header = "codigo;descripcion;unidad;precio;fecha;fuente\n"
    path = _csv(tmp_path, header + "A;Muro;m2;45.000;2026-09-01;Lista\n")
    with pytest.raises(CsvImportError) as raised:
        import_csv(db, "unit_prices", path)
    (problem,) = raised.value.problems
    assert problem.startswith("Fila 2, precio: «45.000» es ambiguo")
    assert "si son 45000, escríbelo 45000 o 45.000,00; si son 45, escríbelo 45" in problem
    assert unit_prices(db) == {}

    rows = "A;Muro;m2;45.000,00;2026-09-01;Lista\nB;Muro;m2;45000;2026-09-01;Lista\n"
    rows += "C;Muro;m2;1234.567;2026-09-01;Lista\nD;Muro;m2;45,000;2026-09-01;Lista\n"
    assert import_csv(db, "unit_prices", _csv(tmp_path, header + rows)) == 4
    prices = {code: price.precio for code, price in unit_prices(db).items()}
    assert prices == {"A": 45000, "B": 45000, "C": pytest.approx(1234.567), "D": 45}


def test_a_wrong_header_points_to_the_template(db: sqlite3.Connection, tmp_path: Path) -> None:
    path = _csv(tmp_path, "code,area\nA,1\n")
    with pytest.raises(CsvImportError, match="debe ser espacio, area_minima"):
        import_csv(db, "area_program", path)


def test_rows_with_a_code_are_updated_and_the_program_is_replaced(
    db: sqlite3.Connection, tmp_path: Path
) -> None:
    header = "partida,codigo_apu,codigo_material\n"
    import_csv(
        db, "budget_items", _csv(tmp_path, header + "muro-0.15,APU-01,\npiso-util,APU-9,M\n")
    )
    import_csv(db, "budget_items", _csv(tmp_path, header + "muro-0.15,APU-02,M-01\n"))
    items = budget_items(db)
    assert items["muro-0.15"].codigo_apu == "APU-02"
    assert items["muro-0.15"].codigo_material == "M-01"
    assert items["piso-util"].codigo_material == "M"

    program = "espacio,area_minima\nHabitación,9\nHabitación,7\n"
    import_csv(db, "area_program", _csv(tmp_path, program))
    import_csv(db, "area_program", _csv(tmp_path, "espacio,area_minima\nBaño,2\n"))
    assert [(r.espacio, r.area_minima) for r in area_program(db)] == [("Baño", 2.0)]


def test_the_command_reports_rows_or_errors(
    db: sqlite3.Connection, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Con coma como separador, la coma decimal va entre comillas.
    ok = _csv(tmp_path, 'espacio,area_minima\nEstar,"12,5"\n')
    assert main(["area_program", str(ok)]) == 0
    assert "1 filas cargadas en area_program" in capsys.readouterr().out
    bad = _csv(tmp_path, "espacio,area_minima\nEstar,cero\n", "malo.csv")
    assert main(["area_program", str(bad)]) == 1
    assert "Fila 2, area_minima" in capsys.readouterr().err
    assert [r.area_minima for r in area_program(db)] == [12.5]
