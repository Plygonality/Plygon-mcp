from __future__ import annotations

import ast
import errno
import importlib.util
import json
import socket
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ADDON_PATH = ROOT / "addon" / "blender_mcp_addon.py"


class FakeTimers:
    def is_registered(self, callback):
        return False

    def register(self, callback, **kwargs):
        return None

    def unregister(self, callback):
        return None


def load_addon(monkeypatch, *, background=False):
    bpy = types.ModuleType("bpy")
    bpy.app = types.SimpleNamespace(background=background, timers=FakeTimers())
    bpy.context = types.SimpleNamespace(
        window_manager=types.SimpleNamespace(windows=()),
        mode="OBJECT",
    )
    bpy.types = types.SimpleNamespace(
        Operator=type("Operator", (), {}),
        Panel=type("Panel", (), {}),
        Scene=type("Scene", (), {}),
    )
    bpy.ops = types.SimpleNamespace()
    bpy.data = types.SimpleNamespace()

    props = types.ModuleType("bpy.props")
    props.IntProperty = lambda **kwargs: None
    props.BoolProperty = lambda **kwargs: None
    props.StringProperty = lambda **kwargs: None

    mathutils = types.ModuleType("mathutils")
    mathutils.Vector = lambda value: value
    mathutils.Euler = lambda value: value

    monkeypatch.setitem(sys.modules, "bpy", bpy)
    monkeypatch.setitem(sys.modules, "bpy.props", props)
    monkeypatch.setitem(sys.modules, "mathutils", mathutils)

    module_name = "_plygon_blender_addon_runtime_test"
    spec = importlib.util.spec_from_file_location(module_name, ADDON_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, module_name, module)
    spec.loader.exec_module(module)
    return module, bpy


def test_addon_extracts_concatenated_commands(monkeypatch):
    addon, _bpy = load_addon(monkeypatch)
    ping = {"type": "ping", "params": {}}
    scene = {"type": "get_scene_info", "params": {"limit": 5}}

    commands, leftover = addon._extract_json_objects(
        (json.dumps(ping) + json.dumps(scene)).encode("utf-8")
    )

    assert commands == [ping, scene]
    assert leftover == b""
    assert addon._encode_message(ping).endswith(b"\n")


def test_addon_recovers_after_malformed_newline_frame(monkeypatch):
    addon, _bpy = load_addon(monkeypatch)
    ping = {"type": "ping", "params": {}}

    commands, leftover = addon._extract_json_objects(
        b'{"type":]\n' + json.dumps(ping).encode("utf-8") + b"\n"
    )

    assert commands == [addon._MALFORMED_JSON, ping]
    assert leftover == b""


def test_server_start_reports_background_failure(monkeypatch):
    addon, _bpy = load_addon(monkeypatch, background=True)

    server = addon.BlenderMCPServer()

    assert server.start() is False
    assert server.running is False


@pytest.mark.parametrize("host", ["", "localhost", "::1"])
def test_server_coerces_loopback_aliases_to_ipv4(monkeypatch, host):
    addon, _bpy = load_addon(monkeypatch)

    assert addon.BlenderMCPServer(host=host).host == "127.0.0.1"


def test_server_start_reports_bind_failure(monkeypatch, capsys):
    addon, _bpy = load_addon(monkeypatch)

    class FailingSocket:
        def setsockopt(self, *args):
            return None

        def bind(self, address):
            raise OSError("network is down")

        def close(self):
            return None

    monkeypatch.setattr(addon.socket, "socket", lambda *args: FailingSocket())
    server = addon.BlenderMCPServer()

    assert server.start() is False
    assert server.running is False
    assert server.socket is None
    assert server.start_failure is None
    assert "failed to start: network is down" in capsys.readouterr().out


_EXCLUSIVE_SENTINEL = 45123
_SHARED_BIND_HELPERS = (
    "_configure_listener_socket",
    "_address_in_use",
    "_port_in_use_message",
    "_report_start_failure",
)


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


