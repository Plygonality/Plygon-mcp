#!/usr/bin/env python3
"""Smoke-test the MCP package imports and optional live Blender ping.

  # Offline (no Blender required)
  python scripts/smoke_test.py

  # Live (Blender addon must be listening)
  python scripts/smoke_test.py --live
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def test_imports() -> None:
    from plygon_blender_mcp import __version__
    from plygon_blender_mcp.connection import BlenderConnection, DEFAULT_HOST, DEFAULT_PORT
    from plygon_blender_mcp.server import mcp, main

    assert __version__
    assert DEFAULT_HOST and DEFAULT_PORT
    assert callable(main)
    assert mcp is not None
    assert BlenderConnection is not None
    print(f"OK imports (version {__version__})")


def test_tool_registration() -> None:
    from plygon_blender_mcp.server import mcp

    # FastMCP keeps tools in an internal registry; probe via list_tools if available.
    tools = getattr(mcp, "_tool_manager", None)
    if tools is not None and hasattr(tools, "list_tools"):
        names = sorted(t.name for t in tools.list_tools())
        print(f"OK tools registered ({len(names)}): {', '.join(names)}")
        required = {
            "ping_blender",
            "get_scene_info",
            "execute_blender_code",
            "create_primitive",
            "get_viewport_screenshot",
        }
        missing = required - set(names)
        assert not missing, f"Missing tools: {missing}"
    else:
        print("OK server module loaded (tool manager introspection unavailable)")


def test_live_ping(host: str, port: int) -> None:
    from plygon_blender_mcp.connection import BlenderConnection

    conn = BlenderConnection(host=host, port=port)
    if not conn.connect():
        raise SystemExit(
            f"FAIL: could not connect to {host}:{port}. "
            "Start the addon in Blender first."
        )
    result = conn.send_command("ping")
    print("OK live ping:", json.dumps(result))
    info = conn.send_command("get_addon_info")
    print("OK addon info:", json.dumps(info, indent=2))
    conn.disconnect()


def port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1.0):
            return True
    except OSError:
        return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="Ping a running Blender addon")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9876)
    args = parser.parse_args()

    test_imports()
    test_tool_registration()

    if args.live:
        if not port_open(args.host, args.port):
            print(f"FAIL: nothing listening on {args.host}:{args.port}")
            return 1
        test_live_ping(args.host, args.port)
    else:
        print("Skip live ping (pass --live when Blender addon is running)")

    print("All smoke checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
