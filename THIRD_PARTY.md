# Third-party notices

Plygon Blender MCP follows the localhost-TCP + FastMCP pattern published as
[ahujasid/blender-mcp](https://github.com/ahujasid/blender-mcp) by Siddharth Ahuja (MIT).

This repo is a **local, no-telemetry fork** for Cursor and studio pipelines.
It is not a from-zero protocol.

Houdini MCP is Plygon work that reuses that same bridge shape
(stdio MCP ↔ localhost TCP ↔ DCC listener).

SOLIDWORKS MCP is Plygon work on that same shape. The listener calls
Dassault Systèmes' SOLIDWORKS COM API. Dassault does not publish this server.

Unreal MCP is Plygon work on that same shape. The listener calls Epic's
Unreal Editor Python API. Epic's own Unreal MCP plugin is a separate editor
feature and is not this server.

Upstream license: MIT. Copyright (c) 2025 Siddharth Ahuja — reproduced in `LICENSE`.
