"""La parte del script del puente que no depende de Rhino: configuración, HTTP y espera."""

import ast
import json
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import archimind_bridge as bridge
import pytest

TOKEN = "secreto"


class FakeOps:
    def ping(self) -> dict[str, Any]:
        return {"rhino": "8.0"}

    def open_file(self, path: str) -> dict[str, Any]:
        if path == "ocupado.3dm":
            raise bridge.OpError("Rhino tiene cambios sin guardar.")
        return {"path": path}

    def load_model_layers(
        self, project: str, base_sha256: str, base_model: str, objects: list[Any]
    ) -> dict[str, Any]:
        bridge.check_load(project, base_sha256, base_model, objects)
        return {"loaded": len(objects)}

    def read_tagged_objects(self) -> dict[str, Any]:
        raise RuntimeError("se rompió")

    def save_as(self, path: str) -> dict[str, Any]:
        return {"path": path}


@pytest.fixture
def server() -> Iterator[bridge.BridgeServer]:
    running = bridge.start(FakeOps(), lambda fn: fn(), 0, TOKEN)
    yield running
    bridge.stop(running)


def _post(
    server: bridge.BridgeServer, op: str, body: bytes = b"{}", token: str = TOKEN
) -> tuple[int, dict[str, Any]]:
    port = server.server_address[1]
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/{op}",
        data=body,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def test_listens_only_on_localhost(server: bridge.BridgeServer) -> None:
    assert server.server_address[0] == "127.0.0.1"


def test_runs_an_operation(server: bridge.BridgeServer) -> None:
    assert _post(server, "ping") == (200, {"ok": True, "result": {"rhino": "8.0"}})
    body = json.dumps({"path": "C:/a.3dm"}).encode()
    assert _post(server, "save_as", body) == (200, {"ok": True, "result": {"path": "C:/a.3dm"}})


@pytest.mark.parametrize("token", ["", "otro"])
def test_rejects_a_wrong_token(server: bridge.BridgeServer, token: str) -> None:
    status, body = _post(server, "ping", token=token)
    assert status == 401 and body["ok"] is False


def test_rejects_unknown_operations(server: bridge.BridgeServer) -> None:
    status, body = _post(server, "run_script", json.dumps({"code": "print(1)"}).encode())
    assert status == 404 and "desconocida" in body["error"]


def test_only_accepts_post(server: bridge.BridgeServer) -> None:
    port = server.server_address[1]
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/ping", headers={"Authorization": f"Bearer {TOKEN}"}
    )
    with pytest.raises(urllib.error.HTTPError) as raised:
        urllib.request.urlopen(request, timeout=5)
    assert raised.value.code == 405


@pytest.mark.parametrize(
    ("body", "status"),
    [(b"no es json", 400), (b'{"otro": 1}', 400), (b"[1, 2]", 400)],
)
def test_rejects_bad_bodies(server: bridge.BridgeServer, body: bytes, status: int) -> None:
    assert _post(server, "save_as", body)[0] == status


def test_rejects_huge_bodies(server: bridge.BridgeServer, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bridge, "MAX_BODY", 10)
    assert _post(server, "save_as", json.dumps({"path": "x" * 20}).encode())[0] == 413


def test_returns_the_message_of_an_op_error(server: bridge.BridgeServer) -> None:
    status, body = _post(server, "open_file", json.dumps({"path": "ocupado.3dm"}).encode())
    assert (status, body["error"]) == (409, "Rhino tiene cambios sin guardar.")


def test_reports_unexpected_errors(server: bridge.BridgeServer) -> None:
    status, body = _post(server, "read_tagged_objects")
    assert status == 500 and "RuntimeError: se rompió" in body["error"]


def test_validates_the_load_payload(server: bridge.BridgeServer) -> None:
    good = {
        "id": "muro-0001",
        "layer": "Muros",
        "kind": "prism",
        "z0": 0,
        "z1": 2.6,
        "footprint": [[0, 0], [1, 0], [1, 1]],
    }
    args = {"project": "C:/casa", "base_sha256": "a", "base_model": "{}"}
    ok = json.dumps(args | {"objects": [good]}).encode()
    assert _post(server, "load_model_layers", ok) == (200, {"ok": True, "result": {"loaded": 1}})
    for bad in (good | {"layer": "Otra"}, good | {"z1": 0}, good | {"kind": "malla"}):
        body = json.dumps(args | {"objects": [bad]}).encode()
        assert _post(server, "load_model_layers", body)[0] == 400


def test_run_posted_returns_the_result_or_the_error() -> None:
    def post(run: Any) -> None:
        threading.Thread(target=run).start()

    assert bridge.run_posted(post, lambda: 42) == 42
    with pytest.raises(ZeroDivisionError):
        bridge.run_posted(post, lambda: 1 / 0)


def test_run_posted_gives_up_when_the_ui_thread_does_not_answer() -> None:
    with pytest.raises(bridge.OpError) as raised:
        bridge.run_posted(lambda run: None, lambda: 1, timeout=0.05)
    assert raised.value.status == 504


def test_stop_frees_the_port_even_with_a_request_waiting() -> None:
    release = threading.Event()

    def invoke(fn: Any) -> Any:
        release.wait(2)
        return fn()

    running = bridge.start(FakeOps(), invoke, 0, TOKEN)
    port = running.server_address[1]
    threading.Thread(target=lambda: _post(running, "ping"), daemon=True).start()
    time.sleep(0.1)
    started = time.monotonic()
    bridge.stop(running, timeout=0.2)
    assert time.monotonic() - started < 1.5
    release.set()
    again = bridge.start(FakeOps(), lambda fn: fn(), port, TOKEN)
    bridge.stop(again)


def test_creates_the_config_once(tmp_path: Path) -> None:
    path = tmp_path / "sub" / "rhino_bridge.json"
    port, token = bridge.load_or_create_config(path)
    assert port == bridge.DEFAULT_PORT and len(token) >= 32
    assert bridge.load_or_create_config(path) == (port, token)
    path.write_text(json.dumps({"port": 5000, "token": "t"}), encoding="utf-8")
    assert bridge.load_or_create_config(path) == (5000, "t")


def test_config_path_follows_the_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(bridge.CONFIG_ENV, str(tmp_path / "c.json"))
    assert bridge.config_path() == tmp_path / "c.json"


def test_scales_points() -> None:
    assert bridge.scale_points([[1, 2, 3]], 1000) == [[1000, 2000, 3000]]


def test_imports_without_rhino() -> None:
    assert bridge.Rhino is None


def test_is_python_39() -> None:
    """Rhino 8 corre CPython 3.9: la sintaxis no puede ser más nueva."""
    ast.parse(Path(bridge.__file__).read_text(encoding="utf-8"), feature_version=(3, 9))
