"""Borradores que los demás servidores entregan a core, el único que escribe el modelo.

Viajan como archivos JSON en la carpeta del proyecto: así ninguna medida pasa por el LLM que
orquesta los servidores.
"""

from pydantic import BaseModel, ConfigDict, Field

from archimind_schema.models import AxisSide, BlockDefinition


class BlockAssignment(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    opening_id: str
    side: AxisSide
    block: BlockDefinition


class BlocksDraft(BaseModel):
    """La carpintería que archimind-bloques propone para unos vanos; core pone los IDs `blq-`."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    assignments: list[BlockAssignment] = Field(min_length=1)
