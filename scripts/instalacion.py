"""Deja ArchiMind listo en Windows: conecta sus servidores con Claude Desktop, configura ODA si
está instalado, crea la carpeta de proyectos con un plano de ejemplo y comprueba todo.

Lo ejecuta `scripts/instalar.ps1` (el doble clic en «Instalar ArchiMind.bat») después de
instalar uv y Git y de `uv sync`. También sirve por su cuenta, para reparar la configuración:

    uv run python scripts/instalacion.py --uv <ruta de uv.exe> [--proyectos <carpeta>] [--rhino]

En la configuración de Claude Desktop solo escribe las entradas de ArchiMind: lo demás se
conserva, y antes de cambiar el archivo deja un respaldo al lado.
"""

import argparse
import importlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
CONFIG_NAME = "claude_desktop_config.json"
BACKUP_INFIX = ".antes-de-archimind-"
# Nombre en Claude Desktop, paquete del workspace y comando del servidor.
SERVERS = (
    ("archimind-core", "archimind-core", "archimind-core"),
    ("archimind-bloques", "archimind-bloques", "archimind-bloques"),
    ("archimind-docs", "archimind-docs", "archimind-docs"),
)
RHINO_SERVER = ("rhino-bridge", "archimind-rhino-bridge", "archimind-rhino-bridge")
SERVER_MODULES = {
    "archimind-core": "archimind_core.server",
    "archimind-bloques": "archimind_bloques.server",
    "archimind-docs": "archimind_docs.server",
    "rhino-bridge": "archimind_rhino_bridge.server",
}
EXAMPLE_PLAN = REPO / "tests" / "golden" / "apto_2hab" / "input.dxf"
EXAMPLE_NAME = "ejemplo-apartamento.dxf"
FIRST_PROJECT = "mi-primer-proyecto"
RHINO_PLUGIN = REPO / "bridges" / "rhino" / "plugin" / "archimind_bridge.py"
# Donde Rhino 8 deja su carpeta de instalación (developer.rhino3d.com, «Finding Rhino's
# Installation Folder»).
RHINO_REGISTRY_KEY = r"SOFTWARE\McNeel\Rhinoceros\8.0\Install"

Entries = dict[str, dict[str, Any]]


class SetupError(Exception):
    """Un paso de la instalación no se pudo hacer; el mensaje está pensado para el usuario."""


@dataclass(frozen=True)
class ConfigResult:
    path: Path
    changed: bool
    backup: Path | None  # el respaldo del archivo anterior, si había algo que respaldar


# --- Claude Desktop ---------------------------------------------------------------------------


def claude_config_files() -> list[Path]:
    """Los archivos de configuración que Claude Desktop puede leer, el de la instalación MSIX
    primero; vacío si no está instalado o no se abrió nunca.

    La instalación MSIX (la del instalador oficial actual y la de Microsoft Store) lee la copia
    de `%LOCALAPPDATA%\\Packages\\Claude_…`, aunque «Editar configuración» abra la de
    `%APPDATA%\\Claude`; las dos no se sincronizan. Por eso se escribe en todas las que hay.
    """
    files = []
    local = os.environ.get("LOCALAPPDATA")
    if local:
        for package in sorted(Path(local, "Packages").glob("Claude_*")):
            files.append(package / "LocalCache" / "Roaming" / "Claude" / CONFIG_NAME)
    roaming = os.environ.get("APPDATA")
    if roaming and Path(roaming, "Claude").is_dir():
        files.append(Path(roaming, "Claude", CONFIG_NAME))
    return files


def server_entries(repo: Path, uv: Path, rhino: bool) -> Entries:
    """Las entradas de `mcpServers` de ArchiMind, con la ruta completa de uv: Claude Desktop no
    siempre ve el PATH del usuario."""
    servers = [*SERVERS, RHINO_SERVER] if rhino else list(SERVERS)
    return {
        name: {
            "command": str(uv),
            "args": ["run", "--directory", str(repo), "--package", package, script],
            "env": {"PYTHONUTF8": "1"},
        }
        for name, package, script in servers
    }