def test_listener_socket_policy_matches_houdini():
    repo = ROOT.parent
    houdini = (
        repo
        / "houdini-mcp"
        / "package"
        / "scripts"
        / "python"
        / "plygon_houdini_mcp"
        / "listener.py"
    )
    for name in _SHARED_BIND_HELPERS:
        assert _function_ast(ADDON_PATH, name) == _function_ast(houdini, name)


@pytest.mark.parametrize(
    ("platform_name", "exclusive"),
    [("win32", True), ("linux", False), ("darwin", False)],
)
def test_listener_socket_option_follows_platform(monkeypatch, platform_name, exclusive):
    addon, _bpy = load_addon(monkeypatch)
    monkeypatch.setattr(addon.sys, "platform", platform_name)
    if exclusive:
        monkeypatch.setattr(
            addon.socket, "SO_EXCLUSIVEADDRUSE", _EXCLUSIVE_SENTINEL, raising=False
        )
    probe = _ProbeSocket()
    monkeypatch.setattr(addon.socket, "socket", lambda *args, **kwargs: probe)
    server = addon.BlenderMCPServer()

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
    addon, _bpy = load_addon(monkeypatch)
    monkeypatch.setattr(addon.sys, "platform", platform_name)
    if platform_name == "win32":
        monkeypatch.setattr(
            addon.socket, "SO_EXCLUSIVEADDRUSE", _EXCLUSIVE_SENTINEL, raising=False
        )
    probe = _ProbeSocket(bind_error=bind_error)
    monkeypatch.setattr(addon.socket, "socket", lambda *args, **kwargs: probe)
    server = addon.BlenderMCPServer(port=9876)

    assert server.start() is False
    assert server.running is False
    assert server.socket is None
    message = addon._port_in_use_message("127.0.0.1", 9876)
    assert server.start_failure == message
    assert f"PlygonMCP: {message}" in capsys.readouterr().out
    expected = _EXCLUSIVE_SENTINEL if platform_name == "win32" else socket.SO_REUSEADDR
    assert probe.events[0] == ("setsockopt", socket.SOL_SOCKET, expected, 1)
    if platform_name == "win32":
        assert probe.events[0][2] != socket.SO_REUSEADDR


def test_busy_port_reports_that_it_is_already_in_use(monkeypatch, capsys):
    addon, _bpy = load_addon(monkeypatch)
    holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    holder.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    holder.bind(("127.0.0.1", 0))
    holder.listen(1)
    port = holder.getsockname()[1]
    server = addon.BlenderMCPServer(port=port)
    try:
        assert server.start() is False
        message = addon._port_in_use_message("127.0.0.1", port)
        assert server.start_failure == message
        assert server.running is False
        assert server.socket is None
        assert f"PlygonMCP: {message}" in capsys.readouterr().out
    finally:
        if server.running:
            server.stop()
        holder.close()


def test_real_socket_option_matches_this_platform(monkeypatch):
    addon, _bpy = load_addon(monkeypatch)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        addon._configure_listener_socket(sock)
        if sys.platform == "win32":
            assert sock.getsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE) == 1
            assert sock.getsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR) == 0
        else:
            assert sock.getsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR) == 1
    finally:
        sock.close()


def test_start_operator_does_not_show_online_after_failure(monkeypatch):
    addon, _bpy = load_addon(monkeypatch)

    class FailedServer:
        running = False

        def __init__(self, host, port):
            self.host = host
            self.port = port

        def start(self):
            return False

    monkeypatch.setattr(addon, "BlenderMCPServer", FailedServer)
    scene = types.SimpleNamespace(
        plygonmcp_port=9876,
        plygonmcp_server_running=True,
    )
    context = types.SimpleNamespace(scene=scene)
    reports = []
    operator = addon.PLYGONMCP_OT_StartServer()
    operator.report = lambda level, message: reports.append((level, message))

    result = operator.execute(context)

    assert result == {"CANCELLED"}
    assert scene.plygonmcp_server_running is False
    assert addon._server is None
    assert reports[-1][0] == {"ERROR"}


