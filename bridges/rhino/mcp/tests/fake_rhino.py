"""Un documento de Rhino en memoria con las cinco operaciones del puente.

Hace lo que hace `RhinoOps` del script del puente, sin RhinoCommon: guarda los objetos que carga
y los devuelve como caras planas, igual que `Extrusion.ToBrep(True)` — cada bucle cerrado, con
otro vértice inicial y en sentido contrario, como puede devolverlos Rhino. Las ayudas de edición
imitan lo que el usuario hace en Rhino (mover, girar, estirar, borrar, copiar…), en metros.
"""

import copy
import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import archimind_bridge as bridge

Point = tuple[float, float]


@dataclass
class FakeObject:
    tag: str | None
    layer: str
    kind: str  # "prism" o "surface"
    rings: list[list[Point]]  # prisma: [huella]; superficie: [exterior, *huecos]
    z0: float
    z1: float = 0.0
    faces: list[Any] | None = None  # si no es None, se devuelve tal cual (objeto «roto»)


@dataclass
class FakeDocument:
    path: str | None = None
    modified: bool = False
    in_command: bool = False
    strings: dict[str, str] = field(default_factory=dict)
    objects: list[FakeObject] = field(default_factory=list)
    disk: dict[str, tuple[dict[str, str], list[FakeObject]]] = field(default_factory=dict)
    calls: list[str] = field(default_factory=list)

    # --- Operaciones del puente ---------------------------------------------------------------

    def ping(self) -> dict[str, Any]:
        self.calls.append("ping")
        counts = dict.fromkeys(bridge.SUBLAYERS, 0)
        for obj in self.objects:
            name = obj.layer.removeprefix(f"{bridge.ROOT_LAYER}::")
            if obj.tag and name in counts:
                counts[name] += 1
        return {
            "rhino": "8.99 (falso)",
            "in_command": self.in_command,
            "document": {
                "path": self.path,
                "name": None,
                "modified": self.modified,
                "units": "Meters",
            },
            "archimind": {
                "project": self.strings.get(bridge.DOC_PROJECT),
                "base_sha256": self.strings.get(bridge.DOC_SHA),
                "objects": counts,
            },
        }

    def open_file(self, path: str) -> dict[str, Any]:
        self.calls.append("open_file")
        self._idle()
        if self.path == path:
            return {"opened": False}
        if self.modified:
            raise bridge.OpError("El documento abierto en Rhino tiene cambios sin guardar.")
        strings, objects = self.disk.get(path, ({}, []))
        self.path, self.strings, self.objects = path, dict(strings), copy.deepcopy(objects)
        return {"opened": True}

    def load_model_layers(
        self, project: str, base_sha256: str, base_model: str, objects: list[dict[str, Any]]
    ) -> dict[str, Any]:
        self.calls.append("load_model_layers")
        self._idle()
        bridge.check_load(project, base_sha256, base_model, objects)
        sublayers = {f"{bridge.ROOT_LAYER}::{name}" for name in bridge.SUBLAYERS}
        self.objects = [o for o in self.objects if not o.tag and o.layer not in sublayers]
        counts = dict.fromkeys(bridge.SUBLAYERS, 0)
        for item in objects:
            layer = f"{bridge.ROOT_LAYER}::{item['layer']}"
            if item["kind"] == "prism":
                ring = [(x, y) for x, y in item["footprint"]]
                self.objects.append(
                    FakeObject(item["id"], layer, "prism", [ring], item["z0"], item["z1"])
                )
            else:
                rings = [[(x, y) for x, y in r] for r in [item["exterior"], *item["holes"]]]
                self.objects.append(FakeObject(item["id"], layer, "surface", rings, item["z"]))
            counts[item["layer"]] += 1
        self.strings.update(
            {bridge.DOC_PROJECT: project, bridge.DOC_SHA: base_sha256, bridge.DOC_BASE: base_model}
        )
        self.modified = True
        return {"loaded": counts}

    def read_tagged_objects(self) -> dict[str, Any]:
        self.calls.append("read_tagged_objects")
        self._idle()
        return {
            "project": self.strings.get(bridge.DOC_PROJECT),
            "base_sha256": self.strings.get(bridge.DOC_SHA),
            "base_model": self.strings.get(bridge.DOC_BASE),
            "objects": [
                {"id": o.tag, "layer": o.layer, "type": "Extrusion", "faces": _faces(o)}
                for o in self.objects
            ],
        }

    def save_as(self, path: str) -> dict[str, Any]:
        self.calls.append("save_as")
        self._idle()
        self.disk[path] = (dict(self.strings), copy.deepcopy(self.objects))
        self.path, self.modified = path, False
        return {"path": path}

    def _idle(self) -> None:
        if self.in_command:
            raise bridge.OpError("Rhino está ejecutando un comando.")

    # --- Ediciones del usuario -----------------------------------------------------------------

    def get(self, tag: str) -> FakeObject:
        return next(o for o in self.objects if o.tag == tag)

    def transform(self, tag: str, fn: Callable[[Point], Point]) -> None:
        obj = self.get(tag)
        obj.rings = [[fn(p) for p in ring] for ring in obj.rings]
        self.modified = True

    def move(self, tag: str, dx: float, dy: float, dz: float = 0.0) -> None:
        self.transform(tag, lambda p: (p[0] + dx, p[1] + dy))
        obj = self.get(tag)
        obj.z0, obj.z1 = obj.z0 + dz, obj.z1 + dz

    def rotate(self, tag: str, angle: float, center: Point) -> None:
        cos, sin = math.cos(angle), math.sin(angle)

        def turn(p: Point) -> Point:
            x, y = p[0] - center[0], p[1] - center[1]
            return (center[0] + x * cos - y * sin, center[1] + x * sin + y * cos)

        self.transform(tag, turn)

    def set_top(self, tag: str, z1: float) -> None:
        self.get(tag).z1 = z1
        self.modified = True

    def delete(self, tag: str) -> None:
        self.objects.remove(self.get(tag))
        self.modified = True

    def duplicate(self, tag: str) -> None:
        self.objects.append(copy.deepcopy(self.get(tag)))
        self.modified = True

    def add_untagged(self, layer: str = "Muros") -> None:
        ring = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
        self.objects.append(
            FakeObject(None, f"{bridge.ROOT_LAYER}::{layer}", "prism", [ring], 0.0, 1.0)
        )
        self.modified = True

    def break_object(self, tag: str) -> None:
        """Como convertirlo en malla: ya no se puede leer."""
        self.get(tag).faces = []
        self.modified = True


def _loop(ring: list[Point], z: float, shift: int, reverse: bool) -> list[list[float]]:
    points = ring[shift % len(ring) :] + ring[: shift % len(ring)]
    if reverse:
        points = points[::-1]
    closed = [*points, points[0]]
    return [[x, y, z] for x, y in closed]


def _faces(obj: FakeObject) -> list[Any] | None:
    if obj.faces is not None:
        return obj.faces or None
    if obj.kind == "surface":
        exterior, *holes = obj.rings
        return [[_loop(exterior, obj.z0, 1, True), *(_loop(h, obj.z0, 2, False) for h in holes)]]
    (ring,) = obj.rings
    faces = [[_loop(ring, obj.z0, 1, True)], [_loop(ring, obj.z1, 2, False)]]
    for a, b in zip(ring, [*ring[1:], ring[0]], strict=True):
        side = [[*a, obj.z0], [*b, obj.z0], [*b, obj.z1], [*a, obj.z1], [*a, obj.z0]]
        faces.append([side])
    return faces
