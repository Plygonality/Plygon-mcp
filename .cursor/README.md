Project MCP for this clone. Cursor launches `uv run` against `blender-mcp/` and `houdini-mcp/`.

If the user `~/.cursor/mcp.json` also defines `plygon-houdini` or `plygon-blender`, Cursor merges each same-name server and gives project fields precedence. It does not launch two same-name copies. Open a different local project when you need to verify the user-wide `uvx --from git+…` config exactly.

Do not create a second alias for either bridge: differently named entries can launch competing clients against ports 9876 and 9877.

Green here still only means the stdio process started. Blender and Houdini must be listening in the GUI.

For the complete installation and verification sequence, follow the root [click-by-click guide](../README.md#install-both-mcps--exact-click-by-click-guide). On Windows that guide uses `.cmd` installers (PowerShell may block `.ps1`), tells you to skip uv reinstall when `uvx --version` already works, and treats a Houdini Console error about `.cursor/houdini-mcp` / `fxhoudinimcp` as a different MCP.
