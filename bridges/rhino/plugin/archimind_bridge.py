#! python3
"""Puente de ArchiMind dentro de Rhino 8: un servidor HTTP local que el servidor MCP
`rhino-bridge` llama para abrir, cargar, leer y guardar el documento.

Se ejecuta desde el editor de scripts de Rhino 8 (comando ScriptEditor → Abrir este archivo →
Ejecutar). Volver a ejecutarlo reinicia el puente con el código nuevo.

- Escucha solo en 127.0.0.1, en el puerto del archivo de configuración
  (`~/.archimind/rhino_bridge.json`, o la ruta de la variable ARCHIMIND_RHINO_BRIDGE). Si el
  archivo no existe, lo crea con un token aleatorio; el servidor MCP lee el mismo archivo.
- Toda petición lleva `Authorization: Bearer <token>`. Solo hay cinco operaciones fijas (OPS):
  nada ejecuta código arbitrario.
- El servidor corre en un hilo secundario; toda operación sobre el documento se ejecuta en el
  hilo de la interfaz con `RhinoApp.InvokeOnUiThread`, porque RhinoDoc no es seguro entre hilos.
- Las coordenadas viajan en metros; se convierten a las unidades del documento al cargar y al
  leer.

Es Python 3.9 (el CPython de Rhino 8) y solo usa la biblioteca estándar y RhinoCommon. La primera
mitad no depende de Rhino y se prueba fuera de él; la segunda es la envoltura de RhinoCommon.
"""

from __future__ import annotations

import hmac
import inspect
import json
import os
import secrets
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Callable

HOST = "127.0.0.1"
DEFAULT_PORT = 48765
CONFIG_ENV = "ARCHIMIND_RHINO_BRIDGE"
OPS = ("ping", "open_file", "load_model_layers", "read_tagged_objects", "save_as")
MAX_BODY = 32 * 1024 * 1024
UI_TIMEOUT_S = 60.0

ROOT_LAYER = "ArchiMind"
# Subcapa → color de la capa (solo para verla en Rhino).
SUBLAYERS = {"Muros": (60, 90, 160), "Vanos": (230, 140, 40), "Espacios": (200, 200, 170)}
ID_KEY = "archimind_id"
# Texto del documento: de qué proyecto son las capas y el modelo.json tal como se cargó.
DOC_PROJECT = "archimind_proyecto"
DOC_SHA = "archimind_base_sha256"
DOC_BASE = "archimind_base"
STICKY_KEY = "archimind_bridge_server"

Invoke = Callable[[Callable[[], Any]], Any]


class OpError(Exception):
    """Una operación que no se puede hacer; el mensaje está pensado para el usuario final."""

    def __init__(self, message: str, status: int = 409) -> None:
        super().__init__(message)
        self.status = status


# --- Configuración ----------------------------------------------------------------------------


def config_path() -> Path:
    custom = os.environ.get(CONFIG_ENV)
    return Path(custom) if custom else Path.home() / ".archimind" / "rhino_bridge.json"


def load_or_create_config(path: Path | None = None) -> tuple[int, str]:
    """El puerto y el token del archivo; si no existe, lo crea con un token nuevo."""
    path = path or config_path()
    if path.is_file():
        data = json.loads(path.read_text(encoding="utf-8"))
        return int(data.get("port", DEFAULT_PORT)), str(data["token"])
    token = secrets.token_urlsafe(32)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"port": DEFAULT_PORT, "token": token}, indent=2), encoding="utf-8")
    return DEFAULT_PORT, token


# --- Servidor HTTP ----------------------------------------------------------------------------


class BridgeServer(HTTPServer):
    # En Windows, SO_REUSEADDR deja que otro proceso se adueñe del mismo puerto.
    allow_reuse_address = False

    def __init__(self, port: int, token: str, ops: Any, invoke: Invoke) -> None:
        super().__init__((HOST, port), _Handler)
        self.token = token
        self.ops = ops
        self.invoke = invoke


