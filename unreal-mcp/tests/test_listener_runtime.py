from __future__ import annotations

import ast
import errno
import importlib.util
import json
import socket
import sys
import threading
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LISTENER_PATH = ROOT / "editor" / "plygon_unreal_mcp" / "listener.py"
_EXCLUSIVE_SENTINEL = 45123
_SHARED_BIND_HELPERS = (
    "_configure_listener_socket",
    "_address_in_use",
    "_report_start_failure",
)


class FakeActor:
    def __init__(self, label="Cube", path="/Game/Maps/Main.Main:PersistentLevel.Cube"):
        self.label = label
        self.path = path
        self.class_name = "StaticMeshActor"
        self.location = (0.0, 0.0, 0.0)
        self.rotation = (0.0, 0.0, 0.0)
        self.scale = (1.0, 1.0, 1.0)
        self.mesh = None
        self.components = []
        self.mesh_component = types.SimpleNamespace(set_static_mesh=self._set_mesh)
        self.location_flags = None
        self.rotation_flags = None

    def _set_mesh(self, mesh):
        self.mesh = mesh
        return True

    def get_actor_label(self, create_if_none=True):
        del create_if_none
        return self.label

    def set_actor_label(self, name, mark_dirty=True):
        del mark_dirty
        self.label = name

    def get_name(self):
        return self.label

    def get_path_name(self):
        return self.path

    def get_class(self):
        return types.SimpleNamespace(get_name=lambda: self.class_name)

    def get_actor_location(self):
        return types.SimpleNamespace(x=self.location[0], y=self.location[1], z=self.location[2])

    def get_actor_rotation(self):
        return types.SimpleNamespace(
            pitch=self.rotation[0], yaw=self.rotation[1], roll=self.rotation[2]
        )

    def get_actor_scale3d(self):
        return types.SimpleNamespace(x=self.scale[0], y=self.scale[1], z=self.scale[2])

    def set_actor_location(self, vector, sweep, teleport):
        self.location = (vector.x, vector.y, vector.z)
        self.location_flags = (sweep, teleport)

    def set_actor_rotation(self, rotator, teleport_physics):
        self.rotation = (rotator.pitch, rotator.yaw, rotator.roll)
        self.rotation_flags = teleport_physics

    def set_actor_scale3d(self, vector):
        self.scale = (vector.x, vector.y, vector.z)

    def get_components_by_class(self, component_class):
        return [item for item in self.components if isinstance(item, component_class)]

    def get_component_by_class(self, component_class):
        found = self.get_components_by_class(component_class)
        return found[0] if found else None

    def get_editor_property(self, name):
        if name == "static_mesh_component":
            return self.mesh_component
        raise AttributeError(name)


class FakeActors:
    def __init__(self):
        self.actors = []
        self.selected = []
        self.destroyed = []
        self.spawned = []

    def get_all_level_actors(self):
        return list(self.actors)

    def get_selected_level_actors(self):
        return list(self.selected)

    def get_actor_reference(self, path):
        for actor in self.actors:
            if actor.path == path:
                return actor
        return None

    def set_selected_level_actors(self, actors):
        self.selected = list(actors)

    def select_nothing(self):
        self.selected = []

    def set_actor_selection_state(self, actor, should_be_selected):
        if should_be_selected and actor not in self.selected:
            self.selected.append(actor)
        if not should_be_selected and actor in self.selected:
            self.selected.remove(actor)

    def spawn_actor_from_class(self, actor_class, location, rotation, transient):
        actor = FakeActor(label=actor_class.__name__, path=f"/Game/Maps/Main.Main:PersistentLevel.{actor_class.__name__}_0")
        actor.class_name = actor_class.__name__
        actor.location = (location.x, location.y, location.z)
        actor.rotation = (rotation.pitch, rotation.yaw, rotation.roll)
        actor.transient = transient
        self.actors.append(actor)
        self.spawned.append(actor)
        return actor

    def destroy_actor(self, actor):
        self.destroyed.append(actor)
        if actor in self.actors:
            self.actors.remove(actor)
        return True


