"""La base de datos del usuario: materiales, precios unitarios (APU), programa de áreas y
partidas del presupuesto.

Es un archivo SQLite en la carpeta de datos del usuario (en Windows, %LOCALAPPDATA%\\ArchiMind),
uno para todos los proyectos. La variable ARCHIMIND_DATOS da otra carpeta. Los datos los carga
el usuario desde CSV (`importers.py`); los servidores solo la leen.
"""

import os
import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import platformdirs
from pydantic import BaseModel, ConfigDict, Field

DATA_ENV = "ARCHIMIND_DATOS"
DB_FILENAME = "archimind.sqlite3"

SCHEMA = """
CREATE TABLE IF NOT EXISTS materials (
    codigo TEXT PRIMARY KEY,
    norma TEXT NOT NULL,
    descripcion TEXT NOT NULL,
    unidad TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS unit_prices (
    codigo TEXT PRIMARY KEY,
    descripcion TEXT NOT NULL,
    unidad TEXT NOT NULL,
    precio REAL NOT NULL CHECK (precio >= 0),
    fecha TEXT NOT NULL,
    fuente TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS area_program (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    espacio TEXT NOT NULL,
    area_minima REAL NOT NULL CHECK (area_minima > 0)
);
CREATE TABLE IF NOT EXISTS budget_items (
    partida TEXT PRIMARY KEY,
    codigo_apu TEXT NOT NULL,
    codigo_material TEXT
);
"""


class DatabaseError(Exception):
    """La base no se puede abrir o le faltan datos; el mensaje está pensado para el usuario."""


class _Row(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class Material(_Row):
    codigo: str = Field(min_length=1)
    norma: str = Field(min_length=1)
    descripcion: str = Field(min_length=1)
    unidad: str = Field(min_length=1)


class UnitPrice(_Row):
    codigo: str = Field(min_length=1)
    descripcion: str = Field(min_length=1)
    unidad: str = Field(min_length=1)
    precio: float = Field(ge=0, allow_inf_nan=False)
    fecha: date
    fuente: str = Field(min_length=1)


class ProgramRow(_Row):
    espacio: str = Field(min_length=1)
    area_minima: float = Field(gt=0, allow_inf_nan=False)


class BudgetItem(_Row):
    partida: str = Field(min_length=1)
    codigo_apu: str = Field(min_length=1)
    codigo_material: str | None = None


@dataclass(frozen=True)
class Table:
    """Una tabla de la base: el modelo de sus filas y su clave (None si se reemplaza entera)."""

    name: str
    row: type[_Row]
    key: str | None


TABLES = {
    table.name: table
    for table in (
        Table("materials", Material, "codigo"),
        Table("unit_prices", UnitPrice, "codigo"),
        Table("area_program", ProgramRow, None),
        Table("budget_items", BudgetItem, "partida"),
    )
}


def data_dir() -> Path:
    custom = os.environ.get(DATA_ENV)
    if custom:
        return Path(custom).expanduser()
    return Path(platformdirs.user_data_dir("ArchiMind", appauthor=False))


def database_path() -> Path:
    return data_dir() / DB_FILENAME


def connect(path: Path | None = None) -> sqlite3.Connection:
    """Abre la base (la crea con sus tablas si no existe)."""
    target = path or database_path()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(target)
        connection.executescript(SCHEMA)
    except (OSError, sqlite3.Error) as exc:
        raise DatabaseError(f"No se pudo abrir la base de datos {target}: {exc}") from exc
    connection.row_factory = sqlite3.Row
    return connection


def materials(connection: sqlite3.Connection) -> dict[str, Material]:
    rows = connection.execute("SELECT * FROM materials ORDER BY codigo")
    return {row["codigo"]: Material.model_validate(dict(row)) for row in rows}


def unit_prices(connection: sqlite3.Connection) -> dict[str, UnitPrice]:
    rows = connection.execute("SELECT * FROM unit_prices ORDER BY codigo")
    return {row["codigo"]: UnitPrice.model_validate(dict(row)) for row in rows}


def area_program(connection: sqlite3.Connection) -> list[ProgramRow]:
    rows = connection.execute("SELECT espacio, area_minima FROM area_program ORDER BY id")
    return [ProgramRow.model_validate(dict(row)) for row in rows]


def budget_items(connection: sqlite3.Connection) -> dict[str, BudgetItem]:
    rows = connection.execute("SELECT * FROM budget_items ORDER BY partida")
    return {row["partida"]: BudgetItem.model_validate(dict(row)) for row in rows}
