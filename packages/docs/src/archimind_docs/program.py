"""El programa de áreas frente a los espacios del modelo.

Cada fila de `area_program` exige un espacio distinto. Se emparejan por nombre sin mayúsculas,
sin tildes y sin el número final («Habitación» con «Habitación 1»). Las filas de mayor área
mínima eligen primero y cada una toma, de los espacios que coinciden y aún no se usaron, el de
mayor área: así dos filas «Habitación» de 9 y 7 m² se reparten las habitaciones lo mejor
posible.
"""

import re
import unicodedata
from dataclasses import dataclass

from archimind_schema import Project, space_area

from archimind_docs.database import ProgramRow

# Un área que difiere del mínimo menos que esto, lo cumple (redondeo del cálculo).
AREA_TOL = 1e-6


@dataclass(frozen=True)
class ProgramMatch:
    row: ProgramRow
    space: str | None  # None: no hay espacio para esta fila
    area: float | None

    @property
    def met(self) -> bool:
        return self.area is not None and self.area >= self.row.area_minima - AREA_TOL


@dataclass(frozen=True)
class ProgramCheck:
    matches: list[ProgramMatch]  # en el orden del programa
    extra: list[tuple[str, float]]  # espacios que el programa no pide
    preliminary: bool


def normalize(name: str) -> str:
    decomposed = unicodedata.normalize("NFKD", name.casefold())
    plain = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"\s*\d+$", "", plain.strip())).strip()


def check_program(project: Project, rows: list[ProgramRow]) -> ProgramCheck:
    spaces = [(s.name, space_area(s)) for s in project.spaces]
    used: set[int] = set()
    found: dict[int, ProgramMatch] = {}
    for index in sorted(range(len(rows)), key=lambda i: -rows[i].area_minima):
        row = rows[index]
        candidates = [
            i
            for i, (name, _) in enumerate(spaces)
            if i not in used and normalize(name) == normalize(row.espacio)
        ]
        if not candidates:
            found[index] = ProgramMatch(row, None, None)
            continue
        best = max(candidates, key=lambda i: spaces[i][1])
        used.add(best)
        found[index] = ProgramMatch(row, *spaces[best])
    extra = [space for i, space in enumerate(spaces) if i not in used]
    return ProgramCheck([found[i] for i in range(len(rows))], extra, not project.scale_confirmed)
