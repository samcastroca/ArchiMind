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

from archimind_core import BuildRulesError, ExportError, HeightsMissing, load_build_rules
from archimind_core.summaries import heights_missing
from archimind_schema import LENGTH_TOL, CutLine, Point2D, Project
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field, ValidationError

from archimind_rhino_bridge import summaries
from archimind_rhino_bridge.changes import read_changes
from archimind_rhino_bridge.client import BridgeError, RhinoBridge
from archimind_rhino_bridge.drawing_files import DrawingError, parse_segments, write_drawing
from archimind_rhino_bridge.files import (
    ProjectError,
    ProjectModel,
    applied_draft,
    create_empty_3dm,
    draft_file,
    load_model,
    outputs_dir,
    proposed_cut,
    rhino_file,
    write_draft,
)
from archimind_rhino_bridge.scene import LAYERS, scene
from archimind_rhino_bridge.styles import StylesError, load_styles
from archimind_rhino_bridge.views import (
    VIEW_NAMES,
    IsoView,
    Side,
    ViewError,
    cut_camera,
    cut_planes,
    default_depth,
    drawing_pieces,
    iso_camera,
    solids_payload,
)

INSTRUCTIONS = """\
rhino-bridge lleva el modelo de un proyecto de ArchiMind a Rhino 8 y lee lo que se editó allí.
Hace falta Rhino abierto con el puente iniciado (un script que el usuario ejecuta en el editor de
scripts de Rhino); si no responde, el error dice qué script ejecutar.
Flujo: abrir_en_rhino (crea o abre salidas/<proyecto>.3dm con las capas ArchiMind::Muros, ::Vanos
y ::Espacios) → el usuario edita en Rhino → leer_cambios (deja un borrador con lo modificado, lo
nuevo y lo borrado) → aplicar_borrador de archimind-core lo guarda en el modelo → abrir_en_rhino
recarga las capas. guardar_3dm cuando quiera conservar el archivo. estado_rhino dice si Rhino
responde y si el documento es del proyecto.
Dibujos de líneas ocultas del modelo, en DXF y SVG: make2d_axonometria (isométricas, también
explotadas) y corte (con la línea que propone proponer_cortes de archimind-core, por su nombre,
o con dos puntos que dé el usuario).
El modelo lo escribe solo archimind-core; este servidor nunca lo modifica. Las medidas salen de
estas herramientas; no las calcules."""

READS = ToolAnnotations(read_only_hint=True, open_world_hint=False)
OPENS = ToolAnnotations(read_only_hint=False, destructive_hint=True, open_world_hint=False)
WRITES_OUTPUT = ToolAnnotations(
    read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False
)
# Errores previstos: su mensaje está escrito para el usuario y llega al modelo como ToolError.
USER_ERRORS = (
    BridgeError,
    BuildRulesError,
    DrawingError,
    ExportError,
    ProjectError,
    StylesError,
    ViewError,
)

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


SlabThickness = Annotated[
    float | None,
    Field(
        description="Espesor de la losa de piso en metros, si el usuario lo da; si no, el de "
        "build_rules.yaml de archimind-core.",
        gt=0,
    ),
]


@_tool(WRITES_OUTPUT)
def make2d_axonometria(
    project_path: ProjectPath,
    vista: Annotated[
        IsoView,
        Field(
            description='Desde dónde se mira, con el norte en Y+: "iso_so" (suroeste, la '
            'habitual), "iso_se", "iso_ne" o "iso_no".'
        ),
    ] = "iso_so",
    explotada: Annotated[
        bool,
        Field(description="Separa en altura cada nivel y, dentro de él, los muros de su losa."),
    ] = False,
    separacion: Annotated[
        float | None,
        Field(
            description="Solo con explotada: separación en metros; si no, la de estilos.yaml.",
            gt=0,
        ),
    ] = None,
    espesor_losa: SlabThickness = None,
) -> str:
    """Dibuja una axonometría isométrica del modelo con líneas ocultas (HiddenLineDrawing de
    Rhino, como Make2D): las piezas del 3D (muros con los vanos abiertos y una losa por nivel),
    con las líneas visibles en la capa VISIBLES y las ocultas, a trazos, en OCULTAS, con los
    grosores de estilos.yaml. Escribe salidas/axonometria-<vista>[-explotada].dxf y .svg. Hace
    falta Rhino abierto con el puente iniciado (no usa ni cambia su documento), la escala
    confirmada y las alturas: si faltan, no dibuja nada y dice cuáles; pídelas al usuario y
    aplícalas con definir_alturas de archimind-core, nunca las supongas."""
    model = load_model(project_path)
    styles = load_styles()
    gap = separacion or styles.exploded_gap_m
    thickness = espesor_losa or load_build_rules().slab_thickness_m
    try:
        pieces = drawing_pieces(model.project, explotada, gap, thickness)
    except HeightsMissing as missing:
        return heights_missing(missing.missing)
    result = bridge.call(
        "hidden_lines",
        solids=solids_payload(pieces),
        camera=iso_camera(vista, pieces),
        clips=[],
        include_hidden=True,
        tolerance=LENGTH_TOL,
    )
    name = f"axonometria-{vista}" + ("-explotada" if explotada else "")
    folder = outputs_dir(model.folder)
    files = write_drawing(
        parse_segments(result),
        {"visible": "VISIBLES", "hidden": "OCULTAS"},
        styles,
        folder / f"{name}.dxf",
        folder / f"{name}.svg",
    )
    title = f"Axonometría {VIEW_NAMES[vista]}"
    notes = [f"Explotada: {gap:.2f} m entre cada losa y sus muros y entre niveles."]
    return summaries.drawing(title, files, styles, notes if explotada else [])


