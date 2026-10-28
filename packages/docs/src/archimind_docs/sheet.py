"""La ficha del proyecto en PDF, con reportlab (Platypus): datos del proyecto, cuadro de áreas,
planta y memoria.

Las cifras salen de `datos_para_memoria` (ya verificadas) y la planta, de `render_model` de
core. El texto usa DejaVu Sans, la fuente que trae matplotlib, para que cualquier carácter de
la memoria se vea (las fuentes estándar de PDF solo cubren Latin-1).
"""

import os
import tempfile
from datetime import date
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

import matplotlib
from archimind_core.render import render_model
from archimind_schema import Project
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    Image,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

FONT, FONT_BOLD = "DejaVuSans", "DejaVuSans-Bold"
MARGIN = 18 * mm
PLAN_SIZE = 150 * mm
TABLE_STYLE = TableStyle(
    [
        ("FONTNAME", (0, 0), (-1, -1), FONT),
        ("FONTNAME", (0, 0), (-1, 0), FONT_BOLD),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8e8e8")),
        ("ALIGN", (-1, 1), (-1, -1), "RIGHT"),
    ]
)


def build_sheet(project: Project, data: dict[str, Any], memory_text: str, path: Path) -> Path:
    _register_fonts()
    styles = _styles()
    preliminary = data["proyecto"]["aviso"]
    story: list[Any] = [
        Paragraph(escape(f"Ficha del proyecto «{project.name}»"), styles["title"]),
        Paragraph(escape(f"Generada el {date.today().isoformat()}."), styles["small"]),
        Spacer(1, 4 * mm),
        Paragraph("Datos del proyecto", styles["heading"]),
        _table(_project_rows(data)),
        Spacer(1, 4 * mm),
        Paragraph("Cuadro de áreas", styles["heading"]),
        _table(_area_rows(data)),
        Spacer(1, 4 * mm),
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        plan = render_model(project, Path(folder) / "planta.png")
        story += [
            # El título no queda solo al pie de una página con la planta en la siguiente.
            KeepTogether(
                [
                    Paragraph("Planta", styles["heading"]),
                    Image(str(plan), width=PLAN_SIZE, height=PLAN_SIZE),
                ]
            ),
            Paragraph("Memoria descriptiva", styles["heading"]),
        ]
        story += [
            Paragraph(escape(" ".join(block.split())), styles["body"])
            for block in memory_text.split("\n\n")
            if block.strip()
        ]

        def decorate(canvas: Canvas, doc: SimpleDocTemplate) -> None:
            canvas.saveState()
            canvas.setFont(FONT, 8)
            canvas.drawString(MARGIN, 10 * mm, f"{project.name} · página {doc.page}")
            if preliminary:
                canvas.setFont(FONT_BOLD, 10)
                canvas.setFillColor(colors.red)
                canvas.drawRightString(A4[0] - MARGIN, A4[1] - 12 * mm, preliminary)
            canvas.restoreState()

        doc = SimpleDocTemplate(
            str(path),
            pagesize=A4,
            leftMargin=MARGIN,
            rightMargin=MARGIN,
            topMargin=MARGIN,
            bottomMargin=MARGIN,
            title=f"Ficha {project.name}",
        )
        doc.build(story, onFirstPage=decorate, onLaterPages=decorate)
    return path


def _register_fonts() -> None:
    folder = Path(matplotlib.get_data_path()) / "fonts" / "ttf"
    for name in (FONT, FONT_BOLD):
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name, os.fspath(folder / f"{name}.ttf")))


def _styles() -> dict[str, ParagraphStyle]:
    sample = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("title", parent=sample["Title"], fontName=FONT_BOLD),
        "heading": ParagraphStyle("heading", parent=sample["Heading2"], fontName=FONT_BOLD),
        "body": ParagraphStyle("body", parent=sample["BodyText"], fontName=FONT, leading=14),
        "small": ParagraphStyle("small", parent=sample["BodyText"], fontName=FONT, fontSize=8),
    }


def _table(rows: list[list[str]]) -> Table:
    table = Table(rows, hAlign="LEFT")
    table.setStyle(TABLE_STYLE)
    return table


def _project_rows(data: dict[str, Any]) -> list[list[str]]:
    scale = "confirmada" if data["proyecto"]["escala_confirmada"] else "sin confirmar"
    counts = data["conteos"]
    rows = [
        ["Dato", "Valor"],
        ["Escala", scale],
        ["Muros", str(counts["muros"])],
        ["Vanos", str(counts["vanos"])],
        ["Espacios", str(counts["espacios"])],
    ]
    for level in data["niveles"]:
        height = "sin confirmar" if level["altura_m"] is None else f"{level['altura_m']:.2f} m"
        rows.append([f"Nivel {level['nombre']}", f"cota {level['cota_m']:.2f} m, altura {height}"])
    return rows


def _area_rows(data: dict[str, Any]) -> list[list[str]]:
    areas = data["areas_m2"]
    rows = [["Espacio", "Categoría", "Área (m²)"]]
    rows += [[s["nombre"], s["categoria"], f"{s['area']:.2f}"] for s in areas["espacios"]]
    rows += [
        ["Área útil", "", f"{areas['util']:.2f}"],
        ["Área construida", "", f"{areas['construida']:.2f}"],
    ]
    if areas["balcones"]:
        rows.append(["Balcones", "", f"{areas['balcones']:.2f}"])
    return rows
