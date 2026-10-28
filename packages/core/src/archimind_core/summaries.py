"""Textos de respuesta del servidor MCP: resúmenes cortos (menos de 50 líneas) y rutas.

Funciones puras sobre los resultados de la lógica del paquete. Todo número sale del modelo; aquí
solo se da formato.
"""

import json
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from archimind_schema import CutLine, EditsDraft, Problem, Project, validate

from archimind_core.blocks import BlocksAssignment
from archimind_core.build import BuildResult
from archimind_core.build_3d import LAYERS, Build3dResult
from archimind_core.compare import VersionDiff, compare_versions
from archimind_core.edits import EditsResult
from archimind_core.heights import HeightsResult, MissingHeight, missing_heights
from archimind_core.history import Version, recent_versions
from archimind_core.inventory import LayerSummary
from archimind_core.layer_roles import ROLE_NAMES, LayerProposal
from archimind_core.project import load_existing, project_folder
from archimind_core.quantities import AreaTable, area_table, opening_counts
from archimind_core.scale import ScaleConfirmation
from archimind_core.units import DrawingUnits
from archimind_core.views import View, describe

MAX_LINES = 50
CATEGORIES = {
    "useful": "útil",
    "balcony": "balcón",
    "circulation": "circulación",
    "service": "servicio",
    "technical": "técnico",
}
OPENING_KINDS = {"door": "puerta", "window": "ventana", "void": "vano libre"}
OPENING_KINDS_PLURAL = {"door": "puertas", "window": "ventanas", "void": "vanos libres"}
UNIT_NAMES = {"Meters": "metros", "Centimeters": "centímetros", "Millimeters": "milímetros"}
SEVERITIES = {"error": "error", "warning": "aviso"}


def count(n: int, singular: str, plural: str | None = None) -> str:
    """«1 muro», «0 muros», «2 errores»."""
    return f"{n} {singular if n == 1 else plural or singular + 's'}"


def truncate(lines: Sequence[str], limit: int) -> list[str]:
    """Las primeras `limit` líneas; si sobran, la última dice cuántas se omiten."""
    if len(lines) <= limit:
        return list(lines)
    return [*lines[: limit - 1], f"  … y {len(lines) - limit + 1} más"]


def project_summary(project_path: str | Path) -> str:
    folder = project_folder(project_path)
    project = load_existing(folder)
    plan = project.source_files[-1] if project.source_files else "ninguno (usa importar_plano)"
    lines = [
        f"Proyecto «{project.name}» en {folder}",
        f"Plano activo: {plan}",
        _scale_line(project),
        _counts_line(project),
    ]
    if project.spaces:
        table = area_table(project)
        lines.append(
            f"Área útil {table.useful_area:.2f} m² · construida {table.built_area:.2f} m²"
            + _label(table.label)
        )
    problems = validate(project)
    lines.append(f"Validación: {_problem_counts(problems)}")
    lines += _versions_block(recent_versions(folder))
    return _text(lines)


def opened(project_path: str | Path, created: bool, version: str | None) -> str:
    head = "Proyecto creado." if created else "Proyecto abierto."
    return _text([head, project_summary(project_path), *_version_line(version)])


def imported(
    plan: str, units: DrawingUnits, inventory: Sequence[LayerSummary], version: str | None
) -> str:
    lines = [f"Plano importado: {plan} (copiado en la carpeta del proyecto; es el plano activo)."]
    lines.append(units_line(units))
    lines.append(f"{count(len(inventory), 'capa')}:")
    lines += truncate([f"  {_layer_line(layer)}" for layer in inventory], 35)
    lines.append("Siguiente paso: proponer_mapeo_capas.")
    return _text([*lines, *_version_line(version)])


def proposals(plan: str, items: Sequence[LayerProposal]) -> str:
    layers = count(len(items), "capa")
    lines = [f"Mapeo propuesto para {plan} ({layers}): capa → rol (confianza) evidencia"]
    lines += truncate(
        [
            f"  {p.layer} → {p.role} ({ROLE_NAMES[p.role]}, {p.confidence:.2f}): {p.evidence}"
            for p in items
        ],
        40,
    )
    mapping = json.dumps({p.layer: p.role for p in items}, ensure_ascii=False)
    lines.append(f"Para aplicarlo, tal cual o corregido, usa aplicar_mapeo con mapping = {mapping}")
    return _text(lines)


