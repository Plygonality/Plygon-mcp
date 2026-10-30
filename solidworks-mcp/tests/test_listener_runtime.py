from __future__ import annotations

import ast
import errno
import json
import socket
import sys
import threading
from pathlib import Path

import pytest

from plygon_solidworks_mcp.listener import (
    MAX_BUFFER_BYTES,
    MAX_COMMANDS_PER_TICK,
    MAX_PENDING_COMMANDS,
    SolidWorksMCPServer,
)

ROOT = Path(__file__).resolve().parents[1]
LISTENER_PATH = ROOT / "src" / "plygon_solidworks_mcp" / "listener.py"
_EXCLUSIVE_SENTINEL = 45123
_SHARED_BIND_HELPERS = (
    "_configure_listener_socket",
    "_address_in_use",
    "_report_start_failure",
)


class FakeSession:
    def __init__(self):
        self.calls = []

    def solidworks_version(self):
        return "test"

    def document_summary(self):
        return {"title": "Part1", "type": "part"}

    def document_info(self, limit=50):
        self.calls.append(("document_info", limit))
        return {"title": "Part1", "limit": limit}

    def create_extruded_box(self, width, depth, height, plane="front", name=""):
        self.calls.append((width, depth, height, plane, name))
        return {"name": name or "Boss-Extrude1"}

    def execute_code(self, code):
        raise AssertionError(code)


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


def _function_ast(path: Path, name: str) -> str:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.dump(node, include_attributes=False)
    raise AssertionError(f"{name} missing from {path}")


def _windows_addr_in_use():
    exc = OSError(
        0,
        "Only one usage of each socket address (protocol/network address/port) is normally permitted",
    )
    exc.winerror = 10048
    return exc


