"""Pruebas de integración del servidor MCP rhino-bridge: cada herramienta se llama en proceso, a
través de un cliente MCP en memoria, contra el servidor HTTP real del script del puente con un
documento de Rhino falso. El proyecto lo prepara el servidor de core, como en el uso real."""

import json
import re
import shutil
import sys
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import archimind_bridge as bridge
import pytest
from archimind_core import server as core_server
from archimind_rhino_bridge import server as rhino_server
from archimind_rhino_bridge.client import CONFIG_ENV, NOT_RUNNING
from archimind_schema import EditsDraft, load_project
from fake_rhino import FakeDocument
from golden import GOLDEN_DIR
from mcp import Client, StdioServerParameters
from mcp.types import TextContent

pytestmark = pytest.mark.anyio

TOOLS = {"estado_rhino", "abrir_en_rhino", "leer_cambios", "guardar_3dm"}
MAX_LINES = 50
TOKEN = "token-de-prueba"


@pytest.fixture
def config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    path = tmp_path / "rhino_bridge.json"
    monkeypatch.setenv(CONFIG_ENV, str(path))
    return path


@pytest.fixture
def rhino(config: Path) -> Iterator[FakeDocument]:
    document = FakeDocument()
    server = bridge.start(document, lambda fn: fn(), 0, TOKEN)
    config.write_text(json.dumps({"port": server.server_address[1], "token": TOKEN}))
    yield document
    bridge.stop(server)


@pytest.fixture
async def client() -> AsyncIterator[Client]:
    async with Client(rhino_server.mcp) as connected:
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
    """apto_2hab abierto, importado, mapeado y con la escala confirmada desde core."""
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
    return folder


# --- Contrato ---------------------------------------------------------------------------


async def test_tools_follow_the_server_rules(client: Client) -> None:
    tools = (await client.list_tools()).tools
    assert {tool.name for tool in tools} == TOOLS
    for tool in tools:
        assert re.fullmatch(r"[a-z]+(_[a-z0-9]+)*", tool.name)
        assert "project_path" in tool.input_schema.get("required", [])
        assert tool.description and len(tool.description) > 80
        assert tool.output_schema is None


async def test_the_stdio_entry_point_starts() -> None:
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "archimind_rhino_bridge.server"]
    )
    async with Client(params) as stdio:
        assert {tool.name for tool in (await stdio.list_tools()).tools} == TOOLS


async def test_without_rhino_every_tool_says_what_to_run(
    client: Client, core: Client, tmp_path: Path, config: Path
) -> None:
    folder = await _project(core, tmp_path)
    for tool in TOOLS:
        assert (await fails(client, tool, project_path=str(folder))).endswith(NOT_RUNNING)


async def test_a_folder_without_a_project(client: Client, tmp_path: Path) -> None:
    message = await fails(client, "estado_rhino", project_path=str(tmp_path / "nada"))
    assert "abrir_proyecto de archimind-core" in message


# --- Flujo ------------------------------------------------------------------------------


async def test_full_flow(client: Client, core: Client, tmp_path: Path, rhino: FakeDocument) -> None:
    folder = await _project(core, tmp_path)
    path = str(folder)
    target = folder / "salidas" / "casa.3dm"

    status = await call(client, "estado_rhino", project_path=path)
    assert "el puente responde" in status and "no tiene las capas de ArchiMind" in status

    opened = await call(client, "abrir_en_rhino", project_path=path)
    assert f"Proyecto abierto en Rhino: {target}." in opened
    assert "8 muros, 9 vanos, 4 espacios" in opened and "PRELIMINAR" not in opened
    assert target.is_file() and rhino.path == str(target) and not rhino.modified
    assert "al día" in await call(client, "estado_rhino", project_path=path)

    # Sin ediciones: no hay borrador.
    unchanged = await call(client, "leer_cambios", project_path=path)
    assert "Sin cambios" in unchanged and not (folder / "salidas/borrador_rhino.json").exists()

    rhino.transform("muro-0001", lambda p: (p[0] + 0.5, p[1]))
    rhino.delete("vano-0003")
    rhino.add_untagged()
    read = await call(client, "leer_cambios", project_path=path)
    assert "3 cambio(s) en Rhino" in read and "aplicar_borrador de archimind-core" in read
    assert "- vano-0003: borrado" in read and "muro-0001:" in read
    assert "- nuevo muro nuevo-1: largo 1.00 m, espesor 1.000 m" in read
    draft_path = folder / "salidas" / "borrador_rhino.json"
    draft = EditsDraft.model_validate_json(draft_path.read_text(encoding="utf-8"))
    assert [edit.id for edit in draft.walls] == ["muro-0001"] and draft.deleted == ["vano-0003"]
    assert [new.ref for new in draft.new_walls] == ["nuevo-1"]
    model_text = (folder / "modelo.json").read_text(encoding="utf-8")
    assert "muro-0001" in model_text  # el puente no toca el modelo

    # Reabrir con el modelo igual conserva las ediciones.
    await call(client, "guardar_3dm", project_path=path)
    kept = await call(client, "abrir_en_rhino", project_path=path)
    assert "se conservan las ediciones" in kept and "8 muros, 8 vanos" in kept

    # El modelo cambia en core: reabrir protege las ediciones sin leer…
    await call(core, "confirmar_escala", project_path=path, muro_id="muro-0002", longitud_real=3.0)
    refused = await fails(client, "abrir_en_rhino", project_path=path)
    assert "aún no se leyeron" in refused and "descartar_cambios=True" in refused
    assert "vano-0003: borrado" in refused
    stale = await call(client, "leer_cambios", project_path=path)
    assert "El modelo cambió desde que se cargó" in stale

    # …hasta que el usuario las descarta.
    reloaded = await call(client, "abrir_en_rhino", project_path=path, descartar_cambios=True)
    assert "Se descartaron 3 cambio(s)" in reloaded and "8 muros, 9 vanos" in reloaded
    assert "Sin cambios" in await call(client, "leer_cambios", project_path=path)
    assert not draft_path.exists()  # el borrador anterior ya no corresponde


