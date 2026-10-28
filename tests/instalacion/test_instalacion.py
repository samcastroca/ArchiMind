"""El instalador: la configuración de Claude Desktop, Rhino, ODA, el proyecto de ejemplo y los
scripts de doble clic. Todo en carpetas temporales: nunca toca la configuración real."""

import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

import ezdxf
import instalacion
import pytest
from ezdxf.addons import odafc
from instalacion import SetupError, merge_config, server_entries

REPO = Path(__file__).resolve().parents[2]
UV = Path("C:/Users/Ana María/.local/bin/uv.exe")
POWERSHELL = shutil.which("powershell")
NOW = datetime(2026, 10, 28, 9, 30, 0)


@pytest.fixture
def claude(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[Path, Path]:
    """Claude Desktop instalado como MSIX y con la carpeta clásica: (msix, clásica)."""
    local, roaming = tmp_path / "Local", tmp_path / "Roaming"
    package = local / "Packages" / "Claude_pzs8sxrjxfjjc"
    package.mkdir(parents=True)
    (roaming / "Claude").mkdir(parents=True)
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    monkeypatch.setenv("APPDATA", str(roaming))
    msix = package / "LocalCache" / "Roaming" / "Claude" / "claude_desktop_config.json"
    return msix, roaming / "Claude" / "claude_desktop_config.json"


def _entries(rhino: bool = False) -> dict[str, Any]:
    return server_entries(Path("C:/Mis documentos/ArchiMind ñ"), UV, rhino)


def _read(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


# --- Dónde está la configuración ----------------------------------------------------------------


def test_both_config_files_are_found_msix_first(claude: tuple[Path, Path]) -> None:
    assert instalacion.claude_config_files() == list(claude)


def test_without_claude_desktop_there_is_nothing_to_configure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    assert instalacion.claude_config_files() == []


# --- Fusión de la configuración -----------------------------------------------------------------


def test_the_entries_run_each_server_with_the_full_path_of_uv() -> None:
    entries = _entries()
    assert set(entries) == {"archimind-core", "archimind-bloques", "archimind-docs"}
    assert entries["archimind-docs"] == {
        "command": str(UV),
        "args": [
            "run",
            "--directory",
            str(Path("C:/Mis documentos/ArchiMind ñ")),
            "--package",
            "archimind-docs",
            "archimind-docs",
        ],
        "env": {"PYTHONUTF8": "1"},
    }
    assert "rhino-bridge" in _entries(rhino=True)


def test_a_missing_file_is_created_without_backup(claude: tuple[Path, Path]) -> None:
    msix, _ = claude
    result = merge_config(msix, _entries(), now=NOW)
    assert result.changed and result.backup is None
    assert _read(msix) == {"mcpServers": _entries()}
    assert not msix.read_bytes().startswith(b"\xef\xbb\xbf")


def test_what_was_there_is_kept_and_backed_up(claude: tuple[Path, Path]) -> None:
    _, classic = claude
    before = {
        "preferences": {"menuBarEnabled": False},
        "mcpServers": {"otro": {"command": "otro.exe", "args": ["--x"]}},
    }
    # El Bloc de notas guarda con BOM.
    classic.write_text(json.dumps(before), encoding="utf-8-sig")
    original = classic.read_bytes()
    result = merge_config(classic, _entries(), now=NOW)

    after = _read(classic)
    assert after["preferences"] == before["preferences"]
    assert list(after["mcpServers"]) == ["otro", *_entries()]
    assert after["mcpServers"]["otro"] == before["mcpServers"]["otro"]
    assert result.backup == classic.with_name(
        "claude_desktop_config.json.antes-de-archimind-20261028-093000"
    )
    assert result.backup.read_bytes() == original


def test_running_it_again_changes_nothing(claude: tuple[Path, Path]) -> None:
    msix, _ = claude
    merge_config(msix, _entries(), now=NOW)
    content = msix.read_bytes()
    again = merge_config(msix, _entries(), now=datetime(2026, 11, 1))
    assert not again.changed and again.backup is None
    assert msix.read_bytes() == content
    assert len(list(msix.parent.iterdir())) == 1  # ni respaldo ni temporales


def test_a_moved_folder_updates_the_paths(claude: tuple[Path, Path]) -> None:
    msix, _ = claude
    merge_config(msix, server_entries(Path("C:/viejo"), UV, False), now=NOW)
    result = merge_config(msix, _entries(), now=NOW)
    assert result.changed and _read(msix)["mcpServers"] == _entries()


def test_an_empty_file_is_filled(claude: tuple[Path, Path]) -> None:
    _, classic = claude
    classic.write_text("  \n", encoding="utf-8")
    result = merge_config(classic, _entries(), now=NOW)
    assert result.backup is None and _read(classic) == {"mcpServers": _entries()}


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ('{"preferences": {"a": 1},}', "línea 1"),
        ('{"mcpServers": []}', "no tiene la forma"),
        ("[1, 2]", "no tiene la forma"),
    ],
)
def test_a_broken_file_is_left_untouched(
    claude: tuple[Path, Path], text: str, message: str
) -> None:
    _, classic = claude
    classic.write_text(text, encoding="utf-8")
    with pytest.raises(SetupError, match=message):
        merge_config(classic, _entries(), now=NOW)
    assert classic.read_text(encoding="utf-8") == text
    assert len(list(classic.parent.iterdir())) == 1


