"""Servidor MCP archimind-core: el único que escribe el modelo semántico de un proyecto.

Cada herramienta es una envoltura delgada sobre la lógica del paquete: recibe `project_path`,
responde con un resumen y rutas de archivo, y si modifica el modelo hace un commit en el
repositorio del proyecto. Se ejecuta con `uv run --package archimind-core archimind-core`.
"""

import functools
import os
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Literal, ParamSpec

from archimind_schema import Project, save_project, validate
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from archimind_core import summaries
from archimind_core.blocks import DRAFT_PATH, BlocksError, apply_block_draft
from archimind_core.build_rules import BuildRulesError
from archimind_core.compare import compare_versions
from archimind_core.drawing import DrawingError
from archimind_core.export_dwg import DwgVersion, export_dwg
from archimind_core.export_dxf import ExportError, export_dxf
from archimind_core.history import HistoryError, commit, load_version
from archimind_core.inventory import layer_inventory
from archimind_core.layer_roles import propose_mapping
from archimind_core.layer_rules import LayerRulesError
from archimind_core.mapping import MappingError
from archimind_core.project import (
    ProjectError,
    active_drawing,
    apply_mapping,
    import_drawing,
    load_existing,
    open_project,
    outputs_dir,
    project_folder,
)
from archimind_core.quantities import QuantitiesError, area_table, export_area_table_csv
from archimind_core.render import render_model
from archimind_core.scale import ScaleError, confirm_scale

INSTRUCTIONS = """\
ArchiMind convierte planos arquitectónicos DXF/DWG en un modelo semántico (muros, vanos,
espacios) guardado en la carpeta de cada proyecto y versionado con git.
Flujo: abrir_proyecto → importar_plano → proponer_mapeo_capas → aplicar_mapeo (con la propuesta
revisada) → confirmar_escala → consultas (listar_espacios, listar_vanos, cuadro_de_areas,
validar_modelo), exportar_plano (png, dxf o dwg) y comparar_versiones.
La carpintería la propone archimind-bloques (insertar_bloques_en_plano) en un borrador; se guarda
en el modelo con asignar_bloques.
Las áreas, longitudes y cantidades salen siempre de estas herramientas; no las calcules ni las
estimes. Si la escala no está confirmada, toda cantidad es PRELIMINAR y hay que decirlo."""

MODEL_URI = "archimind://proyecto/modelo"
# Con "1", el servidor corre en remoto: no está en el equipo del usuario y no exporta DWG.
REMOTE_ENV = "ARCHIMIND_REMOTO"
READS = ToolAnnotations(read_only_hint=True, open_world_hint=False)
WRITES_MODEL = ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=False)
WRITES_OUTPUT = ToolAnnotations(
    read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False
)
# Errores previstos: su mensaje está escrito para el usuario y llega al modelo como ToolError.
USER_ERRORS = (
    BlocksError,
    BuildRulesError,
    DrawingError,
    ExportError,
    HistoryError,
    LayerRulesError,
    MappingError,
    ProjectError,
    QuantitiesError,
    ScaleError,
)

ProjectPath = Annotated[
    str,
    Field(description="Ruta absoluta de la carpeta del proyecto (la que contiene modelo.json)."),
]

mcp = MCPServer("archimind-core", instructions=INSTRUCTIONS)
# Única memoria de la sesión: qué proyecto resume el recurso. El estado vive en la carpeta.
_current_project: Path | None = None

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


def _use(project_path: str) -> tuple[Path, Project]:
    """Carga el proyecto y lo recuerda como el actual del recurso."""
    global _current_project
    folder = project_folder(project_path)
    project = load_existing(folder)
    _current_project = folder
    return folder, project


def _relative(folder: Path, path: Path) -> str:
    return path.relative_to(folder).as_posix() if path.is_relative_to(folder) else str(path)


