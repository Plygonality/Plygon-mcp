from __future__ import annotations

import ast
import errno
import importlib.util
import json
import socket
import sys
import threading
import time
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LISTENER_PATH = ROOT / "editor" / "plygon_unreal_mcp" / "listener.py"


class FakeVector:
    def __init__(self, x=0.0, y=0.0, z=0.0):
        self.x = float(x)
        self.y = float(y)
        self.z = float(z)


class FakeRotator:
    def __init__(self, pitch=0.0, yaw=0.0, roll=0.0):
        self.pitch = float(pitch)
        self.yaw = float(yaw)
        self.roll = float(roll)


class FakeMeshComponent:
    def __init__(self):
        self.mesh = None

    def set_static_mesh(self, mesh):
        self.mesh = mesh
        return True


class FakeGraph:
    def get_path_name(self):
        return "/Game/PCG/DemoGraph"


class FakePCGComponent:
    def __init__(self):
        self.graph_instance = object()
        self.generated = None
        self.graph = FakeGraph()

    def get_graph(self):
        return self.graph

    def generate(self, force):
        self.generated = bool(force)


class FakeActor:
    def __init__(self, label, class_name, components=None):
        self.label = label
        self.class_name = class_name
        self.location = FakeVector()
        self.rotation = FakeRotator()
        self.scale = FakeVector(1, 1, 1)
        self.components = list(components or [])

    def get_actor_label(self):
        return self.label

    def set_actor_label(self, new_actor_label, mark_dirty=True):
        del mark_dirty
        self.label = new_actor_label

    def get_name(self):
        return self.label

    def get_path_name(self):
        return f"/Game/Maps/Test.Test:{self.label}"

    def get_class(self):
        return types.SimpleNamespace(get_name=lambda: self.class_name)

    def get_actor_location(self):
        return self.location

    def set_actor_location(self, new_location, sweep, teleport):
        del sweep, teleport
        self.location = new_location
        return True

    def get_actor_rotation(self):
        return self.rotation

    def set_actor_rotation(self, new_rotation, teleport_physics):
        del teleport_physics
        self.rotation = new_rotation
        return True

    def get_actor_scale3d(self):
        return self.scale

    def set_actor_scale3d(self, new_scale3d):
        self.scale = new_scale3d

    def get_components_by_class(self, component_class):
        return [component for component in self.components if isinstance(component, component_class)]

    @property
    def static_mesh_component(self):
        for component in self.components:
            if isinstance(component, FakeMeshComponent):
                return component
        return None


class FakeActors:
    def __init__(self):
        self.actors = []
        self.selected = []

    def get_all_level_actors(self):
        return list(self.actors)

    def get_selected_level_actors(self):
        return list(self.selected)

    def set_selected_level_actors(self, actors_to_select):
        self.selected = list(actors_to_select)

    def spawn_actor_from_class(self, actor_class, location, rotation, transient=False):
        del transient
        label = actor_class.__name__
        components = []
        if actor_class.__name__ == "StaticMeshActor":
            components.append(FakeMeshComponent())
        actor = FakeActor(label, actor_class.__name__, components)
        actor.location = location
        actor.rotation = rotation
        self.actors.append(actor)
        self.selected = [actor]
        return actor

    def destroy_actor(self, actor_to_destroy):
        self.actors = [actor for actor in self.actors if actor is not actor_to_destroy]
        self.selected = [actor for actor in self.selected if actor is not actor_to_destroy]
        return True


class FakeWorld:
    def get_path_name(self):
        return "/Game/Maps/Test"


class FakeEditor:
    def get_editor_world(self):
        return FakeWorld()


class FakeAssetImportTask:
    def __init__(self):
        self.filename = ""
        self.destination_path = ""
        self.destination_name = ""
        self.automated = False
        self.save = False
        self.replace_existing = False
        self.imported_object_paths = []


class FakeAssetTools:
    def __init__(self, unreal_module):
        self.unreal = unreal_module

    def import_asset_tasks(self, tasks):
        for task in tasks:
            task.imported_object_paths = [f"{task.destination_path}/Imported"]
            self.unreal.imported.append(task.filename)


