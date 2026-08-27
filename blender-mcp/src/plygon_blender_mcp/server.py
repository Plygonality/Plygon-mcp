"""FastMCP server exposing Blender tools to Cursor and other MCP clients."""

from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

from mcp.server.fastmcp import FastMCP, Image

from .connection import get_blender_connection, reset_connection

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("PlygonBlenderMCP")


@asynccontextmanager
async def server_lifespan(server: FastMCP) -> AsyncIterator[Dict[str, Any]]:
    logger.info(
        "Plygon Blender MCP starting (BLENDER_HOST=%s BLENDER_PORT=%s)",
        os.getenv("BLENDER_HOST", "localhost"),
        os.getenv("BLENDER_PORT", "9876"),
    )
    try:
        yield {}
    finally:
        reset_connection()
        logger.info("Plygon Blender MCP shut down")


mcp = FastMCP(
    "plygon-blender-mcp",
    lifespan=server_lifespan,
    instructions=(
        "You are connected to a local Blender instance through Plygon Blender MCP. "
        "Prefer structured tools (create_primitive, set_material, set_object_transform) "
        "for simple edits. Use execute_blender_code for anything more complex, in small "
        "steps. After meaningful changes, call get_scene_info and/or get_viewport_screenshot "
        "to verify results. Always save the user's .blend before destructive operations."
    ),
)


def _json(result: Any) -> str:
    return json.dumps(result, indent=2, default=str)


@mcp.tool()
def ping_blender() -> str:
    """Check that the Blender addon TCP server is reachable and responding."""
    blender = get_blender_connection()
    return _json(blender.send_command("ping"))


@mcp.tool()
def get_addon_info() -> str:
    """Return addon version, Blender version, and supported command capabilities."""
    blender = get_blender_connection()
    return _json(blender.send_command("get_addon_info"))


@mcp.tool()
def get_scene_info(limit: int = 50) -> str:
    """Get structured information about the current Blender scene.

    Includes objects (up to `limit`), cameras, lights, materials, selection,
    frame range, and render settings.
    """
    blender = get_blender_connection()
    return _json(blender.send_command("get_scene_info", {"limit": limit}))


@mcp.tool()
def list_objects(object_type: str = "") -> str:
    """List objects in the scene. Optionally filter by type (MESH, LIGHT, CAMERA, …)."""
    blender = get_blender_connection()
    return _json(blender.send_command("list_objects", {"object_type": object_type}))


@mcp.tool()
def get_object_info(object_name: str) -> str:
    """Get detailed info for one object: transform, materials, mesh stats, etc."""
    blender = get_blender_connection()
    return _json(blender.send_command("get_object_info", {"name": object_name}))


@mcp.tool()
def get_viewport_screenshot(max_size: int = 1000) -> Image:
    """Capture the current 3D viewport and return it as an image for visual review."""
    blender = get_blender_connection()
    temp_path = os.path.join(tempfile.gettempdir(), f"plygon_mcp_{os.getpid()}.png")
    result = blender.send_command(
        "get_viewport_screenshot",
        {"max_size": max_size, "filepath": temp_path, "format": "png"},
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
def execute_blender_code(code: str) -> str:
    """Execute Python code inside Blender with `bpy` and `mathutils` available.

    Break complex tasks into small steps. Capture prints with print() — stdout
    is returned. Prefer saving the user's file before destructive edits.
    """
    blender = get_blender_connection()
    result = blender.send_command("execute_code", {"code": code})
    return _json(result)


@mcp.tool()
def create_primitive(
    shape: str = "CUBE",
    name: str = "",
    location: Optional[List[float]] = None,
    rotation: Optional[List[float]] = None,
    scale: Optional[List[float]] = None,
    size: float = 2.0,
) -> str:
    """Create a mesh primitive.

    shape: CUBE, SPHERE, CYLINDER, CONE, TORUS, PLANE, MONKEY, ICO_SPHERE
    """
    blender = get_blender_connection()
    params: Dict[str, Any] = {
        "shape": shape,
        "name": name,
        "location": location or [0.0, 0.0, 0.0],
        "rotation": rotation or [0.0, 0.0, 0.0],
        "scale": scale or [1.0, 1.0, 1.0],
        "size": size,
    }
    return _json(blender.send_command("create_primitive", params))


@mcp.tool()
def delete_object(object_name: str) -> str:
    """Delete an object by name."""
    blender = get_blender_connection()
    return _json(blender.send_command("delete_object", {"name": object_name}))


@mcp.tool()
def set_object_transform(
    object_name: str,
    location: Optional[List[float]] = None,
    rotation: Optional[List[float]] = None,
    scale: Optional[List[float]] = None,
) -> str:
    """Set location / rotation_euler / scale on an object. Omit fields you don't want to change."""
    blender = get_blender_connection()
    params: Dict[str, Any] = {"name": object_name}
    if location is not None:
        params["location"] = location
    if rotation is not None:
        params["rotation"] = rotation
    if scale is not None:
        params["scale"] = scale
    return _json(blender.send_command("set_object_transform", params))


@mcp.tool()
def set_material(
    object_name: str,
    material_name: str = "",
    color: Optional[List[float]] = None,
    metallic: float = 0.0,
    roughness: float = 0.5,
    create_new: bool = True,
) -> str:
    """Assign a Principled BSDF material. color is RGBA in 0–1 (default light gray)."""
    blender = get_blender_connection()
    params: Dict[str, Any] = {
        "object_name": object_name,
        "material_name": material_name,
        "color": color or [0.8, 0.8, 0.8, 1.0],
        "metallic": metallic,
        "roughness": roughness,
        "create_new": create_new,
    }
    return _json(blender.send_command("set_material", params))


@mcp.tool()
def select_objects(names: List[str], mode: str = "REPLACE") -> str:
    """Select objects by name. mode: REPLACE (default) or ADD."""
    blender = get_blender_connection()
    return _json(blender.send_command("select_objects", {"names": names, "mode": mode}))


@mcp.tool()
def export_scene(filepath: str, format: str = "GLB") -> str:
    """Export the scene. format: GLB, GLTF, FBX, OBJ, or BLEND."""
    blender = get_blender_connection()
    return _json(blender.send_command("export_scene", {"filepath": filepath, "format": format}))


@mcp.prompt()
def blender_agent_strategy() -> str:
    """Recommended workflow when driving Blender from Cursor."""
    return """# Blender agent strategy (Plygon MCP)

1. **Orient** — `get_scene_info` (and optionally `get_viewport_screenshot`) before changing anything.
2. **Plan small** — Prefer `create_primitive`, `set_material`, `set_object_transform` for simple edits.
3. **Code carefully** — Use `execute_blender_code` for topology, modifiers, animation, nodes. One logical step per call; print() useful state.
4. **Verify** — After each meaningful change, re-check with scene info and/or a viewport screenshot.
5. **Don't destroy silently** — Ask before deleting large amounts of work; prefer renaming/hiding when unsure.
6. **Coordinates** — Blender is Z-up, right-handed. Location/rotation/scale are world-space unless parenting says otherwise.
"""


def main() -> None:
    """Entry point used by Cursor / `uv run` / console script."""
    try:
        interactive = sys.stdin.isatty()
    except (AttributeError, OSError):
        interactive = False

    if interactive:
        logger.info(
            "Plygon Blender MCP is waiting for an MCP client on stdin "
            "(Cursor launches this automatically — Ctrl-C to exit)."
        )
    mcp.run()


if __name__ == "__main__":
    main()
