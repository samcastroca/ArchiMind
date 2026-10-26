"""insert_blocks: la carpintería insertada en el plano que exporta core, y el borrador para que
core la guarde en el modelo.

Parte de `salidas/<proyecto>.dxf` (exportar_plano de core, en metros y en las coordenadas del
modelo). Por cada vano con carpintería —la nueva y la que el modelo ya tenía— quita el
rectángulo del vano y pone el INSERT del bloque de planta, rotado según el muro y con su
«adentro» hacia el lado elegido. Escribe `salidas/<proyecto>-carpinteria.dxf` y, si hay
carpintería nueva, `salidas/borrador_bloques.json`. Nunca escribe `modelo.json`.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import ezdxf
from archimind_schema import (
    LENGTH_TOL,
    BlockAssignment,
    BlockDefinition,
    BlocksDraft,
    Opening,
    Project,
    Wall,
    load_project,
    opening_polygon,
)
from ezdxf.document import Drawing
from ezdxf.entities import LWPolyline
from pydantic import TypeAdapter, ValidationError
from shapely import Polygon

from archimind_bloques.catalog import Catalog
from archimind_bloques.export_dxf import INSERT_LAYERS, LAYER_COLORS, add_plan_block
from archimind_bloques.fit import Fit, Preferences, fit_to_opening
from archimind_bloques.generate import generate
from archimind_bloques.geometry import Carpentry
from archimind_bloques.params import CarpentryParams
from archimind_bloques.resolve import FitError
from archimind_bloques.site import Site, insertion, span

OUTPUTS_DIR = "salidas"
DRAFT_NAME = "borrador_bloques.json"
PLAN_SUFFIX = "-carpinteria"
OPENING_LAYERS = ("A-PUERTA", "A-VENTANA", "A-VANO")  # donde core dibuja el rectángulo del vano

_PARAMS: TypeAdapter[CarpentryParams] = TypeAdapter(CarpentryParams)


class InsertError(Exception):
    """La carpintería no se puede insertar; el mensaje está pensado para el usuario final."""


@dataclass(frozen=True)
class Placement:
    opening: Opening
    wall: Wall
    carpentry: Carpentry
    site: Site


@dataclass(frozen=True)
class InsertResult:
    plan: Path
    draft: Path | None  # None si no hubo carpintería nueva
    fits: list[tuple[Fit, Carpentry]]  # la carpintería nueva, por vano
    kept: list[str]  # vanos con bloque del modelo que se volvieron a insertar
    warnings: list[str]


def insert_blocks(
    project_path: str | Path,
    assignments: Mapping[str, Preferences] | None,
    catalog: Catalog,
) -> InsertResult:
    """`assignments` va por ID de vano. Sin asignaciones, todos los vanos de puerta y ventana que
    aún no tienen bloque, con las preferencias por defecto. Si algún vano no calza, no escribe
    nada y dice qué pasa con cada uno."""
    folder = Path(project_path).expanduser().resolve()
    project = _load(folder)
    if not project.scale_confirmed:
        raise InsertError(
            "PRELIMINAR: la escala no está confirmada, así que las medidas de los vanos tampoco. "
            "Confírmala con confirmar_escala de archimind-core antes de insertar carpintería."
        )
    targets = dict(assignments) if assignments else _unassigned(project)
    fits = _fit_all(project, targets, catalog)
    walls = {wall.id: wall for wall in project.walls}
    openings = {opening.id: opening for opening in project.openings}
    placements = []
    for fit, carpentry in fits:
        opening = openings[fit.opening_id]
        placements.append(Placement(opening, walls[opening.wall_id], carpentry, fit.site))
    kept, warnings = _kept(project, set(targets), walls)
    if not placements and not kept:
        raise InsertError(
            "No hay carpintería que insertar: el modelo no tiene vanos de puerta ni de ventana."
        )
    base = folder / OUTPUTS_DIR / f"{folder.name}.dxf"
    if not base.is_file():
        raise InsertError(
            f"Falta el plano exportado {OUTPUTS_DIR}/{base.name}: expórtalo con exportar_plano "
            'de archimind-core (formato "dxf") y vuelve a insertar.'
        )
    doc = ezdxf.readfile(base)
    _place(doc, [*placements, *kept])
    plan = base.with_name(f"{folder.name}{PLAN_SUFFIX}.dxf")
    doc.saveas(plan)

    draft_path = folder / OUTPUTS_DIR / DRAFT_NAME
    draft_path.unlink(missing_ok=True)  # un borrador viejo no debe aplicarse por error
    if fits:
        draft_path.write_text(_draft(fits).model_dump_json(indent=2), encoding="utf-8")
    return InsertResult(
        plan=plan,
        draft=draft_path if fits else None,
        fits=fits,
        kept=[p.opening.id for p in kept],
        warnings=warnings,
    )


def _load(folder: Path) -> Project:
    try:
        return load_project(folder)
    except FileNotFoundError:
        raise InsertError(
            f"No hay un proyecto en {folder}: ábrelo con abrir_proyecto de archimind-core."
        ) from None
    except ValidationError as exc:
        raise InsertError(f"El modelo de {folder} no es válido: {exc}") from exc


def _unassigned(project: Project) -> dict[str, Preferences]:
    return {
        o.id: Preferences()
        for o in project.openings
        if o.kind in ("door", "window") and o.block_id is None
    }


def _fit_all(
    project: Project, targets: Mapping[str, Preferences], catalog: Catalog
) -> list[tuple[Fit, Carpentry]]:
    fits, errors = [], []
    for opening_id, preferences in targets.items():
        try:
            fit = fit_to_opening(project, opening_id, preferences, catalog)
        except FitError as exc:
            errors.append(f"{opening_id}: {exc}")
            continue
        fits.append((fit, generate(fit.params)))
    if errors:
        raise InsertError("No se insertó nada. Estos vanos no calzan:\n" + "\n".join(errors))
    return fits


def _kept(
    project: Project, replaced: set[str], walls: dict[str, Wall]
) -> tuple[list[Placement], list[str]]:
    """La carpintería que el modelo ya tiene en los vanos que no se reemplazan."""
    blocks = {block.id: block for block in project.blocks}
    kept, warnings = [], []
    for opening in project.openings:
        block = blocks.get(opening.block_id) if opening.block_id else None
        if opening.id in replaced or block is None or opening.block_side is None:
            continue
        if (
            abs(opening.width - block.width) > LENGTH_TOL
            or abs(opening.height - block.height) > LENGTH_TOL
        ):
            warnings.append(
                f"{opening.id}: su bloque {block.id} ya no mide lo que el vano y no se insertó; "
                "vuelve a ajustarlo incluyéndolo en las asignaciones"
            )
            continue
        wall = walls[opening.wall_id]
        start, end = span(wall, opening)
        site = Site(start, end, opening.block_side, None, "")
        carpentry = generate(_PARAMS.validate_python(block.parameters))
        kept.append(Placement(opening, wall, carpentry, site))
    return kept, warnings


def _place(doc: Drawing, placements: list[Placement]) -> None:
    """Quita el rectángulo de cada vano e inserta su bloque. Comprueba todos los vanos antes de
    tocar el documento."""
    msp = doc.modelspace()
    outlines = [
        e
        for e in msp.query("LWPOLYLINE")
        if isinstance(e, LWPolyline) and e.dxf.layer in OPENING_LAYERS
    ]
    found, missing = [], []
    for placement in placements:
        footprint = opening_polygon(placement.wall, placement.opening)
        match = next((e for e in outlines if _same_outline(e, footprint)), None)
        if match is None:
            missing.append(placement.opening.id)
        else:
            found.append(match)
    if missing:
        raise InsertError(
            f"El plano exportado no coincide con el modelo actual: no tiene {', '.join(missing)}. "
            'Vuelve a exportarlo con exportar_plano de archimind-core (formato "dxf").'
        )
    for outline in found:
        msp.delete_entity(outline)
    for placement in placements:
        layer = INSERT_LAYERS[placement.carpentry.kind]
        if layer not in doc.layers:
            doc.layers.add(layer, color=LAYER_COLORS[layer])
        point, rotation = insertion(placement.site)
        msp.add_blockref(
            add_plan_block(doc, placement.carpentry),
            point,
            dxfattribs={"layer": layer, "rotation": rotation},
        )


def _same_outline(outline: LWPolyline, footprint: Polygon) -> bool:
    points = [(float(x), float(y)) for x, y in outline.vertices()]
    if len(points) < 3:
        return False
    return bool(Polygon(points).hausdorff_distance(footprint) <= LENGTH_TOL)


def _draft(fits: list[tuple[Fit, Carpentry]]) -> BlocksDraft:
    return BlocksDraft(
        assignments=[
            BlockAssignment(
                opening_id=fit.opening_id,
                side=fit.site.side,
                block=BlockDefinition(
                    name=carpentry.name,
                    kind=carpentry.kind,
                    width=fit.params.width,
                    height=fit.params.height,
                    parameters=fit.params.model_dump(mode="json"),
                ),
            )
            for fit, carpentry in fits
        ]
    )
