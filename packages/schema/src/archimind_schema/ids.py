"""Generación de IDs inéditos: el contador por prefijo solo avanza y se guarda con el modelo."""

from archimind_schema.models import ID_PREFIXES, Project


def new_id(project: Project, prefix: str) -> str:
    if prefix not in ID_PREFIXES:
        raise ValueError(f"prefijo desconocido '{prefix}'; los válidos son {list(ID_PREFIXES)}")
    number = project.next_ids[prefix]
    project.next_ids[prefix] = number + 1
    return f"{prefix}-{number:04d}"