def applied(plan: str, result: BuildResult, version: str | None) -> str:
    project = result.project
    lines = [f"Modelo reconstruido desde {plan}.", _counts_line(project), _scale_line(project)]
    lines.append(f"Problemas: {_problem_counts(result.problems)}.")
    ordered = sorted(result.problems, key=lambda p: p.severity != "error")
    lines += truncate([f"  {_problem_line(p)}" for p in ordered], 35)
    lines.append("Para revisarlo: exportar_plano (png), listar_modelo.")
    return _text([*lines, *_version_line(version)])


def view_choice(plan: str, views: Sequence[View]) -> str:
    """Aviso de aplicar_mapeo cuando el plano tiene varias vistas: no se aplicó nada."""
    lines = [
        f"Aviso: no se aplicó el mapeo. Los muros de {plan} forman {len(views)} vistas separadas "
        "(por ejemplo, una planta y un alzado lado a lado) y mezclarlas daría muros y espacios "
        "falsos:",
        *truncate([f"  Vista {v.number}: {describe(v)}" for v in views], 20),
        "Pregunta al usuario cuál es la planta y repite aplicar_mapeo con vista = su número. "
        "El modelo no ha cambiado.",
    ]
    return _text(lines)


def scale(confirmation: ScaleConfirmation, wall_id: str | None, units: DrawingUnits | None) -> str:
    if not confirmation.changed:
        return "La escala ya estaba confirmada: no hay cambios."
    if wall_id is None:
        name = UNIT_NAMES.get(units.name, units.name) if units is not None else "las del plano"
        return f"Escala confirmada: el plano está en {name}. Las cantidades ya no son preliminares."
    measured = confirmation.measured_length or 0.0
    real = measured * confirmation.factor
    return _text(
        [
            f"Escala recalculada: el eje de {wall_id} medía {measured:.3f} m y ahora mide "
            f"{real:.3f} m (factor {confirmation.factor:.6g}).",
            "Se escalaron muros, vanos, espacios y anotaciones; las alturas y los antepechos no.",
            "La escala queda confirmada: las cantidades ya no son preliminares.",
        ]
    )


def scale_commit_message(confirmation: ScaleConfirmation, wall_id: str | None) -> str:
    if wall_id is None:
        return "Confirma la escala con las unidades del plano"
    real = (confirmation.measured_length or 0.0) * confirmation.factor
    return f"Recalcula la escala: {wall_id} mide {real:.3f} m (factor {confirmation.factor:.6g})"


def problems(project: Project, items: Sequence[Problem]) -> str:
    if not items:
        return f"El modelo de «{project.name}» es válido: sin errores ni avisos."
    lines = [f"Validación de «{project.name}»: {_problem_counts(items)}."]
    ordered = sorted(items, key=lambda p: p.severity != "error")
    lines += truncate([f"  {_problem_line(p)}" for p in ordered], 45)
    return _text(lines)


def spaces(project: Project) -> str:
    if not project.spaces:
        return "El modelo no tiene espacios todavía: aplica el mapeo con aplicar_mapeo."
    table = area_table(project)
    header = f"{count(len(table.spaces), 'espacio')}{_label(table.label)}"
    lines = [f"{header}: id · nombre · categoría · área"]
    lines += truncate(
        [
            f"  {s.id} · {s.name} · {CATEGORIES.get(s.category, s.category)} · {s.area:.2f} m²"
            for s in table.spaces
        ],
        45,
    )
    return _text(lines)


