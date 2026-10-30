"""FastMCP server exposing SOLIDWORKS tools to Cursor and other MCP clients."""

from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, Optional

from mcp.server.fastmcp import FastMCP, Image

from .connection import get_solidworks_connection, reset_connection

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("PlygonSolidWorksMCP")


@asynccontextmanager
async def server_lifespan(server: FastMCP) -> AsyncIterator[Dict[str, Any]]:
    logger.info(
        "Plygon SOLIDWORKS MCP starting (SOLIDWORKS_HOST=%s SOLIDWORKS_PORT=%s)",
        os.getenv("SOLIDWORKS_HOST", "127.0.0.1"),
        os.getenv("SOLIDWORKS_PORT", "9878"),
    )
    try:
        yield {}
    finally:
        reset_connection()
        logger.info("Plygon SOLIDWORKS MCP shut down")


mcp = FastMCP(
    "plygon-solidworks-mcp",
    lifespan=server_lifespan,
    instructions=(
        "You are connected to a local SOLIDWORKS session through Plygon SOLIDWORKS MCP. "
        "The listener runs on the Windows PC where SOLIDWORKS is already open. "
        "Prefer structured tools (get_document_info, create_extruded_box, set_custom_property, "
        "export_document) for simple edits. Use execute_solidworks_code for anything more "
        "complex, in small steps. Length arguments are in the part's current unit "
        "(millimetres on an MMGS template), not meters. "
        "A box is a center rectangle on the named plane extruded along that plane's normal. "
        "After meaningful changes, call get_document_info and/or get_viewport_screenshot. "
        "Save the user's file before destructive operations."
    ),
)


def _json(result: Any) -> str:
    return json.dumps(result, indent=2, default=str)


@mcp.tool()
def ping_solidworks() -> str:
    """Check that the SOLIDWORKS listener TCP server is reachable and responding."""
    solidworks = get_solidworks_connection()
    return _json(solidworks.send_command("ping"))


@mcp.tool()
def get_addon_info() -> str:
    """Return listener version, SOLIDWORKS revision, and supported command capabilities."""
    solidworks = get_solidworks_connection()
    return _json(solidworks.send_command("get_addon_info"))


@mcp.tool()
def get_document_info(limit: int = 50) -> str:
    """Get the active document: type, path, length unit, and the first features.

    `limit` caps how many feature-tree rows are included.
    """
    solidworks = get_solidworks_connection()
    return _json(solidworks.send_command("get_document_info", {"limit": limit}))


@mcp.tool()
def list_features(limit: int = 50) -> str:
    """List features in the active document, oldest first, up to `limit`."""
    solidworks = get_solidworks_connection()
    return _json(solidworks.send_command("list_features", {"limit": limit}))


@mcp.tool()
def get_mass_properties() -> str:
    """Read mass (kg), volume (m³), surface area (m²), and center of mass (m)."""
    solidworks = get_solidworks_connection()
    return _json(solidworks.send_command("get_mass_properties"))


@mcp.tool()
def get_custom_properties() -> str:
    """Read custom properties on the active document (configuration '' )."""
    solidworks = get_solidworks_connection()
    return _json(solidworks.send_command("get_custom_properties"))


@mcp.tool()
def set_custom_property(name: str, value: str) -> str:
    """Set one document custom property. Overwrites an existing text property."""
    solidworks = get_solidworks_connection()
    return _json(
        solidworks.send_command("set_custom_property", {"name": name, "value": value})
    )


@mcp.tool()
def new_document(kind: str = "part") -> str:
    """Open a new SOLIDWORKS document from the default template.

    kind: part, assembly, or drawing.
    """
    solidworks = get_solidworks_connection()
    return _json(solidworks.send_command("new_document", {"kind": kind}))


@mcp.tool()
def create_extruded_box(
    width: float,
    depth: float,
    height: float,
    plane: str = "front",
    name: str = "",
) -> str:
    """Extrude a centered rectangle on the active part.

    width, depth, and height use the part's current length unit. On an MMGS
    template, 60 means 60 mm. plane is front, top, or right: the first three
    reference planes in a default template, matched by type so the label can
    be localized. The rectangle lies on that plane. height is the extrusion
    along the plane normal.
    """
    solidworks = get_solidworks_connection()
    return _json(
        solidworks.send_command(
            "create_extruded_box",
            {
                "width": width,
                "depth": depth,
                "height": height,
                "plane": plane,
                "name": name,
            },
        )
    )


