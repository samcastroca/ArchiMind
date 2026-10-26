"""insert_blocks sobre apto_2hab con el catálogo de prueba. El plano base imita el que exporta
core: el rectángulo de cada vano en A-PUERTA, A-VENTANA o A-VANO, más el contorno de los muros."""

import math
from pathlib import Path

import ezdxf
import pytest
from archimind_bloques.fit import Preferences
from archimind_bloques.insert import DRAFT_NAME, InsertError, insert_blocks
from archimind_bloques.site import insertion
from archimind_schema import (
    Block,
    BlocksDraft,
    Project,
    load_project,
    new_id,
    opening_polygon,
    save_project,
    wall_polygon,
)
from carpentry_cases import CATALOG
from cases import expected_project
from ezdxf import units
from ezdxf.entities import Insert

LAYERS = {"door": "A-PUERTA", "window": "A-VENTANA", "void": "A-VANO"}


def _export(project: Project, folder: Path) -> Path:
    doc = ezdxf.new("R2010", setup=True, units=units.M)
    msp = doc.modelspace()
    walls = {wall.id: wall for wall in project.walls}
    for wall in project.walls:
        msp.add_lwpolyline(list(wall_polygon(wall).exterior.coords)[:-1], close=True)
    for opening in project.openings:
        outline = opening_polygon(walls[opening.wall_id], opening)
        layer = {"layer": LAYERS[opening.kind]}
        msp.add_lwpolyline(list(outline.exterior.coords)[:-1], close=True, dxfattribs=layer)
    path = folder / "salidas" / f"{folder.name}.dxf"
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(path)
    return path


@pytest.fixture
def casa(tmp_path: Path) -> Path:
    folder = tmp_path / "casa"
    project = expected_project("apto_2hab")
    save_project(project, folder)
    _export(project, folder)
    return folder


def _inserts(path: Path) -> dict[tuple[float, float], Insert]:
    msp = ezdxf.readfile(path).modelspace()
    found = {}
    for entity in msp.query("INSERT"):
        assert isinstance(entity, Insert)
        found[(round(entity.dxf.insert.x, 6), round(entity.dxf.insert.y, 6))] = entity
    return found


def _assign(folder: Path, draft: BlocksDraft) -> None:
    """Lo que hace asignar_bloques de core, sin depender de core."""
    project = load_project(folder)
    openings = {opening.id: opening for opening in project.openings}
    for assignment in draft.assignments:
        block = Block(id=new_id(project, "blq"), **assignment.block.model_dump())
        project.blocks.append(block)
        opening = openings[assignment.opening_id]
        opening.block_id, opening.block_side = block.id, assignment.side
    save_project(project, folder)


def _draft(folder: Path) -> BlocksDraft:
    return BlocksDraft.model_validate_json((folder / "salidas" / DRAFT_NAME).read_text("utf-8"))


def test_every_door_and_window_gets_its_block(casa: Path) -> None:
    result = insert_blocks(casa, None, CATALOG)

    assert result.plan == casa / "salidas" / "casa-carpinteria.dxf"
    assert len(result.fits) == 9 and result.kept == [] and result.warnings == []
    doc = ezdxf.readfile(result.plan)
    msp = doc.modelspace()
    left = [e.dxf.layer for e in msp.query("LWPOLYLINE") if e.dxf.layer in LAYERS.values()]
    assert left == []  # los rectángulos de los vanos se reemplazaron por los bloques
    inserts = _inserts(result.plan)
    assert len(inserts) == 9
    for fit, carpentry in result.fits:
        (x, y), rotation = insertion(fit.site)
        insert = inserts[(round(x, 6), round(y, 6))]
        assert insert.dxf.name == carpentry.name
        assert math.isclose(insert.dxf.rotation, rotation)
        assert insert.dxf.layer == LAYERS[carpentry.kind]
        assert carpentry.name in doc.blocks


def test_the_draft_carries_each_new_block(casa: Path) -> None:
    result = insert_blocks(casa, None, CATALOG)

    draft = _draft(casa)
    assert result.draft == casa / "salidas" / DRAFT_NAME
    assert [a.opening_id for a in draft.assignments] == [f.opening_id for f, _ in result.fits]
    for assignment, (fit, carpentry) in zip(draft.assignments, result.fits, strict=True):
        assert assignment.side == fit.site.side
        assert assignment.block.name == carpentry.name
        assert assignment.block.kind == carpentry.kind
        assert assignment.block.parameters == fit.params.model_dump(mode="json")
    assert load_project(casa) == expected_project("apto_2hab")  # el modelo no se toca