def openings(project: Project) -> str:
    if not project.openings:
        return "El modelo no tiene vanos."
    counts = opening_counts(project)
    kinds = Counter(o.kind for o in project.openings)
    by_kind = ", ".join(
        count(n, OPENING_KINDS[k], OPENING_KINDS_PLURAL[k]) for k, n in sorted(kinds.items())
    )
    lines = [
        f"{count(len(project.openings), 'vano')} ({by_kind}){_label(counts.label)}.",
        "Por medida:",
    ]
    lines += truncate(
        [
            f"  {OPENING_KINDS[c.kind]} {c.width:.2f} × {c.height:.2f} m: {c.count}"
            for c in counts.counts
        ],
        12,
    )
    lines.append(
        "Lista: id · tipo ancho × alto · antepecho · muro y distancia desde su inicio · bloque"
    )
    lines += truncate(
        [
            f"  {o.id} · {OPENING_KINDS[o.kind]} {o.width:.2f} × {o.height:.2f} m · "
            f"antepecho {o.sill_height:.2f} m · {o.wall_id} a {o.offset:.2f} m"
            + (f" · {o.block_id}" if o.block_id else "")
            for o in project.openings
        ],
        MAX_LINES - len(lines) - 1,
    )
    return _text(lines)


def blocks_assigned(result: BlocksAssignment, version: str | None) -> str:
    new = sum(item.new for item in result.assigned)
    lines = [
        f"Carpintería asignada a {count(len(result.assigned), 'vano')}: "
        f"{count(new, 'bloque nuevo', 'bloques nuevos')}, "
        f"{count(len(result.assigned) - new, 'reutilizado', 'reutilizados')}.",
        "Vano → bloque (nombre):",
    ]
    lines += truncate(
        [
            f"  {item.opening_id} → {item.block_id}{' (nuevo)' if item.new else ''} "
            f"{item.block_name}"
            for item in result.assigned
        ],
        40,
    )
    if result.removed:
        lines.append(f"Bloques que quedaron sin uso, quitados: {_ids(result.removed)}.")
    problems = [p for p in validate(result.project) if p.code.startswith("bloque_")]
    lines += [f"  {_problem_line(p)}" for p in problems[:3]]
    return _text([*lines, *_version_line(version)])


def edits_count(draft: EditsDraft) -> int:
    edited = len(draft.walls) + len(draft.openings) + len(draft.spaces) + len(draft.deleted)
    return edited + len(draft.new_walls) + len(draft.new_openings) + len(draft.new_spaces)


def edits_commit_message(draft: EditsDraft) -> str:
    return f"Aplica {count(edits_count(draft), 'cambio', 'cambios')} de Rhino"


def edits_applied(
    before: Project, draft: EditsDraft, result: EditsResult, version: str | None
) -> str:
    diff = compare_versions(before, result.project)
    lines = [f"Borrador de Rhino aplicado: {count(edits_count(draft), 'cambio', 'cambios')}."]
    groups = [
        ("Muros editados", [edit.id for edit in draft.walls]),
        ("Vanos editados", [edit.id for edit in draft.openings]),
        ("Borrados", draft.deleted),
    ]
    lines += [f"{label}: {_ids(ids)}." for label, ids in groups if ids]
    new = [f"{ref} → {entity_id}" for ref, entity_id in result.new_ids.items()]
    if new:
        lines.append(f"Nuevos: {_ids(new)}.")
    lines += [f"Renombrado: {i} «{old}» → «{name}»." for i, old, name in result.renamed[:5]]
    if diff.spaces_changed:
        lines.append(f"Espacios con otra área{_label(diff.label)}:")
        lines += truncate(
            [
                f"  {c.id} {c.name}: {c.area_before:.2f} → {c.area_after:.2f} m²"
                for c in diff.spaces_changed
            ],
            15,
        )
    if result.removed_blocks:
        lines.append(f"Bloques que quedaron sin uso, quitados: {_ids(result.removed_blocks)}.")
    known = {(p.code, tuple(p.ids)) for p in validate(before)}
    fresh = [p for p in result.problems if (p.code, tuple(p.ids)) not in known]
    if fresh:
        lines.append(f"Avisos nuevos ({count(len(fresh), 'aviso')}):")
        lines += truncate([f"  {_problem_line(p)}" for p in fresh], 10)
    lines += _version_line(version)
    lines.append("El cuadro de áreas actualizado sale con cuadro_de_areas.")
    return _text(lines)


