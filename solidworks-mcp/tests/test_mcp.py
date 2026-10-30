from __future__ import annotations

import json
import re
import socket
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_package_version():
    import plygon_solidworks_mcp

    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version = "([^"]+)"', pyproject, re.MULTILINE)
    assert match
    assert plygon_solidworks_mcp.__version__ == match.group(1)


def test_default_port_is_the_third_dcc_slot():
    from plygon_solidworks_mcp.connection import DEFAULT_PORT
    from plygon_solidworks_mcp.listener import DEFAULT_PORT as LISTENER_PORT

    assert DEFAULT_PORT == LISTENER_PORT == 9878


def test_extract_one_json_concatenated_payloads():
    from plygon_solidworks_mcp.connection import extract_one_json

    ping = json.dumps({"status": "success", "result": {"pong": True}})
    scene = json.dumps({"status": "success", "result": {"title": "Part1"}})
    blob = (ping + scene).encode("utf-8")

    with pytest.raises(json.JSONDecodeError, match="Extra data"):
        json.loads(blob.decode("utf-8"))

    first, rest = extract_one_json(blob)
    assert first["result"]["pong"] is True
    second, leftover = extract_one_json(rest)
    assert second["result"]["title"] == "Part1"
    assert leftover.strip() == b""


def test_connection_receive_concatenated_json():
    from plygon_solidworks_mcp.connection import SolidWorksConnection

    ping = json.dumps({"status": "success", "result": {"pong": True}})
    scene = json.dumps({"status": "success", "result": {"title": "Part1"}})
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

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    conn = SolidWorksConnection(host=host, port=port)
    assert conn.connect()
    assert conn.send_command("ping") == {"pong": True}
    assert conn.send_command("get_document_info") == {"title": "Part1"}
    conn.disconnect()
    server.close()
    thread.join(timeout=2)


def test_solidworks_error_keeps_connection():
    from plygon_solidworks_mcp.connection import SolidWorksConnection

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
    conn = SolidWorksConnection(host=host, port=port)
    assert conn.connect()
    with pytest.raises(RuntimeError, match="nope"):
        conn.send_command("ping")
    assert conn.sock is not None
    assert conn.send_command("ping") == {"pong": True}
    conn.disconnect()
    server.close()
    thread.join(timeout=2)


def test_falsy_result_is_preserved():
    from plygon_solidworks_mcp.connection import SolidWorksConnection

    payload = (json.dumps({"status": "success", "result": 0}) + "\n").encode("utf-8")
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
    conn = SolidWorksConnection(host=host, port=port)
    assert conn.send_command("ping") == 0
    conn.disconnect()
    server.close()
    thread.join(timeout=2)


def test_refused_message_mentions_the_listener_and_cloud_agents():
    from plygon_solidworks_mcp.connection import REFUSED_MESSAGE, TIMEOUT_MESSAGE

    text = REFUSED_MESSAGE.format(host="127.0.0.1", port=9878)
    assert "9878" in text
    assert "start-solidworks.cmd" in text
    assert "Cloud Agent" in text
    assert "Cloud Agent" in TIMEOUT_MESSAGE.format(host="127.0.0.1", port=9878)


def test_combined_configs_list_solidworks_beside_the_other_dccs():
    repo = ROOT.parent
    for name in ("cursor.mcp.json", "cursor.mcp.windows.json"):
        cfg = json.loads((repo / "configs" / name).read_text(encoding="utf-8"))
        servers = cfg["mcpServers"]
        assert set(servers) >= {"plygon-blender", "plygon-houdini", "plygon-solidworks"}
        env = servers["plygon-solidworks"]["env"]
        assert env["SOLIDWORKS_HOST"] == "127.0.0.1"
        assert env["SOLIDWORKS_PORT"] == "9878"


def test_root_readme_embeds_the_combined_configs():
    repo = ROOT.parent
    readme = (repo / "README.md").read_text(encoding="utf-8")
    for name in ("cursor.mcp.windows.json", "cursor.mcp.json"):
        config = (repo / "configs" / name).read_text(encoding="utf-8").strip()
        assert config in readme


def test_server_tools_registered():
    pytest.importorskip("mcp")
    from plygon_solidworks_mcp.server import mcp

    manager = getattr(mcp, "_tool_manager", None)
    if manager is None or not hasattr(manager, "list_tools"):
        pytest.skip("FastMCP tool manager API unavailable")
    names = {tool.name for tool in manager.list_tools()}
    for required in (
        "ping_solidworks",
        "get_document_info",
        "execute_solidworks_code",
        "create_extruded_box",
        "get_viewport_screenshot",
        "export_document",
        "new_document",
    ):
        assert required in names