@_tool(WRITES_MODEL)
def abrir_proyecto(project_path: ProjectPath) -> str:
    """Abre la carpeta de un proyecto de ArchiMind y, si no existe, la crea con su modelo.json,
    su carpeta salidas/ y su repositorio git. Úsala siempre primero: las demás herramientas
    necesitan un proyecto abierto. Devuelve el resumen del modelo y las últimas versiones."""
    opened = open_project(project_path)
    name = opened.project.name
    message = f"Crea el proyecto {name}" if opened.created else f"Versiona los cambios de {name}"
    version = commit(opened.folder, message)
    _use(str(opened.folder))
    return summaries.opened(opened.folder, opened.created, version)


@_tool(WRITES_MODEL)
def importar_plano(
    project_path: ProjectPath,
    file_path: Annotated[
        str,
        Field(description="Ruta del plano .dxf o .dwg; si es relativa, desde la carpeta."),
    ],
) -> str:
    """Importa un plano DXF o DWG: lo copia a planos/ dentro del proyecto, lo deja como plano
    activo y detecta sus unidades. Todavía no reconstruye el modelo. Úsala con cada plano nuevo
    o cuando el plano cambie. Devuelve las capas y las unidades detectadas. Siguiente paso:
    proponer_mapeo_capas. Un DWG necesita ODA File Converter instalado."""
    folder, _ = _use(project_path)
    drawing = import_drawing(folder, file_path)
    inventory = layer_inventory(drawing)
    plan = _relative(folder, drawing.path)
    units = summaries.UNIT_NAMES.get(drawing.units.name, drawing.units.name)
    how = "declaradas" if drawing.units.confirmed else "inferidas"
    version = commit(
        folder,
        f"Importa {plan} ({summaries.count(len(inventory), 'capa')}, unidades {how}: {units})",
    )
    return summaries.imported(plan, drawing.units, inventory, version)


@_tool(READS)
def proponer_mapeo_capas(project_path: ProjectPath) -> str:
    """Propone qué representa cada capa del plano activo (walls, doors, windows, text,
    dimensions, axes, furniture, ignore o mixed) con una confianza y la evidencia: el nombre de
    la capa y lo que dibuja. No modifica nada. Úsala después de importar_plano y muestra la
    propuesta al usuario antes de aplicar_mapeo, sobre todo las capas de confianza baja."""
    folder, _ = _use(project_path)
    drawing = active_drawing(folder)
    return summaries.proposals(_relative(folder, drawing.path), propose_mapping(drawing))


@_tool(WRITES_MODEL)
def aplicar_mapeo(
    project_path: ProjectPath,
    mapping: Annotated[
        dict[str, str],
        Field(
            description=(
                "Rol de cada capa, {capa: rol}. Roles: walls, doors, windows, text, dimensions, "
                "axes, furniture, ignore, mixed. Las capas que no aparecen se ignoran."
            )
        ),
    ],
) -> str:
    """Guarda el mapeo de capas y reconstruye el modelo (muros, vanos y espacios) desde el plano
    activo. Úsala con la propuesta de proponer_mapeo_capas, tal cual o corregida por el usuario,
    y cada vez que haya que cambiar un rol. Reemplaza los muros, vanos y espacios anteriores por
    otros con IDs nuevos, y la escala vuelve a ser la del plano: si se había confirmado o
    recalculado con confirmar_escala, hay que repetirlo. Devuelve los conteos y los avisos."""
    folder, _ = _use(project_path)
    drawing = active_drawing(folder)
    result = apply_mapping(folder, drawing, mapping)
    project = result.project
    version = commit(
        folder,
        f"Aplica el mapeo de capas: {len(project.walls)} muros, {len(project.openings)} vanos, "
        f"{len(project.spaces)} espacios",
    )
    return summaries.applied(_relative(folder, drawing.path), result, version)


