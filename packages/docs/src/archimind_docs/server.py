"""Servidor MCP archimind-docs: documentos del proyecto a partir del modelo y de la base de
datos del usuario.

Cada herramienta es una envoltura delgada: lee `modelo.json` (nunca lo escribe), toma precios,
materiales y programa de la base SQLite, y responde con un resumen y rutas de archivo. Se
ejecuta con `uv run --package archimind-docs archimind-docs`.
"""

import functools
import json
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, ParamSpec

from archimind_core.project import ProjectError, load_existing, outputs_dir, project_folder
from archimind_schema import Project
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from archimind_docs import summaries
from archimind_docs.budget import export_budget_csv, preliminary_budget
from archimind_docs.database import (
    DatabaseError,
    area_program,
    budget_items,
    connect,
    unit_prices,
)
from archimind_docs.errors import DocsError
from archimind_docs.items import model_items
from archimind_docs.memory import project_memory
from archimind_docs.program import check_program
from archimind_docs.sheet import build_sheet
from archimind_docs.verify import NUMBER, unverified_numbers
from archimind_docs.zoning import coefficients

INSTRUCTIONS = """\
archimind-docs produce los documentos de un proyecto de ArchiMind con cifras que salen del
modelo y de la base de datos del usuario (materiales, precios unitarios APU y programa de
áreas), nunca de ti.
Memoria: datos_para_memoria da las cifras verificadas; redacta solo con ellas y pasa el texto a
generar_ficha_pdf, que rechaza cualquier número que no esté en esas cifras y, si todo cuadra,
genera la ficha PDF del proyecto.
Además: presupuesto_preliminar (cantidades del modelo × APU), verificar_programa_areas y
calcular_cos_cus (el área del lote la da el usuario).
Los datos de la base los carga el usuario con el comando archimind-docs-importar."""

READS = ToolAnnotations(read_only_hint=True, open_world_hint=False)
WRITES_OUTPUT = ToolAnnotations(
    read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False
)
# Errores previstos: su mensaje está escrito para el usuario y llega al modelo como ToolError.
USER_ERRORS = (DatabaseError, DocsError, ProjectError)
IMPORT_COMMAND = "uv run --package archimind-docs archimind-docs-importar"

ProjectPath = Annotated[
    str,
    Field(description="Ruta absoluta de la carpeta del proyecto (la que contiene modelo.json)."),
]

mcp = MCPServer("archimind-docs", instructions=INSTRUCTIONS)

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
    folder = project_folder(project_path)
    return folder, load_existing(folder)


@contextmanager
def _database() -> Iterator[sqlite3.Connection]:
    connection = connect()
    try:
        yield connection
    finally:
        connection.close()


@_tool(WRITES_OUTPUT)
def datos_para_memoria(project_path: ProjectPath) -> str:
    """Devuelve en JSON todas las cifras verificadas del proyecto para redactar la memoria
    descriptiva: niveles, conteos de muros, vanos y espacios, cuadro de áreas (cada espacio,
    útil, construida, balcones), metros de muro por espesor, vanos por medida, partidas del
    modelo con sus cantidades y materiales asignados (de la base y de la carpintería). También
    lo guarda en salidas/datos_memoria.json. Úsala antes de redactar cualquier texto con
    números del proyecto: escribe solo estos números (puedes redondearlos), nunca otros."""
    folder, project = _use(project_path)
    with _database() as connection:
        data = project_memory(project, connection)
    path = outputs_dir(folder) / "datos_memoria.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    compact = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return summaries.memory_saved(path, compact, not project.scale_confirmed)


@_tool(WRITES_OUTPUT)
def presupuesto_preliminar(project_path: ProjectPath) -> str:
    """Presupuesto preliminar: cada partida del modelo (muros por espesor en m², puertas y
    ventanas por medida, pisos por categoría) por el precio unitario del APU que le asigna la
    base, con la fecha y la fuente de cada precio. Las partidas sin APU, con un APU en otra
    unidad o sin cantidad quedan marcadas SIN PRECIO con el motivo y no suman: nunca estimes
    su precio. Escribe salidas/presupuesto_preliminar.csv. Si faltan precios, el usuario los
    carga con archimind-docs-importar (tablas unit_prices y budget_items)."""
    folder, project = _use(project_path)
    with _database() as connection:
        rows, prices = budget_items(connection), unit_prices(connection)
    result = preliminary_budget(model_items(project), rows, prices, project.scale_confirmed)
    path = export_budget_csv(result, outputs_dir(folder) / "presupuesto_preliminar.csv")
    return summaries.budget(project.name, result, path)


@_tool(READS)
def verificar_programa_areas(project_path: ProjectPath) -> str:
    """Compara los espacios del modelo con el programa de áreas de la base (espacio exigido y
    área mínima): cada exigencia toma un espacio con ese nombre (sin contar mayúsculas, tildes
    ni el número final: «Habitación» vale para «Habitación 1»). Responde lo que cumple, lo que
    no llega al mínimo y cuánto le falta, lo que falta y los espacios que el programa no pide.
    No modifica nada."""
    _, project = _use(project_path)
    with _database() as connection:
        rows = area_program(connection)
    if not rows:
        raise DocsError(
            "La base no tiene programa de áreas: el usuario lo carga con "
            f"{IMPORT_COMMAND} area_program <archivo.csv> (plantilla en "
            "packages/docs/plantillas/area_program.csv)."
        )
    return summaries.program(check_program(project, rows))


@_tool(READS)
def calcular_cos_cus(
    project_path: ProjectPath,
    area_lote: Annotated[
        float,
        Field(description="Área del lote en m², la que da el usuario; nunca la supongas.", gt=0),
    ],
) -> str:
    """Calcula el COS (huella construida del nivel más bajo / área del lote) y el CUS (área
    construida de todos los niveles / área del lote), con las áreas del modelo. Pide el área
    del lote al usuario si no la dio. No modifica nada."""
    _, project = _use(project_path)
    return summaries.coefficients(coefficients(project, area_lote))


@_tool(WRITES_OUTPUT)
def generar_ficha_pdf(
    project_path: ProjectPath,
    memoria_texto: Annotated[
        str,
        Field(
            description="La memoria descriptiva redactada con las cifras de datos_para_memoria; "
            "los párrafos se separan con una línea en blanco.",
            min_length=1,
        ),
    ],
) -> str:
    """Genera salidas/ficha_<proyecto>.pdf: datos del proyecto, cuadro de áreas, planta y la
    memoria descriptiva. Antes comprueba que cada número de memoria_texto esté en
    datos_para_memoria (redondeado a los decimales escritos): si alguno no está, no genera
    nada y lista cada número con su contexto para corregirlo. La regla es estricta: años,
    fechas, escalas o cualquier cifra que no esté en esos datos se rechazan, así que no los
    escribas con dígitos. Úsala después de datos_para_memoria."""
    folder, project = _use(project_path)
    with _database() as connection:
        data = project_memory(project, connection)
    rejected = unverified_numbers(memoria_texto, data)
    if rejected:
        raise DocsError(summaries.unverified(rejected))
    path = build_sheet(
        project, data, memoria_texto, outputs_dir(folder) / f"ficha_{folder.name}.pdf"
    )
    numbers = len(NUMBER.findall(memoria_texto))
    return summaries.sheet(path, numbers, not project.scale_confirmed)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