def test_start_operator_reports_busy_port(monkeypatch, capsys):
    addon, _bpy = load_addon(monkeypatch)
    holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    holder.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    holder.bind(("127.0.0.1", 0))
    holder.listen(1)
    port = holder.getsockname()[1]
    scene = types.SimpleNamespace(
        plygonmcp_port=port,
        plygonmcp_server_running=True,
    )
    context = types.SimpleNamespace(scene=scene)
    reports = []
    operator = addon.PLYGONMCP_OT_StartServer()
    operator.report = lambda level, message: reports.append((level, message))
    try:
        result = operator.execute(context)
        message = addon._port_in_use_message("127.0.0.1", port)
        assert result == {"CANCELLED"}
        assert scene.plygonmcp_server_running is False
        assert addon._server is None
        assert reports[-1] == ({"ERROR"}, message)
        assert f"PlygonMCP: {message}" in capsys.readouterr().out
    finally:
        running = addon._server
        if running is not None and hasattr(running, "stop"):
            running.stop()
        holder.close()


def test_protocol_work_is_bounded(monkeypatch):
    addon, _bpy = load_addon(monkeypatch)
    server = addon.BlenderMCPServer()

    assert addon.MAX_BUFFER_BYTES == 4 * 1024 * 1024
    assert addon.MAX_PENDING_COMMANDS == 128
    assert server.command_queue.maxsize == addon.MAX_PENDING_COMMANDS
    assert addon.MAX_COMMANDS_PER_TICK == 1


def test_disconnected_client_work_is_discarded(monkeypatch):
    addon, _bpy = load_addon(monkeypatch)
    server = addon.BlenderMCPServer()
    server.running = True
    executed = []
    server.execute_command = executed.append
    closed = types.SimpleNamespace(is_set=lambda: True)
    server.command_queue.put_nowait(({"type": "ping"}, object(), closed, None))

    server._drain_command_queue()

    assert executed == []
    assert server.command_queue.empty()


def test_viewport_screenshot_rejects_too_small_max_size(monkeypatch):
    addon, _bpy = load_addon(monkeypatch)

    with pytest.raises(ValueError, match="at least 2"):
        addon.BlenderMCPServer().get_viewport_screenshot(max_size=1)


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
        "Host: 127.0.0.1:9876\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("utf-8")
    return head + payload


def test_framer_extracts_execute_code_hidden_in_http_body(monkeypatch):
    """The JSON framer is lenient; the handler must reject HTTP before it runs."""
    addon, _bpy = load_addon(monkeypatch)
    attack = {"type": "execute_code", "params": {"code": "print('MARKER')"}}

    commands, leftover = addon._extract_json_objects(_http_request("POST", attack))

    assert attack in commands
    assert leftover == b""


@pytest.mark.parametrize(
    "method",
    ["GET", "POST", "PUT", "DELETE", "HEAD", "OPTIONS", "PATCH", "CONNECT", "TRACE"],
)
def test_http_request_is_rejected_before_execute_code(monkeypatch, method, capsys):
    addon, _bpy = load_addon(monkeypatch)
    attack = {"type": "execute_code", "params": {"code": "print('MARKER')"}}
    server = addon.BlenderMCPServer()
    server.running = True
    client = FakeClient([b"  " + _http_request(method, attack)])

    server._handle_client(client)

    captured = capsys.readouterr()
    assert server.command_queue.empty()
    assert client.sent == []
    assert client.closed is True
    assert "rejected HTTP request" in captured.out
    assert "MARKER" not in captured.out


def test_json_command_is_still_queued_after_http_guard(monkeypatch):
    addon, _bpy = load_addon(monkeypatch)
    ping = {"type": "ping", "params": {}}
    server = addon.BlenderMCPServer()
    server.running = True
    raw = json.dumps(ping).encode("utf-8") + b"\n"
    client = FakeClient([raw[:1], raw[1:]])

    server._handle_client(client)

    command, _client, _closed, protocol_error = server.command_queue.get_nowait()
    assert command == ping
    assert protocol_error is None
    assert server.command_queue.empty()


