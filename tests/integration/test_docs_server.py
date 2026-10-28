"""Pruebas de integración del servidor MCP archimind-docs: cada herramienta se llama en proceso
con un cliente MCP en memoria. El proyecto lo prepara el servidor de core y la base de datos se
crea en una carpeta temporal con el comando de importación, como en el uso real."""

import json
import re
import shutil
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from archimind_core import server as core_server
from archimind_docs import server as docs_server
from archimind_docs.database import DATA_ENV
from archimind_docs.importers import main as import_main
from archimind_schema import load_project
from golden import GOLDEN_DIR
from mcp import Client, StdioServerParameters
from mcp.types import TextContent

pytestmark = pytest.mark.anyio

TOOLS = {
    "datos_para_memoria",
    "presupuesto_preliminar",
    "verificar_programa_areas",
    "calcular_cos_cus",
}
MAX_LINES = 50


@pytest.fixture(autouse=True)
def data(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    folder = tmp_path / "datos"
    monkeypatch.setenv(DATA_ENV, str(folder))
    return folder


@pytest.fixture
async def client() -> AsyncIterator[Client]:
    async with Client(docs_server.mcp) as connected:
        yield connected


@pytest.fixture
async def core(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Client]:
    monkeypatch.setattr(core_server, "_current_project", None)
    async with Client(core_server.mcp) as connected:
        yield connected


async def call(client: Client, tool: str, **arguments: Any) -> str:
    result = await client.call_tool(tool, arguments)
    text = _text(result.content)
    assert not result.is_error, text
    assert len(text.splitlines()) <= MAX_LINES, f"{tool} respondió {len(text.splitlines())} líneas"
    return text


async def fails(client: Client, tool: str, **arguments: Any) -> str:
    result = await client.call_tool(tool, arguments)
    text = _text(result.content)
    assert result.is_error, text
    return text


def _text(content: list[Any]) -> str:
    assert len(content) == 1 and isinstance(content[0], TextContent)
    return content[0].text


async def _project(core: Client, tmp_path: Path) -> Path:
    """apto_2hab abierto, importado, mapeado, con la escala confirmada y la altura del nivel."""
    folder = tmp_path / "casa"
    path = str(folder)
    await call(core, "abrir_proyecto", project_path=path)
    plan = tmp_path / "entrada" / "apto_2hab.dxf"
    plan.parent.mkdir()
    shutil.copy(GOLDEN_DIR / "apto_2hab" / "input.dxf", plan)
    await call(core, "importar_plano", project_path=path, file_path=str(plan))
    proposal = await call(core, "proponer_mapeo_capas", project_path=path)
    mapping = json.loads(proposal.split("mapping = ", 1)[1])
    await call(core, "aplicar_mapeo", project_path=path, mapping=mapping)
    await call(core, "confirmar_escala", project_path=path)
    level_id = load_project(folder).levels[0].id
    await call(core, "definir_alturas", project_path=path, por_nivel={level_id: 2.6})
    return folder


def load(tmp_path: Path, table: str, text: str) -> None:
    path = tmp_path / f"{table}.csv"
    path.write_text(text, encoding="utf-8")
    assert import_main([table, str(path)]) == 0


# --- Contrato ---------------------------------------------------------------------------


async def test_tools_follow_the_server_rules(client: Client) -> None:
    tools = (await client.list_tools()).tools
    assert {tool.name for tool in tools} == TOOLS
    for tool in tools:
        assert re.fullmatch(r"[a-z][a-z0-9]*(_[a-z0-9]+)*", tool.name)
        assert "project_path" in tool.input_schema["required"]
        assert tool.description and len(tool.description) > 80
        assert tool.output_schema is None


async def test_the_stdio_entry_point_starts() -> None:
    params = StdioServerParameters(command=sys.executable, args=["-m", "archimind_docs.server"])
    async with Client(params) as stdio:
        assert {tool.name for tool in (await stdio.list_tools()).tools} == TOOLS


# --- Herramientas -----------------------------------------------------------------------


async def test_memory_data(client: Client, core: Client, tmp_path: Path) -> None:
    folder = await _project(core, tmp_path)
    load(tmp_path, "materials", "codigo,norma,descripcion,unidad\nM-01,NTC 4026,Bloque,un\n")
    load(tmp_path, "budget_items", "partida,codigo_apu,codigo_material\nmuro-0.20,A1,M-01\n")
    answer = await call(client, "datos_para_memoria", project_path=str(folder))
    path = folder / "salidas" / "datos_memoria.json"
    assert f"(guardadas en {path})" in answer and "PRELIMINAR" not in answer
    data = json.loads(answer.splitlines()[-1])
    assert data == json.loads(path.read_text(encoding="utf-8"))
    assert data["conteos"]["espacios"] == 4
    assert {"origen": "partida muro-0.20", "codigo": "M-01", "descripcion": "Bloque"}.items() <= (
        data["materiales"][0].items()
    )


async def test_preliminary_budget(client: Client, core: Client, tmp_path: Path) -> None:
    folder = await _project(core, tmp_path)
    load(
        tmp_path,
        "unit_prices",
        "codigo;descripcion;unidad;precio;fecha;fuente\n"
        "A-PUERTA;Puerta entamborada;und;350;2026-09-01;Proveedor X\n"
        "A-MURO;Muro de bloque;m²;85,5;2026-08-15;Lista agosto\n",
    )
    load(
        tmp_path,
        "budget_items",
        "partida,codigo_apu,codigo_material\npuerta-0.90x2.10,A-PUERTA,\nmuro-0.20,A-MURO,\n",
    )
    answer = await call(client, "presupuesto_preliminar", project_path=str(folder))
    assert answer.startswith("Presupuesto PRELIMINAR de «casa»: ")
    assert "puerta-0.90x2.10: 1.00 un × 350.00 = 350.00 (A-PUERTA, 2026-09-01, Proveedor X)" in (
        answer
    )
    assert "(A-MURO, 2026-08-15, Lista agosto)" in answer
    assert "SIN PRECIO, no suman al total" in answer
    assert "ventana-1.50x1.20: la partida no está en budget_items" in answer
    path = folder / "salidas" / "presupuesto_preliminar.csv"
    assert f"Detalle en {path}." in answer and path.is_file()


async def test_area_program(client: Client, core: Client, tmp_path: Path) -> None:
    folder = await _project(core, tmp_path)
    empty = await fails(client, "verificar_programa_areas", project_path=str(folder))
    assert "archimind-docs-importar area_program" in empty
    load(tmp_path, "area_program", "espacio,area_minima\nHabitación,9\nHabitación,12\nCocina,6\n")
    answer = await call(client, "verificar_programa_areas", project_path=str(folder))
    assert answer.startswith("Programa de áreas: no cumple (1 de 3 exigencias).")
    assert "Habitación ≥ 12.00 m²: Habitación 2 con 11.52 m² (faltan 0.48 m²)" in answer
    assert "Faltan (ningún espacio con ese nombre):\n  Cocina ≥ 6.00 m²" in answer
    assert "Baño (2.93 m²)" in answer


async def test_cos_and_cus(client: Client, core: Client, tmp_path: Path) -> None:
    folder = await _project(core, tmp_path)
    answer = await call(client, "calcular_cos_cus", project_path=str(folder), area_lote=120)
    assert answer.startswith("Lote de 120.00 m².\nCOS = 0.")
    assert "Planta baja" in answer and "CUS = " in answer
    rejected = await fails(client, "calcular_cos_cus", project_path=str(folder), area_lote=0)
    assert "area_lote" in rejected


async def test_a_folder_without_a_project(client: Client, tmp_path: Path) -> None:
    message = await fails(client, "datos_para_memoria", project_path=str(tmp_path / "nada"))
    assert "abrir_proyecto" in message