class FakeAssets:
    def __init__(self):
        self.existing = {"/Engine/BasicShapes/Cube"}
        self.loaded = {}
        self.assets = ["/Game/PCG/Forest.Forest", "/Game/Meshes/Chair.Chair"]
        self.classes = {
            "/Game/PCG/Forest.Forest": "/Script/PCG.PCGGraph",
            "/Game/Meshes/Chair.Chair": "/Script/Engine.StaticMesh",
        }
        self.directories = {"/Game"}
        self.made = []

    def does_asset_exist(self, path):
        return path in self.existing

    def load_asset(self, path):
        asset = self.loaded.get(path, types.SimpleNamespace(path=path))
        self.loaded[path] = asset
        return asset

    def list_assets(self, directory, recursive, include_folder):
        del directory, recursive, include_folder
        return list(self.assets)

    def find_asset_data(self, path):
        class_path = self.classes.get(str(path), "")

        class Data:
            def get_editor_property(self, name, class_path=class_path):
                if name == "asset_class_path":
                    return class_path
                raise KeyError(name)

        return Data()

    def does_directory_exist(self, path):
        return path in self.directories

    def make_directory(self, path):
        self.made.append(path)
        self.directories.add(path)
        return True


class FakeEditor:
    def __init__(self, actors):
        self.actors = actors

    def get_editor_world(self):
        return types.SimpleNamespace(
            get_name=lambda: "Main",
            get_path_name=lambda: "/Game/Maps/Main.Main",
        )

    def get_level_viewport_camera_info(self):
        return (
            types.SimpleNamespace(x=1.0, y=2.0, z=3.0),
            types.SimpleNamespace(pitch=4.0, yaw=5.0, roll=6.0),
        )


class FakeTask:
    def __init__(self, valid=True, done=True):
        self.valid = valid
        self.done = done

    def is_valid_task(self):
        return self.valid

    def is_task_done(self):
        return self.done


def load_listener(monkeypatch, **overrides):
    unreal = types.ModuleType("unreal")
    unreal.is_editor = lambda: True
    unreal.SystemLibrary = types.SimpleNamespace(get_engine_version=lambda: "5.4.4-35576357+++UE5+Release-5.4")
    unreal.callbacks = {}

    def register_tick(callback):
        unreal.callbacks["tick"] = callback
        return "tick-handle"

    def unregister_tick(handle):
        unreal.callbacks["unreg_tick"] = handle

    def register_shutdown(callback):
        unreal.callbacks["shutdown"] = callback
        return "shutdown-handle"

    def unregister_shutdown(handle):
        unreal.callbacks["unreg_shutdown"] = handle

    unreal.register_slate_post_tick_callback = register_tick
    unreal.unregister_slate_post_tick_callback = unregister_tick
    unreal.register_python_shutdown_callback = register_shutdown
    unreal.unregister_python_shutdown_callback = unregister_shutdown

    class Vector:
        def __init__(self, x=0.0, y=0.0, z=0.0):
            self.x = float(x)
            self.y = float(y)
            self.z = float(z)

    class Rotator:
        def __init__(self, roll=0.0, pitch=0.0, yaw=0.0):
            self.roll = float(roll)
            self.pitch = float(pitch)
            self.yaw = float(yaw)

    class Transaction:
        records = []

        def __init__(self, description):
            self.description = description
            self.cancelled = False
            Transaction.records.append(self)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def cancel(self):
            self.cancelled = True

    unreal.Vector = Vector
    unreal.Rotator = Rotator
    unreal.ScopedEditorTransaction = Transaction
    unreal.EditorActorSubsystem = type("EditorActorSubsystem", (), {})
    unreal.EditorAssetSubsystem = type("EditorAssetSubsystem", (), {})
    unreal.UnrealEditorSubsystem = type("UnrealEditorSubsystem", (), {})
    unreal.StaticMeshActor = type("StaticMeshActor", (), {})
    unreal.PointLight = type("PointLight", (), {})
    unreal.SpotLight = type("SpotLight", (), {})
    unreal.DirectionalLight = type("DirectionalLight", (), {})
    unreal.RectLight = type("RectLight", (), {})
    unreal.CameraActor = type("CameraActor", (), {})
    unreal.CineCameraActor = type("CineCameraActor", (), {})
    unreal.StaticMeshComponent = type("StaticMeshComponent", (), {})
    unreal.PCGComponent = type("PCGComponent", (), {})

    actors = FakeActors()
    assets = FakeAssets()
    editor = FakeEditor(actors)

    def get_editor_subsystem(cls):
        if cls is unreal.EditorActorSubsystem:
            return actors
        if cls is unreal.EditorAssetSubsystem:
            return assets
        if cls is unreal.UnrealEditorSubsystem:
            return editor
        return None

    unreal.get_editor_subsystem = get_editor_subsystem
    unreal.actors = actors
    unreal.assets = assets

    class AssetImportTask:
        def __init__(self):
            self.props = {}

        def set_editor_property(self, name, value):
            self.props[name] = value

        def get_editor_property(self, name):
            if name == "imported_object_paths":
                return ["/Game/PlygonImport/Chair.Chair"]
            return self.props[name]

    imported = {}

    class AssetTools:
        def import_asset_tasks(self, tasks):
            imported["tasks"] = list(tasks)

    unreal.AssetImportTask = AssetImportTask
    unreal.AssetToolsHelpers = types.SimpleNamespace(get_asset_tools=lambda: AssetTools())
    unreal.imported = imported

    shot = {"calls": []}

    def take(res_x, res_y, filename, camera, mask, hdr, delay=0.0, force_game_view=True):
        shot["calls"].append(
            {
                "res": (res_x, res_y),
                "filename": filename,
                "force_game_view": force_game_view,
                "delay": delay,
            }
        )
        Path(filename).write_bytes(b"\x89PNG\r\n")
        return FakeTask()

    unreal.AutomationLibrary = types.SimpleNamespace(take_high_res_screenshot=take)
    unreal.shot = shot

    pcg_calls = {}

    def set_float_parameter(graph_interface, name, value):
        pcg_calls["set"] = (graph_interface, name, value)

    unreal.PCGGraphParametersHelpers = types.SimpleNamespace(set_float_parameter=set_float_parameter)
    unreal.pcg_calls = pcg_calls

    for name, value in overrides.items():
        setattr(unreal, name, value)

    monkeypatch.setitem(sys.modules, "unreal", unreal)
    module_name = "plygon_unreal_mcp._listener_runtime_test"
    spec = importlib.util.spec_from_file_location(module_name, LISTENER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, module_name, module)
    spec.loader.exec_module(module)
    module.unreal = unreal
    return module, unreal