def build_unreal():
    unreal = types.ModuleType("unreal")
    unreal.transactions = []
    unreal.imported = []
    unreal.parameter_calls = []
    unreal.screenshot_calls = []
    unreal.write_screenshot = False
    unreal.engine_version = "5.9.0-0+UE5"
    unreal.slate_callbacks = []
    unreal.shutdown_callbacks = []
    unreal.unregistered_slate = []
    unreal.unregistered_shutdown = []
    unreal.loaded = {"/Engine/BasicShapes/Cube": object()}
    unreal.assets = ["/Game/Meshes/Chair"]

    class ScopedEditorTransaction:
        def __init__(self, description):
            unreal.transactions.append(description)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            del exc_type, exc, tb
            return False

    class SystemLibrary:
        @staticmethod
        def get_engine_version():
            return unreal.engine_version

    class EditorAssetLibrary:
        @staticmethod
        def list_assets(directory_path, recursive=True, include_folder=False):
            del directory_path, recursive, include_folder
            return list(unreal.assets)

        @staticmethod
        def load_asset(asset_path):
            return unreal.loaded.get(asset_path)

    class AssetToolsHelpers:
        @staticmethod
        def get_asset_tools():
            return FakeAssetTools(unreal)

    class AutomationLibrary:
        @staticmethod
        def take_high_res_screenshot(res_x, res_y, filename, force_game_view=True):
            unreal.screenshot_calls.append(
                {
                    "res_x": res_x,
                    "res_y": res_y,
                    "filename": filename,
                    "force_game_view": force_game_view,
                }
            )
            if unreal.write_screenshot:
                Path(filename).write_bytes(b"\x89PNG\r\n")
            return object()

    class PCGGraphParametersHelpers:
        @staticmethod
        def set_float_parameter(graph_instance, name, value):
            unreal.parameter_calls.append(("float", graph_instance, name, value))

        @staticmethod
        def set_int32_parameter(graph_instance, name, value):
            unreal.parameter_calls.append(("int", graph_instance, name, value))

        @staticmethod
        def set_bool_parameter(graph_instance, name, value):
            unreal.parameter_calls.append(("bool", graph_instance, name, value))

        @staticmethod
        def set_string_parameter(graph_instance, name, value):
            unreal.parameter_calls.append(("string", graph_instance, name, value))

        @staticmethod
        def set_vector_parameter(graph_instance, name, value):
            unreal.parameter_calls.append(("vector", graph_instance, name, value))

    unreal.Vector = FakeVector
    unreal.Rotator = FakeRotator
    unreal.ScopedEditorTransaction = ScopedEditorTransaction
    unreal.SystemLibrary = SystemLibrary
    unreal.EditorAssetLibrary = EditorAssetLibrary
    unreal.AssetToolsHelpers = AssetToolsHelpers
    unreal.AssetImportTask = FakeAssetImportTask
    unreal.AutomationLibrary = AutomationLibrary
    unreal.PCGGraphParametersHelpers = PCGGraphParametersHelpers
    unreal.StaticMeshActor = type("StaticMeshActor", (), {})
    unreal.PointLight = type("PointLight", (), {})
    unreal.DirectionalLight = type("DirectionalLight", (), {})
    unreal.SpotLight = type("SpotLight", (), {})
    unreal.CameraActor = type("CameraActor", (), {})
    unreal.CineCameraActor = type("CineCameraActor", (), {})
    unreal.StaticMeshComponent = FakeMeshComponent
    unreal.PCGComponent = FakePCGComponent
    unreal.UnrealEditorSubsystem = type("UnrealEditorSubsystem", (), {})
    unreal.EditorActorSubsystem = type("EditorActorSubsystem", (), {})
    unreal.actors = FakeActors()
    unreal.editor = FakeEditor()
    unreal.is_editor = lambda: True

    def get_editor_subsystem(subsystem):
        if getattr(subsystem, "__name__", "") == "UnrealEditorSubsystem":
            return unreal.editor
        if getattr(subsystem, "__name__", "") == "EditorActorSubsystem":
            return unreal.actors
        return None

    def register_slate_post_tick_callback(callback):
        unreal.slate_callbacks.append(callback)
        return ("slate", len(unreal.slate_callbacks))

    def unregister_slate_post_tick_callback(handle):
        unreal.unregistered_slate.append(handle)

    def register_python_shutdown_callback(callback):
        unreal.shutdown_callbacks.append(callback)
        return ("shutdown", len(unreal.shutdown_callbacks))

    def unregister_python_shutdown_callback(handle):
        unreal.unregistered_shutdown.append(handle)

    unreal.get_editor_subsystem = get_editor_subsystem
    unreal.register_slate_post_tick_callback = register_slate_post_tick_callback
    unreal.unregister_slate_post_tick_callback = unregister_slate_post_tick_callback
    unreal.register_python_shutdown_callback = register_python_shutdown_callback
    unreal.unregister_python_shutdown_callback = unregister_python_shutdown_callback
    return unreal


