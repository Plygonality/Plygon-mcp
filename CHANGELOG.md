# Changelog

## Unreleased

### Reliability

- Fix Houdini Scene Viewer screenshots by using the supported one-frame flipbook API.
- Honor Houdini `create_primitive.parent_path`, validate before mutation, and apply `size` to every supported primitive.
- Support Houdini tuple parameters such as `t: [1, 2, 3]`.
- Preserve disconnected Houdini input slots and report real geometry vertex counts.
- Limit DCC command processing to one request per UI tick, bound pending queues and TCP buffers, discard disconnected work, and recover after malformed newline frames.
- Make Blender server startup report failure instead of falsely showing **Online**.
- Run Blender operators with a stable 3D View context across Blender 3.x and 4.x.
- Use unique screenshot paths for concurrent requests and preserve legitimate falsy protocol results.

### Setup and maintenance

- Teach the Windows Houdini install path from a real first-run: `.cmd` wrappers when PowerShell blocks `.ps1` files, skip uv reinstall when `uvx --version` already works, overlay OneDrive-locked package folders, and keep going if only one of two prefs dirs succeeds.
- Document the leftover `fxhoudinimcp` / `.cursor/houdini-mcp` Houdini Console error as a different MCP (close it; Plygon is port 9877).
- Add a real Cursor + Houdini chess-set screenshot and the prompts that built it to the Houdini install guides, including the root README hero image.
- Add one combined Cursor MCP config for each operating-system family.
- Standardize server names on `plygon-blender` and `plygon-houdini`.
- Add a complete click-by-click installation and verification guide for both DCCs.
- Make installers work without a global Python command; detect fresh Blender profiles and macOS Houdini preference folders.
- Document Cursor's same-name user/project precedence and use explicit uv paths in desktop configs.
- Correct privacy language: the bridge has no telemetry, while Cursor may send tool results to its configured model provider.
- Add mocked DCC runtime regression tests, normal pytest discovery, lockfile refreshes, and GitHub Actions CI.
