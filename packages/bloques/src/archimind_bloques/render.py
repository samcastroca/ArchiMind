"""SVG y PNG de una carpintería: el mismo documento del DXF, dibujado con el addon `drawing` de
ezdxf, en negro y con el grosor de cada pluma.

Se trabaja con `Figure` directamente, sin pyplot: no hay backend global ni estado entre llamadas.
"""

from pathlib import Path

from ezdxf.addons.drawing import Frontend, RenderContext, layout, svg
from ezdxf.addons.drawing.config import (
    BackgroundPolicy,
    ColorPolicy,
    Configuration,
    LineweightPolicy,
)
from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
from matplotlib.figure import Figure

from archimind_bloques.catalog import TYPE_NAMES
from archimind_bloques.export_dxf import build_document
from archimind_bloques.geometry import Carpentry

SVG_SCALE = 1000 / 20  # mm de papel por metro del dibujo: escala 1:20
SVG_MARGIN_MM = 10
# ABSOLUTE: el ancho de cada trazo es el grosor de su pluma, en mm.
CONFIG = Configuration(
    background_policy=BackgroundPolicy.WHITE,
    color_policy=ColorPolicy.BLACK,
    lineweight_policy=LineweightPolicy.ABSOLUTE,
)


def export_svg(carpentry: Carpentry, path: str | Path) -> Path:
    """Planta y alzado a escala 1:20, con los grosores reales de las plumas."""
    doc = build_document(carpentry)
    backend = svg.SVGBackend()
    Frontend(RenderContext(doc), backend, config=CONFIG).draw_layout(doc.modelspace())
    page = layout.Page(0, 0, layout.Units.mm, margins=layout.Margins.all(SVG_MARGIN_MM))
    text = backend.get_string(page, settings=layout.Settings(scale=SVG_SCALE, fit_page=False))
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return target


def render_png(carpentry: Carpentry, path: str | Path, dpi: int = 150) -> Path:
    """Planta y alzado para revisión visual, con el nombre del bloque, el tipo y el perfil."""
    doc = build_document(carpentry)
    fig = Figure(figsize=(8, 10))
    ax = fig.add_axes((0.04, 0.03, 0.92, 0.88))
    # Figura fija: el dibujo se encaja en los ejes sin deformarse y el título tiene todo el ancho.
    backend = MatplotlibBackend(ax, adjust_figure=False)
    Frontend(RenderContext(doc), backend, config=CONFIG).draw_layout(
        doc.modelspace(), finalize=True
    )
    ax.set_aspect("equal")
    params = carpentry.params
    fig.text(
        0.02,
        0.98,
        f"{carpentry.name}\n{TYPE_NAMES[params.type]} · perfil {params.profile.name}",
        va="top",
        fontsize=11,
    )
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(target, dpi=dpi)
    return target
