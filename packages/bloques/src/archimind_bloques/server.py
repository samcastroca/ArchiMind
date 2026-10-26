"""Servidor MCP archimind-bloques: carpintería paramétrica, suelta o en los vanos del modelo.

Cada herramienta es una envoltura delgada sobre la lógica del paquete y responde con un resumen
y rutas de archivo. Nunca escribe `modelo.json`: la carpintería de los vanos se entrega a core en
un borrador (`asignar_bloques` de archimind-core). El catálogo es único para todos los proyectos,
así que sus dos herramientas no reciben `project_path`. Se ejecuta con
`uv run --package archimind-bloques archimind-bloques`.
"""

import functools
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Literal, ParamSpec

from archimind_schema import MODEL_FILENAME, load_project
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from archimind_bloques import summaries
from archimind_bloques.catalog import (
    DEFAULT_CATALOG_PATH,
    CarpentryType,
    CatalogError,
    Profile,
    add_profile,
    load_catalog,
)
from archimind_bloques.create import BlockRequest, create_block
from archimind_bloques.export_3dm import export_3dm
from archimind_bloques.export_dxf import export_dxf
from archimind_bloques.fit import Preferences, fit_to_opening
from archimind_bloques.generate import generate
from archimind_bloques.geometry import Carpentry
from archimind_bloques.insert import OUTPUTS_DIR, InsertError, insert_blocks
from archimind_bloques.render import export_svg, render_png
from archimind_bloques.resolve import FitError

INSTRUCTIONS = """\
ArchiMind genera bloques de carpintería (puertas y ventanas) con los perfiles del catálogo.
Bloque suelto, con las medidas que dé el usuario: crear_bloque. Carpintería de un proyecto:
ajustar_bloque_a_vano (consulta, no escribe nada) → insertar_bloques_en_plano (DXF con la
carpintería y un borrador) → asignar_bloques de archimind-core, que la guarda en el modelo.
Los IDs de vano (vano-) y de recinto (esp-) salen de listar_vanos y listar_espacios de
archimind-core.
No inventes medidas: pasa solo las que dio el usuario; lo que falta sale del vano o del catálogo
y la respuesta dice qué se supuso. Las claves de parametros y preferencias son las del esquema,
en inglés (width, height, leaves, hand, swing, material…)."""

READS = ToolAnnotations(read_only_hint=True, open_world_hint=False)
WRITES_OUTPUT = ToolAnnotations(
    read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False
)
WRITES_CATALOG = ToolAnnotations(
    read_only_hint=False, destructive_hint=False, open_world_hint=False
)
# Errores previstos: su mensaje está escrito para el usuario y llega al modelo como ToolError.
USER_ERRORS = (CatalogError, FitError, InsertError)
BLOCKS_DIR = "bloques"  # dentro de salidas/

Format = Literal["dxf", "svg", "png", "3dm"]
EXPORTS: dict[str, Callable[[Carpentry, Path], Path]] = {
    "dxf": export_dxf,
    "svg": export_svg,
    "png": render_png,
    "3dm": export_3dm,
}

ProjectPath = Annotated[
    str,
    Field(description="Ruta absoluta de la carpeta del proyecto (la que contiene modelo.json)."),
]

mcp = MCPServer("archimind-bloques", instructions=INSTRUCTIONS)
# El catálogo que usan las herramientas; las pruebas lo cambian por el de prueba.
catalog_path: Path = DEFAULT_CATALOG_PATH

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


def _folder(project_path: str) -> Path:
    folder = Path(project_path).expanduser().resolve()
    if not (folder / MODEL_FILENAME).is_file():
        raise ToolError(
            f"No hay un proyecto en {folder}: ábrelo con abrir_proyecto de archimind-core."
        )
    return folder


@_tool(READS)
def listar_catalogo() -> str:
    """Lista los perfiles del catálogo de carpintería, compartido por todos los proyectos: clave,
    nombre, material, tipos que admite, marco, hoja y medidas admisibles de cada hoja, y los
    valores que se usan cuando un pedido no los dice (espesor de muro, antepecho, altos). Úsala
    para saber qué perfiles y materiales hay o cuando el usuario pregunte qué carpintería se
    puede hacer."""
    return summaries.catalog(load_catalog(catalog_path), catalog_path)


@_tool(WRITES_OUTPUT)
def crear_bloque(
    project_path: ProjectPath,
    tipo: Annotated[
        CarpentryType,
        Field(
            description="swing_door (puerta batiente), double_swing_door (batiente doble), "
            "sliding_door (puerta corrediza), sliding_window (ventana corrediza, 2 a 4 hojas), "
            "fixed_window (ventana fija) o awning_window (ventana proyectante)."
        ),
    ],
    parametros: BlockRequest,
    formatos: Annotated[
        list[Format],
        Field(description='Formatos de salida: "dxf", "svg", "png" y "3dm" (Rhino).'),
    ] = ["dxf", "png"],  # noqa: B006 (el SDK solo lo lee para el esquema)
) -> str:
    """Genera un bloque de carpintería suelto, sin un vano del modelo, y lo guarda en
    salidas/bloques/ del proyecto en los formatos pedidos. Úsala cuando el usuario pida una
    puerta o ventana dando sus medidas. En parametros, width (metros) es obligatorio; lo demás
    solo si el usuario lo dijo: height, material o profile, leaves, hand, swing, side,
    sill_height, wall_thickness, leaf_thickness. En «A × B», A es el ancho y B el alto.
    Ejemplo: «ventana corrediza de aluminio de 3 hojas de 2.40 × 1.50» → tipo="sliding_window",
    parametros={"width": 2.40, "height": 1.50, "leaves": 3, "material": "aluminio"}.
    Otro: «puerta de madera de 0.90 que abra hacia afuera, mano derecha» → tipo="swing_door",
    parametros={"width": 0.90, "material": "madera", "swing": "out", "hand": "right"}.
    Devuelve el perfil elegido, la medida de las hojas, lo que se supuso y las rutas."""
    folder = _folder(project_path)
    resolution = create_block(tipo, parametros, load_catalog(catalog_path))
    carpentry = generate(resolution.params)
    target = folder / OUTPUTS_DIR / BLOCKS_DIR
    paths = [
        EXPORTS[fmt](carpentry, target / f"{carpentry.name}.{fmt}")
        for fmt in dict.fromkeys(formatos)
    ]
    return summaries.created(resolution, carpentry, paths)


