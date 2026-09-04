from __future__ import annotations

import json
import socket
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_addon_file_exists_and_has_bl_info():
    addon = (ROOT / "addon" / "blender_mcp_addon.py").read_text(encoding="utf-8")
    assert 'bl_info = {' in addon
    assert "Plygon Blender MCP" in addon
    assert "_extract_json_objects" in addon
    assert "PLYGONMCP_OT_StartServer" in addon


def test_package_version():
    import plygon_blender_mcp

    assert plygon_blender_mcp.__version__


def test_extract_one_json_concatenated_payloads():
    from plygon_blender_mcp.connection import extract_one_json

    ping = json.dumps({"status": "success", "result": {"pong": True}})
    scene = json.dumps({"status": "success", "result": {"objects": ["Cube"]}})
    blob = (ping + scene).encode("utf-8")

    with pytest.raises(json.JSONDecodeError, match="Extra data"):
        json.loads(blob.decode("utf-8"))

    first, rest = extract_one_json(blob)
    assert first == {"status": "success", "result": {"pong": True}}
    second, leftover = extract_one_json(rest)
    assert second == {"status": "success", "result": {"objects": ["Cube"]}}
    assert leftover.strip() == b""


def test_connection_receive_complete_json():
    from plygon_blender_mcp.connection import BlenderConnection

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
            # send in two chunks to exercise reassembly
            client.sendall(payload[:10])
            client.sendall(payload[10:])

    t = threading.Thread(target=serve, daemon=True)
    t.start()

    conn = BlenderConnection(host=host, port=port)
    assert conn.connect()
    result = conn.send_command("ping")
    assert result == {"pong": True}
    conn.disconnect()
    server.close()
    t.join(timeout=2)


def test_connection_receive_concatenated_json():
    from plygon_blender_mcp.connection import BlenderConnection

    ping = json.dumps({"status": "success", "result": {"pong": True}})
    scene = json.dumps({"status": "success", "result": {"objects": ["Cube"]}})
    blob = (ping + scene).encode("utf-8")

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

    t = threading.Thread(target=serve, daemon=True)
    t.start()

    conn = BlenderConnection(host=host, port=port)
    assert conn.connect()
    assert conn.send_command("ping") == {"pong": True}
    assert conn.send_command("get_scene_info") == {"objects": ["Cube"]}
    conn.disconnect()
    server.close()
    t.join(timeout=2)


def test_server_tools_registered():
    from plygon_blender_mcp.server import mcp

    manager = getattr(mcp, "_tool_manager", None)
    if manager is None or not hasattr(manager, "list_tools"):
        pytest.skip("FastMCP tool manager API unavailable")
    names = {t.name for t in manager.list_tools()}
    for required in (
        "ping_blender",
        "get_scene_info",
        "execute_blender_code",
        "create_primitive",
        "set_material",
        "get_viewport_screenshot",
    ):
        assert required in names
