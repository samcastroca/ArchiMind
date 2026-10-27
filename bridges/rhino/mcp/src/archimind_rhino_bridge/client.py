"""Cliente del puente que corre dentro de Rhino (`bridges/rhino/plugin/archimind_bridge.py`).

El puente escucha en 127.0.0.1 con el puerto y el token de un archivo de configuración que él
mismo crea; este cliente lee ese archivo en cada llamada, así sigue funcionando si se reinicia el
puente.
"""

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

CONFIG_ENV = "ARCHIMIND_RHINO_BRIDGE"
HOST = "127.0.0.1"
# El puente espera hasta 60 s al hilo de la interfaz de Rhino; aquí se deja margen.
TIMEOUT_S = 90.0
# Válida en el workspace: el script vive junto a este paquete, en bridges/rhino/plugin/.
PLUGIN_SCRIPT = Path(__file__).resolve().parents[3] / "plugin" / "archimind_bridge.py"
NOT_RUNNING = (
    "Rhino no está abierto o el puente no está iniciado; ejecuta "
    f"{PLUGIN_SCRIPT} desde el editor de scripts"
)


class BridgeError(Exception):
    """El puente no responde o rechazó la operación; el mensaje está pensado para el usuario."""


def config_path() -> Path:
    custom = os.environ.get(CONFIG_ENV)
    return Path(custom) if custom else Path.home() / ".archimind" / "rhino_bridge.json"


class RhinoBridge:
    def call(self, op: str, **args: Any) -> Any:
        """Ejecuta una operación del puente y devuelve su resultado."""
        port, token = _read_config()
        request = urllib.request.Request(
            f"http://{HOST}:{port}/{op}",
            data=json.dumps(args).encode("utf-8"),
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
                return json.loads(response.read())["result"]
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                raise BridgeError(
                    "El puente de Rhino rechazó el token: vuelve a ejecutar "
                    f"{PLUGIN_SCRIPT} desde el editor de scripts."
                ) from exc
            raise BridgeError(_error_message(exc)) from exc
        except TimeoutError as exc:
            raise BridgeError(_timeout_message()) from exc
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, TimeoutError):
                raise BridgeError(_timeout_message()) from exc
            raise BridgeError(NOT_RUNNING) from exc
        except ConnectionError as exc:
            raise BridgeError(NOT_RUNNING) from exc


def _read_config() -> tuple[int, str]:
    try:
        data = json.loads(config_path().read_text(encoding="utf-8"))
        return int(data["port"]), str(data["token"])
    except (OSError, ValueError, KeyError) as exc:
        raise BridgeError(NOT_RUNNING) from exc


def _error_message(exc: urllib.error.HTTPError) -> str:
    try:
        return str(json.loads(exc.read())["error"])
    except (ValueError, KeyError):
        return f"El puente de Rhino respondió con el error HTTP {exc.code}."


def _timeout_message() -> str:
    return (
        f"Rhino no respondió en {TIMEOUT_S:.0f} s: puede tener un cuadro de diálogo abierto. "
        "Ciérralo y vuelve a intentarlo."
    )
