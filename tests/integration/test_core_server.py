"""Pruebas de integración del servidor MCP archimind-core: cada herramienta se llama en proceso,
a través de un cliente MCP en memoria, como la llamaría Claude Desktop."""

import json
import re
import shutil
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import ezdxf
import pytest
from archimind_core import area_table, recent_versions, server
from archimind_core.server import MODEL_URI, mcp
from archimind_schema import (
    Space,
    SpacePolygon,
    load_project,
    new_id,
    save_project,
    validate,
    wall_length,
)
from golden import GOLDEN_DIR, load_expected
from mcp import Client, StdioServerParameters
from mcp.types import TextContent, TextResourceContents

pytestmark = pytest.mark.anyio

TOOLS = {
    "abrir_proyecto",
    "importar_plano",
    "proponer_mapeo_capas",
    "aplicar_mapeo",
    "confirmar_escala",
    "validar_modelo",
    "listar_espacios",
    "listar_vanos",
    "cuadro_de_areas",
    "comparar_versiones",
    "renderizar_vista",
    "exportar_dxf",
}
MAX_LINES = 50
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


@pytest.fixture
async def client(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Client]:
    monkeypatch.setattr(server, "_current_project", None)
    async with Client(mcp) as connected:
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
    assert text.startswith(f"Error executing tool {tool}: "), text  # con el mensaje, no sin él
    return text


async def read_model(client: Client) -> str:
    contents = (await client.read_resource(MODEL_URI)).contents
    assert isinstance(contents[0], TextResourceContents)
    return contents[0].text


def _text(content: list[Any]) -> str:
    assert len(content) == 1 and isinstance(content[0], TextContent)
    return content[0].text


def _plan(tmp_path: Path, case: str, insunits: int | None = None) -> Path:
    """Copia el plano del caso fuera del proyecto, opcionalmente con otras unidades."""
    target = tmp_path / "entrada" / f"{case}.dxf"
    target.parent.mkdir(parents=True, exist_ok=True)
    if insunits is None:
        shutil.copy(GOLDEN_DIR / case / "input.dxf", target)
    else:
        doc = ezdxf.readfile(GOLDEN_DIR / case / "input.dxf")
        doc.header["$INSUNITS"] = insunits
        doc.saveas(target)
    return target


def _versions(folder: Path) -> int:
    return len(recent_versions(folder, limit=100))


async def _built(client: Client, tmp_path: Path, case: str, insunits: int | None = None) -> Path:
    """Abre un proyecto, importa el plano del caso y aplica el mapeo propuesto."""
    folder = tmp_path / "casa"
    await call(client, "abrir_proyecto", project_path=str(folder))
    await call(
        client,
        "importar_plano",
        project_path=str(folder),
        file_path=str(_plan(tmp_path, case, insunits)),
    )
    proposal = await call(client, "proponer_mapeo_capas", project_path=str(folder))
    mapping = json.loads(proposal.split("mapping = ", 1)[1])
    await call(client, "aplicar_mapeo", project_path=str(folder), mapping=mapping)
    return folder


# --- Contrato ---------------------------------------------------------------------------


async def test_tools_follow_the_server_rules(client: Client) -> None:
    tools = (await client.list_tools()).tools
    assert {tool.name for tool in tools} == TOOLS
    assert len(tools) <= 12
    for tool in tools:
        assert re.fullmatch(r"[a-z]+(_[a-z]+)*", tool.name)
        assert "project_path" in tool.input_schema["required"]
        assert tool.description and len(tool.description) > 80
        assert tool.output_schema is None  # texto, sin JSON duplicado
    resources = (await client.list_resources()).resources
    assert [str(r.uri) for r in resources] == [MODEL_URI]


async def test_the_stdio_entry_point_starts() -> None:
    params = StdioServerParameters(command=sys.executable, args=["-m", "archimind_core.server"])
    async with Client(params) as stdio:
        assert {tool.name for tool in (await stdio.list_tools()).tools} == TOOLS


# --- Flujo completo ---------------------------------------------------------------------


