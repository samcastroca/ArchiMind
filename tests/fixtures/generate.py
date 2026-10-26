"""Genera los casos golden: tests/golden/<caso>/input.dxf, expected.json e input.png.

Uso: python tests/fixtures/generate.py [--caso NOMBRE] [--force]
Las salidas esperadas solo se regeneran cuando el usuario lo pide: sin --force no se
sobrescribe ningún archivo existente.
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GOLDEN_DIR = ROOT / "tests" / "golden"
sys.path.insert(0, str(ROOT / "scripts"))

from cases import CASES, expected_project  # noqa: E402
from dxf_writer import write_dxf  # noqa: E402
from render_dxf import render_dxf  # noqa: E402

OUTPUTS = ("input.dxf", "expected.json", "input.png")


def generate(case: str, force: bool = False) -> Path:
    folder = GOLDEN_DIR / case
    existing = [name for name in OUTPUTS if (folder / name).exists()]
    if existing and not force:
        raise FileExistsError(
            f"{case}: ya existen {', '.join(existing)}; usa --force para regenerarlos"
        )
    folder.mkdir(parents=True, exist_ok=True)
    _, dimensions = CASES[case].model()
    project = expected_project(case)
    write_dxf(project, dimensions, CASES[case].style, folder / "input.dxf")
    (folder / "expected.json").write_text(
        project.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    render_dxf(folder / "input.dxf", folder / "input.png")
    return folder


def main() -> int:
    parser = argparse.ArgumentParser(description="Genera los casos golden de planos DXF.")
    parser.add_argument("--caso", choices=sorted(CASES), help="solo este caso")
    parser.add_argument("--force", action="store_true", help="sobrescribe los existentes")
    args = parser.parse_args()
    failed = False
    for case in [args.caso] if args.caso else CASES:
        try:
            print(generate(case, args.force))
        except FileExistsError as exc:
            print(exc, file=sys.stderr)
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
