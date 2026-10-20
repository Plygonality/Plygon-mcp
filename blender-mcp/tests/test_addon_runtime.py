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
