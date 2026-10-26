"""Propuesta del rol de cada capa, por su nombre y por lo que dibuja.

La geometría se analiza en metros. Cada detector explica una parte del contenido de la capa
(peso = longitud para tramos y arcos, 1 para el resto) y el rol sale de qué fracción explica
cada uno; si dos roles explican una parte importante, la capa es `mixed`.
"""

import math
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from itertools import combinations
from typing import TYPE_CHECKING

from archimind_schema import WALL_THICKNESSES, LayerRole
from ezdxf.entities import Arc, Dimension, DXFGraphic, Insert, Line, MText, Text

from archimind_core.inventory import linear_pieces, piece_length
from archimind_core.layer_rules import LayerRules, load_rules

if TYPE_CHECKING:
    from archimind_core.drawing import Drawing

Point = tuple[float, float]

ROLE_NAMES: dict[LayerRole, str] = {
    "walls": "muros",
    "doors": "puertas",
    "windows": "ventanas",
    "text": "textos",
    "dimensions": "cotas",
    "axes": "ejes",
    "furniture": "mobiliario",
    "ignore": "una capa a ignorar",
    "mixed": "varios roles",
}


@dataclass(frozen=True)
class LayerProposal:
    layer: str
    role: LayerRole
    confidence: float
    evidence: str


@dataclass(frozen=True)
class Segment:
    start: Point
    end: Point

    @property
    def length(self) -> float:
        return math.dist(self.start, self.end)


@dataclass(frozen=True)
class SwingArc:
    center: Point
    radius: float
    span_deg: float

    @property
    def length(self) -> float:
        return self.radius * math.radians(self.span_deg)


@dataclass
class LayerContent:
    """Lo que dibuja una capa, en metros."""

    segments: list[Segment] = field(default_factory=list)
    arcs: list[SwingArc] = field(default_factory=list)
    texts: int = 0
    dimensions: int = 0
    other: int = 0
    # Bloques reconocidos por su nombre y el peso de lo que dibujan, por rol.
    blocks: dict[LayerRole, Counter[str]] = field(default_factory=dict)
    block_weight: defaultdict[LayerRole, float] = field(default_factory=lambda: defaultdict(float))


def collect_layers(drawing: "Drawing", rules: LayerRules) -> dict[str, LayerContent]:
    """Contenido de cada capa del espacio modelo, con los bloques explotados como en el
    inventario: lo que está en la capa "0" de un bloque toma la capa del INSERT."""
    k = drawing.units.to_metres
    layers: defaultdict[str, LayerContent] = defaultdict(LayerContent)

    def walk(
        entities: Iterable[DXFGraphic], parent_layer: str | None, credited: LayerRole | None
    ) -> None:
        for entity in entities:
            layer = entity.dxf.layer
            if parent_layer is not None and layer == "0":
                layer = parent_layer
            content = layers[layer]
            if isinstance(entity, Insert):
                role = credited or rules.block_role(entity.dxf.name)
                if role is not None and credited is None:
                    content.blocks.setdefault(role, Counter())[entity.dxf.name] += 1
                walk(entity.virtual_entities(), layer, role)
            elif credited is not None:
                content.block_weight[credited] += _weight(entity) * k
            elif isinstance(entity, Text | MText):
                content.texts += 1
            elif isinstance(entity, Dimension):
                content.dimensions += 1
            elif isinstance(entity, Arc):
                content.arcs.append(_swing_arc(entity, k))
            elif pieces := linear_pieces(entity):
                for piece in pieces:
                    if isinstance(piece, Arc):
                        content.arcs.append(_swing_arc(piece, k))
                    elif isinstance(piece, Line) and piece_length(piece) > 0:
                        start, end = piece.dxf.start, piece.dxf.end
                        content.segments.append(
                            Segment((start.x * k, start.y * k), (end.x * k, end.y * k))
                        )
            else:
                content.other += 1

    walk(drawing.doc.modelspace(), None, None)
    return dict(layers)


