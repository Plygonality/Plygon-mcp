"""FastMCP server exposing Houdini tools to Cursor and other MCP clients."""

from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, List, Optional

from mcp.server.fastmcp import FastMCP, Image

from .connection import get_houdini_connection, reset_connection

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("PlygonHoudiniMCP")


@asynccontextmanager
async def server_lifespan(server: FastMCP) -> AsyncIterator[Dict[str, Any]]:
    logger.info(
        "Plygon Houdini MCP starting (HOUDINI_HOST=%s HOUDINI_PORT=%s)",
        os.getenv("HOUDINI_HOST", "127.0.0.1"),
        os.getenv("HOUDINI_PORT", "9877"),
    )
    try:
        yield {}
    finally:
        reset_connection()
        logger.info("Plygon Houdini MCP shut down")


mcp = FastMCP(
    "plygon-houdini-mcp",
    lifespan=server_lifespan,
    instructions=(
        "You are connected to a local SideFX Houdini instance through Plygon Houdini MCP. "
        "Prefer structured tools (create_node, set_node_parm, connect_nodes, create_primitive) "
        "for simple edits. Use execute_houdini_code for anything more complex, in small "
        "steps. After meaningful changes, call get_scene_info and/or get_viewport_screenshot "
        "to verify results. Houdini is Y-up. Save the user's .hip before destructive operations."
    ),
)


def _json(result: Any) -> str:
    return json.dumps(result, indent=2, default=str)


@mcp.tool()
def ping_houdini() -> str:
    """Check that the Houdini listener TCP server is reachable and responding."""
    houdini = get_houdini_connection()
    return _json(houdini.send_command("ping"))


@mcp.tool()
def get_addon_info() -> str:
    """Return listener version, Houdini version, and supported command capabilities."""
    houdini = get_houdini_connection()
    return _json(houdini.send_command("get_addon_info"))


@mcp.tool()
def get_scene_info(limit: int = 50) -> str:
    """Get structured information about the current Houdini scene.

    Includes hip file path, frame range, top-level /obj nodes (up to `limit),
    and current selection.
    """
    houdini = get_houdini_connection()
    return _json(houdini.send_command("get_scene_info", {"limit": limit}))


@mcp.tool()
def list_nodes(parent_path: str = "/obj", node_type: str = "", recursive: bool = False) -> str:
    """List child nodes under a parent path. Optionally filter by node type."""
    houdini = get_houdini_connection()
    return _json(
        houdini.send_command(
            "list_nodes",
            {"parent_path": parent_path, "node_type": node_type, "recursive": recursive},
        )
    )


@mcp.tool()
def get_node_info(node_path: str) -> str:
    """Get detailed info for one node: type, parms, inputs/outputs, geometry stats."""
    houdini = get_houdini_connection()
    return _json(houdini.send_command("get_node_info", {"node_path": node_path}))


@mcp.tool()
def create_node(parent_path: str, node_type: str, name: str = "") -> str:
    """Create a node under parent_path. Examples: geo under /obj, box under /obj/geo1."""
    houdini = get_houdini_connection()
    return _json(
        houdini.send_command(
            "create_node",
            {"parent_path": parent_path, "node_type": node_type, "name": name},
        )
    )


@mcp.tool()
def delete_node(node_path: str) -> str:
    """Delete a node by path."""
    houdini = get_houdini_connection()
    return _json(houdini.send_command("delete_node", {"node_path": node_path}))


@mcp.tool()
def set_node_parm(node_path: str, parm_name: str, value: Any) -> str:
    """Set a parameter on a node. value can be a number, string, or list for tuples."""
    houdini = get_houdini_connection()
    return _json(
        houdini.send_command(
            "set_node_parm",
            {"node_path": node_path, "parm_name": parm_name, "value": value},
        )
    )


@mcp.tool()
def connect_nodes(output_node_path: str, input_node_path: str, input_index: int = 0) -> str:
    """Wire output_node into input_node at the given input index."""
    houdini = get_houdini_connection()
    return _json(
        houdini.send_command(
            "connect_nodes",
            {
                "output_node_path": output_node_path,
                "input_node_path": input_node_path,
                "input_index": input_index,
            },
        )
    )


