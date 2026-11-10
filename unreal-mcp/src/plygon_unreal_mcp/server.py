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
        "The listener runs inside the editor on the game thread. "
        "Prefer structured tools (spawn_actor, set_actor_transform, delete_actor, "
        "import_asset, set_pcg_parameter, generate_pcg) for simple edits. "
        "Use execute_unreal_python for anything more complex, in small steps. "
        "Unreal is Z-up and 1 unit is 1 centimetre. "
        "rotation is pitch, yaw, roll in degrees. "
        "Editor mutations are wrapped in a transaction, so Ctrl+Z undoes them. "
        "After meaningful changes, call get_level_info and/or get_viewport_screenshot. "
        "Save the user's level before destructive operations. "
        "This bridge is separate from Epic's Unreal MCP plugin. Do not assume that "
        "plugin is this connection."
    ),
)


def _json(result: Any) -> str:
    return json.dumps(result, indent=2, default=str)


@mcp.tool()
def ping_unreal() -> str:
    """Check that the Unreal Editor listener is reachable and responding."""
    unreal_editor = get_unreal_connection()
    return _json(unreal_editor.send_command("ping"))


@mcp.tool()
def get_addon_info() -> str:
    """Return listener version, engine version, and supported command names."""
    unreal_editor = get_unreal_connection()
    return _json(unreal_editor.send_command("get_addon_info"))


@mcp.tool()
def get_level_info(limit: int = 50) -> str:
    """Get the open editor world, viewport camera, selection, and the first actors.

    `limit` caps how many actor rows are included.
    """
    unreal_editor = get_unreal_connection()
    return _json(unreal_editor.send_command("get_level_info", {"limit": limit}))


@mcp.tool()
def list_actors(class_filter: str = "", limit: int = 50) -> str:
    """List actors in the editor world.

    class_filter matches the actor class name or label, case-insensitive.
    Examples: StaticMeshActor, PointLight, Camera.
    """
    unreal_editor = get_unreal_connection()
    return _json(
        unreal_editor.send_command(
            "list_actors", {"class_filter": class_filter, "limit": limit}
        )
    )


@mcp.tool()
def get_actor_info(name: str) -> str:
    """Get one actor by label, object name, or path."""
    unreal_editor = get_unreal_connection()
    return _json(unreal_editor.send_command("get_actor_info", {"name": name}))


@mcp.tool()
def select_actors(names: Optional[List[str]] = None, mode: str = "REPLACE") -> str:
    """Select actors by label or path.

    mode is REPLACE (default) or ADD. An empty list with REPLACE clears the selection.
    """
    unreal_editor = get_unreal_connection()
    return _json(
        unreal_editor.send_command(
            "select_actors", {"names": names or [], "mode": mode}
        )
    )


@mcp.tool()
def spawn_actor(
    kind: str = "static_mesh",
    name: str = "",
    location: Optional[List[float]] = None,
    rotation: Optional[List[float]] = None,
    scale: Optional[List[float]] = None,
    mesh: str = "",
) -> str:
    """Spawn an actor in the current level.

    kind: static_mesh, point_light, spot_light, directional_light, rect_light,
    camera, cine_camera.

    location is [x, y, z] in centimetres. rotation is [pitch, yaw, roll] in
    degrees. scale is [x, y, z].

    mesh is a static mesh asset path such as /Engine/BasicShapes/Cube. When
    kind is static_mesh and mesh is omitted, the listener uses that cube if
    the asset exists.
    """
    unreal_editor = get_unreal_connection()
    params: Dict[str, Any] = {
        "kind": kind,
        "name": name,
        "location": location or [0.0, 0.0, 0.0],
        "rotation": rotation or [0.0, 0.0, 0.0],
        "mesh": mesh,
    }
    if scale is not None:
        params["scale"] = scale
    return _json(unreal_editor.send_command("spawn_actor", params))


@mcp.tool()
def set_actor_transform(
    name: str,
    location: Optional[List[float]] = None,
    rotation: Optional[List[float]] = None,
    scale: Optional[List[float]] = None,
) -> str:
    """Move, rotate, or scale an actor. Omitted fields stay as they are.

    location is centimetres. rotation is pitch, yaw, roll in degrees.
    """
    unreal_editor = get_unreal_connection()
    params: Dict[str, Any] = {"name": name}
    if location is not None:
        params["location"] = location
    if rotation is not None:
        params["rotation"] = rotation
    if scale is not None:
        params["scale"] = scale
    return _json(unreal_editor.send_command("set_actor_transform", params))


@mcp.tool()
def delete_actor(name: str) -> str:
    """Delete an actor by label, object name, or path."""
    unreal_editor = get_unreal_connection()
    return _json(unreal_editor.send_command("delete_actor", {"name": name}))