def test_start_rejects_commandlet(monkeypatch):
    listener, _unreal = load_listener(monkeypatch, is_editor=lambda: False)
    server = listener.UnrealMCPServer()
    assert server.start() is False
    assert server.socket is None


def test_start_rejects_engine_older_than_5_4(monkeypatch):
    listener, _unreal = load_listener(
        monkeypatch,
        SystemLibrary=types.SimpleNamespace(get_engine_version=lambda: "5.3.2-0+UE5"),
    )
    server = listener.UnrealMCPServer()
    assert server.start() is False
    assert server.socket is None
    assert "5.4" in server.start_failure


def test_start_rejects_non_loopback(monkeypatch):
    listener, _unreal = load_listener(monkeypatch)
    server = listener.UnrealMCPServer(host="10.0.0.5")
    assert server.start() is False
    assert "127.0.0.1" in server.start_failure


@pytest.mark.parametrize("host", ["", "localhost", "::1"])
def test_listener_coerces_loopback_aliases_to_ipv4(monkeypatch, host):
    listener, _unreal = load_listener(monkeypatch)
    assert listener.UnrealMCPServer(host=host).host == "127.0.0.1"


def _function_ast(path: Path, name: str) -> str:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.dump(node, include_attributes=False)
    raise AssertionError(f"{name} missing from {path}")


def test_listener_socket_policy_matches_blender():
    blender = ROOT.parent / "blender-mcp" / "addon" / "blender_mcp_addon.py"
    for name in _SHARED_BIND_HELPERS:
        assert _function_ast(LISTENER_PATH, name) == _function_ast(blender, name)


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
    assert probe.events[2][0] == "listen"
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
    assert "Blender Lab" not in message
    assert server.start_failure == message
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


def test_shutdown_callback_unregisters_the_same_tick_handle(monkeypatch):
    listener, unreal = load_listener(monkeypatch)
    server = listener.UnrealMCPServer(port=0)
    assert server.start() is True
    try:
        assert unreal.callbacks["tick"].__func__ is server._drain_command_queue.__func__
        server._on_python_shutdown()
        assert unreal.callbacks["unreg_tick"] == "tick-handle"
        assert "unreg_shutdown" not in unreal.callbacks
        assert server.running is False
    finally:
        if server.running:
            server.stop()


def test_accept_thread_does_not_execute(monkeypatch):
    listener, _unreal = load_listener(monkeypatch)
    server = listener.UnrealMCPServer()
    server.running = True
    called = []
    server.execute_command = lambda command: called.append(command)
    raw = json.dumps({"type": "ping", "params": {}}).encode("utf-8") + b"\n"
    client = FakeClient([raw])

    server._handle_client(client)

    assert called == []
    command, _client, _closed, protocol_error = server.command_queue.get_nowait()
    assert command["type"] == "ping"
    assert protocol_error is None


