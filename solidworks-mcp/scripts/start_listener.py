#!/usr/bin/env python3
"""Attach to a running SOLIDWORKS window and listen on 127.0.0.1:9878.

SOLIDWORKS has no Python shell, so this companion process is the DCC side of
the bridge. Leave it running. It does not launch SOLIDWORKS.

  uv run --directory solidworks-mcp --with pywin32 python solidworks-mcp/scripts/start_listener.py

On Windows, scripts/start-solidworks.cmd does that for you.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from plygon_solidworks_mcp.listener import main


if __name__ == "__main__":
    raise SystemExit(main())