def test_identical_carpentry_is_defined_once(casa: Path) -> None:
    result = insert_blocks(casa, None, CATALOG)
    names = [carpentry.name for _, carpentry in result.fits]
    doc = ezdxf.readfile(result.plan)
    defined = [b.name for b in doc.blocks if b.name in names]
    assert sorted(defined) == sorted(set(names))


def test_the_blocks_already_in_the_model_are_inserted_again(casa: Path) -> None:
    insert_blocks(casa, {"vano-0001": Preferences(), "vano-0009": Preferences()}, CATALOG)
    _assign(casa, _draft(casa))

    result = insert_blocks(casa, {"vano-0002": Preferences(material="pvc")}, CATALOG)

    assert [f.opening_id for f, _ in result.fits] == ["vano-0002"]
    assert result.kept == ["vano-0001", "vano-0009"]
    assert len(_inserts(result.plan)) == 3
    assert [a.opening_id for a in _draft(casa).assignments] == ["vano-0002"]


def test_without_assignments_only_the_openings_without_block(casa: Path) -> None:
    insert_blocks(casa, {"vano-0001": Preferences()}, CATALOG)
    _assign(casa, _draft(casa))

    result = insert_blocks(casa, None, CATALOG)

    assert "vano-0001" not in [f.opening_id for f, _ in result.fits]
    assert result.kept == ["vano-0001"] and len(_inserts(result.plan)) == 9


def test_with_every_opening_assigned_there_is_no_new_draft(casa: Path) -> None:
    insert_blocks(casa, None, CATALOG)
    _assign(casa, _draft(casa))

    result = insert_blocks(casa, None, CATALOG)

    assert result.fits == [] and result.draft is None and len(result.kept) == 9
    assert not (casa / "salidas" / DRAFT_NAME).exists()  # el anterior ya se aplicó


def test_a_block_that_no_longer_fits_is_left_out_with_a_warning(casa: Path) -> None:
    insert_blocks(casa, {"vano-0001": Preferences()}, CATALOG)
    _assign(casa, _draft(casa))
    project = load_project(casa)
    project.blocks[0].width = 1.0
    save_project(project, casa)

    result = insert_blocks(casa, {"vano-0002": Preferences()}, CATALOG)

    assert result.kept == []
    assert result.warnings == [
        "vano-0001: su bloque blq-0001 ya no mide lo que el vano y no se insertó; vuelve a "
        "ajustarlo incluyéndolo en las asignaciones"
    ]


def _nothing_written(folder: Path) -> bool:
    outputs = folder / "salidas"
    return not (outputs / "casa-carpinteria.dxf").exists() and not (outputs / DRAFT_NAME).exists()


def test_an_opening_that_does_not_fit_stops_everything(casa: Path) -> None:
    assignments = {"vano-0001": Preferences(), "vano-0003": Preferences(type="swing_door")}
    with pytest.raises(InsertError, match="No se insertó nada. Estos vanos no calzan:\nvano-0003"):
        insert_blocks(casa, assignments, CATALOG)
    assert _nothing_written(casa)


def test_a_plan_exported_from_another_model_is_rejected(casa: Path) -> None:
    moved = expected_project("apto_2hab")
    moved.openings[0].offset += 0.5
    _export(moved, casa)
    with pytest.raises(InsertError, match="no coincide con el modelo actual: no tiene vano-0001"):
        insert_blocks(casa, None, CATALOG)
    assert _nothing_written(casa)


def test_the_exported_plan_is_needed(casa: Path) -> None:
    (casa / "salidas" / "casa.dxf").unlink()
    with pytest.raises(InsertError, match="Falta el plano exportado salidas/casa.dxf"):
        insert_blocks(casa, None, CATALOG)


def test_the_scale_must_be_confirmed(casa: Path) -> None:
    save_project(expected_project("apto_2hab").model_copy(update={"scale_confirmed": False}), casa)
    with pytest.raises(InsertError, match="PRELIMINAR: la escala no está confirmada"):
        insert_blocks(casa, None, CATALOG)


def test_a_folder_without_project(tmp_path: Path) -> None:
    with pytest.raises(InsertError, match="ábrelo con abrir_proyecto de archimind-core"):
        insert_blocks(tmp_path, None, CATALOG)