@mcp.tool()
def list_assets(
    directory: str = "/Game",
    recursive: bool = True,
    limit: int = 50,
    class_filter: str = "",
) -> str:
    """List asset paths under a Content Browser directory such as /Game.

    class_filter is matched against the asset class path when it is set.
    Leave it empty to skip class lookups.
    """
    unreal_editor = get_unreal_connection()
    return _json(
        unreal_editor.send_command(
            "list_assets",
            {
                "directory": directory,
                "recursive": recursive,
                "limit": limit,
                "class_filter": class_filter,
            },
        )
    )


@mcp.tool()
def import_asset(
    filename: str,
    destination_path: str = "/Game/PlygonImport",
    destination_name: str = "",
    replace_existing: bool = True,
    save: bool = True,
) -> str:
    """Import a file from disk into the Content Browser.

    filename is an absolute path the editor can read. The import is automated,
    so it does not open a dialog.
    """
    unreal_editor = get_unreal_connection()
    return _json(
        unreal_editor.send_command(
            "import_asset",
            {
                "filename": filename,
                "destination_path": destination_path,
                "destination_name": destination_name,
                "replace_existing": replace_existing,
                "save": save,
            },
        )
    )


@mcp.tool()
def get_viewport_screenshot(max_size: int = 1000) -> Image:
    """Capture the level editor viewport and return it as an image.

    The editor writes the PNG on a later tick. The listener waits for that
    file before answering. Keep a level viewport open. max_size is both the
    width and the height of the requested capture.
    """
    unreal_editor = get_unreal_connection()
    temp_path = os.path.join(
        tempfile.gettempdir(), f"plygon_mcp_{os.getpid()}_{uuid.uuid4().hex}.png"
    )
    try:
        result = unreal_editor.send_command(
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
def execute_unreal_python(code: str) -> str:
    """Execute Python inside the Unreal Editor with `unreal` available.

    Break complex tasks into small steps. print() is returned, truncated to
    256 KiB with a `…[truncated N bytes]` note when the print is larger.
    The call is one editor transaction. This is full local code execution
    for any process that can connect to the listener port.
    """
    unreal_editor = get_unreal_connection()
    result = unreal_editor.send_command("execute_code", {"code": code})
    return _json(result)


@mcp.tool()
def list_pcg(directory: str = "/Game", limit: int = 50, include_assets: bool = True) -> str:
    """List PCG components in the level and, optionally, PCG graph assets.

    Requires the PCG plugin. Graph parameter names are not enumerated. The
    5.4 Python API used here does not expose a parameter-name listing call.
    """
    unreal_editor = get_unreal_connection()
    return _json(
        unreal_editor.send_command(
            "list_pcg",
            {"directory": directory, "limit": limit, "include_assets": include_assets},
        )
    )


@mcp.tool()
def set_pcg_parameter(
    name: str,
    parameter: str,
    value: Any,
    value_type: str = "float",
    component_index: int = 0,
) -> str:
    """Set one parameter on an actor's PCG graph instance.

    name is the actor label or path. value_type is bool, float, double, int,
    int64, string, name, or vector. vector is [x, y, z].
    The write uses PCGGraphParametersHelpers on the component's graph instance.
    """
    unreal_editor = get_unreal_connection()
    return _json(
        unreal_editor.send_command(
            "set_pcg_parameter",
            {
                "name": name,
                "parameter": parameter,
                "value": value,
                "value_type": value_type,
                "component_index": component_index,
            },
        )
    )


@mcp.tool()
def generate_pcg(name: str, force: bool = True, component_index: int = 0) -> str:
    """Generate a PCG component on an actor.

    Calls PCGComponent.generate. force defaults to true.
    """
    unreal_editor = get_unreal_connection()
    return _json(
        unreal_editor.send_command(
            "generate_pcg",
            {"name": name, "force": force, "component_index": component_index},
        )
    )


@mcp.prompt()
def unreal_agent_strategy() -> str:
    """Recommended workflow when driving Unreal Editor from Cursor."""
    return """# Unreal agent strategy (Plygon MCP)

1. Orient with get_level_info before changing the level.
2. Prefer spawn_actor, set_actor_transform, delete_actor, import_asset, and the PCG tools for simple edits.
3. Use execute_unreal_python for anything those tools do not cover. One step per call. print() returns stdout.
4. Unreal is Z-up. 1 unit is 1 centimetre. rotation is pitch, yaw, roll in degrees.
5. After a meaningful change, call get_level_info or get_viewport_screenshot.
6. Mutations are editor transactions. The user can undo them.
7. PCG tools need the PCG plugin. Parameter names come from the graph. This bridge does not list them.
8. Epic's Unreal MCP plugin is a different server. This connection is the Plygon listener on 127.0.0.1:9879.
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
