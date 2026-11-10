"""Start the Plygon Unreal listener when the editor runs this file.

Copy this file to the project's Content/Python/init_unreal.py together with the
plygon_unreal_mcp package directory, or point a Startup script at this copy.
"""

from __future__ import annotations

import sys
from pathlib import Path

_here = Path(__file__).resolve().parent
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))

import unreal  # noqa: E402

from plygon_unreal_mcp.listener import start_server  # noqa: E402

_server = start_server()
if _server is None:
    unreal.log_error("PlygonMCP: listener did not start. See the lines above in the Output Log.")
