Project MCP for this clone. Cursor launches `uv run` against `blender-mcp/`, `houdini-mcp/`, and `solidworks-mcp/`.

If the user `~/.cursor/mcp.json` also defines `plygon-houdini`, `plygon-blender`, or `plygon-solidworks`, Cursor merges each same-name server and gives project fields precedence. It does not launch two same-name copies. Open a different local project when you need to verify the user-wide `uvx --from git+…` config exactly.

Do not create a second alias for any bridge: differently named entries can launch competing clients against ports 9876, 9877, and 9878.

Green here still only means the stdio process started. Blender and Houdini must be listening in the GUI. SOLIDWORKS must be open, and `scripts/start-solidworks.cmd` must be listening, on the Windows PC that runs the desktop app. A cloud checkout cannot attach to that COM session.

For the complete installation and verification sequence, follow the root [click-by-click guide](../README.md#install-both-mcps--exact-click-by-click-guide). On Windows that guide uses `.cmd` installers (PowerShell may block `.ps1`), tells you to skip uv reinstall when `uvx --version` already works, and treats a Houdini Console error about `.cursor/houdini-mcp` / `fxhoudinimcp` as a different MCP.
