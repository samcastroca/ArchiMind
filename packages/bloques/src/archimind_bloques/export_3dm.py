"""Sólido 3D de una carpintería en un .3dm de Rhino, en metros, con rhino3dm.

Cada pieza del marco y de las hojas es una extrusión maciza (una caja) y cada vidrio una
superficie plana. Van en las capas «Marco», «Hoja» y «Vidrio», cada objeto con su nombre.

Los stubs de rhino3dm 8.35 no coinciden con la extensión: no declaran los constructores de Box
y PlaneSurface ni el argumento de atributos de Add*, y dan por solo lectura propiedades que se
pueden asignar. Los `type: ignore` marcan esas llamadas; las firmas se comprobaron en tiempo de
ejecución y las pruebas releen cada archivo con rhino3dm.
"""

from pathlib import Path

import rhino3dm

from archimind_bloques.geometry import Carpentry

LAYERS = {
    "frame": ("Marco", (110, 110, 110, 255)),
    "sash": ("Hoja", (150, 100, 60, 255)),
    "glass": ("Vidrio", (110, 170, 210, 255)),
}


def export_3dm(carpentry: Carpentry, path: str | Path) -> Path:
    model = rhino3dm.File3dm()
    model.Settings.ModelUnitSystem = rhino3dm.UnitSystem.Meters  # type: ignore[misc]
    layers = {part: model.Layers.AddLayer(name, color) for part, (name, color) in LAYERS.items()}

    for piece in carpentry.solids:
        solid = rhino3dm.Box(rhino3dm.BoundingBox(*piece.min, *piece.max))  # type: ignore[call-arg]
        extrusion = rhino3dm.Extrusion.CreateBoxExtrusion(solid, True)
        model.Objects.AddExtrusion(extrusion, _attributes(piece.name, layers[piece.part]))  # type: ignore[call-arg]
    for pane in carpentry.panes:
        # Plano vertical y = cte: su eje u es x y su eje v es z.
        plane = rhino3dm.Plane(
            rhino3dm.Point3d(0, pane.y, 0), rhino3dm.Vector3d(1, 0, 0), rhino3dm.Vector3d(0, 0, 1)
        )
        surface = rhino3dm.PlaneSurface(  # type: ignore[call-arg]
            plane, rhino3dm.Interval(pane.x0, pane.x1), rhino3dm.Interval(pane.z0, pane.z1)
        )
        model.Objects.AddSurface(surface, _attributes(pane.name, layers["glass"]))  # type: ignore[call-arg]

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if not model.Write(str(target), 0):
        raise OSError(f"rhino3dm no pudo escribir {target}")
    return target


def _attributes(name: str, layer_index: int) -> rhino3dm.ObjectAttributes:
    attributes = rhino3dm.ObjectAttributes()
    attributes.Name = name  # type: ignore[misc]
    attributes.LayerIndex = layer_index  # type: ignore[misc]
    return attributes
