"""Mapeo de capas a roles: conversión desde la propuesta y validación de los roles."""

from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING, get_args

from archimind_schema import LayerRole

if TYPE_CHECKING:
    from archimind_core.layer_roles import LayerProposal

ROLES: tuple[str, ...] = get_args(LayerRole)


class MappingError(Exception):
    """El mapeo no se puede aplicar; el mensaje está pensado para el usuario final."""


def proposals_to_mapping(proposals: Iterable["LayerProposal"]) -> dict[str, LayerRole]:
    return {proposal.layer: proposal.role for proposal in proposals}


def validate_roles(mapping: Mapping[str, str]) -> None:
    """Lanza MappingError si algún rol del mapeo no es uno de los posibles."""
    invalid = sorted(f"{layer} → {role}" for layer, role in mapping.items() if role not in ROLES)
    if invalid:
        raise MappingError(
            f"Roles no válidos: {', '.join(invalid)}. Los roles posibles son {', '.join(ROLES)}"
        )