def _weight(entity: DXFGraphic) -> float:
    """Peso de una entidad en unidades del dibujo: su longitud si es lineal, si no 1."""
    if isinstance(entity, Arc):
        return piece_length(entity)
    lengths = [piece_length(piece) for piece in linear_pieces(entity)]
    return sum(lengths) if lengths else 1.0


def _swing_arc(arc: Arc, k: float) -> SwingArc:
    center = arc.ocs().to_wcs(arc.dxf.center)
    span = (arc.dxf.end_angle - arc.dxf.start_angle) % 360
    return SwingArc((center.x * k, center.y * k), float(arc.dxf.radius) * k, span)


# --- Detectores geométricos ------------------------------------------------------------------


@dataclass(frozen=True)
class _Placed:
    """Un tramo en el marco común de su grupo de paralelos."""

    index: int
    offset: float  # a lo largo de la normal
    s0: float  # a lo largo de la dirección
    s1: float


def _habitual_thickness(gap: float, tol: float) -> float | None:
    return next((t for t in WALL_THICKNESSES if abs(gap - t) <= tol), None)


def _parallel_groups(segments: Sequence[Segment], angle_tol_deg: float) -> list[list[_Placed]]:
    """Tramos agrupados por dirección (± tolerancia) y ordenados por su offset normal."""
    angles = sorted(
        (math.degrees(math.atan2(s.end[1] - s.start[1], s.end[0] - s.start[0])) % 180, i)
        for i, s in enumerate(segments)
    )
    groups: list[list[tuple[float, int]]] = []
    for angle, i in angles:
        if groups and angle - groups[-1][0][0] <= angle_tol_deg:
            groups[-1].append((angle, i))
        else:
            groups.append([(angle, i)])
    # 179.9° y 0° son la misma dirección.
    if len(groups) > 1 and groups[0][0][0] + 180 - groups[-1][-1][0] <= angle_tol_deg:
        groups[0] = groups.pop() + groups[0]
    placed_groups = []
    for group in groups:
        ref = math.radians(group[0][0])
        d, n = (math.cos(ref), math.sin(ref)), (-math.sin(ref), math.cos(ref))
        placed = []
        for _, i in group:
            seg = segments[i]
            s = [p[0] * d[0] + p[1] * d[1] for p in (seg.start, seg.end)]
            t = [p[0] * n[0] + p[1] * n[1] for p in (seg.start, seg.end)]
            placed.append(_Placed(i, (t[0] + t[1]) / 2, min(s), max(s)))
        placed_groups.append(sorted(placed, key=lambda p: p.offset))
    return placed_groups


def _neighbours(group: list[_Placed], position: int, max_gap: float) -> Iterable[_Placed]:
    """Los tramos del grupo por encima de `position` a menos de `max_gap` de offset."""
    base = group[position].offset
    for other in group[position + 1 :]:
        if other.offset - base > max_gap:
            return
        yield other


def find_windows(segments: Sequence[Segment], rules: LayerRules) -> list[tuple[int, int, int]]:
    """Ventanas dibujadas como tres tramos paralelos de igual extensión y equiespaciados, que
    juntos ocupan un espesor de muro habitual. Cada tramo está en una ventana como mucho."""
    tol = rules.length_tolerance_m
    max_gap = max(WALL_THICKNESSES) + tol
    windows: list[tuple[int, int, int]] = []
    used: set[int] = set()
    for group in _parallel_groups(segments, rules.angle_tolerance_deg):
        for position, a in enumerate(group):
            if a.index in used:
                continue
            same = [
                b
                for b in _neighbours(group, position, max_gap)
                if b.index not in used
                and b.offset - a.offset > tol
                and abs(b.s0 - a.s0) <= tol
                and abs(b.s1 - a.s1) <= tol
            ]
            triple = next(
                (
                    (b, c)
                    for b, c in combinations(same, 2)
                    if c.offset - b.offset > tol
                    and abs((b.offset - a.offset) - (c.offset - b.offset)) <= tol
                    and _habitual_thickness(c.offset - a.offset, tol) is not None
                ),
                None,
            )
            if triple is not None:
                b, c = triple
                windows.append((a.index, b.index, c.index))
                used |= {a.index, b.index, c.index}
    return windows