def load_listener(monkeypatch, unreal_module=None):
    unreal_module = unreal_module or build_unreal()
    monkeypatch.setitem(sys.modules, "unreal", unreal_module)
    module_name = "plygon_unreal_listener_under_test"
    spec = importlib.util.spec_from_file_location(module_name, LISTENER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, module_name, module)
    spec.loader.exec_module(module)
    return module, unreal_module


class _ProbeSocket:
    def __init__(self, bind_error=None):
        self.events = []
        self.bind_error = bind_error

    def setsockopt(self, level, option, value):
        self.events.append(("setsockopt", level, option, value))

    def bind(self, address):
        self.events.append(("bind", address))
        if self.bind_error is not None:
            raise self.bind_error

    def listen(self, backlog):
        self.events.append(("listen", backlog))
        raise RuntimeError("stop-after-configure")

    def close(self):
        self.events.append(("close",))


def _windows_addr_in_use():
    exc = OSError(
        0,
        "Only one usage of each socket address (protocol/network address/port) is normally permitted",
    )
    exc.winerror = 10048
    return exc


def _function_ast(path: Path, name: str) -> str:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.dump(node, include_attributes=False)
    raise AssertionError(f"{name} missing from {path}")


_EXCLUSIVE_SENTINEL = 45123
_SHARED_BIND_HELPERS = (
    "_configure_listener_socket",
    "_address_in_use",
    "_report_start_failure",
)


def test_listener_socket_policy_matches_blender():
    blender = ROOT.parent / "blender-mcp" / "addon" / "blender_mcp_addon.py"
    for name in _SHARED_BIND_HELPERS:
        assert _function_ast(LISTENER_PATH, name) == _function_ast(blender, name)


@pytest.mark.parametrize("host", ["", "localhost", "::1"])
def test_listener_coerces_loopback_aliases_to_ipv4(monkeypatch, host):
    listener, _unreal = load_listener(monkeypatch)
    assert listener.UnrealMCPServer(host=host).host == "127.0.0.1"


def test_listener_refuses_non_loopback_bind(monkeypatch, capsys):
    listener, _unreal = load_listener(monkeypatch)
    server = listener.UnrealMCPServer(host="10.0.0.5", port=9879)
    assert server.start() is False
    assert server.socket is None
    assert "refusing to bind 10.0.0.5" in capsys.readouterr().out


def test_listener_rejects_old_engine(monkeypatch, capsys):
    listener, unreal_module = load_listener(monkeypatch)
    unreal_module.engine_version = "5.3.2-0+UE5"
    server = listener.UnrealMCPServer()
    assert server.start() is False
    assert "5.4 or newer" in capsys.readouterr().out


def test_listener_rejects_commandlet(monkeypatch, capsys):
    listener, unreal_module = load_listener(monkeypatch)
    unreal_module.is_editor = lambda: False
    assert listener.UnrealMCPServer().start() is False
    assert "outside the Unreal Editor" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("platform_name", "exclusive"),
    [("win32", True), ("linux", False), ("darwin", False)],
)
def test_listener_socket_option_follows_platform(monkeypatch, platform_name, exclusive):
    listener, _unreal = load_listener(monkeypatch)
    monkeypatch.setattr(listener.sys, "platform", platform_name)
    if exclusive:
        monkeypatch.setattr(
            listener.socket, "SO_EXCLUSIVEADDRUSE", _EXCLUSIVE_SENTINEL, raising=False
        )
    probe = _ProbeSocket()
    monkeypatch.setattr(listener.socket, "socket", lambda *args, **kwargs: probe)
    server = listener.UnrealMCPServer()

    assert server.start() is False
    assert server.start_failure is None
    expected = _EXCLUSIVE_SENTINEL if exclusive else socket.SO_REUSEADDR
    assert probe.events[0] == ("setsockopt", socket.SOL_SOCKET, expected, 1)
    assert probe.events[1] == ("bind", ("127.0.0.1", server.port))
    chosen = [event[2] for event in probe.events if event[0] == "setsockopt"]
    if exclusive:
        assert socket.SO_REUSEADDR not in chosen
    else:
        assert _EXCLUSIVE_SENTINEL not in chosen