@mcp.tool()
def layout_nodes(parent_path: str) -> str:
    """Auto-layout child nodes in a network (e.g. /obj/geo1)."""
    houdini = get_houdini_connection()
    return _json(houdini.send_command("layout_nodes", {"parent_path": parent_path}))


@mcp.tool()
def cook_node(node_path: str, block: bool = True) -> str:
    """Force-cook a node to update its geometry/output."""
    houdini = get_houdini_connection()
    return _json(houdini.send_command("cook_node", {"node_path": node_path, "block": block}))


@mcp.tool()
def execute_houdini_code(code: str) -> str:
    """Execute Python code inside Houdini with `hou` available.

    Break complex tasks into small steps. Capture prints with print() — stdout
    is returned. Prefer saving the user's hip before destructive edits.
    """
    houdini = get_houdini_connection()
    result = houdini.send_command("execute_code", {"code": code})
    return _json(result)


@mcp.tool()
def execute_hscript(command: str) -> str:
    """Execute an HScript command in Houdini."""
    houdini = get_houdini_connection()
    result = houdini.send_command("execute_hscript", {"command": command})
    return _json(result)


@mcp.tool()
def get_viewport_screenshot(max_size: int = 1000) -> Image:
    """Capture the current Scene Viewer and return it as an image for visual review."""
    houdini = get_houdini_connection()
    temp_path = os.path.join(tempfile.gettempdir(), f"plygon_mcp_{os.getpid()}.png")
    result = houdini.send_command(
        "get_viewport_screenshot",
        {"max_size": max_size, "filepath": temp_path},
    )
    if isinstance(result, dict) and result.get("error"):
        raise RuntimeError(result["error"])

    path = result.get("filepath", temp_path) if isinstance(result, dict) else temp_path
    if not os.path.exists(path):
        raise RuntimeError("Screenshot file was not created")

    with open(path, "rb") as f:
        image_bytes = f.read()
    try:
        os.remove(path)
    except OSError:
        pass
    return Image(data=image_bytes, format="png")


@mcp.tool()
def save_hip(filepath: str = "") -> str:
    """Save the current hip file. Pass filepath to save-as; omit to overwrite current."""
    houdini = get_houdini_connection()
    params: Dict[str, Any] = {}
    if filepath:
        params["filepath"] = filepath
    return _json(houdini.send_command("save_hip", params))


@mcp.tool()
def create_primitive(
    shape: str = "box",
    name: str = "",
    parent_path: str = "/obj",
    size: float = 1.0,
    location: Optional[List[float]] = None,
) -> str:
    """Create a SOP primitive inside a new geo object.

    shape: box, sphere, grid, tube, torus, circle, line
    """
    houdini = get_houdini_connection()
    params: Dict[str, Any] = {
        "shape": shape,
        "name": name,
        "parent_path": parent_path,
        "size": size,
        "location": location or [0.0, 0.0, 0.0],
    }
    return _json(houdini.send_command("create_primitive", params))


@mcp.prompt()
def houdini_agent_strategy() -> str:
    """Recommended workflow when driving Houdini from Cursor."""
    return """# Houdini agent strategy (Plygon MCP)

1. **Orient** — `get_scene_info` (and optionally `get_viewport_screenshot`) before changing anything.
2. **Plan small** — Prefer `create_primitive`, `create_node`, `set_node_parm`, `connect_nodes` for simple edits.
3. **Code carefully** — Use `execute_houdini_code` for VEX wrangles, complex SOP chains, DOPs, LOPs. One logical step per call; print() useful state.
4. **Verify** — After each meaningful change, re-check with scene info and/or a viewport screenshot.
5. **Don't destroy silently** — Ask before deleting large networks; prefer bypass/hide when unsure.
6. **Coordinates** — Houdini is Y-up, right-handed. /obj contains geo containers; SOPs live inside geo nodes.
7. **Cook** — Call `cook_node` after parameter changes when you need fresh geometry stats.
"""


def main() -> None:
    """Entry point used by Cursor / `uv run` / console script."""
    try:
        interactive = sys.stdin.isatty()
    except (AttributeError, OSError):
        interactive = False

    if interactive:
        logger.info(
            "Plygon Houdini MCP is waiting for an MCP client on stdin "
            "(Cursor launches this automatically — Ctrl-C to exit)."
        )
    mcp.run()


if __name__ == "__main__":
    main()
