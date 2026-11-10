"""FastMCP server exposing Unreal Editor tools to Cursor and other MCP clients."""

from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, List, Optional

from mcp.server.fastmcp import FastMCP, Image

from .connection import get_unreal_connection, reset_connection

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("PlygonUnrealMCP")


@asynccontextmanager
async def server_lifespan(server: FastMCP) -> AsyncIterator[Dict[str, Any]]:
    logger.info(
        "Plygon Unreal MCP starting (UNREAL_HOST=%s UNREAL_PORT=%s)",
        os.getenv("UNREAL_HOST", "127.0.0.1"),
        os.getenv("UNREAL_PORT", "9879"),
    )
    try:
        yield {}
    finally:
        reset_connection()
        logger.info("Plygon Unreal MCP shut down")


mcp = FastMCP(
    "plygon-unreal-mcp",
    lifespan=server_lifespan,
    instructions=(
        "You are connected to a local Unreal Editor through Plygon Unreal MCP. "
        "Prefer structured tools for actor, asset, and PCG edits. "
        "Use execute_python for anything those tools do not cover, in small steps. "
        "After meaningful changes, call get_level_info and/or get_viewport_screenshot. "
        "Editor mutations are undoable in the editor with Edit > Undo. "
        "Save the user's level before destructive operations. "
        "This bridge is separate from Epic's Unreal MCP plugin."
    ),
)


def _json(result: Any) -> str:
    return json.dumps(result, indent=2, default=str)


@mcp.tool()
def ping_unreal() -> str:
    """Check that the Unreal Editor TCP listener is reachable and responding."""
    unreal = get_unreal_connection()
    return _json(unreal.send_command("ping"))


@mcp.tool()
def get_addon_info() -> str:
    """Return listener version, engine version, and supported command capabilities."""
    unreal = get_unreal_connection()
    return _json(unreal.send_command("get_addon_info"))


@mcp.tool()
def get_level_info(limit: int = 50) -> str:
    """Get the current editor level: path, actor count, a limited actor list, and the selection."""
    unreal = get_unreal_connection()
    return _json(unreal.send_command("get_level_info", {"limit": limit}))


@mcp.tool()
def list_actors(limit: int = 100) -> str:
    """List loaded actors in the current editor level, up to `limit`."""
    unreal = get_unreal_connection()
    return _json(unreal.send_command("list_actors", {"limit": limit}))


@mcp.tool()
def select_actors(names: List[str], mode: str = "REPLACE") -> str:
    """Select actors by label, object name, or path. mode is REPLACE (default) or ADD."""
    unreal = get_unreal_connection()
    return _json(unreal.send_command("select_actors", {"names": names, "mode": mode}))


@mcp.tool()
def spawn_actor(
    kind: str = "static_mesh",
    name: str = "",
    location: Optional[List[float]] = None,
    rotation: Optional[List[float]] = None,
    scale: Optional[List[float]] = None,
    mesh_path: str = "",
) -> str:
    """Spawn an actor in the current level.

    kind: static_mesh, cube, point_light, directional_light, spot_light, camera, cine_camera.
    location is x, y, z in world units. rotation is pitch, yaw, roll in degrees.
    A static mesh uses mesh_path, or the engine Basic Shapes cube when mesh_path is empty.
    The spawn is one editor transaction.
    """
    unreal = get_unreal_connection()
    params: Dict[str, Any] = {
        "kind": kind,
        "name": name,
        "location": location or [0.0, 0.0, 0.0],
        "rotation": rotation or [0.0, 0.0, 0.0],
        "scale": scale or [1.0, 1.0, 1.0],
        "mesh_path": mesh_path,
    }
    return _json(unreal.send_command("spawn_actor", params))


@mcp.tool()
def set_actor_transform(
    name: str,
    location: Optional[List[float]] = None,
    rotation: Optional[List[float]] = None,
    scale: Optional[List[float]] = None,
) -> str:
    """Set location, rotation, or scale on one actor. Omit fields you do not want to change.

    location is x, y, z. rotation is pitch, yaw, roll in degrees. scale is x, y, z.
    The change is one editor transaction.
    """
    unreal = get_unreal_connection()
    params: Dict[str, Any] = {"name": name}
    if location is not None:
        params["location"] = location
    if rotation is not None:
        params["rotation"] = rotation
    if scale is not None:
        params["scale"] = scale
    return _json(unreal.send_command("set_actor_transform", params))


@mcp.tool()
def delete_actor(name: str) -> str:
    """Delete one actor by label, object name, or path. The delete is one editor transaction."""
    unreal = get_unreal_connection()
    return _json(unreal.send_command("delete_actor", {"name": name}))


@mcp.tool()
def list_assets(directory: str = "/Game", recursive: bool = True, limit: int = 100) -> str:
    """List asset paths under a Content Browser directory. `/Game` is the project content root."""
    unreal = get_unreal_connection()
    return _json(
        unreal.send_command(
            "list_assets",
            {"directory": directory, "recursive": recursive, "limit": limit},
        )
    )