@pytest.mark.parametrize(
    ("platform_name", "bind_error"),
    [
        ("linux", OSError(errno.EADDRINUSE, "Address already in use")),
        ("darwin", OSError(errno.EADDRINUSE, "Address already in use")),
        ("win32", _windows_addr_in_use()),
    ],
)
def test_address_in_use_reports_a_clear_message(monkeypatch, capsys, platform_name, bind_error):
    listener, _unreal = load_listener(monkeypatch)
    monkeypatch.setattr(listener.sys, "platform", platform_name)
    if platform_name == "win32":
        monkeypatch.setattr(
            listener.socket, "SO_EXCLUSIVEADDRUSE", _EXCLUSIVE_SENTINEL, raising=False
        )
    probe = _ProbeSocket(bind_error=bind_error)
    monkeypatch.setattr(listener.socket, "socket", lambda *args, **kwargs: probe)
    server = listener.UnrealMCPServer(port=9879)

    assert server.start() is False
    message = listener._port_in_use_message("127.0.0.1", 9879)
    assert server.start_failure == message
    assert "Blender Lab" not in message
    assert f"PlygonMCP: {message}" in capsys.readouterr().out


def test_real_socket_option_matches_this_platform(monkeypatch):
    listener, _unreal = load_listener(monkeypatch)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        listener._configure_listener_socket(sock)
        if sys.platform == "win32":
            assert sock.getsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE) == 1
            assert sock.getsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR) == 0
        else:
            assert sock.getsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR) == 1
    finally:
        sock.close()


def test_ping_is_not_answered_until_the_game_thread_drains(monkeypatch):
    listener, _unreal = load_listener(monkeypatch)
    server = listener.UnrealMCPServer(port=0)
    assert server.start() is True
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        client.connect(("127.0.0.1", server.port))
        client.sendall(b'{"type":"ping","params":{}}\n')
        deadline = time.time() + 2
        while server.command_queue.empty() and time.time() < deadline:
            time.sleep(0.01)
        assert not server.command_queue.empty()
        client.settimeout(0.2)
        with pytest.raises(socket.timeout):
            client.recv(4096)
        server._drain_command_queue(0.0)
        client.settimeout(2)
        payload = json.loads(client.recv(4096).decode("utf-8"))
        assert payload["status"] == "success"
        assert payload["result"] == {"pong": True}
    finally:
        client.close()
        server.stop()


def test_editor_shutdown_stops_the_listener(monkeypatch):
    listener, unreal_module = load_listener(monkeypatch)
    server = listener.UnrealMCPServer(port=0)
    assert server.start() is True
    try:
        assert server._slate_handle is not None
        assert unreal_module.shutdown_callbacks
        unreal_module.shutdown_callbacks[0]()
        assert server.running is False
        assert server.socket is None
        assert unreal_module.unregistered_slate
        assert unreal_module.unregistered_shutdown
    finally:
        if server.running:
            server.stop()


def test_mutations_use_editor_transactions(monkeypatch):
    listener, unreal_module = load_listener(monkeypatch)
    server = listener.UnrealMCPServer()
    spawned = server.execute_command(
        {
            "type": "spawn_actor",
            "params": {"kind": "cube", "name": "Cube", "location": [10, 20, 30]},
        }
    )
    assert spawned["status"] == "success"
    assert spawned["result"]["label"] == "Cube"
    assert spawned["result"]["location"] == [10.0, 20.0, 30.0]
    actor = unreal_module.actors.actors[0]
    assert actor.static_mesh_component.mesh is unreal_module.loaded["/Engine/BasicShapes/Cube"]

    moved = server.execute_command(
        {"type": "set_actor_transform", "params": {"name": "Cube", "location": [1, 2, 3]}}
    )
    assert moved["result"]["location"] == [1.0, 2.0, 3.0]

    selected = server.execute_command(
        {"type": "select_actors", "params": {"names": ["Cube"], "mode": "REPLACE"}}
    )
    assert selected["result"]["selected"][0]["label"] == "Cube"

    deleted = server.execute_command({"type": "delete_actor", "params": {"name": "Cube"}})
    assert deleted["result"]["deleted"] == "Cube"
    assert unreal_module.actors.actors == []
    assert unreal_module.transactions == [
        "Plygon spawn actor",
        "Plygon transform actor",
        "Plygon select actors",
        "Plygon delete actor",
    ]