def merge_config(
    path: Path, entries: Entries, refresh: Entries | None = None, now: datetime | None = None
) -> ConfigResult:
    """Pone `entries` en `mcpServers` y actualiza las de `refresh` que ya estén. Conserva todo lo
    demás. Si el archivo cambia, antes deja un respaldo; si no cambia, no lo toca."""
    text = path.read_text(encoding="utf-8-sig") if path.is_file() else ""
    try:
        config = json.loads(text) if text.strip() else {}
    except json.JSONDecodeError as exc:
        raise SetupError(
            f"{path} tiene un error de formato (línea {exc.lineno}, columna {exc.colno}) y no se "
            "tocó. Suele ser una coma o una comilla de más o de menos: corrígelo, o cámbiale el "
            "nombre al archivo para empezar de cero, y vuelve a ejecutar el instalador."
        ) from exc
    if not isinstance(config, dict) or not isinstance(config.get("mcpServers", {}), dict):
        raise SetupError(
            f"{path} no tiene la forma que espera Claude Desktop y no se tocó: cámbiale el "
            "nombre al archivo y vuelve a ejecutar el instalador."
        )
    servers = config.setdefault("mcpServers", {})
    wanted = {**entries, **{n: e for n, e in (refresh or {}).items() if n in servers}}
    if all(servers.get(name) == entry for name, entry in wanted.items()):
        return ConfigResult(path, False, None)
    servers.update(wanted)
    backup = None
    if text.strip():
        stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
        backup = path.with_name(f"{path.name}{BACKUP_INFIX}{stamp}")
        shutil.copy2(path, backup)
    _write_atomically(path, json.dumps(config, indent=2, ensure_ascii=False) + "\n")
    return ConfigResult(path, True, backup)


def _write_atomically(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, prefix=".claude-", suffix=".tmp", delete=False
    ) as tmp:
        tmp.write(text)
    try:
        os.replace(tmp.name, path)
    except BaseException:
        Path(tmp.name).unlink(missing_ok=True)
        raise


# --- Rhino, ODA y proyecto de ejemplo -----------------------------------------------------------


def _registry_rhino_path() -> str | None:
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, RHINO_REGISTRY_KEY) as key:
            value, _ = winreg.QueryValueEx(key, "InstallPath")
    except (ImportError, OSError):
        return None
    return str(value)


def rhino_installed(registry: Callable[[], str | None] = _registry_rhino_path) -> bool:
    install = registry()
    if install and Path(install).is_dir():
        return True
    program_files = os.environ.get("ProgramFiles")
    return bool(program_files) and Path(program_files, "Rhino 8", "System", "Rhino.exe").is_file()


def configure_oda() -> str:
    """Si ODA File Converter está instalado y ezdxf no lo encuentra, le guarda la ruta en su
    configuración (`~/.config/ezdxf/ezdxf.ini`). Devuelve la línea del resumen."""
    import ezdxf
    from ezdxf.addons import odafc

    if odafc.is_installed():
        return f"[OK] ODA File Converter (para DWG): {odafc.get_win_exec_path()}"
    program_files = os.environ.get("ProgramFiles")
    found = (
        list(Path(program_files, "ODA").glob("ODAFileConverter*/ODAFileConverter.exe"))
        if program_files
        else []
    )
    if not found:
        return (
            "[--] ODA File Converter no está instalado. Solo hace falta para planos DWG; con DXF "
            "no se necesita (ver docs/instalacion-manual.md)."
        )
    exe = max(found, key=lambda path: [int(n) for n in re.findall(r"\d+", path.parent.name)])
    ezdxf.options.set("odafc-addon", "win_exec_path", str(exe))
    ezdxf.options.write_home_config()
    return f"[OK] ODA File Converter (para DWG) configurado: {exe}"


def example_project(folder: Path) -> Path:
    """La carpeta de proyectos con un plano de ejemplo; lo que ya existe no se toca."""
    folder.mkdir(parents=True, exist_ok=True)
    plan = folder / EXAMPLE_NAME
    if not plan.exists():
        shutil.copyfile(EXAMPLE_PLAN, plan)
    return plan


# --- Comprobaciones -----------------------------------------------------------------------------


