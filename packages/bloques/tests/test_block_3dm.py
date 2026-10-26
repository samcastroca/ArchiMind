"""El .3dm se relee con rhino3dm: unidades, capas y cada pieza con su caja exacta.

Los stubs de rhino3dm 8.35 piden un argumento en GetBoundingBox que la extensión no acepta y no
declaran iterable la tabla de objetos (ver export_3dm.py).
"""

from pathlib import Path

import pytest
import rhino3dm
from archimind_bloques import export_3dm, generate
from carpentry_cases import EXAMPLES, TOL


def _box(geometry: rhino3dm.GeometryBase) -> tuple[float, ...]:
    found = geometry.GetBoundingBox()  # type: ignore[call-arg]
    return (found.Min.X, found.Min.Y, found.Min.Z, found.Max.X, found.Max.Y, found.Max.Z)


@pytest.mark.parametrize("case", sorted(EXAMPLES))
def test_the_model_reads_back(tmp_path: Path, case: str) -> None:
    carpentry = generate(EXAMPLES[case])
    path = export_3dm(carpentry, tmp_path / "salidas" / f"{carpentry.name}.3dm")

    model = rhino3dm.File3dm.Read(str(path))
    assert model.Settings.ModelUnitSystem == rhino3dm.UnitSystem.Meters
    layers = [layer.Name for layer in model.Layers]
    assert layers == ["Marco", "Hoja", "Vidrio"]
    objects = {obj.Attributes.Name: obj for obj in model.Objects}  # type: ignore[attr-defined]
    assert len(objects) == len(carpentry.solids) + len(carpentry.panes)

    for piece in carpentry.solids:
        obj = objects[piece.name]
        assert isinstance(obj.Geometry, rhino3dm.Extrusion), piece.name
        assert obj.Geometry.IsSolid
        assert layers[obj.Attributes.LayerIndex] == ("Marco" if piece.part == "frame" else "Hoja")
        assert _box(obj.Geometry) == pytest.approx((*piece.min, *piece.max), abs=TOL)
    for pane in carpentry.panes:
        obj = objects[pane.name]
        assert isinstance(obj.Geometry, rhino3dm.Surface), pane.name
        assert layers[obj.Attributes.LayerIndex] == "Vidrio"
        assert _box(obj.Geometry) == pytest.approx(
            (pane.x0, pane.y, pane.z0, pane.x1, pane.y, pane.z1), abs=TOL
        )