def heights_defined(result: HeightsResult, version: str | None) -> str:
    lines = []
    if result.levels:
        lines.append("Alturas confirmadas por nivel:")
        lines += [f"  {level_id}: {h:.2f} m" for level_id, h in result.levels.items()]
    if result.kept_walls:
        lines.append(
            f"Conservan su altura propia: {_ids(result.kept_walls)} (se cambia por_espacio o "
            "editándolos en Rhino)."
        )
    if result.walls:
        lines.append(f"{count(len(result.walls), 'muro')} con altura por espacio:")
        lines += truncate([f"  {w}: {h:.2f} m" for w, h in sorted(result.walls.items())], 20)
    if result.warnings:
        lines.append("Avisos:")
        lines += truncate([f"  {w}" for w in result.warnings], 8)
    pending = missing_heights(result.project)
    if pending:
        lines += _missing_lines(pending)
    return _text([*lines, *_version_line(version)])


def heights_commit_message(result: HeightsResult) -> str:
    parts = [f"{level_id} {h:.2f} m" for level_id, h in result.levels.items()]
    if result.walls:
        parts.append(f"{count(len(result.walls), 'muro')} por espacio")
    return f"Define alturas: {', '.join(parts)}"


def built_3d(result: Build3dResult, from_rules: bool) -> str:
    source = ", el de build_rules.yaml" if from_rules else ""
    layers = ", ".join(f"{LAYERS[kind][0]} {result.counts.get(kind, 0)}" for kind in LAYERS)
    return _text(
        [
            f"Modelo 3D guardado en {result.path} (metros, sólidos cerrados).",
            f"Objetos por capa: {layers}.",
            f"Losa de piso de {result.slab_thickness:.2f} m{source}, bajo la cota de cada nivel.",
            "Cada objeto lleva su ID en el user string archimind_id: el muro en los machones, el "
            "vano en dinteles y antepechos, el nivel en las losas.",
        ]
    )


def cuts(project: Project, items: Sequence[CutLine], path: Path) -> str:
    if not items:
        return _text(
            [
                f"No hay cortes para proponer en «{project.name}»: toda posición central corre a "
                "lo largo de un muro.",
                "Pide al usuario los dos puntos de la línea de corte para corte de rhino-bridge.",
            ]
        )
    lines = [f"Cortes propuestos para «{project.name}»:"]
    lines += [f"  {c.name} (corte {c.label}): {c.description}" for c in items]
    lines.append(f"Guardados en {path}.")
    if not project.scale_confirmed:
        lines.append("PRELIMINAR: la escala no está confirmada.")
    lines.append(
        "Pregunta al usuario cuál quiere y llama a corte de rhino-bridge con ese nombre en "
        "linea_de_corte."
    )
    return _text(lines)


def heights_missing(items: Sequence[MissingHeight]) -> str:
    lines = ["No se construyó el 3D: faltan alturas y no se suponen."]
    lines += _missing_lines(items)
    lines.append(
        "Pregunta las alturas al usuario y aplícalas con definir_alturas, p. ej. por_nivel="
        f'{{"{items[0].level_id}": 2.60}} o por_espacio={{"esp-0001": 2.40}}.'
    )
    return _text(lines)


def _missing_lines(items: Sequence[MissingHeight]) -> list[str]:
    lines = ["Sin altura confirmada (muros sin altura propia en niveles sin confirmar):"]
    lines += truncate(
        [
            f"  {m.level_id} «{m.level_name}» (por defecto {m.default_height:.2f} m, sin "
            f"confirmar): {count(len(m.wall_ids), 'muro')}: {_ids(m.wall_ids, 8)}"
            for m in items
        ],
        10,
    )
    return lines


