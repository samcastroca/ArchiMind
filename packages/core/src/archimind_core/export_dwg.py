"""Exportación del modelo a DWG: el DXF de `export_dxf`, convertido con ODA File Converter."""

from pathlib import Path
from typing import Literal

from archimind_schema import Project
from ezdxf.addons import odafc

from archimind_core.drawing import ODA_INSTALL_HELP
from archimind_core.export_dxf import ExportError, export_dxf, require_confirmed_scale

DwgVersion = Literal["R2013", "R2018"]


def export_dwg(project: Project, path: str | Path, version: DwgVersion = "R2018") -> Path:
    """Escribe el modelo en un DWG en metros y deja al lado el DXF del que sale (mismo nombre,
    extensión .dxf). Sin la escala confirmada o sin ODA File Converter, no escribe nada."""
    require_confirmed_scale(project)
    if not odafc.is_installed():
        raise ExportError(
            "Para exportar en DWG hace falta ODA File Converter, que no está instalado. Opciones: "
            f"(1) {ODA_INSTALL_HELP}, y volver a pedir el DWG; o (2) exportar con "
            'formato="dxf": AutoCAD lo abre igual y desde ahí se puede guardar como DWG.'
        )
    target = Path(path)
    dxf = export_dxf(project, target.with_suffix(".dxf"))
    target.unlink(missing_ok=True)
    try:
        odafc.convert(dxf, target, version=version)
    except odafc.ODAFCError as exc:
        raise ExportError(f"ODA File Converter no pudo convertir {dxf.name} a DWG: {exc}") from exc
    if not target.is_file():  # convert no avisa cuando ODA no escribe nada
        raise ExportError(
            f"ODA File Converter no generó {target.name}. El DXF está en {dxf}; se puede abrir "
            "en AutoCAD y guardarlo como DWG desde ahí."
        )
    return target