def test_json_containing_http_words_is_not_rejected(monkeypatch):
    addon, _bpy = load_addon(monkeypatch)
    command = {
        "type": "execute_code",
        "params": {"code": "print('POST / HTTP/1.1')"},
    }
    server = addon.BlenderMCPServer()
    server.running = True
    client = FakeClient([json.dumps(command).encode("utf-8") + b"\n"])

    server._handle_client(client)

    queued, *_rest = server.command_queue.get_nowait()
    assert queued == command


def test_execute_code_truncates_large_stdout(monkeypatch):
    addon, _bpy = load_addon(monkeypatch)
    extra = 1234
    huge = addon.BlenderMCPServer().execute_code(
        f"print('x' * {addon.MAX_EXECUTE_STDOUT_BYTES + extra}, end='')"
    )
    small = addon.BlenderMCPServer().execute_code("print('ok')")
    silent = addon.BlenderMCPServer().execute_code("value = 1")

    assert huge["executed"] is True
    assert huge["result"].endswith(f"\n…[truncated {extra} bytes]")
    assert huge["result"].count("x") == addon.MAX_EXECUTE_STDOUT_BYTES
    assert small == {"executed": True, "result": "ok\n"}
    assert silent == {"executed": True, "result": ""}

    from plygon_blender_mcp.connection import MAX_BUFFER_BYTES as client_limit

    payload = addon._encode_message({"status": "success", "result": huge})
    assert len(payload) < addon.MAX_BUFFER_BYTES
    assert len(payload) < client_limit
    assert addon.MAX_EXECUTE_STDOUT_BYTES == 256 * 1024


def test_truncate_stdout_keeps_utf8_boundary(monkeypatch):
    addon, _bpy = load_addon(monkeypatch)
    text = "€" * 10

    truncated = addon._truncate_stdout(text, limit=4)

    assert truncated.startswith("€")
    assert truncated.endswith("\n…[truncated 27 bytes]")


MESH_OPERATORS = (
    "primitive_cube_add",
    "primitive_uv_sphere_add",
    "primitive_cylinder_add",
    "primitive_cone_add",
    "primitive_torus_add",
    "primitive_plane_add",
    "primitive_monkey_add",
    "primitive_ico_sphere_add",
)

SHAPE_OPERATOR = {
    "CUBE": "primitive_cube_add",
    "SPHERE": "primitive_uv_sphere_add",
    "CYLINDER": "primitive_cylinder_add",
    "CONE": "primitive_cone_add",
    "TORUS": "primitive_torus_add",
    "PLANE": "primitive_plane_add",
    "MONKEY": "primitive_monkey_add",
    "ICO_SPHERE": "primitive_ico_sphere_add",
}

EXPECTED_SIZE_KWARGS = {
    "CUBE": {"size": 2.0},
    "PLANE": {"size": 2.0},
    "MONKEY": {"size": 2.0},
    "SPHERE": {"radius": 1.0},
    "ICO_SPHERE": {"radius": 1.0},
    "CYLINDER": {"radius": 1.0, "depth": 2.0},
    "CONE": {"radius1": 1.0, "depth": 2.0},
    "TORUS": {"major_radius": 1.0, "minor_radius": 0.25},
}


class _ScaleVector(tuple):
    def __new__(cls, value):
        return tuple.__new__(cls, tuple(value))


def _install_mesh_ops(bpy):
    calls = {name: [] for name in MESH_OPERATORS}

    def make(name):
        def operator(**kwargs):
            calls[name].append(kwargs)
            return {"FINISHED"}

        return operator

    bpy.ops.mesh = types.SimpleNamespace(**{name: make(name) for name in MESH_OPERATORS})
    return calls


