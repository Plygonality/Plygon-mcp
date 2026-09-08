# Steal this

Plygon is a public MIT workshop. Forks are expected.

- Public slug is [`Plygonality/Plygon-mcp`](https://github.com/Plygonality/Plygon-mcp). Keep clone, `uvx`, and badge URLs on that owner/repo.
- Blender MCP lives in `blender-mcp/`
- Houdini MCP lives in `houdini-mcp/`
- Keep the TCP protocol small; add tools when a real shot needs them
- No telemetry. Don't add any.

## Windows Houdini prefs

Installers must find `Documents\houdini21.0` and `OneDrive\Documenten\houdini21.0`, not `Documents\houdini\21.0`. Houdini only loads `packages/*.json` at the top level — always write `packages/plygon_houdini_mcp.json` next to the copied folder.

## Listener threading

`hou.ui.addEventLoopCallback` already runs on the UI thread. Never wait on `hdefereval.executeInMainThreadWithResult` from that callback: Houdini freezes after `queued ping` and Cursor times out.

## Cursor vs DCC

Green MCP + tools listed only means stdio/`uvx` spawned. The DCC still has to listen on 9876/9877. Document Cloud Agents as unable to reach a local DCC.

Open a PR if your change would help another tech artist on the first clone.