def areas(project: Project, table: AreaTable, csv_path: Path | None) -> str:
    lines = [f"Cuadro de áreas de «{project.name}»{_label(table.label)}"]
    lines += truncate(
        [
            f"  {s.name} ({CATEGORIES.get(s.category, s.category)}): {s.area:.2f} m²"
            for s in table.spaces
        ],
        42,
    )
    lines.append(
        f"Área útil: {table.useful_area:.2f} m² · Área construida: {table.built_area:.2f} m² · "
        f"Balcones: {table.balcony_area:.2f} m²"
    )
    if csv_path is not None:
        lines.append(f"CSV: {csv_path}")
    else:
        lines.append("CSV no exportado: confirma la escala con confirmar_escala para exportarlo.")
    return _text(lines)


def diff(version_a: str, version_b: str, result: VersionDiff) -> str:
    lines = [f"Cambios de {version_a} a {version_b}{_label(result.label)}:"]
    if result.spaces_changed:
        lines.append("Espacios con área distinta (más de 0.5 %):")
        lines += truncate(
            [
                f"  {c.id} {c.name}: {c.area_before:.2f} → {c.area_after:.2f} m² "
                f"({c.relative_change:+.1%})"
                for c in result.spaces_changed
            ],
            15,
        )
    for title, ids in (
        ("Muros añadidos", result.walls_added),
        ("Muros eliminados", result.walls_removed),
        ("Muros movidos o con otro espesor", result.walls_moved),
        ("Vanos modificados", result.openings_modified),
    ):
        if ids:
            lines.append(f"{title} ({len(ids)}): {_ids(ids)}")
    if len(lines) == 1:
        lines.append("Sin cambios en espacios, muros ni vanos.")
    return _text(lines)


def units_line(units: DrawingUnits) -> str:
    name = UNIT_NAMES.get(units.name, units.name)
    if units.confirmed:
        return f"Unidades: {name}, declaradas en el plano ({units.evidence}); escala confirmada."
    return (
        f"Unidades: {name}, inferidas ({units.evidence}). La escala queda sin confirmar y las "
        "cantidades serán PRELIMINARES hasta usar confirmar_escala."
    )


def _scale_line(project: Project) -> str:
    if project.scale_confirmed:
        return "Escala: confirmada."
    return (
        "Escala: sin confirmar, las cantidades son PRELIMINARES; se confirma con confirmar_escala."
    )


def _counts_line(project: Project) -> str:
    return (
        f"Modelo: {count(len(project.levels), 'nivel', 'niveles')}, "
        f"{count(len(project.walls), 'muro')}, {count(len(project.openings), 'vano')}, "
        f"{count(len(project.spaces), 'espacio')}."
    )


def _layer_line(layer: LayerSummary) -> str:
    entities = ", ".join(f"{n} {kind}" for kind, n in layer.entity_counts.items())
    parts = [f"{layer.layer}: {entities}"]
    if layer.line_length_m > 0:
        parts.append(f"{layer.line_length_m:.1f} m de línea")
    if layer.blocks:
        parts.append("bloques " + ", ".join(f"{name} ×{n}" for name, n in layer.blocks.items()))
    if layer.sample_texts:
        parts.append("textos: " + ", ".join(layer.sample_texts[:3]))
    return "; ".join(parts)


def _problem_line(problem: Problem) -> str:
    ids = f" [{', '.join(problem.ids)}]" if problem.ids else ""
    return f"{SEVERITIES[problem.severity]} {problem.code}{ids}: {problem.message}"


def _problem_counts(items: Sequence[Problem]) -> str:
    errors = sum(p.severity == "error" for p in items)
    return f"{count(errors, 'error', 'errores')}, {count(len(items) - errors, 'aviso')}"


def _versions_block(versions: Sequence[Version]) -> list[str]:
    if not versions:
        return ["Versiones: ninguna todavía."]
    return ["Versiones recientes:", *(f"  {v.hash} {v.date} {v.message}" for v in versions)]


def _version_line(version: str | None) -> list[str]:
    return [f"Versión {version}." if version else "Sin cambios que versionar."]


def _label(label: str | None) -> str:
    return f" ({label})" if label else ""


def _ids(ids: Sequence[str], limit: int = 15) -> str:
    shown = ", ".join(ids[:limit])
    return shown if len(ids) <= limit else f"{shown} … y {len(ids) - limit} más"


def _text(lines: Sequence[str]) -> str:
    return "\n".join(lines)