@mcp.tool()
def import_asset(
    filename: str,
    destination_path: str = "/Game",
    destination_name: str = "",
    replace_existing: bool = False,
) -> str:
    """Import a file from disk into the Content Browser. The import is one editor transaction.

    filename is an absolute path on this machine. destination_path is a Content Browser
    directory such as `/Game/Imported`.
    """
    unreal = get_unreal_connection()
    return _json(
        unreal.send_command(
            "import_asset",
            {
                "filename": filename,
                "destination_path": destination_path,
                "destination_name": destination_name,
                "replace_existing": replace_existing,
            },
        )
    )


@mcp.tool()
def get_viewport_screenshot(max_size: int = 1000) -> Image:
    """Capture the level viewport and return it as an image.

    The capture is max_size by max_size pixels. The editor writes the file on a
    later tick, and this call waits for that file.
    """
    unreal = get_unreal_connection()
    temp_path = os.path.join(
        tempfile.gettempdir(), f"plygon_mcp_{os.getpid()}_{uuid.uuid4().hex}.png"
    )
    written = temp_path
    try:
        result = unreal.send_command(
            "get_viewport_screenshot",
            {"max_size": max_size, "filepath": temp_path},
        )
        if isinstance(result, dict) and result.get("error"):
            raise RuntimeError(result["error"])

        written = result.get("filepath", temp_path) if isinstance(result, dict) else temp_path
        if not os.path.exists(written):
            raise RuntimeError("Screenshot file was not created")

        with open(written, "rb") as handle:
            image_bytes = handle.read()
        return Image(data=image_bytes, format="png")
    finally:
        for candidate in {temp_path, written}:
            try:
                os.remove(candidate)
            except OSError:
                pass


@mcp.tool()
def execute_python(code: str) -> str:
    """Execute Python inside the Unreal Editor with the `unreal` module available.

    Break complex tasks into small steps. print() is captured and returned,
    truncated to 256 KiB with a `…[truncated N bytes]` note when the print is
    larger. The call is one editor transaction, so Edit > Undo reverts editor
    changes the script recorded. Prefer saving the level before destructive edits.
    """
    unreal = get_unreal_connection()
    return _json(unreal.send_command("execute_python", {"code": code}))


@mcp.tool()
def list_pcg(limit: int = 50) -> str:
    """List PCG components in the current level and the graph asset each one uses."""
    unreal = get_unreal_connection()
    return _json(unreal.send_command("list_pcg", {"limit": limit}))


@mcp.tool()
def set_pcg_parameter(
    name: str,
    value: Any,
    actor: str = "",
    value_type: str = "",
) -> str:
    """Set one parameter on a PCG graph instance.

    actor is a label, object name, or path. Leave it empty when the level has one
    PCG component. value_type is bool, int, int64, float, double, string, name, or
    vector. When value_type is empty, the value's Python type selects the setter.
    The change is one editor transaction.
    """
    unreal = get_unreal_connection()
    return _json(
        unreal.send_command(
            "set_pcg_parameter",
            {"actor": actor, "name": name, "value": value, "value_type": value_type},
        )
    )


@mcp.tool()
def generate_pcg(actor: str = "", force: bool = True) -> str:
    """Generate PCG components. Leave actor empty to generate every component in the level.

    The generate call is one editor transaction.
    """
    unreal = get_unreal_connection()
    return _json(unreal.send_command("generate_pcg", {"actor": actor, "force": force}))


@mcp.prompt()
def unreal_agent_strategy() -> str:
    """Recommended workflow when driving Unreal Editor from Cursor."""
    return """# Unreal agent strategy (Plygon MCP)

1. Orient. Call get_level_info before changing the level.
2. Prefer spawn_actor, set_actor_transform, delete_actor, and the PCG tools for simple edits.
3. Use execute_python for anything those tools do not cover. One logical step per call.
4. After a meaningful change, call get_level_info or get_viewport_screenshot.
5. Spawns, transforms, deletes, imports, PCG edits, and execute_python are editor transactions. The user can revert the last one with Edit > Undo.
6. Coordinates are Unreal world units. Rotation is pitch, yaw, roll in degrees.
7. This bridge is not Epic's Unreal MCP. Do not assume that plugin's tools are the ones listed here.
"""


def main() -> None:
    """Entry point used by Cursor / `uv run` / console script."""
    try:
        interactive = sys.stdin.isatty()
    except (AttributeError, OSError):
        interactive = False

    if interactive:
        logger.info(
            "Plygon Unreal MCP is waiting for an MCP client on stdin "
            "(Cursor launches this automatically. Ctrl-C to exit)."
        )
    mcp.run()


if __name__ == "__main__":
    main()
