"""Renderiza a PNG el modelo reconstruido de un plano superpuesto al DXF original.

Muros en azul, vanos en naranja y espacios rellenos con su nombre y su área. El mapeo de capas
es el que propone `propose_mapping`.

Uso: python scripts/render_model.py plano.dxf [salida.png] [--dpi 200]
     python scripts/render_model.py --all   (los casos golden en tests/output/build_model/)
"""

import argparse
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from archimind_core import (  # noqa: E402
    BuildResult,
    DrawingError,
    build_model,
    proposals_to_mapping,
    propose_mapping,
    read_drawing,
)
from archimind_core.render import draw_model  # noqa: E402
from ezdxf.addons.drawing.config import (  # noqa: E402
    BackgroundPolicy,
    ColorPolicy,
    Configuration,
)
from render_dxf import draw_dxf  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
GOLDEN_DIR = ROOT / "tests" / "golden"
OUTPUT_DIR = ROOT / "tests" / "output" / "build_model"


def render_model(dxf_path: Path, png_path: Path, dpi: int = 200) -> BuildResult:
    drawing = read_drawing(dxf_path)
    result = build_model(drawing, proposals_to_mapping(propose_mapping(drawing)))
    project = result.project
    # El DXF se dibuja en sus unidades; el modelo, en metros, se lleva a ellas.
    k = 1 / drawing.units.to_metres

    fig = plt.figure(figsize=(10, 10))
    ax = fig.add_axes((0, 0.06, 1, 0.94))
    gray = Configuration(
        background_policy=BackgroundPolicy.WHITE,
        color_policy=ColorPolicy.CUSTOM,
        custom_fg_color="#8c8c8c",
    )
    draw_dxf(drawing.doc, ax, gray)
    legend = draw_model(ax, project, k)
    warnings = [p for p in result.problems if p.code != "valores_por_defecto"]
    fig.legend(handles=legend, loc="lower left", ncols=3, frameon=False)
    fig.text(
        0.01,
        0.98,
        f"{dxf_path.parent.name}/{dxf_path.name} · {len(warnings)} avisos",
        va="top",
        fontsize=10,
    )
    png_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(png_path, dpi=dpi)
    plt.close(fig)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Renderiza el modelo reconstruido sobre el DXF.")
    parser.add_argument("dxf", nargs="?")
    parser.add_argument("png", nargs="?")
    parser.add_argument("--all", action="store_true", help="todos los casos golden")
    parser.add_argument("--dpi", type=int, default=200)
    args = parser.parse_args()
    if args.all:
        jobs = [
            (case / "input.dxf", OUTPUT_DIR / f"{case.name}.png")
            for case in sorted(GOLDEN_DIR.iterdir())
            if (case / "input.dxf").is_file()
        ]
    elif args.dxf:
        source = Path(args.dxf)
        jobs = [(source, Path(args.png) if args.png else source.with_suffix(".modelo.png"))]
    else:
        parser.error("indicar un DXF o --all")
    try:
        for source, target in jobs:
            result = render_model(source, target, args.dpi)
            warnings = [p for p in result.problems if p.code != "valores_por_defecto"]
            print(f"{target} ({len(warnings)} avisos)")
            for problem in warnings:
                print(f"  {problem.code}: {problem.message}")
    except DrawingError as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