async def test_full_flow_with_a_confirmed_plan(client: Client, tmp_path: Path) -> None:
    folder = tmp_path / "casa"
    path = str(folder)

    assert "Proyecto creado." in await call(client, "abrir_proyecto", project_path=path)
    assert _versions(folder) == 1
    reopened = await call(client, "abrir_proyecto", project_path=path)
    assert "Proyecto abierto." in reopened and "Sin cambios que versionar." in reopened
    assert _versions(folder) == 1

    imported = await call(
        client, "importar_plano", project_path=path, file_path=str(_plan(tmp_path, "apto_2hab"))
    )
    assert "Plano importado: planos/apto_2hab.dxf" in imported
    assert "declaradas en el plano" in imported and "A-MURO" in imported
    assert (folder / "planos" / "apto_2hab.dxf").is_file()
    assert _versions(folder) == 2

    proposal = await call(client, "proponer_mapeo_capas", project_path=path)
    assert "A-MURO → walls" in proposal
    mapping = json.loads(proposal.split("mapping = ", 1)[1])
    assert _versions(folder) == 2

    applied = await call(client, "aplicar_mapeo", project_path=path, mapping=mapping)
    project = load_project(folder)
    assert f"{len(project.walls)} muros" in applied and "Escala: confirmada." in applied
    assert f"Versión {recent_versions(folder)[0].hash}." in applied
    assert recent_versions(folder)[0].message.startswith("Aplica el mapeo de capas")
    assert _versions(folder) == 3

    spaces = await call(client, "listar_espacios", project_path=path)
    for name in (s.name for s in load_expected("apto_2hab").spaces):
        assert name in spaces
    openings = await call(client, "listar_vanos", project_path=path)
    assert f"{len(project.openings)} vanos" in openings
    assert all(o.id in openings for o in project.openings)
    validation = await call(client, "validar_modelo", project_path=path)
    assert ("es válido" in validation) == (not validate(project))

    areas = await call(client, "cuadro_de_areas", project_path=path)
    table = area_table(project)
    assert f"Área útil: {table.useful_area:.2f} m²" in areas
    assert (folder / "salidas" / "cuadro_de_areas.csv").is_file()

    view = await call(client, "renderizar_vista", project_path=path)
    assert (folder / "salidas" / "vista.png").read_bytes().startswith(PNG_SIGNATURE)
    assert str(folder / "salidas" / "vista.png") in view
    exported = await call(client, "exportar_dxf", project_path=path)
    assert str(folder / "salidas" / "casa.dxf") in exported
    assert ezdxf.readfile(folder / "salidas" / "casa.dxf").units == ezdxf.units.M

    already = await call(client, "confirmar_escala", project_path=path)
    assert "ya estaba confirmada" in already
    assert _versions(folder) == 3  # consultas y salidas no versionan nada

    summary = await read_model(client)
    assert "Proyecto «casa»" in summary and recent_versions(folder)[0].hash in summary


async def test_recalculated_scale_shows_up_between_versions(client: Client, tmp_path: Path) -> None:
    folder = await _built(client, tmp_path, "apto_2hab")
    wall = load_project(folder).walls[0]
    real = round(wall_length(wall) * 1.1, 3)

    rescaled = await call(
        client, "confirmar_escala", project_path=str(folder), muro_id=wall.id, longitud_real=real
    )

    assert f"ahora mide {real:.3f} m" in rescaled
    after = next(w for w in load_project(folder).walls if w.id == wall.id)
    assert wall_length(after) == pytest.approx(real)
    assert recent_versions(folder)[0].message.startswith(f"Recalcula la escala: {wall.id}")
    changes = await call(
        client, "comparar_versiones", project_path=str(folder), version_a="HEAD~1", version_b="HEAD"
    )
    assert "Muros movidos o con otro espesor" in changes and wall.id in changes
    assert "Espacios con área distinta" in changes and "+21.0%" in changes


async def test_inferred_units_stay_preliminary_until_confirmed(
    client: Client, tmp_path: Path
) -> None:
    folder = await _built(client, tmp_path, "milimetros", insunits=0)
    path = str(folder)
    assert not load_project(folder).scale_confirmed

    for tool in ("listar_espacios", "cuadro_de_areas"):
        assert "PRELIMINAR: escala sin confirmar" in await call(client, tool, project_path=path)
    assert "CSV no exportado" in await call(client, "cuadro_de_areas", project_path=path)
    assert "confirma la escala" in await fails(client, "exportar_dxf", project_path=path)

    confirmed = await call(client, "confirmar_escala", project_path=path)
    assert "Escala confirmada: el plano está en milímetros" in confirmed
    assert load_project(folder).scale_confirmed
    assert "CSV: " in await call(client, "cuadro_de_areas", project_path=path)
    assert recent_versions(folder)[0].message == "Confirma la escala con las unidades del plano"