def find_wall_pairs(segments: Sequence[Segment], rules: LayerRules) -> list[tuple[int, int, float]]:
    """Pares de tramos paralelos que se solapan a lo largo y están separados por un espesor de
    muro habitual: (tramo, tramo, espesor)."""
    tol = rules.length_tolerance_m
    max_gap = max(WALL_THICKNESSES) + tol
    pairs: list[tuple[int, int, float]] = []
    for group in _parallel_groups(segments, rules.angle_tolerance_deg):
        for position, a in enumerate(group):
            for b in _neighbours(group, position, max_gap):
                thickness = _habitual_thickness(b.offset - a.offset, tol)
                overlap = min(a.s1, b.s1) - max(a.s0, b.s0)
                if thickness is not None and overlap > tol:
                    pairs.append((a.index, b.index, thickness))
    return pairs


def find_door_swings(
    arcs: Sequence[SwingArc], segments: Sequence[Segment], rules: LayerRules
) -> tuple[list[tuple[int, int]], list[int]]:
    """Arcos de giro de puerta: ((arco, hoja), ...) cuando una línea de la longitud del radio
    sale del centro del arco, y los arcos de giro sueltos, sin hoja."""
    tol = rules.length_tolerance_m
    swings: list[tuple[int, int]] = []
    loose: list[int] = []
    used: set[int] = set()
    for ai, arc in enumerate(arcs):
        if abs(arc.span_deg - rules.door_arc_span_deg) > rules.door_arc_tolerance_deg:
            continue
        leaf = next(
            (
                si
                for si, seg in enumerate(segments)
                if si not in used
                and abs(seg.length - arc.radius) <= tol
                and min(math.dist(seg.start, arc.center), math.dist(seg.end, arc.center)) <= tol
            ),
            None,
        )
        if leaf is None:
            loose.append(ai)
        else:
            swings.append((ai, leaf))
            used.add(leaf)
    return swings, loose


# --- Decisión por capa -----------------------------------------------------------------------


@dataclass(frozen=True)
class LayerAnalysis:
    """Qué fracción del contenido explica cada rol y con qué evidencia."""

    shares: dict[LayerRole, float]
    details: dict[LayerRole, str]


def analyze_layer(content: LayerContent, rules: LayerRules) -> LayerAnalysis:
    segments = content.segments
    weights: defaultdict[LayerRole, float] = defaultdict(float)
    details: defaultdict[LayerRole, list[str]] = defaultdict(list)

    swings, loose = find_door_swings(content.arcs, segments, rules)
    door_leaves = {leaf for _, leaf in swings}
    if swings:
        weights["doors"] += sum(content.arcs[a].length + segments[s].length for a, s in swings)
        details["doors"].append(f"{len(swings)} arcos de giro de 90° con su hoja")
    if loose:
        # Un arco de 90° sin hoja sugiere una puerta, pero con menos peso.
        weights["doors"] += sum(content.arcs[a].length for a in loose) / 2
        details["doors"].append(f"{len(loose)} arcos de 90° sin hoja")

    rest = [i for i in range(len(segments)) if i not in door_leaves]
    windows = find_windows([segments[i] for i in rest], rules)
    in_windows = {rest[i] for window in windows for i in window}
    if windows:
        weights["windows"] += sum(segments[i].length for i in in_windows)
        details["windows"].append(f"{len(windows)} ventanas de tres líneas paralelas")

    rest = [i for i in rest if i not in in_windows]
    pairs = find_wall_pairs([segments[i] for i in rest], rules)
    in_pairs = {rest[i] for a, b, _ in pairs for i in (a, b)}
    if pairs:
        weights["walls"] += sum(segments[i].length for i in in_pairs)
        thicknesses = ", ".join(f"{t:.2f}" for t in sorted({t for _, _, t in pairs}))
        details["walls"].append(f"{len(pairs)} pares de tramos paralelos a {thicknesses} m")

    if content.texts:
        weights["text"] += content.texts
        details["text"].append(f"{content.texts} textos")
    if content.dimensions:
        weights["dimensions"] += content.dimensions
        details["dimensions"].append(f"{content.dimensions} cotas")
    for role, names in content.blocks.items():
        weights[role] += content.block_weight[role]
        listed = ", ".join(sorted(names))
        details[role].append(f"{names.total()} bloques {listed}")

    total = (
        sum(s.length for s in segments)
        + sum(a.length for a in content.arcs)
        + content.texts
        + content.dimensions
        + content.other
        + sum(content.block_weight.values())
    )
    shares = {role: w / total for role, w in weights.items()} if total > 0 else {}
    return LayerAnalysis(shares, {role: " y ".join(parts) for role, parts in details.items()})


