"""Los 20 pedidos de tests/pedidos_bloques.yaml, llamados por MCP como desde Claude Desktop y con
el catalog.yaml real (una copia, para que agregar_al_catalogo no lo cambie). Comprueba que cada
llamada esperada es válida y que lo resuelto es lo que dice la lista: si se cambia el catálogo,
esta prueba avisa qué pedidos hay que actualizar."""

import shutil
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
import yaml
from archimind_bloques import DEFAULT_CATALOG_PATH, load_catalog
from archimind_bloques import server as bloques_server
from archimind_bloques.create import BlockRequest, create_block
from archimind_bloques.fit import Preferences, fit_to_opening
from archimind_bloques.insert import DRAFT_NAME
from archimind_core import (
    apply_mapping,
    export_dxf,
    import_drawing,
    open_project,
    outputs_dir,
    proposals_to_mapping,
    propose_mapping,
)
from archimind_schema import BlocksDraft, Project, load_project
from golden import GOLDEN_DIR
from mcp import Client
from mcp.types import TextContent

pytestmark = pytest.mark.anyio

PEDIDOS_PATH = Path(__file__).parents[1] / "pedidos_bloques.yaml"
PEDIDOS: list[dict[str, Any]] = yaml.safe_load(PEDIDOS_PATH.read_text(encoding="utf-8"))["pedidos"]
CATALOG_TOOLS = {"listar_catalogo", "agregar_al_catalogo"}


def test_there_are_twenty_requests_for_every_tool() -> None:
    assert len(PEDIDOS) == 20
    assert {p["herramienta"] for p in PEDIDOS} == {
        "listar_catalogo",
        "crear_bloque",
        "ajustar_bloque_a_vano",
        "insertar_bloques_en_plano",
        "agregar_al_catalogo",
    }
    assert all(("esperado" in p) != ("error" in p) for p in PEDIDOS)


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """apto_2hab construido y exportado con core, como en la preparación de la lista."""
    folder = tmp_path_factory.mktemp("plantilla") / "casa"
    open_project(folder)
    drawing = import_drawing(folder, GOLDEN_DIR / "apto_2hab" / "input.dxf")
    apply_mapping(folder, drawing, proposals_to_mapping(propose_mapping(drawing)))
    export_dxf(load_project(folder), outputs_dir(folder) / "casa.dxf")
    return folder


@pytest.fixture
async def bloques(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> AsyncIterator[Client]:
    catalog = tmp_path / "catalog.yaml"
    shutil.copy(DEFAULT_CATALOG_PATH, catalog)
    monkeypatch.setattr(bloques_server, "catalog_path", catalog)
    async with Client(bloques_server.mcp) as connected:
        yield connected


@pytest.mark.parametrize(
    "pedido", PEDIDOS, ids=[f"{i + 1:02d}-{p['herramienta']}" for i, p in enumerate(PEDIDOS)]
)
async def test_request(
    pedido: dict[str, Any], bloques: Client, built: Path, tmp_path: Path
) -> None:
    folder = tmp_path / "casa"
    shutil.copytree(built, folder)
    tool, arguments = pedido["herramienta"], dict(pedido["argumentos"])
    if tool not in CATALOG_TOOLS:
        arguments["project_path"] = str(folder)

    result = await bloques.call_tool(tool, arguments)

    content = result.content
    assert len(content) == 1 and isinstance(content[0], TextContent)
    text = content[0].text
    if "error" in pedido:
        assert result.is_error and pedido["error"] in text, text
        return
    assert not result.is_error, text
    expected = pedido["esperado"]
    for phrase in expected.get("texto", []):
        assert phrase in text
    project = load_project(folder)
    if tool == "crear_bloque":
        request = BlockRequest.model_validate(arguments["parametros"])
        resolution = create_block(arguments["tipo"], request, load_catalog())
        _check(expected, resolution.params, resolution.profile_key, None)
    elif tool == "ajustar_bloque_a_vano":
        _check_fit(expected, project, arguments["vano_id"], arguments.get("preferencias", {}))
    elif tool == "insertar_bloques_en_plano":
        draft = BlocksDraft.model_validate_json((folder / "salidas" / DRAFT_NAME).read_text())
        assert {a.opening_id for a in draft.assignments} == set(expected["vanos"])
        preferences = arguments.get("asignaciones", {})
        for opening_id, fields in expected["vanos"].items():
            _check_fit(fields, project, opening_id, preferences.get(opening_id, {}))


def _check_fit(
    expected: dict[str, Any], project: Project, opening_id: str, preferences: dict[str, Any]
) -> None:
    chosen = Preferences.model_validate(preferences)
    fit = fit_to_opening(project, opening_id, chosen, load_catalog())
    _check(expected, fit.params, fit.profile_key, fit.site.room.id if fit.site.room else None)


def _check(expected: dict[str, Any], params: Any, profile_key: str, room: str | None) -> None:
    for field, value in expected.items():
        if field == "texto":
            continue
        actual = {"profile": profile_key, "opens_into": room}.get(field, None)
        if field not in ("profile", "opens_into"):
            actual = getattr(params, field)
        if isinstance(value, float):
            assert actual == pytest.approx(value), field
        else:
            assert actual == value, field