class _Handler(BaseHTTPRequestHandler):
    server: BridgeServer

    def do_POST(self) -> None:  # noqa: N802 (nombre de http.server)
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            self._reply(413, error="La petición es demasiado grande.")
            return
        # Se lee siempre: en Windows, responder sin leer el cuerpo corta la conexión.
        body = self.rfile.read(length)
        if not self._authorized():
            self._reply(401, error="Token del puente incorrecto.")
            return
        op = self.path.strip("/")
        if op not in OPS:
            self._reply(404, error=f"Operación desconocida: {op}.")
            return
        try:
            args = json.loads(body or b"{}")
        except ValueError:
            self._reply(400, error="El cuerpo de la petición no es JSON.")
            return
        method = getattr(self.server.ops, op)
        try:
            inspect.signature(method).bind(**args)
        except TypeError:
            self._reply(400, error=f"Argumentos no válidos para {op}.")
            return
        try:
            result = self.server.invoke(lambda: method(**args))
        except OpError as exc:
            self._reply(exc.status, error=str(exc))
        except Exception as exc:  # noqa: BLE001 (todo error vuelve al cliente)
            self._reply(500, error=f"Error interno del puente: {type(exc).__name__}: {exc}")
        else:
            self._reply(200, result=result)

    def do_GET(self) -> None:  # noqa: N802
        self._reply(405, error="Solo se admite POST.")

    do_PUT = do_DELETE = do_PATCH = do_GET  # noqa: N815

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        """Sin registro por petición: la terminal de Rhino es del usuario."""

    def _authorized(self) -> bool:
        header = self.headers.get("Authorization", "")
        expected = f"Bearer {self.server.token}"
        return hmac.compare_digest(header.encode("utf-8"), expected.encode("utf-8"))

    def _reply(self, status: int, result: Any = None, error: str | None = None) -> None:
        body = {"ok": True, "result": result} if error is None else {"ok": False, "error": error}
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def start(ops: Any, invoke: Invoke, port: int, token: str) -> BridgeServer:
    """Arranca el servidor en un hilo daemon; con el puerto 0, el sistema elige uno libre."""
    server = BridgeServer(port, token, ops, invoke)
    thread = threading.Thread(target=server.serve_forever, name="archimind-bridge", daemon=True)
    thread.start()
    return server


def stop(server: BridgeServer, timeout: float = 5.0) -> None:
    """Apaga desde otro hilo: si una petición espera al hilo de la interfaz y quien apaga es ese
    hilo, `shutdown` se bloquearía hasta agotar la espera."""
    stopper = threading.Thread(target=server.shutdown, daemon=True)
    stopper.start()
    stopper.join(timeout)
    server.server_close()


def run_posted(
    post: Callable[[Callable[[], None]], Any], fn: Callable[[], Any], timeout: float = UI_TIMEOUT_S
) -> Any:
    """Entrega `fn` a `post` (que la ejecuta en otro hilo) y espera su resultado o su error."""
    done = threading.Event()
    box: dict[str, Any] = {}

    def run() -> None:
        try:
            box["result"] = fn()
        except BaseException as exc:  # noqa: BLE001 (se relanza en el hilo que espera)
            box["error"] = exc
        finally:
            done.set()

    post(run)
    if not done.wait(timeout):
        raise OpError(
            f"Rhino no respondió en {timeout:.0f} s: puede tener un cuadro de diálogo abierto. "
            "Ciérralo y vuelve a intentarlo.",
            status=504,
        )
    if "error" in box:
        raise box["error"]
    return box["result"]


# --- Datos ------------------------------------------------------------------------------------


def scale_points(points: list[list[float]], k: float) -> list[list[float]]:
    return [[c * k for c in point] for point in points]