def _percent(share: float) -> str:
    return f"{round(share * 100)} %"


def decide(
    analysis: LayerAnalysis, name_matches: dict[LayerRole, str], rules: LayerRules
) -> tuple[LayerRole, float, str]:
    """Rol, confianza y evidencia (sin punto final) a partir del nombre y la geometría."""
    conf = rules.confidence
    strong = sorted(
        (role for role, share in analysis.shares.items() if share >= rules.mixed_min_share),
        key=lambda role: -analysis.shares[role],
    )

    def described(role: LayerRole) -> str:
        return f"{analysis.details[role]} ({_percent(analysis.shares[role])} del contenido)"

    if len(strong) > 1:
        parts = [described(role) for role in strong]
        return "mixed", conf.mixed, "Mezcla " + ", ".join(parts[:-1]) + " y " + parts[-1]
    if strong:
        geo = strong[0]
        if geo in name_matches:
            return geo, conf.agree, f"El nombre contiene {name_matches[geo]} y hay {described(geo)}"
        if name_matches:
            named, word = next(iter(name_matches.items()))
            return (
                geo,
                conf.conflict,
                f"El nombre sugiere {ROLE_NAMES[named]} ({word}), pero hay {described(geo)}",
            )
        confidence = min(1.0, conf.geometry_base + conf.geometry_gain * analysis.shares[geo])
        return geo, confidence, f"El nombre no indica el rol; hay {described(geo)}"
    if len(name_matches) == 1:
        role, word = next(iter(name_matches.items()))
        return (
            role,
            conf.name_only,
            f"El nombre contiene {word}; la geometría no lo confirma ni lo contradice",
        )
    if name_matches:
        suggested = [f"{ROLE_NAMES[role]} ({word})" for role, word in name_matches.items()]
        return (
            "mixed",
            conf.mixed,
            "El nombre sugiere " + " y ".join(suggested) + " y la geometría no desempata",
        )
    return "ignore", conf.none, "Ni el nombre ni la geometría indican un rol"


def propose_mapping(drawing: "Drawing", rules: LayerRules | None = None) -> list[LayerProposal]:
    """Rol propuesto para cada capa del espacio modelo, ordenado por nombre de capa."""
    rules = rules or load_rules()
    proposals = []
    for layer, content in sorted(collect_layers(drawing, rules).items()):
        role, confidence, evidence = decide(
            analyze_layer(content, rules), rules.name_matches(layer), rules
        )
        if not drawing.units.confirmed:
            evidence += "; escala no confirmada, medidas preliminares"
        proposals.append(LayerProposal(layer, role, round(confidence, 2), evidence + "."))
    return proposals