@_tool(WRITES_OUTPUT)
def corte(
    project_path: ProjectPath,
    linea_de_corte: Annotated[
        str | tuple[Point2D, Point2D],
        Field(
            description='El nombre de un corte de proponer_cortes (p. ej. "longitudinal"), o dos '
            "puntos [[x, y], [x, y]] en metros solo si el usuario los da."
        ),
    ],
    mirando: Annotated[
        Side,
        Field(description="Hacia qué lado de la línea, recorrida del primer punto al segundo."),
    ],
    profundidad: Annotated[
        float | None,
        Field(
            description="Hasta dónde se dibuja lo que hay detrás del corte, en metros; si no, "
            "hasta el fondo del edificio.",
            gt=0,
        ),
    ] = None,
    espesor_losa: SlabThickness = None,
) -> str:
    """Dibuja un corte del modelo con HiddenLineDrawing de Rhino: lo que corta la línea (muros y
    losa) en la capa CORTADO y lo que se ve detrás, hasta la profundidad, en PROYECTADO, con los
    grosores de estilos.yaml (0.50 y 0.18 mm). Escribe salidas/corte-<nombre>.dxf y .svg
    (corte.dxf con puntos). Lo habitual: proponer_cortes de archimind-core, el usuario elige un
    nombre y se pasa en linea_de_corte; si no hay propuesta o el nombre no existe, el error lo
    dice. Hace falta Rhino abierto con el puente iniciado (no usa ni cambia su documento), la
    escala confirmada y las alturas: si faltan, no dibuja nada y dice cuáles; pídelas al
    usuario y aplícalas con definir_alturas de archimind-core, nunca las supongas."""
    model = load_model(project_path)
    styles = load_styles()
    thickness = espesor_losa or load_build_rules().slab_thickness_m
    cut, stale = _cut_line(model, linea_de_corte)
    try:
        pieces = drawing_pieces(model.project, False, 0.0, thickness)
    except HeightsMissing as missing:
        return heights_missing(missing.missing)
    depth = profundidad or default_depth(pieces, cut.start, cut.end, mirando)
    result = bridge.call(
        "hidden_lines",
        solids=solids_payload(pieces),
        camera=cut_camera(cut.start, cut.end, mirando, pieces),
        clips=cut_planes(cut.start, cut.end, mirando, depth),
        include_hidden=False,
        tolerance=LENGTH_TOL,
    )
    name = "corte" if cut.name == "manual" else f"corte-{cut.name}"
    folder = outputs_dir(model.folder)
    files = write_drawing(
        parse_segments(result),
        {"section": "CORTADO", "visible": "PROYECTADO"},
        styles,
        folder / f"{name}.dxf",
        folder / f"{name}.svg",
    )
    source = " (hasta el fondo del edificio)" if profundidad is None else ""
    notes = [f"Profundidad: {depth:.2f} m{source}."]
    if "CORTADO" not in files.counts:
        notes.append("La línea no corta ningún muro ni losa: solo hay vista proyectada.")
    if stale:
        notes.append(
            "El modelo cambió desde proponer_cortes: la línea puede no ser la mejor; vuelve a "
            "proponerlos si el usuario quiere."
        )
    title = f"Corte {cut.label} mirando hacia la {mirando}"
    return summaries.drawing(title, files, styles, notes)


def _cut_line(model: ProjectModel, line: str | tuple[Point2D, Point2D]) -> tuple[CutLine, bool]:
    """El corte propuesto con ese nombre, o uno con los dos puntos dados."""
    if isinstance(line, str):
        return proposed_cut(model, line)
    try:
        return CutLine(name="manual", label="por dos puntos", start=line[0], end=line[1]), False
    except ValidationError as exc:
        raise ViewError("Los dos puntos de la línea de corte deben ser distintos.") from exc


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
