from __future__ import annotations

import json
import socket
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_listener_file_exists():
    listener = (ROOT / "package" / "scripts" / "python" / "plygon_houdini_mcp" / "listener.py").read_text(
        encoding="utf-8"
    )
    assert "HoudiniMCPServer" in listener
    assert "executeInMainThreadWithResult" in listener
    assert "Plygon Houdini MCP" in listener


def test_package_manifest_exists():
    manifest = ROOT / "package" / "plygon_houdini_mcp.json"
    assert manifest.is_file()
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert "env" in data


def test_shelf_tool_exists():
    shelf = (ROOT / "package" / "toolbar" / "plygon_houdini_mcp.shelf").read_text(encoding="utf-8")
    assert "Start MCP Server" in shelf
    assert "plygon_houdini_mcp" in shelf


def test_package_version():
    import plygon_houdini_mcp

    assert plygon_houdini_mcp.__version__


def test_connection_receive_complete_json():
    from plygon_houdini_mcp.connection import HoudiniConnection

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

    t = threading.Thread(target=serve, daemon=True)
    t.start()

    conn = HoudiniConnection(host=host, port=port)
    assert conn.connect()
    result = conn.send_command("ping")
    assert result == {"pong": True}
    conn.disconnect()
    server.close()
    t.join(timeout=2)


def test_server_tools_registered():
    from plygon_houdini_mcp.server import mcp

    manager = getattr(mcp, "_tool_manager", None)
    if manager is None or not hasattr(manager, "list_tools"):
        pytest.skip("FastMCP tool manager API unavailable")
    names = {t.name for t in manager.list_tools()}
    for required in (
        "ping_houdini",
        "get_scene_info",
        "execute_houdini_code",
        "create_primitive",
        "get_viewport_screenshot",
        "create_node",
        "connect_nodes",
    ):
        assert required in names