def test_spawn_light_and_camera(monkeypatch):
    listener, unreal_module = load_listener(monkeypatch)
    server = listener.UnrealMCPServer()
    light = server.execute_command({"type": "spawn_actor", "params": {"kind": "point_light", "name": "Key"}})
    camera = server.execute_command({"type": "spawn_actor", "params": {"kind": "camera", "name": "Cam"}})
    assert light["result"]["class"] == "PointLight"
    assert camera["result"]["class"] == "CameraActor"
    assert [actor.label for actor in unreal_module.actors.actors] == ["Key", "Cam"]


def test_execute_python_captures_stdout_and_truncates(monkeypatch):
    listener, unreal_module = load_listener(monkeypatch)
    server = listener.UnrealMCPServer()
    short = server.execute_command({"type": "execute_python", "params": {"code": "print('hello')"}})
    assert short["result"] == {"executed": True, "result": "hello\n"}
    huge = "print('x' * 300000)"
    long = server.execute_command({"type": "execute_python", "params": {"code": huge}})
    text = long["result"]["result"]
    assert text.endswith("…[truncated 43872 bytes]") or "truncated" in text
    assert len(text.encode("utf-8")) < listener.MAX_BUFFER_BYTES
    assert unreal_module.transactions[-2:] == ["Plygon execute_python", "Plygon execute_python"]


def test_list_and_import_assets(monkeypatch):
    listener, unreal_module = load_listener(monkeypatch)
    server = listener.UnrealMCPServer()
    listed = server.execute_command({"type": "list_assets", "params": {"directory": "/Game"}})
    assert listed["result"]["assets"] == ["/Game/Meshes/Chair"]
    imported = server.execute_command(
        {
            "type": "import_asset",
            "params": {"filename": "C:/props/chair.fbx", "destination_path": "/Game/Imported"},
        }
    )
    assert imported["result"]["imported_object_paths"] == ["/Game/Imported/Imported"]
    assert unreal_module.imported == ["C:/props/chair.fbx"]
    assert "Plygon import asset" in unreal_module.transactions


def test_pcg_list_set_and_generate(monkeypatch):
    listener, unreal_module = load_listener(monkeypatch)
    component = FakePCGComponent()
    unreal_module.actors.actors.append(FakeActor("Scatter", "Actor", [component]))
    server = listener.UnrealMCPServer()
    listed = server.execute_command({"type": "list_pcg", "params": {}})
    assert listed["result"]["components"][0]["graph"] == "/Game/PCG/DemoGraph"
    updated = server.execute_command(
        {"type": "set_pcg_parameter", "params": {"actor": "Scatter", "name": "Density", "value": 0.25}}
    )
    assert updated["status"] == "success"
    assert unreal_module.parameter_calls[0][0] == "float"
    assert unreal_module.parameter_calls[0][2] == "Density"
    generated = server.execute_command({"type": "generate_pcg", "params": {"actor": "Scatter", "force": True}})
    assert generated["result"]["generated"] == ["Scatter"]
    assert component.generated is True
    assert "Plygon set PCG parameter" in unreal_module.transactions
    assert "Plygon generate PCG" in unreal_module.transactions


def test_pcg_reports_a_missing_plugin(monkeypatch):
    listener, unreal_module = load_listener(monkeypatch)
    del unreal_module.PCGComponent
    server = listener.UnrealMCPServer()
    result = server.execute_command({"type": "list_pcg", "params": {}})
    assert result["status"] == "error"
    assert "PCGComponent" in result["message"]


def test_screenshot_waits_for_a_later_tick(monkeypatch, tmp_path):
    listener, unreal_module = load_listener(monkeypatch)
    path = tmp_path / "shot.png"
    server = listener.UnrealMCPServer()
    server.running = True
    deferred = server.execute_command(
        {"type": "get_viewport_screenshot", "params": {"max_size": 320, "filepath": str(path)}}
    )
    assert deferred is listener._DEFERRED
    assert unreal_module.screenshot_calls[0]["force_game_view"] is True

    class Client:
        def __init__(self):
            self.sent = []

        def sendall(self, data):
            self.sent.append(data)

    client = Client()
    closed = threading.Event()
    server._deferred_client = (client, closed)
    server._drain_command_queue(0.0)
    assert client.sent == []
    path.write_bytes(b"\x89PNG\r\n")
    server._drain_command_queue(0.0)
    payload = json.loads(client.sent[0].decode("utf-8"))
    assert payload["status"] == "success"
    assert payload["result"]["filepath"] == str(path)
    assert payload["result"]["width"] == 320


def test_screenshot_rejects_too_small_max_size(monkeypatch):
    listener, _unreal = load_listener(monkeypatch)
    with pytest.raises(ValueError, match="at least 2"):
        listener.UnrealMCPServer().get_viewport_screenshot(max_size=1)