async def test_reloads_when_the_model_changed_without_edits(
    client: Client, core: Client, tmp_path: Path, rhino: FakeDocument
) -> None:
    folder = await _project(core, tmp_path)
    path = str(folder)
    await call(client, "abrir_en_rhino", project_path=path)
    await call(core, "confirmar_escala", project_path=path, muro_id="muro-0002", longitud_real=3.0)
    assert "cambió desde que se cargó" in await call(client, "estado_rhino", project_path=path)
    reloaded = await call(client, "abrir_en_rhino", project_path=path)
    assert "cargadas desde el modelo" in reloaded and "descartaron" not in reloaded
    assert "al día" in await call(client, "estado_rhino", project_path=path)


async def test_refuses_a_document_with_unsaved_changes(
    client: Client, core: Client, tmp_path: Path, rhino: FakeDocument
) -> None:
    folder = await _project(core, tmp_path)
    rhino.path, rhino.modified = "C:/otro.3dm", True
    message = await fails(client, "abrir_en_rhino", project_path=str(folder))
    assert "cambios sin guardar" in message
    assert "load_model_layers" not in rhino.calls


async def test_other_documents_are_not_read_or_saved(
    client: Client, core: Client, tmp_path: Path, rhino: FakeDocument
) -> None:
    folder = await _project(core, tmp_path)
    for tool in ("leer_cambios", "guardar_3dm"):
        message = await fails(client, tool, project_path=str(folder))
        assert "no es el de casa: ábrelo con abrir_en_rhino" in message
    assert "save_as" not in rhino.calls


async def test_an_empty_model_is_not_opened(
    client: Client, core: Client, tmp_path: Path, rhino: FakeDocument
) -> None:
    path = str(tmp_path / "vacio")
    await call(core, "abrir_proyecto", project_path=path)
    assert "aplicar_mapeo" in await fails(client, "abrir_en_rhino", project_path=path)


async def test_a_running_command_is_reported(
    client: Client, core: Client, tmp_path: Path, rhino: FakeDocument
) -> None:
    folder = await _project(core, tmp_path)
    rhino.in_command = True
    assert "ejecutando un comando" in await call(client, "estado_rhino", project_path=str(folder))
    assert "ejecutando un comando" in await fails(
        client, "abrir_en_rhino", project_path=str(folder)
    )


async def test_edit_cycle_moves_a_wall_and_updates_the_areas(
    client: Client, core: Client, tmp_path: Path, rhino: FakeDocument
) -> None:
    """El ciclo de PRUEBA_MANUAL.md: mover 20 cm el tabique entre las habitaciones de
    apto_2hab, leer los cambios, aplicarlos y ver el cuadro de áreas nuevo."""
    folder = await _project(core, tmp_path)
    path = str(folder)
    areas = await call(core, "cuadro_de_areas", project_path=path)
    assert "Habitación 1 (útil): 9.19 m²" in areas and "Habitación 2 (útil): 11.52 m²" in areas
    useful = re.search(r"Área útil: ([\d.]+) m²", areas)
    assert useful is not None

    await call(client, "abrir_en_rhino", project_path=path)
    model = load_project(folder)
    (partition,) = [
        w for w in model.walls if {round(p[1], 3) for p in w.axis} == {3.6} and w.thickness < 0.15
    ]
    rhino.move(partition.id, 0, 0.2)
    read = await call(client, "leer_cambios", project_path=path)
    assert f"- {partition.id}: movido 0.20 m" in read

    applied = await call(core, "aplicar_borrador", project_path=path)
    assert "Borrador de Rhino aplicado: 1 cambio." in applied
    assert "Habitación 1: 9.19 → 8.52 m²" in applied
    assert "Habitación 2: 11.52 → 12.19 m²" in applied

    areas = await call(core, "cuadro_de_areas", project_path=path)
    assert "Habitación 1 (útil): 8.52 m²" in areas and "Habitación 2 (útil): 12.19 m²" in areas
    assert f"Área útil: {useful.group(1)} m²" in areas

    # Lo aplicado no cuenta como cambio pendiente: Rhino recarga sin pedir descartar.
    again = await call(client, "leer_cambios", project_path=path)
    assert "ya se aplicaron al modelo" in again
    reloaded = await call(client, "abrir_en_rhino", project_path=path)
    assert "ya estaban aplicadas en el modelo" in reloaded and "descartaron" not in reloaded
    assert "Sin cambios" in await call(client, "leer_cambios", project_path=path)