@_tool(WRITES_MODEL)
def confirmar_escala(
    project_path: ProjectPath,
    muro_id: Annotated[
        str | None,
        Field(description="ID del muro de referencia (p. ej. muro-0003), junto con longitud_real."),
    ] = None,
    longitud_real: Annotated[
        float | None,
        Field(description="Longitud real del eje de ese muro, en metros (mayor que 0)."),
    ] = None,
) -> str:
    """Confirma la escala del modelo para que las cantidades dejen de ser preliminares.
    Sin muro_id ni longitud_real, confirma las unidades detectadas al importar: úsala cuando el
    usuario confirme que el plano está en esas unidades. Con los dos, recalcula la escala: escala
    todo el modelo para que el eje de ese muro mida longitud_real metros; úsala cuando el usuario
    conozca una medida real. Necesita el modelo reconstruido con aplicar_mapeo."""
    folder, project = _use(project_path)
    confirmation = confirm_scale(project, muro_id, longitud_real)
    units = active_drawing(folder).units if muro_id is None and confirmation.changed else None
    if not confirmation.changed:
        return summaries.scale(confirmation, muro_id, units)
    save_project(confirmation.project, folder)
    version = commit(folder, summaries.scale_commit_message(confirmation, muro_id))
    return f"{summaries.scale(confirmation, muro_id, units)}\nVersión {version}."


@_tool(READS)
def validar_modelo(project_path: ProjectPath) -> str:
    """Revisa el modelo y lista todos sus errores y avisos: IDs, referencias, polígonos,
    solapes, vanos fuera del muro, espesores, uniones abiertas y escala. No modifica nada.
    Úsala después de aplicar_mapeo o cuando una cantidad parezca rara."""
    _, project = _use(project_path)
    return summaries.problems(project, validate(project))


@_tool(READS)
def listar_espacios(project_path: ProjectPath) -> str:
    """Lista los espacios del modelo con su ID, nombre, categoría y área. Úsala para ver qué
    recintos se reconocieron o para buscar el ID de un espacio. Para los totales, usa
    cuadro_de_areas."""
    _, project = _use(project_path)
    return summaries.spaces(project)


@_tool(READS)
def listar_vanos(project_path: ProjectPath) -> str:
    """Lista las puertas, ventanas y vanos libres: el conteo por tipo y medida, y cada vano con
    su ancho, alto, antepecho y muro. Úsala para revisar la carpintería del modelo."""
    _, project = _use(project_path)
    return summaries.openings(project)


@_tool(WRITES_OUTPUT)
def cuadro_de_areas(project_path: ProjectPath) -> str:
    """Calcula el cuadro de áreas: el área de cada espacio y los totales de área útil,
    construida y de balcones. Con la escala confirmada, también lo exporta a
    salidas/cuadro_de_areas.csv; si no, las áreas salen marcadas PRELIMINAR. Úsala cada vez que
    el usuario pregunte por superficies: nunca las calcules tú."""
    folder, project = _use(project_path)
    table = area_table(project)
    csv_path = None
    if not table.preliminary:
        csv_path = export_area_table_csv(table, outputs_dir(folder) / "cuadro_de_areas.csv")
    return summaries.areas(project, table, csv_path)


@_tool(READS)
def comparar_versiones(
    project_path: ProjectPath,
    version_a: Annotated[
        str,
        Field(description="Versión de partida: hash de commit o referencia como HEAD~1."),
    ],
    version_b: Annotated[
        str,
        Field(description="Versión de llegada: hash de commit o referencia como HEAD."),
    ],
) -> str:
    """Compara dos versiones del modelo: espacios cuya área cambió más de 0.5 %, muros
    añadidos, eliminados o movidos y vanos modificados. Los hashes salen de las respuestas de las
    herramientas que modifican el modelo y del resumen del proyecto. Un aplicar_mapeo intermedio
    da IDs nuevos: sus muros aparecen como eliminados y añadidos."""
    folder, _ = _use(project_path)
    model_a = load_version(folder, version_a)
    model_b = load_version(folder, version_b)
    return summaries.diff(version_a, version_b, compare_versions(model_a, model_b))