def check_load(project: Any, base_sha256: Any, base_model: Any, objects: Any) -> None:
    """Valida la carga de `load_model_layers` antes de tocar el documento."""
    if not isinstance(project, str) or not project:
        raise OpError("Falta la carpeta del proyecto.", status=400)
    if not isinstance(base_sha256, str) or not isinstance(base_model, str):
        raise OpError("Falta el modelo base.", status=400)
    if not isinstance(objects, list):
        raise OpError("objects debe ser una lista.", status=400)
    for item in objects:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise OpError("Cada objeto necesita un id.", status=400)
        if not isinstance(item.get("name", ""), str):
            raise OpError(f"{item['id']}: el nombre debe ser texto.", status=400)
        if item.get("layer") not in SUBLAYERS:
            raise OpError(f"{item['id']}: capa desconocida {item.get('layer')}.", status=400)
        kind = item.get("kind")
        if kind == "prism":
            z0, z1 = item.get("z0"), item.get("z1")
            numbers = isinstance(z0, (int, float)) and isinstance(z1, (int, float))
            if len(item.get("footprint") or []) < 3 or not (numbers and z1 > z0):
                raise OpError(f"{item['id']}: prisma sin huella o sin alto.", status=400)
        elif kind == "surface":
            if len(item.get("exterior") or []) < 3 or "z" not in item:
                raise OpError(f"{item['id']}: superficie sin contorno.", status=400)
        else:
            raise OpError(f"{item['id']}: tipo de objeto desconocido {kind}.", status=400)


# --- RhinoCommon ------------------------------------------------------------------------------

try:
    import Rhino
    import scriptcontext
    import System
except ImportError:  # fuera de Rhino (pruebas): solo la parte de arriba se usa
    Rhino = None


def invoke_on_ui(fn: Callable[[], Any]) -> Any:
    return run_posted(lambda run: Rhino.RhinoApp.InvokeOnUiThread(System.Action(run)), fn)


class RhinoOps:
    """Las cinco operaciones; corren en el hilo de la interfaz. Usan siempre
    `RhinoDoc.ActiveDoc`: `scriptcontext.doc` queda fijo al documento de cuando corrió el
    script."""

    def ping(self) -> dict[str, Any]:
        doc = Rhino.RhinoDoc.ActiveDoc
        info: dict[str, Any] = {
            "rhino": str(Rhino.RhinoApp.Version),
            "in_command": bool(Rhino.Commands.Command.InCommand()),
            "document": None,
            "archimind": None,
        }
        if doc is None:
            return info
        info["document"] = _document_info(doc)
        counts = dict.fromkeys(SUBLAYERS, 0)
        for _, tag, layer in _archimind_objects(doc):
            name = layer.split("::")[-1]
            if tag and layer == f"{ROOT_LAYER}::{name}" and name in counts:
                counts[name] += 1
        info["archimind"] = {
            "project": doc.Strings.GetValue(DOC_PROJECT) or None,
            "base_sha256": doc.Strings.GetValue(DOC_SHA) or None,
            "objects": counts,
        }
        return info

    def open_file(self, path: str) -> dict[str, Any]:
        _idle()
        if not path.lower().endswith(".3dm") or not os.path.isfile(path):
            raise OpError(f"No existe el archivo .3dm {path}.", status=400)
        doc = Rhino.RhinoDoc.ActiveDoc
        if doc is not None and doc.Path and _same_path(doc.Path, path):
            return {"opened": False, "document": _document_info(doc)}
        if doc is not None and doc.Modified:
            raise OpError(
                f"El documento abierto en Rhino ({doc.Name or 'sin título'}) tiene cambios sin "
                "guardar: guárdalo o descártalo antes de abrir el proyecto."
            )
        # El parámetro out (wasAlreadyOpen) vuelve en una tupla.
        result = Rhino.RhinoDoc.Open(path)
        opened = result[0] if isinstance(result, tuple) else result
        if opened is None:
            raise OpError(f"Rhino no pudo abrir {path}.")
        return {"opened": True, "document": _document_info(opened)}

    def load_model_layers(
        self, project: str, base_sha256: str, base_model: str, objects: list[dict[str, Any]]
    ) -> dict[str, Any]:
        _idle()
        check_load(project, base_sha256, base_model, objects)
        doc = _active_doc()
        k = Rhino.RhinoMath.UnitScale(Rhino.UnitSystem.Meters, doc.ModelUnitSystem)
        tol = doc.ModelAbsoluteTolerance
        undo = doc.BeginUndoRecord("ArchiMind: cargar el modelo")
        try:
            layers = _ensure_layers(doc)
            for obj, _, _ in list(_archimind_objects(doc)):
                doc.Objects.Delete(obj, True, True)
            counts = dict.fromkeys(SUBLAYERS, 0)
            for item in objects:
                attributes = Rhino.DocObjects.ObjectAttributes()
                attributes.LayerIndex = layers[item["layer"]]
                attributes.Name = item.get("name") or item["id"]
                attributes.SetUserString(ID_KEY, item["id"])
                if item["kind"] == "prism":
                    guid = doc.Objects.AddExtrusion(_extrusion(item, k, tol), attributes)
                else:
                    guid = doc.Objects.AddBrep(_planar_brep(item, k, tol), attributes)
                if guid == System.Guid.Empty:
                    raise OpError(f"Rhino no pudo agregar {item['id']}.")
                counts[item["layer"]] += 1
            doc.Strings.SetString(DOC_PROJECT, project)
            doc.Strings.SetString(DOC_SHA, base_sha256)
            doc.Strings.SetString(DOC_BASE, base_model)
        finally:
            doc.EndUndoRecord(undo)
        doc.Views.Redraw()
        return {"loaded": counts}

    def read_tagged_objects(self) -> dict[str, Any]:
        _idle()
        doc = _active_doc()
        k = Rhino.RhinoMath.UnitScale(doc.ModelUnitSystem, Rhino.UnitSystem.Meters)
        objects = [
            {
                "id": tag or None,
                "name": obj.Attributes.Name or None,
                "layer": layer,
                "type": str(obj.ObjectType),
                "faces": _faces(obj.Geometry, k),
            }
            for obj, tag, layer in _archimind_objects(doc)
        ]
        return {
            "project": doc.Strings.GetValue(DOC_PROJECT) or None,
            "base_sha256": doc.Strings.GetValue(DOC_SHA) or None,
            "base_model": doc.Strings.GetValue(DOC_BASE) or None,
            "objects": objects,
        }

    def save_as(self, path: str) -> dict[str, Any]:
        _idle()
        if not path.lower().endswith(".3dm"):
            raise OpError(f"Solo se guarda en .3dm, no en {path}.", status=400)
        if not _active_doc().SaveAs(path):
            raise OpError(f"Rhino no pudo guardar {path}.")
        return {"path": path}