def _active_object(bpy, name="Mesh"):
    obj = types.SimpleNamespace(
        name=name,
        type="MESH",
        data=types.SimpleNamespace(name=name),
        scale=(1.0, 1.0, 1.0),
    )
    bpy.context.view_layer = types.SimpleNamespace(objects=types.SimpleNamespace(active=obj))
    return obj


@pytest.mark.parametrize("shape", list(SHAPE_OPERATOR))
def test_create_primitive_scale_is_object_scale_for_every_shape(monkeypatch, shape):
    addon, bpy = load_addon(monkeypatch)
    addon.mathutils.Vector = _ScaleVector
    calls = _install_mesh_ops(bpy)
    obj = _active_object(bpy, name=shape.title())
    location = [0, 3, 0.5] if shape == "TORUS" else [0, 0, 0]
    name = "Ring" if shape == "TORUS" else ""

    result = addon.BlenderMCPServer().create_primitive(
        shape=shape,
        name=name,
        location=location,
        scale=[2, 1, 1],
    )

    kwargs = calls[SHAPE_OPERATOR[shape]][0]
    assert "scale" not in kwargs
    assert set(kwargs) == {"location", "rotation", *EXPECTED_SIZE_KWARGS[shape]}
    assert kwargs["location"] == tuple(location)
    assert kwargs["rotation"] == (0.0, 0.0, 0.0)
    for key, value in EXPECTED_SIZE_KWARGS[shape].items():
        assert kwargs[key] == value
    assert obj.scale == (2, 1, 1)
    assert result["shape"] == shape
    assert result["type"] == "MESH"
    if shape == "TORUS":
        assert result["name"] == "Ring"
        assert obj.name == "Ring"
        assert obj.data.name == "Ring"


def test_create_primitive_switches_to_object_mode_before_add(monkeypatch):
    addon, bpy = load_addon(monkeypatch)
    log = []
    bpy.context.mode = "EDIT"

    def mode_set(**kwargs):
        log.append(("mode", kwargs.get("mode"), bpy.context.mode))
        bpy.context.mode = kwargs["mode"]

    def cube_add(**kwargs):
        log.append(("add", bpy.context.mode, "scale" not in kwargs))

    bpy.ops.object = types.SimpleNamespace(mode_set=mode_set)
    _install_mesh_ops(bpy)
    bpy.ops.mesh.primitive_cube_add = cube_add
    obj = _active_object(bpy, name="EditMesh")

    result = addon.BlenderMCPServer().create_primitive(shape="CUBE", name="Separate")

    assert log == [("mode", "OBJECT", "EDIT"), ("add", "OBJECT", True)]
    assert bpy.context.mode == "OBJECT"
    assert result["name"] == "Separate"
    assert obj.name == "Separate"
    assert obj is bpy.context.view_layer.objects.active


def test_create_primitive_rejects_unknown_shape(monkeypatch):
    addon, bpy = load_addon(monkeypatch)
    calls = _install_mesh_ops(bpy)

    with pytest.raises(ValueError, match="Unknown shape"):
        addon.BlenderMCPServer().create_primitive(shape="NOPE")

    assert all(items == [] for items in calls.values())


def _editor_area(area_type, width, height, *, with_window_region=True):
    regions = []
    if with_window_region:
        regions.append(types.SimpleNamespace(type="WINDOW", width=width, height=height))
    return types.SimpleNamespace(
        type=area_type,
        width=width,
        height=height,
        regions=regions,
        spaces=types.SimpleNamespace(active=types.SimpleNamespace()),
    )


def _use_areas(bpy, areas):
    screen = types.SimpleNamespace(areas=list(areas))
    workspace = types.SimpleNamespace(name="Current", screens=[screen])
    window = types.SimpleNamespace(
        workspace=workspace,
        screen=screen,
        scene=types.SimpleNamespace(name="Scene"),
        view_layer=types.SimpleNamespace(name="ViewLayer"),
    )
    bpy.context.window_manager = types.SimpleNamespace(windows=[window])
    return window


