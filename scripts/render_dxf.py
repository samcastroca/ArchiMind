"""Renderiza el espacio modelo de un DXF a PNG con el addon drawing de ezdxf.

Uso: python scripts/render_dxf.py entrada.dxf [salida.png] [--dpi 200]
Sin salida, escribe el PNG junto al DXF con el mismo nombre.
"""

import argparse
import sys
from pathlib import Path

import ezdxf
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from ezdxf import recover  # noqa: E402
from ezdxf.addons.drawing import Frontend, RenderContext  # noqa: E402
from ezdxf.addons.drawing.config import BackgroundPolicy, ColorPolicy, Configuration  # noqa: E402
from ezdxf.addons.drawing.matplotlib import MatplotlibBackend  # noqa: E402


def render_dxf(dxf_path: str | Path, png_path: str | Path | None = None, dpi: int = 200) -> Path:
    source = Path(dxf_path)
    target = Path(png_path) if png_path is not None else source.with_suffix(".png")
    try:
        doc, auditor = recover.readfile(source)
    except OSError as exc:
        raise ValueError(f"No se pudo leer {source}: no existe o no es un DXF") from exc
    except ezdxf.DXFStructureError as exc:
        raise ValueError(f"{source} es un DXF dañado: {exc}") from exc
    if auditor.has_errors:
        raise ValueError(f"{source} tiene errores graves de estructura y no se puede renderizar")
    fig = plt.figure(figsize=(10, 10))
    ax = fig.add_axes((0, 0, 1, 1))
    config = Configuration(background_policy=BackgroundPolicy.WHITE, color_policy=ColorPolicy.COLOR)
    Frontend(RenderContext(doc), MatplotlibBackend(ax), config=config).draw_layout(
        doc.modelspace(), finalize=True
    )
    fig.savefig(target, dpi=dpi)
    plt.close(fig)
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description="Renderiza un DXF a PNG.")
    parser.add_argument("dxf")
    parser.add_argument("png", nargs="?")
    parser.add_argument("--dpi", type=int, default=200)
    args = parser.parse_args()
    try:
        print(render_dxf(args.dxf, args.png, args.dpi))
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
