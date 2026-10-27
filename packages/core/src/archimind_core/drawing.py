"""Lectura de planos DXF y DWG (este último mediante ODA File Converter)."""

from dataclasses import dataclass
from pathlib import Path

import ezdxf
from ezdxf import recover
from ezdxf.addons import odafc
from ezdxf.document import Drawing as DXFDocument

from archimind_core.units import DrawingUnits, detect_units

ODA_URL = "https://www.opendesign.com/guestfiles/oda_file_converter"
ODA_INSTALL_HELP = (
    f"instalarlo gratis desde {ODA_URL}; si no queda en la ruta por defecto, indicarla en "
    "'win_exec_path' de la sección [odafc-addon] de la configuración de ezdxf"
)


class DrawingError(Exception):
    """El plano no se puede leer; el mensaje está pensado para el usuario final."""


@dataclass(frozen=True)
class Drawing:
    path: Path
    doc: DXFDocument
    units: DrawingUnits


def read_drawing(path: str | Path) -> Drawing:
    source = Path(path)
    if not source.is_file():
        raise DrawingError(f"No existe el archivo {source}")
    suffix = source.suffix.lower()
    if suffix == ".dxf":
        doc = _read_dxf(source)
    elif suffix == ".dwg":
        doc = _read_dwg(source)
    else:
        raise DrawingError(f"{source.name}: formato no admitido; se esperaba un .dxf o un .dwg")
    return Drawing(source, doc, detect_units(doc))


def _read_dxf(source: Path) -> DXFDocument:
    try:
        doc, auditor = recover.readfile(source)
    except OSError as exc:
        raise DrawingError(f"No se pudo leer {source}: {exc}") from exc
    except ezdxf.DXFStructureError as exc:
        raise DrawingError(f"{source.name} es un DXF dañado: {exc}") from exc
    if auditor.has_errors:
        raise DrawingError(f"{source.name} tiene errores graves de estructura y no se puede leer")
    return doc


def _read_dwg(source: Path) -> DXFDocument:
    if not odafc.is_installed():
        raise DrawingError(
            f"{source.name} es un DWG y para leerlo hace falta ODA File Converter, que no está "
            f"instalado. Opciones: (1) {ODA_INSTALL_HELP}; o (2) exportar el plano a DXF desde "
            "AutoCAD u otro CAD (Guardar como → DXF) e importar ese archivo."
        )
    try:
        doc: DXFDocument = odafc.readfile(source)
    except odafc.ODAFCError as exc:
        raise DrawingError(f"ODA File Converter no pudo convertir {source.name}: {exc}") from exc
    return doc
