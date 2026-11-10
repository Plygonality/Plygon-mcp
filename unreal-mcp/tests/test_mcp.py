from __future__ import annotations

import json
import re
import socket
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_listener_file_exists():
    listener = (ROOT / "editor" / "plygon_unreal_mcp" / "listener.py").read_text(encoding="utf-8")
    assert "UnrealMCPServer" in listener
    assert "register_slate_post_tick_callback" in listener
    assert "unregister_slate_post_tick_callback" in listener
    assert "register_python_shutdown_callback" in listener
    assert "ScopedEditorTransaction" in listener
    assert "self.execute_command(command)" in listener
    handle = listener.split("def _handle_client", 1)[1].split("def execute_command", 1)[0]
    assert "self.execute_command" not in handle
    loop = listener.split("def _server_loop", 1)[1].split("def _note_game_thread", 1)[0]
    assert "unreal." not in loop
    init_unreal = (ROOT / "editor" / "init_unreal.py").read_text(encoding="utf-8")
    assert "start_server" in init_unreal


def test_package_version():
    import plygon_unreal_mcp

    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version = "([^"]+)"', pyproject, re.MULTILINE)
    assert match
    expected = match.group(1)
    editor_init = (ROOT / "editor" / "plygon_unreal_mcp" / "__init__.py").read_text(encoding="utf-8")
    assert plygon_unreal_mcp.__version__ == expected
    assert f'__version__ = "{expected}"' in editor_init
    assert expected == "0.2.1"


def test_extract_one_json_concatenated_payloads():
    from plygon_unreal_mcp.connection import extract_one_json

    ping = json.dumps({"status": "success", "result": {"pong": True}})
    level = json.dumps({"status": "success", "result": {"world_name": "Untitled"}})
    blob = (ping + level).encode("utf-8")

    with pytest.raises(json.JSONDecodeError, match="Extra data"):
        json.loads(blob.decode("utf-8"))

    first, rest = extract_one_json(blob)
    assert first == {"status": "success", "result": {"pong": True}}
    second, leftover = extract_one_json(rest)
    assert second == {"status": "success", "result": {"world_name": "Untitled"}}
    assert leftover.strip() == b""


def test_connection_receive_complete_json():
    from plygon_unreal_mcp.connection import UnrealConnection

    payload = json.dumps({"status": "success", "result": {"pong": True}}).encode("utf-8")

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    host, port = server.getsockname()

    def serve():
        client, _ = server.accept()
        with client:
            data = client.recv(65536)
            assert b"ping" in data
            client.sendall(payload[:10])
            client.sendall(payload[10:])

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()

    conn = UnrealConnection(host=host, port=port)
    assert conn.connect()
    result = conn.send_command("ping")
    assert result == {"pong": True}
    conn.disconnect()
    server.close()
    thread.join(timeout=2)


def test_connection_receive_concatenated_json():
    from plygon_unreal_mcp.connection import UnrealConnection

    ping = json.dumps({"status": "success", "result": {"pong": True}})
    level = json.dumps({"status": "success", "result": {"world_name": "Untitled"}})
    blob = (ping + level).encode("utf-8")

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    host, port = server.getsockname()

    def serve():
        client, _ = server.accept()
        with client:
            client.recv(65536)
            client.sendall(blob)
            try:
                client.recv(65536)
            except Exception:
                pass

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()

    conn = UnrealConnection(host=host, port=port)
    assert conn.connect()
    assert conn.send_command("ping") == {"pong": True}
    assert conn.send_command("get_level_info") == {"world_name": "Untitled"}
    conn.disconnect()
    server.close()
    thread.join(timeout=2)


def test_resolve_loopback_host():
    from plygon_unreal_mcp.connection import resolve_loopback_host

    assert resolve_loopback_host("localhost") == "127.0.0.1"
    assert resolve_loopback_host("::1") == "127.0.0.1"
    assert resolve_loopback_host("") == "127.0.0.1"
    assert resolve_loopback_host("10.0.0.5") == "10.0.0.5"


def test_unreal_error_keeps_connection():
    from plygon_unreal_mcp.connection import UnrealConnection

    err = (json.dumps({"status": "error", "message": "nope"}) + "\n").encode("utf-8")
    ok = (json.dumps({"status": "success", "result": {"pong": True}}) + "\n").encode("utf-8")

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    host, port = server.getsockname()

    def serve():
        client, _ = server.accept()
        with client:
            client.recv(65536)
            client.sendall(err)
            client.recv(65536)
            client.sendall(ok)

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()

    conn = UnrealConnection(host=host, port=port)
    assert conn.connect()
    with pytest.raises(RuntimeError, match="nope"):
        conn.send_command("ping")
    assert conn.sock is not None
    assert conn.send_command("ping") == {"pong": True}
    conn.disconnect()
    server.close()
    thread.join(timeout=2)


def test_unreal_preserves_falsy_result():
    from plygon_unreal_mcp.connection import UnrealConnection

    payload = (json.dumps({"status": "success", "result": False}) + "\n").encode("utf-8")
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    host, port = server.getsockname()

    def serve():
        client, _ = server.accept()
        with client:
            client.recv(65536)
            client.sendall(payload)

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    conn = UnrealConnection(host=host, port=port)

    assert conn.send_command("ping") is False

    conn.disconnect()
    server.close()
    thread.join(timeout=2)


def test_server_tools_registered():
    pytest.importorskip("mcp")
    from plygon_unreal_mcp.server import mcp

    manager = getattr(mcp, "_tool_manager", None)
    if manager is None or not hasattr(manager, "list_tools"):
        pytest.skip("FastMCP tool manager API unavailable")
    names = {tool.name for tool in manager.list_tools()}
    for required in (
        "ping_unreal",
        "get_addon_info",
        "get_level_info",
        "list_actors",
        "select_actors",
        "spawn_actor",
        "set_actor_transform",
        "delete_actor",
        "list_assets",
        "import_asset",
        "get_viewport_screenshot",
        "execute_unreal_python",
        "list_pcg",
        "set_pcg_parameter",
        "generate_pcg",
    ):
        assert required in names


def test_default_port_is_9879():
    from plygon_unreal_mcp.connection import DEFAULT_HOST, DEFAULT_PORT

    assert DEFAULT_HOST == "127.0.0.1"
    assert DEFAULT_PORT == 9879