# --- Errores ----------------------------------------------------------------------------


async def test_errors_reach_the_model_with_a_clear_message(client: Client, tmp_path: Path) -> None:
    missing = str(tmp_path / "no-existe")
    assert "ábrelo primero con abrir_proyecto" in await fails(
        client, "listar_espacios", project_path=missing
    )

    folder = tmp_path / "casa"
    path = str(folder)
    await call(client, "abrir_proyecto", project_path=path)
    pdf = tmp_path / "plano.pdf"
    pdf.write_bytes(b"%PDF-1.7")
    assert "formato no admitido" in await fails(
        client, "importar_plano", project_path=path, file_path=str(pdf)
    )
    assert "No existe el archivo" in await fails(
        client, "importar_plano", project_path=path, file_path=str(tmp_path / "nada.dxf")
    )
    assert "importar_plano" in await fails(client, "proponer_mapeo_capas", project_path=path)

    await call(
        client, "importar_plano", project_path=path, file_path=str(_plan(tmp_path, "rect_simple"))
    )
    assert "aplica el mapeo" in await fails(client, "confirmar_escala", project_path=path)
    assert "Roles no válidos: A-MURO → paredes" in await fails(
        client, "aplicar_mapeo", project_path=path, mapping={"A-MURO": "paredes"}
    )
    before = _versions(folder)

    await call(client, "aplicar_mapeo", project_path=path, mapping={"A-MURO": "walls"})
    assert "No existe el muro muro-0999" in await fails(
        client, "confirmar_escala", project_path=path, muro_id="muro-0999", longitud_real=4.0
    )
    assert "juntos" in await fails(
        client, "confirmar_escala", project_path=path, muro_id="muro-0001"
    )
    assert "mayor que 0" in await fails(
        client, "confirmar_escala", project_path=path, muro_id="muro-0001", longitud_real=-1.0
    )
    message = await fails(
        client, "comparar_versiones", project_path=path, version_a="zzz", version_b="HEAD"
    )
    assert "La versión 'zzz' no existe" in message and "Versiones recientes" in message
    assert _versions(folder) == before + 1  # solo el aplicar_mapeo que sí funcionó


# --- Recurso y respuestas cortas ---------------------------------------------------------


async def test_the_resource_follows_the_last_project_used(client: Client, tmp_path: Path) -> None:
    assert "usa abrir_proyecto" in await read_model(client)
    await call(client, "abrir_proyecto", project_path=str(tmp_path / "uno"))
    await call(client, "abrir_proyecto", project_path=str(tmp_path / "dos"))
    assert "Proyecto «dos»" in await read_model(client)
    await call(client, "listar_espacios", project_path=str(tmp_path / "uno"))
    summary = await read_model(client)
    assert "Proyecto «uno»" in summary and "Escala: sin confirmar" in summary


async def test_long_lists_are_cut_short(client: Client, tmp_path: Path) -> None:
    """120 espacios que apuntan a un nivel inexistente: 120 espacios y 120 errores que listar."""
    folder = tmp_path / "torre"
    await call(client, "abrir_proyecto", project_path=str(folder))
    project = load_project(folder).model_copy(update={"scale_confirmed": True})
    for i in range(120):
        x, y = (i % 12) * 4.0, (i // 12) * 4.0
        project.spaces.append(
            Space(
                id=new_id(project, "esp"),
                level_id="niv-0099",
                name=f"Oficina {i + 1}",
                polygon=SpacePolygon(exterior=[(x, y), (x + 3, y), (x + 3, y + 3), (x, y + 3)]),
                category="useful",
            )
        )
    save_project(project, folder)
    path = str(folder)

    # call() ya comprueba que ninguna respuesta pasa de 50 líneas.
    assert "  … y 76 más" in await call(client, "listar_espacios", project_path=path)
    assert "  … y 79 más" in await call(client, "cuadro_de_areas", project_path=path)
    validation = await call(client, "validar_modelo", project_path=path)
    assert "120 errores" in validation and "  … y 76 más" in validation
