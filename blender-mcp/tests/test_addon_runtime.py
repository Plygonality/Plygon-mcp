from __future__ import annotations

import importlib.util
import json
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


def test_server_start_reports_bind_failure(monkeypatch):
    addon, _bpy = load_addon(monkeypatch)

    class FailingSocket:
        def setsockopt(self, *args):
            return None

        def bind(self, address):
            raise OSError("address already in use")

        def close(self):
            return None

    monkeypatch.setattr(addon.socket, "socket", lambda *args: FailingSocket())
    server = addon.BlenderMCPServer()

    assert server.start() is False
    assert server.running is False
    assert server.socket is None


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
