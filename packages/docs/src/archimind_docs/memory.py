"""Las cifras verificadas del proyecto para redactar la memoria: todas salen del modelo (con
funciones de core) o de la base, ya redondeadas como se escriben.

Una altura de nivel sin confirmar no es una medida: sale como null.
"""

import sqlite3
from collections import Counter
from typing import Any

from archimind_core.quantities import PRELIMINARY_LABEL, area_table, opening_counts, wall_quantities
from archimind_schema import Project

from archimind_docs.database import budget_items
from archimind_docs.database import materials as stored_materials
from archimind_docs.items import (
    FLOOR_NAMES,
    AssignedMaterial,
    ModelItem,
    assigned_materials,
    model_items,
)

OPENING_NAMES = {"door": "puertas", "window": "ventanas", "void": "vanos libres"}


def memory_data(
    project: Project, items: list[ModelItem], materials: list[AssignedMaterial]
) -> dict[str, Any]:
    table = area_table(project)
    categories = Counter(FLOOR_NAMES[s.category] for s in project.spaces)
    kinds = Counter(OPENING_NAMES[o.kind] for o in project.openings)
    return {
        "proyecto": {
            "nombre": project.name,
            "escala_confirmada": project.scale_confirmed,
            "aviso": None if project.scale_confirmed else PRELIMINARY_LABEL,
        },
        "niveles": [
            {
                "nombre": level.name,
                "cota_m": round(level.elevation, 2),
                "altura_m": round(level.default_height, 2) if level.height_confirmed else None,
            }
            for level in sorted(project.levels, key=lambda lv: lv.elevation)
        ],
        "conteos": {
            "niveles": len(project.levels),
            "muros": len(project.walls),
            "vanos": len(project.openings),
            "vanos_por_tipo": dict(sorted(kinds.items())),
            "espacios": len(project.spaces),
            "espacios_por_categoria": dict(sorted(categories.items())),
        },
        "areas_m2": {
            "espacios": [
                {"nombre": s.name, "categoria": FLOOR_NAMES[s.category], "area": round(s.area, 2)}
                for s in table.spaces
            ],
            "util": round(table.useful_area, 2),
            "construida": round(table.built_area, 2),
            "balcones": round(table.balcony_area, 2),
        },
        "muros_por_espesor": [
            {"espesor_m": round(thickness, 3), "longitud_m": round(length, 2)}
            for thickness, length in wall_quantities(project).length_by_thickness.items()
        ],
        "vanos_por_medida": [
            {
                "tipo": OPENING_NAMES[c.kind],
                "ancho_m": c.width,
                "alto_m": c.height,
                "cantidad": c.count,
            }
            for c in opening_counts(project).counts
        ],
        "partidas": [
            {
                "partida": item.key,
                "descripcion": item.description,
                "unidad": item.unit,
                "cantidad": None if item.quantity is None else round(item.quantity, 2),
                "falta": item.missing,
            }
            for item in items
        ],
        "materiales": [
            {
                "origen": m.source,
                "codigo": m.code,
                "descripcion": m.description,
                "norma": m.standard,
                "nota": m.note,
            }
            for m in materials
        ],
    }


def project_memory(project: Project, connection: sqlite3.Connection) -> dict[str, Any]:
    """Las cifras del proyecto con los materiales que le asigna la base."""
    items = model_items(project)
    assigned = assigned_materials(
        project, items, budget_items(connection), stored_materials(connection)
    )
    return memory_data(project, items, assigned)