def test_queries_do_not_open_transactions(monkeypatch):
    listener, unreal_module = load_listener(monkeypatch)
    server = listener.UnrealMCPServer()
    info = server.execute_command({"type": "get_level_info", "params": {"limit": 5}})
    assert info["result"]["level"] == "/Game/Maps/Test"
    assert info["result"]["engine_version"] == "5.9.0-0+UE5"
    assert server.execute_command({"type": "ping"})["result"] == {"pong": True}
    assert unreal_module.transactions == []


class FakeClient:
    def __init__(self, chunks):
        self._chunks = list(chunks)
        self.closed = False
        self.sent = []

    def settimeout(self, value):
        del value

    def recv(self, _size):
        if not self._chunks:
            return b""
        return self._chunks.pop(0)

    def sendall(self, data):
        self.sent.append(data)

    def close(self):
        self.closed = True


def _http_request(method: str, body: dict) -> bytes:
    payload = json.dumps(body).encode("utf-8")
    head = (
        f"{method} / HTTP/1.1\r\n"
        "Host: 127.0.0.1:9879\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("utf-8")
    return head + payload


def _byte_chunks(payload: bytes, size: int) -> list[bytes]:
    return [payload[index : index + size] for index in range(0, len(payload), size)]


@pytest.mark.parametrize("method", ["GET", "POST", "PUT", "DELETE", "HEAD", "OPTIONS", "PATCH", "CONNECT", "TRACE"])
def test_http_request_is_rejected_before_execute_python(monkeypatch, method, capsys):
    listener, _unreal = load_listener(monkeypatch)
    attack = {"type": "execute_python", "params": {"code": "print('MARKER')"}}
    server = listener.UnrealMCPServer()
    server.running = True
    client = FakeClient([_http_request(method, attack)])

    server._handle_client(client)

    assert server.command_queue.empty()
    assert client.sent == []
    assert client.closed is True
    assert "rejected HTTP request" in capsys.readouterr().out


@pytest.mark.parametrize("chunk_size", [1, 2])
def test_split_http_request_line_is_rejected(monkeypatch, chunk_size, capsys):
    listener, _unreal = load_listener(monkeypatch)
    attack = {"type": "execute_python", "params": {"code": "print('MARKER')"}}
    server = listener.UnrealMCPServer()
    server.running = True
    client = FakeClient(_byte_chunks(_http_request("POST", attack), chunk_size))

    server._handle_client(client)

    captured = capsys.readouterr()
    assert server.command_queue.empty()
    assert "rejected HTTP request" in captured.out
    assert "MARKER" not in captured.out


@pytest.mark.parametrize("chunk_size", [1, 4])
def test_split_protocol_message_is_queued(monkeypatch, chunk_size):
    listener, _unreal = load_listener(monkeypatch)
    ping = {"type": "ping", "params": {}}
    server = listener.UnrealMCPServer()
    server.running = True
    raw = json.dumps(ping).encode("utf-8") + b"\n"
    client = FakeClient(_byte_chunks(raw, chunk_size))

    server._handle_client(client)

    command, _client, _closed, protocol_error = server.command_queue.get_nowait()
    assert command == ping
    assert protocol_error is None


def test_listener_recovers_after_malformed_newline_frame(monkeypatch):
    listener, _unreal = load_listener(monkeypatch)
    raw = b"{not json}\n" + json.dumps({"type": "ping"}).encode("utf-8") + b"\n"
    commands, leftover = listener._extract_json_objects(raw)
    assert commands[0] is listener._MALFORMED_JSON
    assert commands[1] == {"type": "ping"}
    assert leftover == b""


def test_listener_protocol_work_is_bounded(monkeypatch):
    listener, _unreal = load_listener(monkeypatch)
    server = listener.UnrealMCPServer()
    assert listener.MAX_BUFFER_BYTES == 4 * 1024 * 1024
    assert listener.MAX_PENDING_COMMANDS == 128
    assert server.command_queue.maxsize == listener.MAX_PENDING_COMMANDS
    assert listener.MAX_COMMANDS_PER_TICK == 1


def test_accept_handler_does_not_call_execute_command():
    tree = ast.parse(LISTENER_PATH.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "UnrealMCPServer":
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "_handle_client":
                    source = ast.dump(item)
                    assert "execute_command" not in source
                    return
    raise AssertionError("handler missing")
