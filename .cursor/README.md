Project MCP for this clone. Cursor launches `uv run` against `blender-mcp/` and `houdini-mcp/`.

If you already added `houdini` / `plygon-blender` in **user** `~/.cursor/mcp.json` (the Windows `uvx --from git+…` config), disable project MCP or you will run two clients on 9876 and 9877.

Green here still only means the stdio process started. Blender and Houdini must be listening in the GUI.