def check_servers(names: list[str]) -> list[str]:
    """Una línea por servidor: si su código se puede cargar."""
    lines = []
    for name in names:
        try:
            importlib.import_module(SERVER_MODULES[name])
        except Exception as exc:  # cualquier fallo al cargar es un servidor que no arrancará
            lines.append(f"[FALTA] {name} no se puede cargar: {type(exc).__name__}: {exc}")
        else:
            lines.append(f"[OK] {name}")
    return lines


def check_git() -> str:
    try:
        version = subprocess.run(
            ["git", "--version"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return (
            "[FALTA] Git no está instalado o no se encuentra: ArchiMind lo necesita para guardar "
            "las versiones de cada proyecto. Instálalo desde https://git-scm.com/downloads/win y "
            "vuelve a ejecutar el instalador."
        )
    return f"[OK] {version}"


# --- Programa -----------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--uv", type=Path, required=True, help="Ruta completa de uv.exe.")
    parser.add_argument(
        "--proyectos",
        type=Path,
        default=Path.home() / "Documents" / "ArchiMind-proyectos",
        help="Carpeta de proyectos, donde se deja el plano de ejemplo.",
    )
    parser.add_argument(
        "--rhino", action="store_true", help="Conectar rhino-bridge aunque no se detecte Rhino 8."
    )
    args = parser.parse_args(argv)
    uv = args.uv.resolve()
    blocking = 0

    print("\nComprobando ArchiMind:")
    rhino = args.rhino or rhino_installed()
    names = [name for name, _, _ in SERVERS] + (["rhino-bridge"] if rhino else [])
    lines = [*check_servers(names), check_git()]
    print("\n".join(f"  {line}" for line in lines))
    blocking += sum(line.startswith("[FALTA]") for line in lines)

    print("\nConectando ArchiMind con Claude Desktop:")
    files = claude_config_files()
    entries = server_entries(REPO, uv, rhino)
    # Sin Rhino detectado, un rhino-bridge que ya estaba se conserva con la ruta al día.
    refresh = {"rhino-bridge": server_entries(REPO, uv, True)["rhino-bridge"]}
    if not files:
        blocking += 1
        print(
            "  [FALTA] No encontré Claude Desktop. Instálalo desde https://claude.ai/download, "
            "ábrelo una vez y vuelve a ejecutar el instalador."
        )
    for path in files:
        try:
            result = merge_config(path, entries, refresh)
        except (SetupError, OSError) as exc:
            blocking += 1
            print(f"  [FALTA] {exc}")
            continue
        if not result.changed:
            print(f"  [OK] Ya estaba configurado: {path}")
        else:
            print(f"  [OK] Configurado: {path}")
            if result.backup is not None:
                print(f"       (la configuración anterior quedó en {result.backup.name})")

    print("\nOpcionales:")
    try:
        print(f"  {configure_oda()}")
    except Exception as exc:  # ODA es opcional: un fallo aquí no detiene la instalación
        print(f"  [--] No se pudo configurar ODA File Converter: {exc}")
    if rhino:
        print(f"  [OK] Rhino 8: para usarlo, abre en su ScriptEditor el archivo {RHINO_PLUGIN}")
    else:
        print("  [--] Rhino 8 no está instalado: el puente con Rhino no se conecta.")

    try:
        plan = example_project(args.proyectos)
    except OSError as exc:
        print(f"  [--] No se pudo preparar la carpeta de proyectos {args.proyectos}: {exc}")
        plan = EXAMPLE_PLAN
    else:
        print(f"  [OK] Carpeta de proyectos, con un plano de ejemplo: {args.proyectos}")

    if blocking:
        print(f"\nQuedan {blocking} cosa(s) por resolver: revisa las líneas [FALTA] de arriba.")
        return 1
    print(
        "\nListo. Cierra Claude Desktop del todo (clic derecho en su icono junto al reloj → "
        "Salir), ábrelo de nuevo y, en un chat nuevo, escríbele:\n\n"
        f"  Abre el proyecto en {args.proyectos / FIRST_PROJECT} e importa el plano {plan}\n\n"
        "Cuando Claude pida permiso para usar las herramientas de ArchiMind, pulsa Permitir."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
