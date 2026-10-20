# Changelog

## Unreleased

### Security

- Reject an HTTP request line on the first chunk of a Blender (`127.0.0.1:9876`) or Houdini (`127.0.0.1:9877`) bridge connection. A browser `fetch` can no longer smuggle `execute_code` through the JSON framer. MCP clients send bare newline-delimited JSON and are unchanged. The ports stay unauthenticated for other local processes and must remain on loopback.
- The Houdini change is only that request-line guard. Tool names, input schemas, the port, and Cursor config keys are unchanged.

### Reliability

- Apply Blender `create_primitive` scale on the object after the operator returns. `TORUS` no longer crashes on the missing `scale` property, and every shape leaves `object.scale` equal to the argument instead of baking it into the mesh.
- When the active Blender workspace has no 3D Viewport, temporarily turn the largest editor into a 3D Viewport, capture `get_viewport_screenshot`, and restore the editor. Assigning `window.workspace` does not update the screen inside the listener's timer tick, so the workspace is left alone.
- Truncate Blender `execute_code` stdout to 256 KiB and append `…[truncated N bytes]` so a huge `print` stays under the 4 MiB frame limit. The client buffer limit is unchanged.
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
- Add a real Cursor + Houdini chess-set screenshot and the prompts that built it to the Houdini install guides, including the root README and `houdini-mcp/README.md` hero images.
- Add one combined Cursor MCP config for each operating-system family.
- Standardize server names on `plygon-blender` and `plygon-houdini`.
- Add a complete click-by-click installation and verification guide for both DCCs.
- Make installers work without a global Python command; detect fresh Blender profiles and macOS Houdini preference folders.
- Document Cursor's same-name user/project precedence and use explicit uv paths in desktop configs.
- Correct privacy language: the bridge has no telemetry, while Cursor may send tool results to its configured model provider.
- Add mocked DCC runtime regression tests, normal pytest discovery, lockfile refreshes, and GitHub Actions CI.