@mcp.tool()
def rebuild() -> str:
    """Rebuild the active document."""
    solidworks = get_solidworks_connection()
    return _json(solidworks.send_command("rebuild"))


@mcp.tool()
def save_document(filepath: str = "") -> str:
    """Save the active document. Pass filepath to save a copy; omit to save in place."""
    solidworks = get_solidworks_connection()
    params: Dict[str, Any] = {}
    if filepath:
        params["filepath"] = filepath
    return _json(solidworks.send_command("save_document", params))


@mcp.tool()
def export_document(filepath: str) -> str:
    """Export the active document. The extension picks the format.

    Supported: .step, .stp, .iges, .igs, .stl, .pdf, .x_t, .x_b, .3mf
    """
    solidworks = get_solidworks_connection()
    return _json(solidworks.send_command("export_document", {"filepath": filepath}))


@mcp.tool()
def get_viewport_screenshot(max_size: int = 1000) -> Image:
    """Capture the current SOLIDWORKS view and return it as a PNG.

    Keep the model window visible. The listener fits the view, saves a bitmap,
    and converts it to PNG.
    """
    solidworks = get_solidworks_connection()
    temp_path = os.path.join(
        tempfile.gettempdir(), f"plygon_sw_{os.getpid()}_{uuid.uuid4().hex}.png"
    )
    try:
        result = solidworks.send_command(
            "get_viewport_screenshot",
            {"max_size": max_size, "filepath": temp_path},
        )
        if isinstance(result, dict) and result.get("error"):
            raise RuntimeError(result["error"])

        path = result.get("filepath", temp_path) if isinstance(result, dict) else temp_path
        if not os.path.exists(path):
            raise RuntimeError("Screenshot file was not created")

        with open(path, "rb") as handle:
            image_bytes = handle.read()
        return Image(data=image_bytes, format="png")
    finally:
        try:
            os.remove(temp_path)
        except OSError:
            pass


@mcp.tool()
def execute_solidworks_code(code: str) -> str:
    """Run Python in the listener process with `sw` and `model` in scope.

    `sw` is the running SOLIDWORKS application. `model` is the active document,
    or None when nothing is open. This is full local code execution for any
    process that can connect to the listener port. Break work into small steps.
    print() is returned, truncated to 256 KiB.
    """
    solidworks = get_solidworks_connection()
    result = solidworks.send_command("execute_code", {"code": code})
    return _json(result)


@mcp.prompt()
def solidworks_agent_strategy() -> str:
    """Recommended workflow when driving SOLIDWORKS from Cursor."""
    return """# SOLIDWORKS agent strategy (Plygon MCP)

1. **Orient** — `get_document_info` (and optionally `get_viewport_screenshot`) before changing anything.
2. **Plan small** — Prefer `new_document`, `create_extruded_box`, `set_custom_property`, and `export_document`.
3. **Units** — width, depth, and height are in the document's length unit. An MMGS part uses millimetres. The API itself is meters; the listener converts.
4. **Code carefully** — Use `execute_solidworks_code` for holes, mates, drawings, and configurations. One logical step per call. `sw` is the application and `model` is the active document.
5. **Verify** — After each meaningful change, rebuild if the geometry changed, then check document info and a viewport screenshot.
6. **Don't destroy silently** — Ask before overwriting a saved part. Save first.
7. **Window** — SOLIDWORKS must stay open on the Windows machine. The listener does not start a second session.
"""


def main() -> None:
    """Entry point used by Cursor / `uv run` / console script."""
    try:
        interactive = sys.stdin.isatty()
    except (AttributeError, OSError):
        interactive = False

    if interactive:
        logger.info(
            "Plygon SOLIDWORKS MCP is waiting for an MCP client on stdin "
            "(Cursor launches this automatically — Ctrl-C to exit)."
        )
    mcp.run()


if __name__ == "__main__":
    main()
