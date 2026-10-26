"""Bloque DXF de una carpintería, en metros: la planta y el alzado, cada uno como un BLOCK.

El punto base de la planta es el origen del bloque: el borde del vano sobre el eje del muro.
Las entidades van en la capa "0" con color BYBLOCK, así que toman la capa y el color del
INSERT, pero con el grosor de su pluma fijo: el bloque conserva sus grosores donde se inserte.
"""

from pathlib import Path

import ezdxf
from ezdxf import bbox, units
from ezdxf.document import Drawing
from ezdxf.layouts import BlockLayout

from archimind_bloques.geometry import Arc, Carpentry, Pen, Polyline, Stroke

# Grosor de cada pluma en centésimas de mm, como los guarda el DXF.
LINEWEIGHTS = {Pen.CUT: 35, Pen.SEEN: 25, Pen.THIN: 13, Pen.HIDDEN: 13}
# El patrón DASHED de ezdxf es un trazo de 1.27 unidades y un hueco de 0.254; en metros, a
# 0.05 quedan trazos de 6.35 cm y huecos de 1.27 cm (3.2 y 0.6 mm a 1:20).
HIDDEN_LINETYPE, HIDDEN_LTSCALE = "DASHED", 0.05
INSERT_LAYERS = {"door": "A-PUERTA", "window": "A-VENTANA"}
ELEVATION_LAYER = "A-ALZADO"
LAYER_COLORS = {"A-PUERTA": 3, "A-VENTANA": 4, ELEVATION_LAYER: 8}
ELEVATION_SUFFIX = "-ALZADO"
ELEVATION_GAP_M = 0.5  # separación entre la planta y el alzado en el espacio modelo


def elevation_block_name(carpentry: Carpentry) -> str:
    return carpentry.name + ELEVATION_SUFFIX


def build_document(carpentry: Carpentry) -> Drawing:
    """Documento R2010 con los dos bloques. En el espacio modelo, la planta va insertada en
    el origen y el alzado encima, alineado en x."""
    doc = ezdxf.new("R2010", setup=True, units=units.M)
    doc.header["$LWDISPLAY"] = 1
    plan = doc.blocks.get(add_plan_block(doc, carpentry))
    elevation = doc.blocks.new(elevation_block_name(carpentry), base_point=(0, 0))
    _add_strokes(elevation, carpentry.elevation)

    plan_layer = INSERT_LAYERS[carpentry.kind]
    for layer in (plan_layer, ELEVATION_LAYER):
        doc.layers.add(layer, color=LAYER_COLORS[layer])
    msp = doc.modelspace()
    msp.add_blockref(plan.name, (0, 0), dxfattribs={"layer": plan_layer})
    # El alzado tiene el origen en el piso; se acerca a la planta sin el hueco del antepecho.
    lift = bbox.extents(plan).extmax.y + ELEVATION_GAP_M - bbox.extents(elevation).extmin.y
    msp.add_blockref(elevation.name, (0, lift), dxfattribs={"layer": ELEVATION_LAYER})
    return doc


def add_plan_block(doc: Drawing, carpentry: Carpentry) -> str:
    """Define en `doc` el BLOCK de la planta, si aún no está, y devuelve su nombre. Dos
    carpinterías con el mismo nombre son la misma: se define una vez."""
    if carpentry.name not in doc.blocks:
        _add_strokes(doc.blocks.new(carpentry.name, base_point=(0, 0)), carpentry.plan)
    return carpentry.name


def export_dxf(carpentry: Carpentry, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    build_document(carpentry).saveas(target)
    return target


def _add_strokes(block: BlockLayout, strokes: tuple[Stroke, ...]) -> None:
    for stroke in strokes:
        attribs: dict[str, str | int | float] = {
            "layer": "0",
            "color": 0,  # BYBLOCK
            "lineweight": LINEWEIGHTS[stroke.pen],
            "linetype": "CONTINUOUS",
        }
        if stroke.pen is Pen.HIDDEN:
            attribs |= {"linetype": HIDDEN_LINETYPE, "ltscale": HIDDEN_LTSCALE}
        match stroke:
            case Polyline():
                block.add_lwpolyline(stroke.points, close=stroke.closed, dxfattribs=attribs)
            case Arc():
                block.add_arc(
                    stroke.center,
                    stroke.radius,
                    stroke.start_angle,
                    stroke.end_angle,
                    dxfattribs=attribs,
                )