def _active_doc() -> Any:
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is None:
        raise OpError("Rhino no tiene ningún documento abierto.")
    return doc


def _idle() -> None:
    if Rhino.Commands.Command.InCommand():
        raise OpError(
            "Rhino está ejecutando un comando: termínalo o cancélalo (Esc) y vuelve a intentarlo."
        )


def _same_path(a: str, b: str) -> bool:
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def _document_info(doc: Any) -> dict[str, Any]:
    return {
        "path": doc.Path or None,
        "name": doc.Name or None,
        "modified": bool(doc.Modified),
        "units": str(doc.ModelUnitSystem),
    }


def _archimind_objects(doc: Any) -> Any:
    """(objeto, archimind_id, capa) de los objetos con ID en cualquier capa y de todos los de las
    subcapas de ArchiMind, ocultos y bloqueados incluidos."""
    sublayers = {f"{ROOT_LAYER}::{name}" for name in SUBLAYERS}
    settings = Rhino.DocObjects.ObjectEnumeratorSettings()
    settings.HiddenObjects = True
    settings.LockedObjects = True
    settings.IncludeLights = False
    settings.IncludeGrips = False
    for obj in doc.Objects.GetObjectList(settings):
        tag = obj.Attributes.GetUserString(ID_KEY)
        layer = doc.Layers[obj.Attributes.LayerIndex].FullPath
        if tag or layer in sublayers:
            yield obj, tag, layer


def _ensure_layers(doc: Any) -> dict[str, int]:
    """Crea ArchiMind y sus subcapas si faltan, visibles y sin bloquear; devuelve sus índices."""
    root = _ensure_layer(doc, ROOT_LAYER, None, (0, 0, 0))
    root_id = doc.Layers[root].Id
    return {
        name: _ensure_layer(doc, f"{ROOT_LAYER}::{name}", root_id, color)
        for name, color in SUBLAYERS.items()
    }


