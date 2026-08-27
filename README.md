# Plygon

Tech art and bpy tooling.

## Blender MCP (Cursor)

Local Model Context Protocol bridge so Cursor agents can drive Blender:

→ [`blender-mcp/`](blender-mcp/README.md)

Quick path:

1. Install the add-on from `blender-mcp/addon/blender_mcp_addon.py`
2. In Blender: **N → PlygonMCP → Start MCP Server**
3. Point Cursor at `blender-mcp/configs/cursor.mcp.json` (set absolute paths)