@_tool(WRITES_OUTPUT)
def exportar_plano(
    project_path: ProjectPath,
    formato: Annotated[
        Literal["png", "dxf", "dwg"],
        Field(
            description=(
                '"png" para mirar la planta, "dxf" para llevarla a un programa de CAD, "dwg" solo '
                "si el usuario lo pide."
            )
        ),
    ] = "dxf",
    version_dwg: Annotated[
        DwgVersion,
        Field(
            description=(
                'Solo con formato="dwg": "R2018" para AutoCAD 2018 o posterior, "R2013" para '
                "AutoCAD 2013 a 2017."
            )
        ),
    ] = "R2018",
) -> str:
    """Dibuja la planta del modelo en salidas/. Con formato="png", salidas/vista.png: espacios
    con nombre y área, muros y vanos, para revisar a ojo el modelo reconstruido. Con
    formato="dxf" (por defecto), salidas/<proyecto>.dxf: un DXF limpio en metros con los muros
    con los vanos recortados, puertas, ventanas, espacios, sus nombres y sus áreas, cada uno en
    su capa. Ofrécelo para llevar el plano a cualquier CAD (AutoCAD, BricsCAD, Rhino, LibreCAD…);
    es además el plano sobre el que archimind-bloques inserta la carpintería. Con formato="dwg",
    salidas/<proyecto>.dwg, el mismo dibujo, con el DXF al lado: úsalo solo si el usuario pide
    DWG o lo entrega a alguien que trabaja en AutoCAD, con version_dwg="R2013" si usa AutoCAD
    2013 a 2017. El DWG necesita ODA File Converter en el equipo del servidor y no está
    disponible en modo remoto; si falla, ofrece el DXF. DXF y DWG necesitan la escala confirmada.
    Devuelve la ruta del archivo."""
    folder, project = _use(project_path)
    if formato == "png":
        path = render_model(project, outputs_dir(folder) / "vista.png")
        note = "" if project.scale_confirmed else " (escala sin confirmar: áreas preliminares)"
        return f"Vista guardada en {path}{note}."
    if formato == "dwg":
        if os.environ.get(REMOTE_ENV) == "1":
            raise ExportError(
                "El formato DWG no está disponible en modo remoto: la conversión necesita ODA File "
                'Converter instalado en el equipo del servidor. Exporta con formato="dxf": '
                "AutoCAD lo abre igual y desde ahí se puede guardar como DWG."
            )
        path = export_dwg(project, outputs_dir(folder) / f"{folder.name}.dwg", version_dwg)
        return (
            f"DWG {version_dwg} exportado en {path}, con el DXF al lado en "
            f"{path.with_suffix('.dxf')} (metros; capas A-MURO, A-PUERTA, A-VENTANA, A-ESPACIO…)."
        )
    path = export_dxf(project, outputs_dir(folder) / f"{folder.name}.dxf")
    return f"DXF exportado en {path} (metros; capas A-MURO, A-PUERTA, A-VENTANA, A-ESPACIO…)."


@_tool(WRITES_MODEL)
def asignar_bloques(
    project_path: ProjectPath,
    borrador: Annotated[
        str,
        Field(
            description=(
                "Ruta del borrador que escribió insertar_bloques_en_plano; si es relativa, desde "
                "la carpeta del proyecto."
            )
        ),
    ] = DRAFT_PATH,
) -> str:
    """Guarda en el modelo la carpintería que propuso archimind-bloques: a cada vano del
    borrador le pone su bloque (ID blq-) y el lado del muro hacia el que mira. Los vanos con la
    misma carpintería comparten bloque y los bloques que quedan sin uso se quitan. Úsala después
    de insertar_bloques_en_plano (archimind-bloques), cuando el usuario esté conforme con el
    DXF; normalmente sin borrador, que por defecto es salidas/borrador_bloques.json. Si el modelo
    cambió desde el borrador, no aplica nada y pide repetir la inserción. Devuelve vano → bloque y
    la versión."""
    folder, _ = _use(project_path)
    result = apply_block_draft(folder, borrador)
    version = commit(folder, f"Asigna bloques a {summaries.count(len(result.assigned), 'vano')}")
    return summaries.blocks_assigned(result, version)


@mcp.resource(
    MODEL_URI,
    name="modelo",
    title="Modelo del proyecto actual",
    mime_type="text/plain",
)
def modelo_actual() -> str:
    """Resumen del modelo del último proyecto abierto o usado en esta sesión: plano activo,
    escala, conteos, áreas, validación y últimas versiones."""
    if _current_project is None:
        return "No hay ningún proyecto abierto en esta sesión: usa abrir_proyecto con su ruta."
    try:
        return summaries.project_summary(_current_project)
    except USER_ERRORS as exc:
        return str(exc)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
