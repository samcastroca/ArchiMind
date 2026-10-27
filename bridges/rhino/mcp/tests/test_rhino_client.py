"""El cliente del puente: los errores llegan con un mensaje para el usuario."""

import json
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import archimind_bridge as bridge
import pytest
from archimind_rhino_bridge import client
from archimind_rhino_bridge.client import NOT_RUNNING, PLUGIN_SCRIPT, BridgeError, RhinoBridge
from fake_rhino import FakeDocument

TOKEN = "secreto"


@pytest.fixture
def config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    path = tmp_path / "rhino_bridge.json"
    monkeypatch.setenv(client.CONFIG_ENV, str(path))
    return path


@pytest.fixture
def running(config: Path) -> Iterator[bridge.BridgeServer]:
    server = bridge.start(FakeDocument(), lambda fn: fn(), 0, TOKEN)
    _write(config, server.server_address[1], TOKEN)
    yield server
    bridge.stop(server)


def _write(path: Path, port: int, token: str) -> None:
    path.write_text(json.dumps({"port": port, "token": token}), encoding="utf-8")


def test_the_message_names_the_script() -> None:
    assert PLUGIN_SCRIPT.is_file()
    assert NOT_RUNNING == (
        "Rhino no está abierto o el puente no está iniciado; ejecuta "
        f"{PLUGIN_SCRIPT} desde el editor de scripts"
    )


def test_without_config_rhino_is_not_running(config: Path) -> None:
    with pytest.raises(BridgeError) as raised:
        RhinoBridge().call("ping")
    assert str(raised.value) == NOT_RUNNING


def test_a_closed_port_means_rhino_is_not_running(
    running: bridge.BridgeServer, config: Path
) -> None:
    port = running.server_address[1]
    bridge.stop(running)
    _write(config, port, TOKEN)
    with pytest.raises(BridgeError) as raised:
        RhinoBridge().call("ping")
    assert str(raised.value) == NOT_RUNNING


def test_calls_an_operation(running: bridge.BridgeServer) -> None:
    assert RhinoBridge().call("ping")["rhino"] == "8.99 (falso)"


def test_a_wrong_token(running: bridge.BridgeServer, config: Path) -> None:
    _write(config, running.server_address[1], "otro")
    with pytest.raises(BridgeError, match="rechazó el token"):
        RhinoBridge().call("ping")


def test_an_operation_error_keeps_its_message(running: bridge.BridgeServer) -> None:
    running.ops.in_command = True
    with pytest.raises(BridgeError, match="Rhino está ejecutando un comando."):
        RhinoBridge().call("read_tagged_objects")


def test_a_slow_rhino(config: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def slow(fn: Any) -> Any:
        time.sleep(0.5)
        return fn()

    server = bridge.start(FakeDocument(), slow, 0, TOKEN)
    _write(config, server.server_address[1], TOKEN)
    monkeypatch.setattr(client, "TIMEOUT_S", 0.1)
    try:
        with pytest.raises(BridgeError, match="no respondió"):
            RhinoBridge().call("ping")
    finally:
        bridge.stop(server)