def test_drain_runs_ping_on_the_caller_thread(monkeypatch):
    listener, _unreal = load_listener(monkeypatch)
    server = listener.UnrealMCPServer()
    server.running = True
    client = FakeClient([])
    closed = threading.Event()
    server.command_queue.put(({"type": "ping", "params": {}}, client, closed, None))

    server._drain_command_queue(0.016)

    assert server._game_thread_id == threading.get_ident()
    assert b'"pong": true' in client.sent[0]


def test_execute_off_the_game_thread_is_refused(monkeypatch):
    listener, _unreal = load_listener(monkeypatch)
    server = listener.UnrealMCPServer()
    server.running = True
    server._drain_command_queue(0.0)
    result = {}

    def other():
        result["value"] = server.execute_command({"type": "ping", "params": {}})

    thread = threading.Thread(target=other)
    thread.start()
    thread.join(timeout=2)

    assert result["value"]["status"] == "error"
    assert "game thread" in result["value"]["message"]


def test_spawn_transform_and_delete_use_transactions(monkeypatch):
    listener, unreal = load_listener(monkeypatch)
    server = listener.UnrealMCPServer()
    unreal.ScopedEditorTransaction.records.clear()

    spawned = server.spawn_actor(
        kind="static_mesh",
        name="Crate",
        location=[10, 20, 30],
        rotation=[10, 20, 30],
        scale=[2, 2, 2],
    )

    assert spawned["label"] == "Crate"
    assert spawned["location"] == [10.0, 20.0, 30.0]
    assert spawned["rotation"] == [10.0, 20.0, 30.0]
    assert spawned["mesh"] == "/Engine/BasicShapes/Cube"
    actor = unreal.actors.spawned[0]
    assert actor.rotation == (10.0, 20.0, 30.0)
    assert actor.mesh is not None
    assert unreal.ScopedEditorTransaction.records[-1].description == "Plygon MCP spawn static_mesh"

    moved = server.set_actor_transform(name="Crate", location=[1, 2, 3])
    assert moved["location"] == [1.0, 2.0, 3.0]
    assert actor.location_flags == (False, True)
    assert "transform" in unreal.ScopedEditorTransaction.records[-1].description

    selected = server.select_actors(names=["Crate"], mode="REPLACE")
    assert selected["selected"][0]["label"] == "Crate"
    assert unreal.actors.selected == [actor]

    deleted = server.delete_actor(name="Crate")
    assert deleted["label"] == "Crate"
    assert actor in unreal.actors.destroyed
    assert unreal.ScopedEditorTransaction.records[-1].description == "Plygon MCP delete actor"
    assert not any(record.cancelled for record in unreal.ScopedEditorTransaction.records)


def test_execute_code_truncates_stdout_and_cancels_on_failure(monkeypatch):
    listener, unreal = load_listener(monkeypatch)
    server = listener.UnrealMCPServer()
    unreal.ScopedEditorTransaction.records.clear()

    ok = server.execute_code("print('hello')")
    assert ok["result"] == "hello\n"

    huge = server.execute_code("print('x' * 400000)")
    assert huge["result"].endswith("]")
    assert "…[truncated " in huge["result"]
    assert len(huge["result"].encode("utf-8")) < listener.MAX_BUFFER_BYTES

    with pytest.raises(RuntimeError, match="boom"):
        server.execute_code("raise RuntimeError('boom')")
    assert unreal.ScopedEditorTransaction.records[-1].cancelled is True


def test_level_info_and_asset_list(monkeypatch):
    listener, unreal = load_listener(monkeypatch)
    server = listener.UnrealMCPServer()
    unreal.actors.actors.append(FakeActor())

    info = server.get_level_info(limit=10)
    assert info["world_name"] == "Main"
    assert info["viewport_camera"]["location"] == [1.0, 2.0, 3.0]
    assert info["viewport_camera"]["rotation"] == [4.0, 5.0, 6.0]
    assert info["actor_count"] == 1

    assets = server.list_assets(class_filter="StaticMesh", limit=10)
    assert assets["assets"] == [
        {"path": "/Game/Meshes/Chair.Chair", "class": "/Script/Engine.StaticMesh"}
    ]


