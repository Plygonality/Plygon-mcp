Project MCP for this clone. Cursor launches `uv run` against `blender-mcp/`, `houdini-mcp/`, `solidworks-mcp/`, and `unreal-mcp/`.

If the user `~/.cursor/mcp.json` also defines `plygon-houdini`, `plygon-blender`, `plygon-solidworks`, or `plygon-unreal`, Cursor merges each same-name server and gives project fields precedence. It does not launch two same-name copies. Open a different local project when you need to verify the user-wide `uvx --from git+…` config exactly.

Do not create a second alias for any bridge: differently named entries can launch competing clients against ports 9876, 9877, 9878, and 9879.

Green here still only means the stdio process started. Blender and Houdini must be listening in the GUI. SOLIDWORKS must be open, and `scripts/start-solidworks.cmd` must be listening, on the Windows PC that runs the desktop app. Unreal Editor must print `listening on 127.0.0.1:9879`. A cloud checkout cannot attach to that COM session or to the editor.

For the complete installation and verification sequence, follow the root [click-by-click guide](../README.md#install-both-mcps--exact-click-by-click-guide). On Windows that guide uses `.cmd` installers (PowerShell may block `.ps1`), tells you to skip uv reinstall when `uvx --version` already works, and treats a Houdini Console error about `.cursor/houdini-mcp` / `fxhoudinimcp` as a different MCP.
