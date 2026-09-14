# Steal this

Plygon is a public MIT workshop. Forks are expected.

- Public slug is [`Plygonality/Plygon-mcp`](https://github.com/Plygonality/Plygon-mcp). Keep clone, `uvx`, and badge URLs on that owner/repo.
- Blender MCP lives in `blender-mcp/`
- Houdini MCP lives in `houdini-mcp/`
- Keep the TCP protocol small; add tools when a real shot needs them
- No bridge telemetry. Don't add any. Do not claim Cursor/model traffic stays local: tool results may be sent to the user's configured model provider.

## Windows Houdini prefs

Installers must find `Documents\houdini21.0` and `OneDrive\Documenten\houdini21.0`, not `Documents\houdini\21.0`. Houdini only loads `packages/*.json` at the top level — always write `packages/plygon_houdini_mcp.json` next to the copied folder.

OneDrive may lock `rmtree` with Access is denied. Overlay-copy in that case, and do not abort a multi-folder install if another prefs folder already succeeded. Windows docs should use `scripts/install-houdini.cmd` so PowerShell execution policy cannot block the first run. Check `uvx --version` before reinstalling uv: Cursor often locks `uv.exe`. Treat a Houdini Console error about `.cursor/houdini-mcp` / `fxhoudinimcp` / `help_menu` as a different MCP (port 8100), not Plygon (9877).

Paste one command per line. Never concatenate `cd` with the next installer.

## Listener threading

`hou.ui.addEventLoopCallback` already runs on the UI thread. Never wait on `hdefereval.executeInMainThreadWithResult` from that callback: Houdini freezes after `queued ping` and Cursor times out.

Process bounded work per DCC UI tick. Keep receive buffers and pending-command queues bounded, preserve request order, discard queued work after its client disconnects, and return a response for every complete JSON value—even malformed command shapes. Newline-terminated malformed JSON must not block the next valid frame.

## Cursor vs DCC

Green MCP + tools listed only means stdio/`uvx` spawned. The DCC still has to listen on 9876/9877. Document Cloud Agents as unable to reach a local DCC.

## Test both packages

```bash
cd blender-mcp && uv sync --extra dev --locked && uv run pytest -q
cd ../houdini-mcp && uv sync --extra dev --locked && uv run pytest -q
```

Mocked tests must cover DCC-side framing and handlers that can run without Blender/Houdini. Use each `scripts/smoke_test.py --live` before release when the GUI applications are available. Keep both lockfiles current with their corresponding `pyproject.toml`.

Installer tests must include fresh Blender profiles, Windows Houdini preference paths, macOS `~/Library/Preferences/houdini/<version>`, and Linux `~/houdini<version>`. Cover OneDrive `rmtree` denial (overlay copy) and a dual prefs install where one folder is locked. User-facing Windows install commands should be `.cmd` wrappers plus uv's managed Python rather than assuming `python` is globally installed or that `.ps1` files can run.

Open a PR if your change would help another tech artist on the first clone.
