#!/usr/bin/env python3
"""Smoke-test the MCP package imports and an optional live editor ping.

  # Offline (no Unreal Editor required)
  python scripts/smoke_test.py

  # Live (the editor listener must be running)
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


def check_imports() -> None:
    from plygon_unreal_mcp import __version__
    from plygon_unreal_mcp.connection import DEFAULT_HOST, DEFAULT_PORT, UnrealConnection
    from plygon_unreal_mcp.server import main, mcp

    assert __version__
    assert DEFAULT_HOST == "127.0.0.1"
    assert DEFAULT_PORT == 9879
    assert callable(main)
    assert mcp is not None
    assert UnrealConnection is not None
    print(f"OK imports (version {__version__})")


def check_tool_registration() -> None:
    from plygon_unreal_mcp.server import mcp

    tools = getattr(mcp, "_tool_manager", None)
    if tools is not None and hasattr(tools, "list_tools"):
        names = sorted(tool.name for tool in tools.list_tools())
        print(f"OK tools registered ({len(names)}): {', '.join(names)}")
        required = {
            "ping_unreal",
            "get_level_info",
            "execute_unreal_python",
            "spawn_actor",
            "get_viewport_screenshot",
            "list_pcg",
            "generate_pcg",
        }
        missing = required - set(names)
        assert not missing, f"Missing tools: {missing}"
    else:
        print("OK server module loaded (tool manager introspection unavailable)")


def run_live_ping(host: str, port: int) -> None:
    from plygon_unreal_mcp.connection import UnrealConnection

    conn = UnrealConnection(host=host, port=port)
    if not conn.connect():
        raise SystemExit(
            f"FAIL: could not connect to {host}:{port}. "
            "Start the listener in the Unreal Editor first "
            "(Output Log should say listening on 127.0.0.1:9879)."
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
    parser.add_argument("--live", action="store_true", help="Ping a running Unreal Editor listener")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9879)
    args = parser.parse_args()

    check_imports()
    check_tool_registration()

    if args.live:
        if not port_open(args.host, args.port):
            print(
                f"FAIL: nothing listening on {args.host}:{args.port} (connection refused). "
                "Start the Unreal Editor listener."
            )
            return 1
        run_live_ping(args.host, args.port)
    else:
        print("Skip live ping (pass --live when the Unreal Editor listener is running)")

    print("All smoke checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
