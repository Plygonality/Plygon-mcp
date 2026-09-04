#!/usr/bin/env python3
"""Smoke-test the MCP package imports and optional live Houdini ping.

  # Offline (no Houdini required)
  python scripts/smoke_test.py

  # Live (Houdini listener must be running)
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
    from plygon_houdini_mcp import __version__
    from plygon_houdini_mcp.connection import HoudiniConnection, DEFAULT_HOST, DEFAULT_PORT
    from plygon_houdini_mcp.server import mcp, main

    assert __version__
    assert DEFAULT_HOST and DEFAULT_PORT
    assert callable(main)
    assert mcp is not None
    assert HoudiniConnection is not None
    print(f"OK imports (version {__version__})")


def test_tool_registration() -> None:
    from plygon_houdini_mcp.server import mcp

    tools = getattr(mcp, "_tool_manager", None)
    if tools is not None and hasattr(tools, "list_tools"):
        names = sorted(t.name for t in tools.list_tools())
        print(f"OK tools registered ({len(names)}): {', '.join(names)}")
        required = {
            "ping_houdini",
            "get_scene_info",
            "execute_houdini_code",
            "create_primitive",
            "get_viewport_screenshot",
            "create_node",
        }
        missing = required - set(names)
        assert not missing, f"Missing tools: {missing}"
    else:
        print("OK server module loaded (tool manager introspection unavailable)")


def test_live_ping(host: str, port: int) -> None:
    from plygon_houdini_mcp.connection import HoudiniConnection

    conn = HoudiniConnection(host=host, port=port)
    if not conn.connect():
        raise SystemExit(
            f"FAIL: could not connect to {host}:{port}. "
            "Start the listener in Houdini first."
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
    parser.add_argument("--live", action="store_true", help="Ping a running Houdini listener")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9877)
    args = parser.parse_args()

    test_imports()
    test_tool_registration()

    if args.live:
        if not port_open(args.host, args.port):
            print(f"FAIL: nothing listening on {args.host}:{args.port}")
            return 1
        test_live_ping(args.host, args.port)
    else:
        print("Skip live ping (pass --live when Houdini listener is running)")

    print("All smoke checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