@_tool(READS)
def ajustar_bloque_a_vano(
    project_path: ProjectPath,
    vano_id: Annotated[str, Field(description="ID del vano (p. ej. vano-0003), de listar_vanos.")],
    preferencias: Preferences | None = None,
) -> str:
    """Propone la carpintería de un vano del modelo sin escribir nada: tipo, perfil, hojas, mano
    y hacia qué recinto abre, con el porqué de cada elección. Las medidas salen del vano y del
    muro. preferencias, todas opcionales: type, material o profile, leaves, hand, swing, side,
    leaf_thickness y opens_into (el esp- del recinto hacia el que abre). Ejemplos: «en el
    vano-0003 una corrediza de aluminio de 3 hojas» → vano_id="vano-0003",
    preferencias={"type": "sliding_window", "material": "aluminio", "leaves": 3}; «que la
    puerta vano-0007 abra hacia el pasillo esp-0002» → vano_id="vano-0007",
    preferencias={"opens_into": "esp-0002"}. Devuelve también las asignaciones listas para
    insertar_bloques_en_plano."""
    folder = _folder(project_path)
    project = load_project(folder)
    chosen = preferencias or Preferences()
    fit = fit_to_opening(project, vano_id, chosen, load_catalog(catalog_path))
    opening = next(o for o in project.openings if o.id == fit.opening_id)
    line = summaries.opening_line(fit, opening.kind, opening.width, opening.height, opening.wall_id)
    requested = chosen.model_dump(exclude_none=True)
    return summaries.fitted(fit, generate(fit.params), requested, line)


@_tool(WRITES_OUTPUT)
def insertar_bloques_en_plano(
    project_path: ProjectPath,
    asignaciones: Annotated[
        dict[str, Preferences] | None,
        Field(
            description="Preferencias por vano, {vano_id: preferencias}, las mismas de "
            "ajustar_bloque_a_vano ({} para lo de por defecto). Sin asignaciones, todos los "
            "vanos de puerta y ventana que aún no tienen bloque."
        ),
    ] = None,
) -> str:
    """Inserta la carpintería en el plano del proyecto: parte de salidas/<proyecto>.dxf (que
    exporta exportar_plano de archimind-core con formato "dxf"; hace falta la escala
    confirmada), cambia el rectángulo de cada vano por su bloque, rotado según el muro y
    abriendo hacia el lado que corresponde, y escribe salidas/<proyecto>-carpinteria.dxf. Los
    vanos que ya tienen bloque en el modelo se vuelven a dibujar. Ejemplo: «pon una corrediza de
    3 hojas en vano-0003 y la puerta por defecto en vano-0001» →
    asignaciones={"vano-0003": {"type": "sliding_window", "leaves": 3}, "vano-0001": {}}. No
    modifica el modelo: deja salidas/borrador_bloques.json, que se guarda con asignar_bloques
    de archimind-core cuando el usuario esté conforme. Si un vano no calza, no escribe nada y
    dice por qué."""
    folder = _folder(project_path)
    result = insert_blocks(folder, asignaciones, load_catalog(catalog_path))
    return summaries.inserted(result, folder)


@_tool(WRITES_CATALOG)
def agregar_al_catalogo(
    clave: Annotated[
        str, Field(description="Clave del perfil: minúsculas, números y guiones bajos (pvc_70).")
    ],
    perfil: Profile,
) -> str:
    """Agrega un perfil de carpintería al catálogo, compartido por todos los proyectos. Úsala
    cuando el usuario dé las medidas de un perfil de fabricante; no inventes ninguna: si falta
    alguna, pregúntala. perfil, en metros: name, material, types (de swing_door,
    double_swing_door, sliding_door, sliding_window, fixed_window, awning_window), frame {face:
    ancho visto, depth: fondo}, sash {face, depth} (la hoja), overlap (traslape), glass (espesor
    del vidrio), sash_width {min, max} y sash_height {min, max} (medidas admisibles de cada
    hoja). Ejemplo: clave="pvc_70", perfil={"name": "PVC serie 70", "material": "pvc", "types":
    ["sliding_window", "fixed_window"], "frame": {"face": 0.06, "depth": 0.07}, "sash": {"face":
    0.05, "depth": 0.03}, "overlap": 0.03, "glass": 0.005, "sash_width": {"min": 0.35, "max":
    1.10}, "sash_height": {"min": 0.35, "max": 1.60}}. Si la clave ya existe, no cambia nada."""
    updated = add_profile(catalog_path, clave, perfil)
    return summaries.profile_added(clave, updated, catalog_path)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