def test_import_asset_sets_documented_task_fields(monkeypatch, tmp_path):
    listener, unreal = load_listener(monkeypatch)
    server = listener.UnrealMCPServer()
    source = tmp_path / "chair.fbx"
    source.write_bytes(b"fbx")

    result = server.import_asset(filename=str(source), destination_name="Chair")

    task = unreal.imported["tasks"][0]
    assert task.props["filename"] == str(source)
    assert task.props["destination_path"] == "/Game/PlygonImport"
    assert task.props["destination_name"] == "Chair"
    assert task.props["automated"] is True
    assert task.props["save"] is True
    assert result["imported_object_paths"] == ["/Game/PlygonImport/Chair.Chair"]
    assert "/Game/PlygonImport" in unreal.assets.made


def test_screenshot_waits_for_the_file_and_keeps_editor_view(monkeypatch, tmp_path):
    listener, unreal = load_listener(monkeypatch)
    server = listener.UnrealMCPServer()
    server.running = True
    path = tmp_path / "shot.png"
    client = FakeClient([])
    closed = threading.Event()
    server.command_queue.put(
        (
            {"type": "get_viewport_screenshot", "params": {"max_size": 640, "filepath": str(path)}},
            client,
            closed,
            None,
        )
    )

    server._drain_command_queue(0.0)

    assert unreal.shot["calls"][0]["force_game_view"] is False
    assert unreal.shot["calls"][0]["res"] == (640, 640)
    body = client.sent[0]
    assert b'"success": true' in body
    assert str(path).encode("utf-8") in body


def test_screenshot_reports_a_timeout_when_the_file_never_appears(monkeypatch, tmp_path):
    listener, unreal = load_listener(monkeypatch)

    def take(*args, **kwargs):
        del args, kwargs
        return FakeTask(valid=False, done=False)

    unreal.AutomationLibrary = types.SimpleNamespace(take_high_res_screenshot=take)
    server = listener.UnrealMCPServer()
    path = tmp_path / "missing.png"
    server.get_viewport_screenshot(max_size=32, filepath=str(path))
    server._pending_capture["deadline"] = 0
    server._pending_capture["client_closed"] = threading.Event()

    ready = server._poll_capture()

    assert ready["status"] == "error"
    assert "did not accept" in ready["message"]


def test_pcg_lists_components_and_sets_parameters_on_the_instance(monkeypatch):
    listener, unreal = load_listener(monkeypatch)
    server = listener.UnrealMCPServer()
    actor = FakeActor(label="Forest", path="/Game/Maps/Main.Main:PersistentLevel.Forest")

    class Component(unreal.PCGComponent):
        def __init__(self):
            self.graph = types.SimpleNamespace(
                get_path_name=lambda: "/Game/PCG/Forest.Forest",
                get_name=lambda: "Forest",
                get_editor_property=lambda name: [] if name == "nodes" else None,
            )
            self.graph_instance = types.SimpleNamespace(
                graph=self.graph,
                get_path_name=lambda: "/Game/PCG/Forest.Forest_Inst",
            )
            self.get_graph_calls = 0
            self.generation_in_progress = False

        def get_graph(self):
            self.get_graph_calls += 1
            return self.graph

        def generate(self, force):
            self.generation_in_progress = bool(force)

        def get_path_name(self):
            return actor.path + ".PCG"

    component = Component()
    actor.components.append(component)
    unreal.actors.actors.append(actor)

    listed = server.list_pcg(limit=10)
    assert listed["components"][0]["actor_label"] == "Forest"
    assert listed["components"][0]["graph"]["path"] == "/Game/PCG/Forest.Forest"
    assert component.get_graph_calls == 1
    assert listed["graphs"][0]["path"] == "/Game/PCG/Forest.Forest"

    set_result = server.set_pcg_parameter(
        name="Forest", parameter="Density", value=0.25, value_type="float"
    )
    target, parameter, value = unreal.pcg_calls["set"]
    assert target is component.graph_instance
    assert parameter == "Density"
    assert value == 0.25
    assert set_result["parameter"] == "Density"

    generated = server.generate_pcg(name="Forest", force=True)
    assert generated["generation_in_progress"] is True
    assert component.generation_in_progress is True