def test_screenshot_keeps_visible_view3d(monkeypatch):
    addon, bpy = load_addon(monkeypatch)
    view = _editor_area("VIEW_3D", 800, 600)
    _use_areas(bpy, [view])
    seen = {}

    def capture(_self, view3d_context, filepath, max_size, image_format):
        seen["area"] = view3d_context["area"]
        seen["type_during"] = view.type
        return {"success": True, "width": 10, "height": 8, "filepath": filepath, "method": "test"}

    monkeypatch.setattr(addon.BlenderMCPServer, "_capture_viewport_to_file", capture)

    result = addon.BlenderMCPServer().get_viewport_screenshot(max_size=64)

    assert result["success"] is True
    assert seen["area"] is view
    assert seen["type_during"] == "VIEW_3D"
    assert view.type == "VIEW_3D"


def test_screenshot_borrows_largest_editor_and_restores_it(monkeypatch):
    addon, bpy = load_addon(monkeypatch)
    small = _editor_area("PROPERTIES", 40, 40)
    node_editor = _editor_area("NODE_EDITOR", 900, 500)
    window = _use_areas(bpy, [small, node_editor])
    seen = {}

    def capture(_self, view3d_context, filepath, max_size, image_format):
        seen["area"] = view3d_context["area"]
        seen["types"] = [area.type for area in window.screen.areas]
        return {"success": True, "width": 4, "height": 4, "filepath": filepath, "method": "test"}

    monkeypatch.setattr(addon.BlenderMCPServer, "_capture_viewport_to_file", capture)

    result = addon.BlenderMCPServer().get_viewport_screenshot()

    assert result["success"] is True
    assert seen["area"] is node_editor
    assert seen["types"] == ["PROPERTIES", "VIEW_3D"]
    assert [area.type for area in window.screen.areas] == ["PROPERTIES", "NODE_EDITOR"]
    assert window.workspace.name == "Current"


def test_screenshot_restores_editor_when_capture_fails(monkeypatch):
    addon, bpy = load_addon(monkeypatch)
    node_editor = _editor_area("NODE_EDITOR", 640, 480)
    _use_areas(bpy, [node_editor])

    def capture(*_args, **_kwargs):
        raise RuntimeError("capture failed")

    monkeypatch.setattr(addon.BlenderMCPServer, "_capture_viewport_to_file", capture)

    with pytest.raises(RuntimeError, match="capture failed"):
        addon.BlenderMCPServer().get_viewport_screenshot()

    assert node_editor.type == "NODE_EDITOR"


def test_screenshot_without_any_editor_explains_how_to_recover(monkeypatch):
    addon, bpy = load_addon(monkeypatch)
    window = _use_areas(bpy, [])

    with pytest.raises(ValueError, match="Layout") as exc:
        addon.BlenderMCPServer().get_viewport_screenshot()

    message = str(exc.value)
    assert "execute_blender_code" in message
    assert "bpy.data.workspaces['Layout']" in message
    assert window.screen.areas == []


def test_screenshot_restores_editor_when_area_has_no_window_region(monkeypatch):
    addon, bpy = load_addon(monkeypatch)
    node_editor = _editor_area("NODE_EDITOR", 640, 480, with_window_region=False)
    _use_areas(bpy, [node_editor])

    with pytest.raises(ValueError, match="Layout"):
        addon.BlenderMCPServer().get_viewport_screenshot()

    assert node_editor.type == "NODE_EDITOR"


def test_screenshot_size_check_does_not_touch_editors(monkeypatch):
    addon, bpy = load_addon(monkeypatch)
    node_editor = _editor_area("NODE_EDITOR", 640, 480)
    _use_areas(bpy, [node_editor])

    with pytest.raises(ValueError, match="at least 2"):
        addon.BlenderMCPServer().get_viewport_screenshot(max_size=1)

    assert node_editor.type == "NODE_EDITOR"
