"""Los segmentos de HiddenLineDrawing como DXF en metros y SVG, cada tipo en su capa.

Las coordenadas de la HLD no tienen un origen útil (son las de la cámara): el dibujo se lleva
para que su esquina inferior izquierda quede en el origen. En un corte, y = 0 es así la cara
inferior de la losa más baja.
"""

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import ezdxf
from ezdxf import units
from ezdxf.addons.drawing import Frontend, RenderContext, layout, svg
from ezdxf.addons.drawing.config import (
    BackgroundPolicy,
    ColorPolicy,
    Configuration,
    LineweightPolicy,
)

from archimind_rhino_bridge.styles import Styles

SVG_MARGIN_MM = 10
# ABSOLUTE: el ancho de cada trazo es el grosor de su capa, en mm.
SVG_CONFIG = Configuration(
    background_policy=BackgroundPolicy.WHITE,
    color_policy=ColorPolicy.BLACK,
    lineweight_policy=LineweightPolicy.ABSOLUTE,
)

Points = list[tuple[float, float]]


class DrawingError(Exception):
    """Rhino no devolvió un dibujo utilizable; el mensaje está pensado para el usuario final."""


@dataclass(frozen=True)
class DrawingFiles:
    dxf: Path
    svg: Path
    counts: dict[str, int]  # capa → segmentos


def parse_segments(result: Any) -> list[tuple[str, Points]]:
    """(tipo, puntos) de la respuesta de `hidden_lines`."""
    try:
        return [
            (str(s["kind"]), [(float(x), float(y)) for x, y in s["points"]])
            for s in result["segments"]
        ]
    except (KeyError, TypeError, ValueError) as exc:
        raise DrawingError("El puente de Rhino devolvió líneas ocultas mal formadas.") from exc


def write_drawing(
    segments: Sequence[tuple[str, Points]],
    layers: Mapping[str, str],
    styles: Styles,
    dxf_path: Path,
    svg_path: Path,
) -> DrawingFiles:
    """Cada segmento va a la capa de su tipo según `layers` (p. ej. "section" → "CORTADO");
    los tipos que no están en `layers` se descartan. Las capas llevan grosor, color y tipo de
    línea de los estilos; las entidades, todo por capa."""
    kept = [(layers[kind], points) for kind, points in segments if kind in layers]
    if not kept:
        raise DrawingError(
            "Rhino no devolvió ninguna línea para este dibujo: revisa la vista o la profundidad."
        )
    min_x = min(x for _, points in kept for x, _ in points)
    min_y = min(y for _, points in kept for _, y in points)

    doc = ezdxf.new("R2010", setup=True, units=units.M)
    doc.header["$LWDISPLAY"] = 1
    for name in dict.fromkeys(layers.values()):
        style = styles.layers[name]
        doc.layers.add(
            name, color=style.color, linetype=style.linetype, lineweight=style.lineweight
        )
    msp = doc.modelspace()
    for layer, points in kept:
        shifted = [(x - min_x, y - min_y) for x, y in points]
        msp.add_lwpolyline(shifted, dxfattribs={"layer": layer, "ltscale": styles.linetype_scale})
    dxf_path.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(dxf_path)

    backend = svg.SVGBackend()
    Frontend(RenderContext(doc), backend, config=SVG_CONFIG).draw_layout(msp)
    page = layout.Page(0, 0, layout.Units.mm, margins=layout.Margins.all(SVG_MARGIN_MM))
    scale = 1000 / styles.svg_scale  # mm de papel por metro del dibujo
    text = backend.get_string(page, settings=layout.Settings(scale=scale, fit_page=False))
    svg_path.write_text(text, encoding="utf-8")
    return DrawingFiles(dxf_path, svg_path, dict(Counter(layer for layer, _ in kept)))
