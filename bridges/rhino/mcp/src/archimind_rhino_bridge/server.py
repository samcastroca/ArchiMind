"""Servidor MCP rhino-bridge: el modelo de un proyecto en Rhino 8 y lo que se edita allí.

Habla con el puente que corre dentro de Rhino (`bridges/rhino/plugin/archimind_bridge.py`), que
el usuario inicia desde el editor de scripts. Cada herramienta es una envoltura delgada y responde
con un resumen y rutas de archivo. Nunca escribe `modelo.json`: lo que cambió en Rhino se entrega
en un borrador (`salidas/borrador_rhino.json`). Se ejecuta con
`uv run --package archimind-rhino-bridge archimind-rhino-bridge`.
"""

import functools
import os
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any, ParamSpec

from archimind_schema import Project
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field, ValidationError

from archimind_rhino_bridge import summaries
from archimind_rhino_bridge.changes import read_changes
from archimind_rhino_bridge.client import BridgeError, RhinoBridge
from archimind_rhino_bridge.files import (
    ProjectError,
    ProjectModel,
    applied_draft,
    create_empty_3dm,
    draft_file,
    load_model,
    rhino_file,
    write_draft,
)
from archimind_rhino_bridge.scene import LAYERS, scene

INSTRUCTIONS = """\
rhino-bridge lleva el modelo de un proyecto de ArchiMind a Rhino 8 y lee lo que se editó allí.
Hace falta Rhino abierto con el puente iniciado (un script que el usuario ejecuta en el editor de
scripts de Rhino); si no responde, el error dice qué script ejecutar.
Flujo: abrir_en_rhino (crea o abre salidas/<proyecto>.3dm con las capas ArchiMind::Muros, ::Vanos
y ::Espacios) → el usuario edita en Rhino → leer_cambios (deja un borrador con lo modificado, lo
nuevo y lo borrado) → aplicar_borrador de archimind-core lo guarda en el modelo → abrir_en_rhino
recarga las capas. guardar_3dm cuando quiera conservar el archivo. estado_rhino dice si Rhino
responde y si el documento es del proyecto.
El modelo lo escribe solo archimind-core; este servidor nunca lo modifica. Las medidas salen de
estas herramientas; no las calcules."""

READS = ToolAnnotations(read_only_hint=True, open_world_hint=False)
OPENS = ToolAnnotations(read_only_hint=False, destructive_hint=True, open_world_hint=False)
WRITES_OUTPUT = ToolAnnotations(
    read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False
)
# Errores previstos: su mensaje está escrito para el usuario y llega al modelo como ToolError.
USER_ERRORS = (BridgeError, ProjectError)

ProjectPath = Annotated[
    str,
    Field(description="Ruta absoluta de la carpeta del proyecto (la que contiene modelo.json)."),
]

mcp = MCPServer("rhino-bridge", instructions=INSTRUCTIONS)
bridge = RhinoBridge()

P = ParamSpec("P")


def _tool(annotations: ToolAnnotations) -> Callable[[Callable[P, str]], Callable[P, str]]:
    """Registra la herramienta y convierte los errores previstos en ToolError: en el SDK, el
    mensaje de cualquier otra excepción no llega al cliente. Las respuestas son texto, sin
    salida estructurada que lo repita como JSON."""

    def register(fn: Callable[P, str]) -> Callable[P, str]:
        @functools.wraps(fn)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> str:
            try:
                return fn(*args, **kwargs)
            except USER_ERRORS as exc:
                raise ToolError(str(exc)) from exc

        mcp.tool(annotations=annotations, structured_output=False)(wrapper)
        return fn

    return register


def _same(project: str | None, folder: Path) -> bool:
    if not project:
        return False
    return os.path.normcase(str(Path(project).resolve())) == os.path.normcase(str(folder))


def _base(state: dict[str, Any]) -> Project:
    try:
        return Project.model_validate_json(state["base_model"] or "")
    except ValidationError as exc:
        raise ProjectError(
            "El modelo que guarda el documento de Rhino no es válido: vuelve a cargarlo con "
            "abrir_en_rhino y descartar_cambios=True."
        ) from exc


def _check_own(project: str | None, model: ProjectModel) -> None:
    if not _same(project, model.folder):
        raise ProjectError(
            f"El documento abierto en Rhino no es el de {model.folder.name}: ábrelo con "
            "abrir_en_rhino."
        )


def _per_layer(objects: list[dict[str, Any]]) -> dict[str, int]:
    """Objetos con archimind_id por subcapa."""
    found = dict.fromkeys(LAYERS.values(), 0)
    for record in objects:
        name = str(record.get("layer", "")).removeprefix("ArchiMind::")
        if record.get("id") and name in found:
            found[name] += 1
    return found