def test_rhino_bridge_is_refreshed_only_if_it_was_there(claude: tuple[Path, Path]) -> None:
    msix, classic = claude
    refresh = {"rhino-bridge": _entries(rhino=True)["rhino-bridge"]}
    merge_config(msix, _entries(), refresh, now=NOW)
    assert "rhino-bridge" not in _read(msix)["mcpServers"]

    old = {"command": "uv", "args": ["run", "--directory", "C:/viejo"], "env": {}}
    classic.write_text(json.dumps({"mcpServers": {"rhino-bridge": old}}), encoding="utf-8")
    merge_config(classic, _entries(), refresh, now=NOW)
    assert _read(classic)["mcpServers"]["rhino-bridge"] == refresh["rhino-bridge"]


# --- Rhino, ODA y el proyecto de ejemplo --------------------------------------------------------


def test_rhino_8_is_found_in_the_registry_or_in_program_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("ProgramFiles", str(tmp_path))
    assert instalacion.rhino_installed(lambda: str(tmp_path))
    assert not instalacion.rhino_installed(lambda: None)
    exe = tmp_path / "Rhino 8" / "System" / "Rhino.exe"
    exe.parent.mkdir(parents=True)
    exe.touch()
    assert instalacion.rhino_installed(lambda: None)


@pytest.fixture
def oda_options(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Any:
    """Las opciones de ezdxf sin ODA y con su ini en una carpeta temporal; al final, como
    estaban."""
    previous = ezdxf.options.get("odafc-addon", "win_exec_path")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("ProgramFiles", str(tmp_path / "Program Files"))
    ezdxf.options.set("odafc-addon", "win_exec_path", str(tmp_path / "no-existe.exe"))
    yield tmp_path
    ezdxf.options.set("odafc-addon", "win_exec_path", previous)


def test_oda_is_configured_with_its_newest_version(oda_options: Path) -> None:
    oda = oda_options / "Program Files" / "ODA"
    for version in ("ODAFileConverter 9.9.0", "ODAFileConverter 25.12.0"):
        (oda / version).mkdir(parents=True)
        (oda / version / "ODAFileConverter.exe").touch()
    newest = oda / "ODAFileConverter 25.12.0" / "ODAFileConverter.exe"

    line = instalacion.configure_oda()
    assert line == f"[OK] ODA File Converter (para DWG) configurado: {newest}"
    assert odafc.get_win_exec_path() == str(newest)
    ini = (oda_options / "config" / "ezdxf" / "ezdxf.ini").read_text(encoding="utf-8")
    assert f"win_exec_path = {newest}" in ini


def test_without_oda_nothing_is_written(oda_options: Path) -> None:
    assert "no está instalado" in instalacion.configure_oda()
    assert not (oda_options / "config").exists()


def test_the_example_plan_is_copied_once(tmp_path: Path) -> None:
    folder = tmp_path / "Proyectos ñ"
    plan = instalacion.example_project(folder)
    assert plan == folder / "ejemplo-apartamento.dxf"
    assert plan.read_bytes() == instalacion.EXAMPLE_PLAN.read_bytes()
    plan.write_text("mío", encoding="utf-8")
    instalacion.example_project(folder)
    assert plan.read_text(encoding="utf-8") == "mío"


# --- El programa entero -------------------------------------------------------------------------


def test_main_configures_claude_and_says_what_to_write(
    claude: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(instalacion, "check_git", lambda: "[OK] git version 2")
    monkeypatch.setattr(instalacion, "configure_oda", lambda: "[--] ODA no está instalado")
    monkeypatch.setattr(instalacion, "rhino_installed", lambda: False)
    projects = tmp_path / "Proyectos"
    assert instalacion.main(["--uv", str(UV), "--proyectos", str(projects)]) == 0

    out = capsys.readouterr().out
    for path in claude:
        assert set(_read(path)["mcpServers"]) == {
            "archimind-core",
            "archimind-bloques",
            "archimind-docs",
        }
        assert f"Configurado: {path}" in out
    plan = projects / "ejemplo-apartamento.dxf"
    assert f"Abre el proyecto en {projects / 'mi-primer-proyecto'} e importa el plano {plan}" in out
    assert "[FALTA]" not in out


def test_main_fails_and_explains_without_claude_desktop(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    monkeypatch.setattr(instalacion, "check_git", lambda: "[OK] git version 2")
    monkeypatch.setattr(instalacion, "configure_oda", lambda: "[--] ODA no está instalado")
    assert instalacion.main(["--uv", str(UV), "--proyectos", str(tmp_path / "p")]) == 1
    out = capsys.readouterr().out
    assert "[FALTA] No encontré Claude Desktop" in out and "claude.ai/download" in out


# --- Los scripts de doble clic ------------------------------------------------------------------


@pytest.mark.parametrize("name", ["Instalar ArchiMind.bat", "Importar datos.bat"])
def test_the_bat_files_are_plain_ascii(name: str) -> None:
    (REPO / name).read_bytes().decode("ascii")


@pytest.mark.parametrize("name", ["instalar.ps1", "importar_datos.ps1"])
def test_the_powershell_scripts_have_a_bom(name: str) -> None:
    # Sin BOM, PowerShell 5.1 lee el archivo como ANSI y rompe los acentos.
    assert (REPO / "scripts" / name).read_bytes().startswith(b"\xef\xbb\xbf")


@pytest.mark.skipif(POWERSHELL is None, reason="hace falta PowerShell")
@pytest.mark.parametrize("name", ["instalar.ps1", "importar_datos.ps1"])
def test_the_powershell_scripts_parse(name: str) -> None:
    path = REPO / "scripts" / name
    command = (
        "$errores = $null; [System.Management.Automation.Language.Parser]::ParseFile("
        f"'{path}', [ref]$null, [ref]$errores) | Out-Null; $errores.Count"
    )
    result = subprocess.run(
        [str(POWERSHELL), "-NoProfile", "-Command", command],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "0"
