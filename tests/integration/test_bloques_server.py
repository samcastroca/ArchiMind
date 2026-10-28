"""Pruebas de integración del servidor MCP archimind-bloques: cada herramienta se llama en
proceso, a través de un cliente MCP en memoria, como la llamaría Claude Desktop. El flujo
completo usa también el servidor de core, que es el que guarda la carpintería en el modelo."""

import json
import re
import shutil
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from archimind_bloques import server as bloques_server
from archimind_bloques.insert import DRAFT_NAME
from archimind_core import server as core_server
from archimind_schema import load_project, validate
from golden import GOLDEN_DIR
from mcp import Client, StdioServerParameters
from mcp.types import TextContent

pytestmark = pytest.mark.anyio

TOOLS = {
    "listar_catalogo",
    "crear_bloque",
    "ajustar_bloque_a_vano",
    "insertar_bloques_en_plano",
    "agregar_al_catalogo",
}
CATALOG_TOOLS = {"listar_catalogo", "agregar_al_catalogo"}  # el catálogo es único
TEST_CATALOG = Path(__file__).parents[2] / "packages" / "bloques" / "tests" / "catalog_prueba.yaml"
MAX_LINES = 50


@pytest.fixture
async def bloques(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> AsyncIterator[Client]:
    catalog = tmp_path / "catalog.yaml"
    shutil.copy(TEST_CATALOG, catalog)
    monkeypatch.setattr(bloques_server, "catalog_path", catalog)
    async with Client(bloques_server.mcp) as connected:
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


async def _project(core: Client, tmp_path: Path, export: bool = True) -> Path:
    """apto_2hab abierto, importado, mapeado y, si se pide, exportado a DXF desde core."""
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
    if export:
        await call(core, "exportar_plano", project_path=path, formato="dxf")
    return folder


# --- Contrato ---------------------------------------------------------------------------


async def test_tools_follow_the_server_rules(bloques: Client) -> None:
    tools = (await bloques.list_tools()).tools
    assert {tool.name for tool in tools} == TOOLS
    assert len(tools) <= 12
    for tool in tools:
        assert re.fullmatch(r"[a-z]+(_[a-z]+)*", tool.name)
        required = tool.input_schema.get("required", [])
        assert ("project_path" in required) is (tool.name not in CATALOG_TOOLS)
        assert tool.description and len(tool.description) > 80
        assert tool.output_schema is None  # texto, sin JSON duplicado
        if tool.input_schema.get("properties") and tool.name != "listar_catalogo":
            assert "Ejemplo" in tool.description, tool.name


async def test_the_description_teaches_the_example_request(bloques: Client) -> None:
    tools = {tool.name: tool for tool in (await bloques.list_tools()).tools}
    description = tools["crear_bloque"].description or ""
    assert "ventana corrediza de aluminio de 3 hojas de 2.40 × 1.50" in description
    assert '"leaves": 3, "material": "aluminio"' in description
    schema = json.dumps(tools["crear_bloque"].input_schema, ensure_ascii=False)
    assert "Ancho del vano, en metros" in schema  # cada campo con su descripción


async def test_the_stdio_entry_point_starts() -> None:
    params = StdioServerParameters(command=sys.executable, args=["-m", "archimind_bloques.server"])
    async with Client(params) as stdio:
        assert {tool.name for tool in (await stdio.list_tools()).tools} == TOOLS


# --- Catálogo y bloques sueltos ---------------------------------------------------------


async def test_the_catalog_is_listed_and_grows(bloques: Client) -> None:
    listed = await call(bloques, "listar_catalogo")
    assert "Catálogo de carpintería (2 perfiles)" in listed
    assert "prueba: Perfil de prueba (aluminio)" in listed and "antepecho de 0.90 m" in listed

    profile = {
        "name": "PVC serie 70",
        "material": "pvc",
        "types": ["sliding_window", "fixed_window"],
        "frame": {"face": 0.06, "depth": 0.07},
        "sash": {"face": 0.05, "depth": 0.03},
        "overlap": 0.03,
        "glass": 0.005,
        "sash_width": {"min": 0.35, "max": 1.10},
        "sash_height": {"min": 0.35, "max": 1.60},
    }
    added = await call(bloques, "agregar_al_catalogo", clave="pvc_70", perfil=profile)
    assert "pvc_70: PVC serie 70 (pvc)" in added and "ahora 3 perfiles" in added
    assert "pvc_70" in await call(bloques, "listar_catalogo")
    assert "ya tiene el perfil «pvc_70»" in await fails(
        bloques, "agregar_al_catalogo", clave="pvc_70", perfil=profile
    )


async def test_a_loose_block_in_every_format(bloques: Client, core: Client, tmp_path: Path) -> None:
    folder = tmp_path / "casa"
    await call(core, "abrir_proyecto", project_path=str(folder))

    created = await call(
        bloques,
        "crear_bloque",
        project_path=str(folder),
        tipo="sliding_window",
        parametros={"width": 2.40, "height": 1.50, "leaves": 3, "material": "aluminio"},
        formatos=["dxf", "svg", "png", "3dm"],
    )

    assert "Ventana corrediza de 3 hojas, 2.40 × 1.50 m, perfil prueba" in created
    assert "muro de 0.15 m de espesor, el del catálogo" in created
    name = created.splitlines()[0].removeprefix("Bloque ")
    for fmt in ("dxf", "svg", "png", "3dm"):
        path = folder / "salidas" / "bloques" / f"{name}.{fmt}"
        assert path.is_file() and str(path) in created


async def test_objects_sent_as_json_text_are_accepted(
    bloques: Client, core: Client, tmp_path: Path
) -> None:
    """Claude Desktop a veces manda los objetos como texto JSON."""
    folder = tmp_path / "casa"
    await call(core, "abrir_proyecto", project_path=str(folder))
    created = await call(
        bloques,
        "crear_bloque",
        project_path=str(folder),
        tipo="swing_door",
        parametros='{"width": 0.9, "hand": "right"}',
    )
    assert "mano derecha" in created
    assert sorted(p.suffix for p in (folder / "salidas" / "bloques").iterdir()) == [".dxf", ".png"]


async def test_loose_block_errors(bloques: Client, core: Client, tmp_path: Path) -> None:
    missing = await fails(
        bloques,
        "crear_bloque",
        project_path=str(tmp_path),
        tipo="swing_door",
        parametros={"width": 0.9},
    )
    assert "ábrelo con abrir_proyecto de archimind-core" in missing
    folder = tmp_path / "casa"
    await call(core, "abrir_proyecto", project_path=str(folder))
    too_wide = await fails(
        bloques,
        "crear_bloque",
        project_path=str(folder),
        tipo="swing_door",
        parametros={"width": 2.0},
    )
    assert "Ninguna carpintería del catálogo calza" in too_wide and "ancho máximo" in too_wide
    unknown = await fails(
        bloques,
        "crear_bloque",
        project_path=str(folder),
        tipo="fixed_window",
        parametros={"width": 1.0, "profile": "bronce"},
    )
    assert "no tiene el perfil «bronce»" in unknown


# --- Flujo con el modelo ----------------------------------------------------------------


async def test_full_flow_from_fit_to_the_model(
    bloques: Client, core: Client, tmp_path: Path
) -> None:
    folder = await _project(core, tmp_path)
    path = str(folder)
    door = next(o for o in load_project(folder).openings if o.kind == "door")

    fitted = await call(bloques, "ajustar_bloque_a_vano", project_path=path, vano_id=door.id)
    assert f"{door.id}: puerta de {door.width:.2f} × {door.height:.2f} m" in fitted
    assert "Puerta batiente" in fitted and "No se escribió nada." in fitted
    assert f'asignaciones = {{"{door.id}": {{}}}}' in fitted
    assert not (folder / "salidas" / DRAFT_NAME).exists()

    inserted = await call(bloques, "insertar_bloques_en_plano", project_path=path)
    openings = [o for o in load_project(folder).openings if o.kind in ("door", "window")]
    assert f"salidas/casa-carpinteria.dxf: {len(openings)} vanos nuevos" in inserted
    assert "asignar_bloques de archimind-core" in inserted
    assert (folder / "salidas" / "casa-carpinteria.dxf").is_file()
    assert load_project(folder).blocks == []  # bloques nunca escribe el modelo

    assigned = await call(core, "asignar_bloques", project_path=path)
    model = load_project(folder)
    assert f"Carpintería asignada a {len(openings)} vanos" in assigned
    assert all(_by_id(model, o.id).block_id is not None for o in openings)
    assert not [p for p in validate(model) if p.code.startswith("bloque_")]
    assert "· blq-0001" in await call(core, "listar_modelo", project_path=path, que="vanos")

    again = await call(
        bloques,
        "insertar_bloques_en_plano",
        project_path=path,
        asignaciones={door.id: {"type": "sliding_door"}},
    )
    assert f"1 vano nuevo y {len(openings) - 1} vanos con el bloque que ya tenían" in again
    await call(core, "asignar_bloques", project_path=path)
    after = load_project(folder)
    sliding = next(b for b in after.blocks if b.id == _by_id(after, door.id).block_id)
    assert sliding.parameters["type"] == "sliding_door"
    assert sliding.id != _by_id(model, door.id).block_id


def _by_id(model: Any, opening_id: str) -> Any:
    return next(o for o in model.openings if o.id == opening_id)


async def test_flow_errors_say_what_to_do(bloques: Client, core: Client, tmp_path: Path) -> None:
    folder = await _project(core, tmp_path, export=False)
    path = str(folder)
    assert "exportar_plano" in await fails(bloques, "insertar_bloques_en_plano", project_path=path)
    assert "No existe el vano vano-0999" in await fails(
        bloques, "ajustar_bloque_a_vano", project_path=path, vano_id="vano-0999"
    )
    window = next(o for o in load_project(folder).openings if o.kind == "window")
    wrong = await fails(
        bloques,
        "ajustar_bloque_a_vano",
        project_path=path,
        vano_id=window.id,
        preferencias={"hand": "left"},
    )
    assert "hand no se aplica" in wrong


async def test_unexpected_failures_keep_their_message_and_are_logged(
    bloques: Client,
    core: Client,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    folder = tmp_path / "casa"
    await call(core, "abrir_proyecto", project_path=str(folder))

    def locked(*_: object) -> None:
        raise PermissionError("el DXF está abierto en AutoCAD")

    monkeypatch.setitem(bloques_server.EXPORTS, "dxf", locked)
    message = await fails(
        bloques,
        "crear_bloque",
        project_path=str(folder),
        tipo="swing_door",
        parametros={"width": 0.9},
        formatos=["dxf"],
    )
    assert "PermissionError: el DXF está abierto en AutoCAD" in message
    assert "registro del servidor" in message
    [record] = [r for r in caplog.records if r.name == "archimind_bloques"]
    assert record.exc_info is not None and "crear_bloque" in record.getMessage()