@_tool(READS)
def estado_rhino(project_path: ProjectPath) -> str:
    """Comprueba si Rhino está abierto con el puente iniciado y qué documento tiene: su ruta, si
    tiene cambios sin guardar, si sus capas ArchiMind son de este proyecto (con cuántos muros,
    vanos y espacios) y si el modelo cambió desde que se cargó. No modifica nada. Úsala cuando el
    usuario pregunte por Rhino o antes de las demás si no sabes si está abierto."""
    model = load_model(project_path)
    info: dict[str, Any] = bridge.call("ping")
    archimind = info.get("archimind") or {}
    same = _same(archimind.get("project"), model.folder)
    return summaries.status(model.sha256, model.folder, info, same)


@_tool(OPENS)
def abrir_en_rhino(
    project_path: ProjectPath,
    descartar_cambios: Annotated[
        bool,
        Field(
            description="Solo si el usuario acepta perder las ediciones de Rhino que aún no se "
            "leyeron con leer_cambios."
        ),
    ] = False,
) -> str:
    """Abre el proyecto en Rhino: salidas/<proyecto>.3dm (lo crea en metros si no existe) con
    el modelo en las capas ArchiMind::Muros (muros como sólidos), ::Vanos (una caja en cada hueco)
    y ::Espacios (superficies), cada objeto con su archimind_id. Si el modelo no cambió desde la
    última carga, conserva lo editado en Rhino; si cambió, recarga esas capas (las demás no se
    tocan) y guarda el archivo. Si en Rhino hay ediciones sin leer y el modelo cambió, no hace
    nada y lo dice: primero leer_cambios, o descartar_cambios=True si el usuario las quiere
    perder. Rhino no debe tener otro documento con cambios sin guardar."""
    model = load_model(project_path)
    project = model.project
    if not (project.walls or project.openings or project.spaces):
        raise ProjectError(
            f"El modelo de {project.name} está vacío: reconstrúyelo con aplicar_mapeo de "
            "archimind-core."
        )
    target = rhino_file(model.folder)
    if not target.is_file():
        create_empty_3dm(target)
    bridge.call("open_file", path=str(target))
    state: dict[str, Any] = bridge.call("read_tagged_objects")
    same = _same(state.get("project"), model.folder)
    if same and state.get("base_sha256") == model.sha256:
        kept = _per_layer(state["objects"])
        return summaries.opened(target, None, kept, [], None, not project.scale_confirmed)
    discarded: list[str] = []
    applied = False
    if same:
        try:
            pending = read_changes(_base(state), state["objects"], state["base_sha256"])
        except ProjectError:
            if not descartar_cambios:
                raise
        else:
            applied = pending.draft is not None and pending.draft == applied_draft(model.folder)
            if pending.draft is not None and not applied and not descartar_cambios:
                raise ProjectError(summaries.pending(pending.lines))
            discarded = pending.lines if pending.draft is not None and not applied else []
    result: dict[str, Any] = bridge.call(
        "load_model_layers",
        project=str(model.folder),
        base_sha256=model.sha256,
        base_model=model.text,
        objects=scene(project),
    )
    bridge.call("save_as", path=str(target))
    foreign = state.get("project") if state.get("project") and not same else None
    return summaries.opened(
        target, result["loaded"], {}, discarded, foreign, not project.scale_confirmed, applied
    )


@_tool(WRITES_OUTPUT)
def leer_cambios(project_path: ProjectPath) -> str:
    """Lee lo que se editó en Rhino en las capas ArchiMind respecto del modelo que se cargó:
    muros movidos, girados, estirados o con otro espesor o alto, vanos desplazados o con otra
    medida, espacios con otro contorno o renombrados, lo que se borró y lo dibujado sin
    archimind_id en las capas ArchiMind (muros, vanos y espacios nuevos). Lo deja en
    salidas/borrador_rhino.json sin modificar el modelo, y avisa de lo que no puede leer
    (copias, sólidos que ya no son prismas rectangulares). Úsala cuando el usuario diga que
    terminó de editar en Rhino; después, aplicar_borrador de archimind-core lo guarda."""
    model = load_model(project_path)
    state: dict[str, Any] = bridge.call("read_tagged_objects")
    _check_own(state.get("project"), model)
    result = read_changes(_base(state), state["objects"], state["base_sha256"])
    stale = state["base_sha256"] != model.sha256
    if stale and result.draft is not None and result.draft == applied_draft(model.folder):
        write_draft(model.folder, None)
        return summaries.already_applied(len(result.lines))
    had_draft = draft_file(model.folder).is_file()
    path = write_draft(model.folder, result.draft)
    return summaries.changes(result, path, had_draft and path is None, stale)


@_tool(WRITES_OUTPUT)
def guardar_3dm(project_path: ProjectPath) -> str:
    """Guarda el documento de Rhino del proyecto en salidas/<proyecto>.3dm, con todo lo que
    tenga (también las capas que no son de ArchiMind). Úsala cuando el usuario quiera conservar
    el archivo de Rhino; no lee los cambios: para eso, leer_cambios."""
    model = load_model(project_path)
    info: dict[str, Any] = bridge.call("ping")
    _check_own((info.get("archimind") or {}).get("project"), model)
    target = rhino_file(model.folder)
    bridge.call("save_as", path=str(target))
    return summaries.saved(target)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
