"""Carga de los CSV del usuario en la base: todo o nada, con el número de cada fila que falla.

Los CSV son UTF-8 (con o sin BOM), separados por coma o por punto y coma, con los encabezados
de su plantilla (`packages/docs/plantillas/`). Los números admiten coma decimal y punto de
miles («1.234,56»); un solo punto con tres cifras y sin coma («45.000») puede ser 45 o 45 mil y
se rechaza. Una tabla con código se actualiza por código; el programa de áreas se reemplaza
entero.
"""

import argparse
import csv
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from archimind_docs.database import TABLES, DatabaseError, connect, database_path

MAX_ERRORS = 20
# Un punto y tres cifras, sin coma: «45.000» es 45 con punto decimal o 45 mil con punto de miles.
AMBIGUOUS = re.compile(r"\d{1,3}\.\d{3}")


class CsvImportError(DatabaseError):
    """El CSV no se cargó; `problems` dice qué falló en cada fila."""

    def __init__(self, path: Path, problems: list[str]) -> None:
        listed = problems[:MAX_ERRORS]
        if len(problems) > MAX_ERRORS:
            listed.append(f"… y {len(problems) - MAX_ERRORS} problemas más")
        super().__init__(f"No se cargó nada de {path.name}:\n" + "\n".join(listed))
        self.problems = problems


def import_csv(connection: sqlite3.Connection, table_name: str, path: str | Path) -> int:
    """Valida todas las filas y, si ninguna falla, las carga; devuelve cuántas cargó."""
    source = Path(path)
    table = TABLES.get(table_name)
    if table is None:
        raise DatabaseError(f"No hay una tabla {table_name}: son {', '.join(TABLES)}.")
    try:
        text = source.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        raise DatabaseError(f"No se pudo leer {source} como UTF-8: {exc}") from exc
    lines = text.splitlines()
    if not lines:
        raise CsvImportError(source, ["El archivo está vacío: le falta el encabezado."])
    delimiter = ";" if lines[0].count(";") > lines[0].count(",") else ","
    reader = csv.DictReader(lines, delimiter=delimiter)
    columns = list(table.row.model_fields)
    header = [name.strip().lower() for name in reader.fieldnames or []]
    if header != columns:
        raise CsvImportError(
            source,
            [f"Encabezado {', '.join(header)}: debe ser {', '.join(columns)} (ver la plantilla)."],
        )
    reader.fieldnames = header

    rows: list[dict[str, Any]] = []
    problems = []
    for number, raw in enumerate(reader, start=2):
        if not any((value or "").strip() for value in raw.values()):
            continue  # fila vacía
        values = {name: _value(table.row, name, raw.get(name)) for name in columns}
        for name in columns:
            text = (raw.get(name) or "").strip()
            if _numeric(table.row, name) and AMBIGUOUS.fullmatch(text):
                problems.append(f"Fila {number}, {name}: {_ambiguous(text)}.")
        try:
            rows.append(table.row.model_validate(values).model_dump(mode="json"))
        except ValidationError as exc:
            for error in exc.errors():
                field = ".".join(str(part) for part in error["loc"])
                problems.append(f"Fila {number}, {field}: {error['msg']}.")
    if problems:
        raise CsvImportError(source, problems)

    placeholders = ", ".join("?" for _ in columns)
    insert = f"INSERT OR REPLACE INTO {table.name} ({', '.join(columns)}) VALUES ({placeholders})"
    with connection:
        if table.key is None:
            connection.execute(f"DELETE FROM {table.name}")
        connection.executemany(insert, [[row[c] for c in columns] for row in rows])
    return len(rows)


def _value(row: type[Any], name: str, raw: str | None) -> Any:
    """El texto de la celda; vacío es None, y en los campos numéricos se acepta coma decimal."""
    text = (raw or "").strip()
    if not text:
        return None
    if _numeric(row, name) and "," in text:
        return text.replace(".", "").replace(",", ".")
    return text


def _numeric(row: type[Any], name: str) -> bool:
    return row.model_fields[name].annotation is float


def _ambiguous(text: str) -> str:
    """El motivo del rechazo de «45.000», con cómo escribir cada lectura sin ambigüedad."""
    whole, fraction = text.split(".")
    thousands = whole + fraction
    decimal = f"{whole},{fraction.rstrip('0')}".rstrip(",")
    return (
        f"«{text}» es ambiguo: si son {thousands}, escríbelo {thousands} o {text},00; si son "
        f"{decimal}, escríbelo {decimal}"
    )


def main(argv: list[str] | None = None) -> int:
    """`archimind-docs-importar <tabla> <archivo.csv>`."""
    parser = argparse.ArgumentParser(
        prog="archimind-docs-importar",
        description=f"Carga un CSV en la base de datos de ArchiMind ({database_path()}).",
    )
    parser.add_argument("tabla", choices=list(TABLES))
    parser.add_argument("archivo", type=Path)
    args = parser.parse_args(argv)
    try:
        connection = connect()
        try:
            loaded = import_csv(connection, args.tabla, args.archivo)
        finally:
            connection.close()
    except DatabaseError as exc:
        print(exc, file=sys.stderr)
        return 1
    print(f"{loaded} filas cargadas en {args.tabla} ({database_path()}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
