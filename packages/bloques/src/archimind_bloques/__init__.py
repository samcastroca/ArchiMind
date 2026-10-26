"""Servidor MCP archimind-bloques: bloques de carpintería."""

from archimind_bloques.catalog import (
    DEFAULT_CATALOG_PATH,
    TYPE_NAMES,
    CarpentryType,
    Catalog,
    CatalogError,
    Defaults,
    Profile,
    add_profile,
    load_catalog,
)
from archimind_bloques.export_3dm import export_3dm
from archimind_bloques.export_dxf import build_document, elevation_block_name, export_dxf
from archimind_bloques.generate import generate
from archimind_bloques.geometry import Arc, Box, Carpentry, Pane, Pen, Polyline, Stroke
from archimind_bloques.naming import block_name
from archimind_bloques.params import (
    AwningWindow,
    CarpentryParams,
    DoubleSwingDoor,
    FixedWindow,
    SlidingDoor,
    SlidingWindow,
    SwingDoor,
)
from archimind_bloques.render import export_svg, render_png

__all__ = [
    "DEFAULT_CATALOG_PATH",
    "TYPE_NAMES",
    "Arc",
    "AwningWindow",
    "Box",
    "Carpentry",
    "CarpentryParams",
    "CarpentryType",
    "Catalog",
    "CatalogError",
    "Defaults",
    "DoubleSwingDoor",
    "FixedWindow",
    "Pane",
    "Pen",
    "Polyline",
    "Profile",
    "SlidingDoor",
    "SlidingWindow",
    "Stroke",
    "SwingDoor",
    "add_profile",
    "block_name",
    "build_document",
    "elevation_block_name",
    "export_3dm",
    "export_dxf",
    "export_svg",
    "generate",
    "load_catalog",
    "render_png",
]
