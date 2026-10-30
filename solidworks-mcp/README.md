<p align="center"><strong>Cursor talks. SOLIDWORKS builds. The bridge stays on your machine.</strong></p>

<p align="center">
  <a href="https://github.com/Plygonality/Plygon-mcp"><img src="https://img.shields.io/github/stars/Plygonality/Plygon-mcp?style=flat-square&color=ff6a1a" alt="GitHub stars"></a>
  <a href="../LICENSE"><img src="https://img.shields.io/badge/license-MIT-ff6a1a?style=flat-square" alt="MIT"></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-3776ab?style=flat-square&logo=python&logoColor=white" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/SOLIDWORKS-2022%2B%20Windows-orange?style=flat-square" alt="SOLIDWORKS 2022+ Windows">
  <img src="https://img.shields.io/badge/telemetry-none-7dffa3?style=flat-square" alt="No telemetry">
</p>

# Plygon SOLIDWORKS MCP

Give Cursor hands inside the SOLIDWORKS window you already have open.

The agent reads the active part, builds a simple extrusion, sets custom properties, exports STEP, and screenshots the view so it can check its own work. The same loop as the Blender and Houdini bridges: **inspect → change → look → export**.

SOLIDWORKS has no Python shell, so the DCC side is a small listener process. It attaches to that open window with the SOLIDWORKS COM API. It does not launch a second session.

```
Cursor agent  ──stdio MCP──►  plygon-solidworks-mcp  ──TCP 127.0.0.1:9878──►  listener  ──COM──►  your SOLIDWORKS window
```

A green row in **Customize → MCPs** only means Cursor started `uvx`. The listener must print `PlygonMCP: listening on 127.0.0.1:9878`. Ping from a **local** Agent chat. A Cloud Agent cannot see your PC.

This bridge is Windows-only, because SOLIDWORKS is. The MCP package itself imports on any OS so the tests can run without a seat.

---

## Install

You need three things:

1. SOLIDWORKS 2022 or newer, already open, with a default part template set in **Tools → Options → Default Templates**.
2. The listener window, started from this repo and left open.
3. `plygon-solidworks` in Cursor's `mcp.json`, beside `plygon-blender` and `plygon-houdini` if you use those too.

`uvx` does not install anything inside SOLIDWORKS.

### 1. Install uv once

Use [Step 1 of the repo guide](../README.md#step-1--install-uv-once). On Windows, check `& "$env:USERPROFILE\.local\bin\uvx.exe" --version` before running the Astral installer again. Cursor often locks `uv.exe`.

### 2. Open SOLIDWORKS, then start the listener

Open the normal SOLIDWORKS window. Then, from the repo folder, paste **one** command:

```powershell
.\scripts\start-solidworks.cmd
```

If PowerShell says running scripts is disabled, that `.cmd` file is the one to use, not `start-solidworks.ps1`.

Leave the window open. Continue only after it prints:

```text
PlygonMCP: listening on 127.0.0.1:9878
```

The first run downloads `pywin32`. The listener attaches to the SOLIDWORKS you opened. Closing the listener does not close SOLIDWORKS.

### 3. Add the MCP in Cursor

Quit Cursor from the tray so it sees `uv`, then reopen it. If `mcp.json` already has the Blender and Houdini entries, add `plygon-solidworks` inside the same `"mcpServers"` object. The combined Windows and macOS files are [`configs/cursor.mcp.windows.json`](../configs/cursor.mcp.windows.json) and [`configs/cursor.mcp.json`](../configs/cursor.mcp.json).

Windows, this server alone:

```json
{
  "mcpServers": {
    "plygon-solidworks": {
      "command": "cmd",
      "args": [
        "/c",
        "%USERPROFILE%\\.local\\bin\\uvx.exe",
        "--from",
        "git+https://github.com/Plygonality/Plygon-mcp.git#subdirectory=solidworks-mcp",
        "plygon-solidworks-mcp"
      ],
      "env": {
        "SOLIDWORKS_HOST": "127.0.0.1",
        "SOLIDWORKS_PORT": "9878",
        "PYTHONUTF8": "1"
      }
    }
  }
}
```

Turn **plygon-solidworks** on and wait until the row is green and lists tools.

The `v0.2.0` tag does not contain this bridge. The `--from` URL above tracks `main`.

### 4. Ping from a local Agent

1. The listener window still says **listening on 127.0.0.1:9878**.
2. SOLIDWORKS is still open.
3. In the desktop Cursor app, open a new **Agent** chat. Do not use a Cloud Agent.
4. Paste: `Ping SOLIDWORKS. Do not change the document and do not call any other tool.`
5. Confirm the result contains `"pong": true`.

Copy-paste tasks: [`examples/prompts.md`](examples/prompts.md).

---

## What the agent can call

| Tool | What it does |
|---|---|
| `ping_solidworks` | Listener is up |
| `get_document_info` / `list_features` | Active file, unit, feature tree |
| `get_mass_properties` | Mass in kg, volume in m³, center of mass in m |
| `get_custom_properties` / `set_custom_property` | Document custom properties |
| `new_document` | New part, assembly, or drawing from the default template |
| `create_extruded_box` | Centered rectangle on Front, Top, or Right, extruded along the normal |
| `rebuild` | Rebuild the active document |
| `save_document` / `export_document` | Save, or export STEP, IGES, STL, PDF, Parasolid, 3MF |
| `get_viewport_screenshot` | Fit the view, grab a bitmap, return a PNG |
| `execute_solidworks_code` | Python in the listener, with `sw` and `model` |

`width`, `depth`, and `height` use the part's current length unit. On an MMGS template, `60` is 60 mm. The SOLIDWORKS API wants meters; the listener converts. A feet-and-inches document treats that single number as inches.

`create_extruded_box` finds the plane by feature type (`RefPlane`), in Front / Top / Right order, so a French or German template still works. The plane's display name can differ. The sketch type string stays the English API value `PLANE`.

Anything past a box — holes, mates, drawings, configurations — belongs in `execute_solidworks_code`, one step at a time, with a screenshot after each step.

---

## Privacy

The listener binds `127.0.0.1:9878`. That port is unauthenticated. Do not forward it or bind it on a LAN address.

`execute_solidworks_code` runs in the listener process, which holds a COM handle to SOLIDWORKS. Anyone who can open that port can drive the session. A browser `fetch` is rejected. Other local programs that speak newline-delimited JSON are not.

Cursor can send tool results, including screenshots and part metadata, to the model provider configured in Cursor. Save the part before a destructive edit.

---

## Tests

CI does not start SOLIDWORKS. The suite drives a stand-in COM object and checks unit conversion, the extrusion call, the HTTP rejection, and the socket rules shared with the other bridges.

```bash
cd solidworks-mcp && uv sync --extra dev --locked && uv run pytest -q
uv run python scripts/smoke_test.py
```

On a machine with SOLIDWORKS open and the listener running:

```powershell
uv run python solidworks-mcp\scripts\smoke_test.py --live
```