def _ensure_layer(doc: Any, full_path: str, parent_id: Any, color: tuple[int, int, int]) -> int:
    index = doc.Layers.FindByFullPath(full_path, -1)
    if index < 0:
        layer = Rhino.DocObjects.Layer()
        layer.Name = full_path.split("::")[-1]
        layer.Color = System.Drawing.Color.FromArgb(*color)
        if parent_id is not None:
            layer.ParentLayerId = parent_id
        index = doc.Layers.Add(layer)
        if index < 0:
            raise OpError(f"Rhino no pudo crear la capa {full_path}.")
    layer = doc.Layers[index]
    if not layer.IsVisible or layer.IsLocked:
        layer.IsVisible = True
        layer.IsLocked = False
        layer.CommitChanges()
    return int(index)


def _polyline_curve(points: list[list[float]], z: float, k: float) -> Any:
    vertices = System.Collections.Generic.List[Rhino.Geometry.Point3d]()
    for x, y in [*points, points[0]]:
        vertices.Add(Rhino.Geometry.Point3d(x * k, y * k, z * k))
    return Rhino.Geometry.PolylineCurve(vertices)


def _extrusion(item: dict[str, Any], k: float, tol: float) -> Any:
    """La huella extruida de z0 a z1. El sentido del alto depende del plano de la curva: si quedó
    hacia abajo, se invierte."""
    curve = _polyline_curve(item["footprint"], item["z0"], k)
    height = (item["z1"] - item["z0"]) * k
    extrusion = Rhino.Geometry.Extrusion.Create(curve, height, True)
    if extrusion is not None and extrusion.GetBoundingBox(True).Min.Z < item["z0"] * k - tol:
        extrusion = Rhino.Geometry.Extrusion.Create(curve, -height, True)
    if extrusion is None:
        raise OpError(f"Rhino no pudo extruir {item['id']}.")
    return extrusion


def _planar_brep(item: dict[str, Any], k: float, tol: float) -> Any:
    curves = System.Collections.Generic.List[Rhino.Geometry.Curve]()
    for loop in [item["exterior"], *item.get("holes", [])]:
        curves.Add(_polyline_curve(loop, item["z"], k))
    breps = Rhino.Geometry.Brep.CreatePlanarBreps(curves, tol)
    if breps is None or len(breps) != 1:
        raise OpError(f"Rhino no pudo crear la superficie de {item['id']}.")
    return breps[0]


def _faces(geometry: Any, k: float) -> list[list[list[list[float]]]] | None:
    """Las caras planas como bucles de puntos en metros, el exterior primero; None si el objeto
    no es una extrusión o un Brep de caras poligonales."""
    if isinstance(geometry, Rhino.Geometry.Extrusion):
        brep = geometry.ToBrep(True)  # True: una cara por tramo, no una cara con quiebres
    elif isinstance(geometry, Rhino.Geometry.Brep):
        brep = geometry
    else:
        return None
    faces = []
    for face in brep.Faces:
        loops: list[list[list[float]]] = []
        for loop in face.Loops:
            ok, polyline = loop.To3dCurve().TryGetPolyline()
            if not ok:
                return None
            points = scale_points([[p.X, p.Y, p.Z] for p in polyline], k)
            if loop.LoopType == Rhino.Geometry.BrepLoopType.Outer:
                loops.insert(0, points)
            else:
                loops.append(points)
        faces.append(loops)
    return faces


def main() -> None:
    previous = scriptcontext.sticky.get(STICKY_KEY)
    if previous is not None:
        stop(previous)
    port, token = load_or_create_config()
    try:
        server = start(RhinoOps(), invoke_on_ui, port, token)
    except OSError as exc:
        print(f"No se pudo abrir el puerto {port} ({exc}). Cambia «port» en {config_path()}.")
        return
    scriptcontext.sticky[STICKY_KEY] = server
    print(f"Puente ArchiMind activo en {HOST}:{port} (configuración en {config_path()}).")
    print("Volver a ejecutar este script lo reinicia; se detiene al cerrar Rhino.")


if __name__ == "__main__":
    main()