def test_pcg_without_get_graph_uses_the_5_4_instance(monkeypatch):
    listener, unreal = load_listener(monkeypatch)
    server = listener.UnrealMCPServer()
    actor = FakeActor(label="Scatter")

    class Component(unreal.PCGComponent):
        def __init__(self):
            self.graph_instance = types.SimpleNamespace(
                graph=types.SimpleNamespace(
                    get_path_name=lambda: "/Game/PCG/Scatter.Scatter",
                    get_name=lambda: "Scatter",
                    get_editor_property=lambda name: [],
                ),
                get_path_name=lambda: "/Game/PCG/Scatter_Inst",
            )

        def get_path_name(self):
            return "component"

    assert not hasattr(Component, "get_graph")
    component = Component()
    actor.components.append(component)
    unreal.actors.actors.append(actor)

    listed = server.list_pcg(include_assets=False)
    assert listed["components"][0]["graph"]["name"] == "Scatter"


def test_listener_extracts_concatenated_commands(monkeypatch):
    listener, _unreal = load_listener(monkeypatch)
    ping = {"type": "ping", "params": {}}
    level = {"type": "get_level_info", "params": {"limit": 5}}
    blob = (json.dumps(ping) + json.dumps(level)).encode("utf-8")

    commands, leftover = listener._extract_json_objects(blob)

    assert commands == [ping, level]
    assert leftover == b""


class FakeClient:
    def __init__(self, chunks):
        self._chunks = list(chunks)
        self.closed = False
        self.sent = []
        self.timeout = None

    def settimeout(self, value):
        self.timeout = value

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


@pytest.mark.parametrize(
    "method",
    ["GET", "POST", "PUT", "DELETE", "HEAD", "OPTIONS", "PATCH", "CONNECT", "TRACE"],
)
def test_http_request_is_rejected_before_execute_code(monkeypatch, method, capsys):
    listener, _unreal = load_listener(monkeypatch)
    attack = {"type": "execute_code", "params": {"code": "print('MARKER')"}}
    server = listener.UnrealMCPServer()
    server.running = True
    client = FakeClient([_http_request(method, attack)])

    server._handle_client(client)

    assert server.command_queue.empty()
    assert client.sent == []
    assert client.closed is True
    assert "rejected HTTP request" in capsys.readouterr().out


def _byte_chunks(payload: bytes, size: int) -> list[bytes]:
    return [payload[index : index + size] for index in range(0, len(payload), size)]


@pytest.mark.parametrize("chunk_size", [1, 2])
def test_split_http_request_line_is_rejected(monkeypatch, chunk_size, capsys):
    listener, _unreal = load_listener(monkeypatch)
    attack = {"type": "execute_code", "params": {"code": "print('MARKER')"}}
    server = listener.UnrealMCPServer()
    server.running = True
    client = FakeClient(_byte_chunks(_http_request("POST", attack), chunk_size))

    server._handle_client(client)

    captured = capsys.readouterr()
    assert server.command_queue.empty()
    assert "rejected HTTP request" in captured.out
    assert "MARKER" not in captured.out


def test_long_ambiguous_http_prefix_is_rejected(monkeypatch, capsys):
    listener, _unreal = load_listener(monkeypatch)
    attack = {"type": "execute_code", "params": {"code": "print('MARKER')"}}
    server = listener.UnrealMCPServer()
    server.running = True
    filler = b"GET /" + (b"a" * listener._HTTP_GUARD_BYTES)
    raw = filler + b" HTTP/1.1\r\n\r\n" + json.dumps(attack).encode("utf-8") + b"\n"
    client = FakeClient([raw[: listener._HTTP_GUARD_BYTES], raw[listener._HTTP_GUARD_BYTES :]])

    server._handle_client(client)

    captured = capsys.readouterr()
    assert server.command_queue.empty()
    assert "rejected HTTP request" in captured.out
    assert "MARKER" not in captured.out


def test_oversized_buffer_closes_the_client(monkeypatch):
    listener, _unreal = load_listener(monkeypatch)
    listener.MAX_BUFFER_BYTES = 40
    server = listener.UnrealMCPServer()
    server.running = True
    raw = b'{"type": "ping", "params": {"blob": "' + (b"a" * 80) + b'"}}\n'
    client = FakeClient([raw])

    server._handle_client(client)

    assert client.closed is True
    assert server.command_queue.empty()


def test_split_protocol_message_is_queued(monkeypatch):
    listener, _unreal = load_listener(monkeypatch)
    ping = {"type": "ping", "params": {}}
    server = listener.UnrealMCPServer()
    server.running = True
    raw = json.dumps(ping).encode("utf-8") + b"\n"
    client = FakeClient(_byte_chunks(raw, 1))

    server._handle_client(client)

    command, _client, _closed, protocol_error = server.command_queue.get_nowait()
    assert command == ping
    assert protocol_error is None
