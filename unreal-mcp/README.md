# Plygon Unreal MCP

Local MCP bridge for Unreal Editor 5.4 and newer. Cursor talks to a stdio server. That server talks newline-delimited JSON to a Python listener inside the editor on `127.0.0.1:9879`.

The listener is not Epic's Unreal MCP plugin. See [Epic's Unreal MCP](#epics-unreal-mcp) below. Both can be used in the same editor.

```
Cursor agent  --stdio MCP-->  plygon-unreal-mcp  --TCP 127.0.0.1:9879-->  editor Python listener  -->  your level
```

A green row in **Customize → MCPs** only means Cursor started `uvx`. The Output Log must say `PlygonMCP: listening on 127.0.0.1:9879`. Ping from a local Agent chat. A Cloud Agent cannot see your PC.

`uvx` does not install anything inside the editor. The listener comes from a checkout of this repo.

Package version: 0.2.1. That matches the other Plygon bridges. This package is not in the `v0.2.1` git tag. Until it is on the default branch, point `--from` at the branch that contains `unreal-mcp/`, or run it from a local checkout.

## Requirements

- Unreal Editor 5.4 or newer. 5.3 and older are refused.
- The Python Editor Script Plugin enabled.
- The PCG plugin, only if you use the PCG tools.
- `uv` on the machine that runs Cursor. See [Step 1 of the repo guide](../README.md#step-1--install-uv-once).

The editor side uses the `unreal` module. Commands run on the game thread from `unreal.register_slate_post_tick_callback`. They are not run from the socket thread. Editor changes are wrapped in `unreal.ScopedEditorTransaction`, so Ctrl+Z can undo them.

Unreal is Z-up. One unit is one centimetre. `rotation` is pitch, yaw, roll in degrees.

## 1. Put the listener on the editor Python path

Clone or download this repo. Then either:

**Additional Paths.** Edit, Project Settings, Plugins, Python, Additional Paths. Add the `unreal-mcp/editor` directory from this checkout. Restart the editor. The editor runs `init_unreal.py` from every directory on its Python path.

**Startup Scripts.** The same `editor/init_unreal.py` can be added under Startup Scripts instead. Those run after the default level loads. Do not add both unless you mean to. `start_server` does nothing if it is already listening.

**Python console,** if startup did not print the listening line:

```python
import sys
sys.path.append(r"C:\Users\<you>\Documents\Plygon-mcp\unreal-mcp\editor")
from plygon_unreal_mcp.listener import start_server
start_server()
```

Continue only after the Output Log prints:

```text
PlygonMCP: listening on 127.0.0.1:9879
```

Leave the editor open. To stop it from the console: `from plygon_unreal_mcp.listener import stop_server; stop_server()`. Closing the editor also stops it.

## 2. Add the MCP in Cursor

Quit Cursor from the tray so it sees `uv`, then reopen it. Add `plygon-unreal` inside the existing `"mcpServers"` object. Do not add a second `"mcpServers"` object.

Windows, this server alone. Emil's machine launches `uvx` this way:

```json
{
  "mcpServers": {
    "plygon-unreal": {
      "command": "cmd",
      "args": [
        "/c",
        "%USERPROFILE%\\.local\\bin\\uvx.exe",
        "--from",
        "git+https://github.com/Plygonality/Plygon-mcp.git#subdirectory=unreal-mcp",
        "plygon-unreal-mcp"
      ],
      "env": {
        "UNREAL_HOST": "127.0.0.1",
        "UNREAL_PORT": "9879",
        "PYTHONUTF8": "1"
      }
    }
  }
}
```

Before this directory is on the default branch, replace the `--from` value with a ref that contains it, for example `git+https://github.com/Plygonality/Plygon-mcp.git@<branch>#subdirectory=unreal-mcp`. A local checkout can use `uv run --directory <repo>/unreal-mcp plygon-unreal-mcp` instead of `uvx`.

Turn **plygon-unreal** on and wait until the row is green and lists tools.

The combined Windows and macOS files are [`configs/cursor.mcp.windows.json`](configs/cursor.mcp.windows.json) and [`configs/cursor.mcp.json`](configs/cursor.mcp.json). The repo-level copies are [`../configs/cursor.mcp.windows.json`](../configs/cursor.mcp.windows.json) and [`../configs/cursor.mcp.json`](../configs/cursor.mcp.json).

## 3. Ping from a local Agent

1. The Output Log still says **listening on 127.0.0.1:9879**.
2. A level is open.
3. In the desktop Cursor app, open a new **Agent** chat. Do not use a Cloud Agent.
4. Paste: `Ping Unreal. Do not change the level and do not call any other tool.`
5. Confirm the result contains `"pong": true`.

Copy-paste tasks: [`examples/prompts.md`](examples/prompts.md).

## What the agent can call

| Tool | What it does |
|---|---|
| `ping_unreal` | Listener is up |
| `get_addon_info` | Listener version, engine version, command names |
| `get_level_info` / `list_actors` / `get_actor_info` | Open world, actors, selection, viewport camera |
| `select_actors` | Replace or add to the selection |
| `spawn_actor` | Static mesh, point, spot, directional, or rect light, camera, or cine camera |
| `set_actor_transform` / `delete_actor` | Move or delete by label or path |
| `list_assets` / `import_asset` | Content Browser listing and an automated file import |
| `get_viewport_screenshot` | Level viewport PNG. The editor writes it on a later tick |
| `execute_unreal_python` | Python in the editor, with `unreal` in scope and stdout captured |
| `list_pcg` | PCG components in the level, and PCG graph assets |
| `set_pcg_parameter` / `generate_pcg` | Set one graph-instance parameter, then generate |

`spawn_actor` rotation is `[pitch, yaw, roll]` in degrees. A static mesh with no `mesh` argument uses `/Engine/BasicShapes/Cube` when that asset exists.

PCG parameter names are not listed. The 5.4 Python API this bridge calls has setters, not a parameter directory. Pass the name you already know (`Density`, and so on) and a `value_type` of `bool`, `float`, `double`, `int`, `int64`, `string`, `name`, or `vector`.

## Epic's Unreal MCP

Unreal Engine 5.9 Preview ships Epic's own Unreal MCP work. The [5.9 release notes](https://dev.epicgames.com/documentation/en-us/unreal-engine/unreal-engine-5-9-release-notes) describe it as an editor feature with preferences for the server port, allowed origins, and the highest protocol version, plus a project-level Model Context Protocol settings page and more toolsets (Blueprints, editor actions, scene capture, and others). The 5.9 MegaJam notes also say the server can be on while the Toolset plugins are off, in which case it lists no editor tools until those plugins are enabled.

That plugin is a different process and a different protocol from this bridge:

- Epic's plugin is part of the editor and speaks MCP itself. Its port is whatever the editor preferences say. This repo does not document that port, because the 5.9 notes do not state a default.
- Plygon is a separate stdio process that Cursor launches. It sends newline-delimited JSON to `127.0.0.1:9879`, where this Python listener runs inside the editor.
- The two do not share a port. You can enable Epic's plugin and also run this listener. Cursor entries for them should use different server names.

This bridge does not call the 5.9 toolset registry. It calls the Python API documented for 5.4 and guards the one newer call it knows about (`PCGComponent.get_graph`) with `hasattr`.

## Troubleshooting

| What you see | What to do |
|---|---|
| MCP row is red / `'uvx' is not recognized` | On Windows the command must be `cmd`, `/c`, and `%USERPROFILE%\.local\bin\uvx.exe`. Quit Cursor from the tray and reopen it. |
| Green row, `Could not connect to Unreal Editor on 127.0.0.1:9879` | The listener is not running. Check Additional Paths or Startup Scripts, then the Output Log. A green row only means `uvx` started. |
| `Port 9879 is already in use` | Another listener has the port. Stop it, or pick one free port in `start_server(port=...)` and set `UNREAL_PORT` to the same value. |
| `Refusing to bind` | The listener only binds `127.0.0.1`. Do not point it at a LAN address. |
| Engine older than 5.4 | Use 5.4 or newer. |
| Ping times out while the log says listening | A modal dialog is blocking the game thread. Close it. Keep a level viewport open. Do not ping from a Cloud Agent. |
| `PCG Python types are not available` | Enable the PCG plugin and restart the editor. |
| Screenshot says the file was not written | Open a level viewport. The capture is requested with `AutomationLibrary.take_high_res_screenshot` and finishes on a later tick. |
| `unreal.AutomationLibrary.take_high_res_screenshot is not available` | That class is part of the editor Python API from 5.4. If the attribute is missing, this editor build does not expose it. |
| Works locally, fails in a Cloud Agent | Cloud `127.0.0.1` is not your PC. Use a desktop Agent chat. |

Windows port check:

```powershell
Get-NetTCPConnection -LocalPort 9879 -State Listen -ErrorAction SilentlyContinue
```

## Privacy

The listener binds `127.0.0.1:9879` only. The port is unauthenticated. Do not forward it. `execute_unreal_python` runs whatever Python the caller sends, inside the editor, on the game thread. A browser `fetch` to the port is rejected. Other local programs that speak newline-delimited JSON still can.

Cursor can send tool results, including screenshots, to the model provider configured in Cursor.

## Tests

Unreal Editor is not installed in CI. The tests mock the `unreal` module and the TCP peer.

```bash
cd unreal-mcp && uv sync --extra dev --locked && uv run pytest -q
uv run python scripts/smoke_test.py
```

`scripts/smoke_test.py --live` pings a listener that is already running.