def _http_request(method: str, body: dict) -> bytes:
    payload = json.dumps(body).encode("utf-8")
    head = (
        f"{method} / HTTP/1.1\r\n"
        "Host: 127.0.0.1:9878\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("utf-8")
    return head + payload


def _byte_chunks(payload: bytes, size: int) -> list[bytes]:
    return [payload[index : index + size] for index in range(0, len(payload), size)]


def test_listener_socket_policy_matches_blender():
    blender = ROOT.parent / "blender-mcp" / "addon" / "blender_mcp_addon.py"
    for name in _SHARED_BIND_HELPERS:
        assert _function_ast(LISTENER_PATH, name) == _function_ast(blender, name)


@pytest.mark.parametrize("host", ["", "localhost", "::1"])
def test_listener_coerces_loopback_aliases_to_ipv4(host):
    assert SolidWorksMCPServer(host=host).host == "127.0.0.1"


def test_listener_protocol_work_is_bounded():
    server = SolidWorksMCPServer()
    assert MAX_BUFFER_BYTES == 4 * 1024 * 1024
    assert MAX_PENDING_COMMANDS == 128
    assert server.command_queue.maxsize == MAX_PENDING_COMMANDS
    assert MAX_COMMANDS_PER_TICK == 1


def test_listener_extracts_concatenated_commands():
    from plygon_solidworks_mcp import listener

    ping = {"type": "ping", "params": {}}
    scene = {"type": "get_document_info", "params": {"limit": 5}}
    commands, leftover = listener._extract_json_objects(
        (json.dumps(ping) + json.dumps(scene)).encode("utf-8")
    )
    assert commands == [ping, scene]
    assert leftover == b""
    assert listener._encode_message(ping).endswith(b"\n")


def test_listener_recovers_after_malformed_newline_frame():
    from plygon_solidworks_mcp import listener

    ping = {"type": "ping", "params": {}}
    commands, leftover = listener._extract_json_objects(
        b'{"type":]\n' + json.dumps(ping).encode("utf-8") + b"\n"
    )
    assert commands == [listener._MALFORMED_JSON, ping]
    assert leftover == b""


@pytest.mark.parametrize(
    ("platform_name", "exclusive"),
    [("win32", True), ("linux", False), ("darwin", False)],
)
def test_listener_socket_option_follows_platform(monkeypatch, platform_name, exclusive):
    from plygon_solidworks_mcp import listener

    monkeypatch.setattr(listener.sys, "platform", platform_name)
    if exclusive:
        monkeypatch.setattr(listener.socket, "SO_EXCLUSIVEADDRUSE", _EXCLUSIVE_SENTINEL, raising=False)
    probe = _ProbeSocket()
    monkeypatch.setattr(listener.socket, "socket", lambda *args, **kwargs: probe)
    server = SolidWorksMCPServer()

    assert server.start() is False
    assert server.start_failure is None
    expected = _EXCLUSIVE_SENTINEL if exclusive else socket.SO_REUSEADDR
    assert probe.events[0] == ("setsockopt", socket.SOL_SOCKET, expected, 1)
    assert probe.events[1] == ("bind", ("127.0.0.1", server.port))
    assert probe.events[2][0] == "listen"


@pytest.mark.parametrize(
    ("platform_name", "bind_error"),
    [
        ("linux", OSError(errno.EADDRINUSE, "Address already in use")),
        ("darwin", OSError(errno.EADDRINUSE, "Address already in use")),
        ("win32", _windows_addr_in_use()),
    ],
)
def test_address_in_use_reports_a_clear_message(monkeypatch, capsys, platform_name, bind_error):
    from plygon_solidworks_mcp import listener

    monkeypatch.setattr(listener.sys, "platform", platform_name)
    if platform_name == "win32":
        monkeypatch.setattr(listener.socket, "SO_EXCLUSIVEADDRUSE", _EXCLUSIVE_SENTINEL, raising=False)
    probe = _ProbeSocket(bind_error=bind_error)
    monkeypatch.setattr(listener.socket, "socket", lambda *args, **kwargs: probe)
    server = SolidWorksMCPServer(port=9878)

    assert server.start() is False
    message = listener._port_in_use_message("127.0.0.1", 9878)
    assert "Blender Lab" not in message
    assert server.start_failure == message
    assert f"PlygonMCP: {message}" in capsys.readouterr().out


def test_other_bind_errors_stay_generic(monkeypatch, capsys):
    from plygon_solidworks_mcp import listener

    probe = _ProbeSocket(bind_error=OSError("network is down"))
    monkeypatch.setattr(listener.socket, "socket", lambda *args, **kwargs: probe)

    assert SolidWorksMCPServer().start() is False
    assert "failed to start: network is down" in capsys.readouterr().out


def test_busy_port_reports_that_it_is_already_in_use(capsys):
    from plygon_solidworks_mcp import listener

    holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    holder.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    holder.bind(("127.0.0.1", 0))
    holder.listen(1)
    port = holder.getsockname()[1]
    server = SolidWorksMCPServer(port=port)
    try:
        assert server.start() is False
        message = listener._port_in_use_message("127.0.0.1", port)
        assert server.start_failure == message
        assert f"PlygonMCP: {message}" in capsys.readouterr().out
    finally:
        holder.close()


def test_start_without_a_running_session_does_not_listen(capsys):
    server = SolidWorksMCPServer(port=0)
    try:
        assert server.start() is False
        assert server.running is False
        assert server.socket is None
        assert "Windows" in (server.start_failure or "")
    finally:
        if server.running:
            server.stop()
    assert "listening on" not in capsys.readouterr().out


def test_injected_session_answers_ping_on_the_socket():
    server = SolidWorksMCPServer(port=0)
    session = FakeSession()
    assert server.start(session=session)
    try:
        with socket.create_connection(("127.0.0.1", server.port), timeout=2) as client:
            client.sendall(json.dumps({"type": "ping", "params": {}}).encode() + b"\n")
            client.settimeout(2)
            data = b""
            while b"\n" not in data:
                data += client.recv(4096)
        payload = json.loads(data.decode())
        assert payload["result"] == {"pong": True}
    finally:
        server.stop()


def test_command_dispatch_filters_unknown_fields():
    server = SolidWorksMCPServer()
    server.session = FakeSession()
    response = server.execute_command(
        {
            "type": "create_extruded_box",
            "params": {
                "width": 60,
                "depth": 40,
                "height": 12,
                "plane": "front",
                "name": "Rib",
                "extra": True,
            },
        }
    )
    assert response["status"] == "success"
    assert server.session.calls == [(60, 40, 12, "front", "Rib")]


def test_unknown_command_is_an_error_result():
    server = SolidWorksMCPServer()
    server.session = FakeSession()
    response = server.execute_command({"type": "delete_everything", "params": {}})
    assert response["status"] == "error"
    assert "Unknown command" in response["message"]


def test_disconnected_client_work_is_discarded():
    server = SolidWorksMCPServer()
    server.running = True
    server.session = FakeSession()
    closed = threading.Event()
    closed.set()
    server.command_queue.put_nowait(({"type": "get_document_info"}, object(), closed, None))

    assert server._drain_command_queue() is True
    assert server.session.calls == []


def test_framer_extracts_execute_code_hidden_in_http_body():
    from plygon_solidworks_mcp import listener

    attack = {"type": "execute_code", "params": {"code": "print('MARKER')"}}
    commands, leftover = listener._extract_json_objects(_http_request("POST", attack))
    assert attack in commands
    assert leftover == b""


@pytest.mark.parametrize(
    "method",
    ["GET", "POST", "PUT", "DELETE", "HEAD", "OPTIONS", "PATCH", "CONNECT", "TRACE"],
)
def test_http_request_is_rejected_before_execute_code(method, capsys):
    attack = {"type": "execute_code", "params": {"code": "print('MARKER')"}}
    server = SolidWorksMCPServer()
    server.running = True
    server.session = FakeSession()
    client = FakeClient([_http_request(method, attack)])

    server._handle_client(client)

    assert server.command_queue.empty()
    assert client.sent == []
    assert client.closed is True
    assert "rejected HTTP request" in capsys.readouterr().out
    assert server.session.calls == []


@pytest.mark.parametrize("chunk_size", [1, 4])
def test_split_protocol_message_is_queued(chunk_size):
    ping = {"type": "ping", "params": {}}
    server = SolidWorksMCPServer()
    server.running = True
    raw = json.dumps(ping).encode("utf-8") + b"\n"
    client = FakeClient(_byte_chunks(raw, chunk_size))

    server._handle_client(client)

    command, _client, _closed, protocol_error = server.command_queue.get_nowait()
    assert command == ping
    assert protocol_error is None


def test_windows_cmd_wrapper_starts_the_listener():
    repo = ROOT.parent
    cmd = (repo / "scripts" / "start-solidworks.cmd").read_text(encoding="utf-8")
    ps1 = (repo / "scripts" / "start-solidworks.ps1").read_text(encoding="utf-8")
    for text in (cmd, ps1):
        assert "start_listener.py" in text
        assert "pywin32" in text
        assert "solidworks-mcp" in text


def test_real_socket_option_matches_this_platform():
    from plygon_solidworks_mcp import listener

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
