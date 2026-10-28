<p align="center">
  <img src="assets/banner.svg" alt="Plygon Blender MCP" width="100%">
</p>

<p align="center"><strong>Cursor talks. Blender builds. The DCC bridge stays local by default.</strong></p>

<p align="center">
  <a href="https://github.com/Plygonality/Plygon-mcp"><img src="https://img.shields.io/github/stars/Plygonality/Plygon-mcp?style=flat-square&color=ff6a1a" alt="GitHub stars"></a>
  <a href="../LICENSE"><img src="https://img.shields.io/badge/license-MIT-ff6a1a?style=flat-square" alt="MIT"></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-3776ab?style=flat-square&logo=python&logoColor=white" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/Blender-3.0%2B-orange?style=flat-square&logo=blender&logoColor=white" alt="Blender 3.0+">
  <img src="https://img.shields.io/badge/telemetry-none-7dffa3?style=flat-square" alt="No telemetry">
</p>

# Plygon Blender MCP

Give Cursor (and its agent models) hands inside Blender.

Describe a set. The agent inspects the scene, creates meshes, assigns materials, frames a camera, and **screenshots the viewport** so it can judge its own work — the same loop you’d run as a TD, minus the clicking.

Local, no-telemetry fork of [ahujasid/blender-mcp](https://github.com/ahujasid/blender-mcp) (MIT) for Cursor and studio pipelines. See [`THIRD_PARTY.md`](../THIRD_PARTY.md).

Fork it from GitHub. Run it on localhost. Own the code.

```
Cursor agent  ──stdio MCP──►  plygon-blender-mcp  ──TCP 127.0.0.1:9876──►  Blender add-on  ──bpy──►  your .blend
```

A green row in **Customize → MCPs** only means Cursor spawned `uvx`. The N-panel must say **Online · port 9876**. Ping from a **local Agent** chat — a Cloud Agent cannot reach Blender on your PC. `uvx` does not install this add-on.

---

## Why this one

Most “AI for Blender” stacks want your scene in the cloud, or they dump 300 tools into the context window.

Plygon is the opposite:

- **Local.** The MCP and Blender talk on `127.0.0.1:9876`. That’s it.
- **No bridge telemetry.** Plygon does not phone home. Cursor may send prompts, scene data, and screenshots to your configured model provider.
- **Small enough to fork.** One add-on. One Python server. Read it in an afternoon, then make it yours.
- **Built for Cursor agents.** Structured tools for the boring bits, `execute_blender_code` for the rest, viewport capture so the model can *see*.

---

## Get it from GitHub

Installing both DCCs? Use the canonical [click-by-click Blender + Houdini guide](../README.md#install-both-mcps--exact-click-by-click-guide).

```bash
git clone https://github.com/Plygonality/Plygon-mcp.git
cd Plygon-mcp
```

Or hit **Fork** — this repo is MIT on purpose.

### 1. Drop the add-on into Blender

The add-on is the single file [`addon/blender_mcp_addon.py`](addon/blender_mcp_addon.py). Blender installs that `.py` file. Do not zip it. `bl_info` requires Blender 3.0.0 or newer (add-on version 1.1.0). The `plygon-blender-mcp` package version is 0.2.0.

Click-by-click download, install, Cursor config, and the ping test are in the root guide: [Step 2 — Download and install the Blender MCP](../README.md#step-2--download-and-install-the-blender-mcp).

- File: https://github.com/Plygonality/Plygon-mcp/blob/main/blender-mcp/addon/blender_mcp_addon.py
- Raw file: https://raw.githubusercontent.com/Plygonality/Plygon-mcp/main/blender-mcp/addon/blender_mcp_addon.py

1. Open **Blender** (the GUI app, not `blender -b`). If **Quick Setup** is open, click **Continue** first.
2. On Blender 4.2 and newer: **Edit**, **Preferences**, **Add-ons**, the dropdown arrow at the top right, **Install from Disk...**, select `blender_mcp_addon.py`. **Enable on Install** is ticked by default. Leave it ticked, then click **Install from Disk**. On Blender 3.0 through 4.1: **Install...**, select the same file, then **Install Add-on**.
3. Search for `Plygon`. On Blender 4.2 and newer the row is **Plygon Blender MCP** and the checkbox is usually already on. Click it only if it is off. On Blender 3.0 through 4.1 the row is **Interface: Plygon Blender MCP**. Click that checkbox.
4. In the 3D Viewport press **N**. **PlygonMCP** is a vertical tab in the sidebar, below **Item**, **Tool**, and **View**. Click **Start MCP Server**.
5. Confirm **Online · port 9876**. Leave Blender open.

Script alternative: [`scripts/install-blender.cmd`](../scripts/install-blender.cmd) on Windows (use this when PowerShell blocks `.ps1` files), or this from the repo on macOS/Linux:

```bash
"$HOME/.local/bin/uv" run --no-project python blender-mcp/scripts/install_addon.py
```

The script detects fresh Blender version folders even when `scripts/addons` does not exist yet.

### 2. Connect Cursor

Cursor does **not** use Settings → MCP. Use **Customize → MCPs**.

**Install uv first (one time).** On Windows, first check `& "$env:USERPROFILE\.local\bin\uvx.exe" --version`. If it prints a version, skip the download. Cursor often locks `uv.exe` ("being used by another process") — quit Cursor from the tray, or skip reinstall when the version check already works.

Windows PowerShell — paste **one command at a time**, never `cd` plus this line:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
& "$env:USERPROFILE\.local\bin\uvx.exe" --version
```

macOS / Linux:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source "$HOME/.local/bin/env"
"$HOME/.local/bin/uvx" --version
```

If `source "$HOME/.local/bin/env"` prints `No such file or directory`, that error is harmless when `~/.local/bin` is already on `PATH`. Continue when `uvx --version` prints a version number.

Do not `pip install uv`.

Then **fully quit Cursor** (Windows: tray icon → Quit; Mac: **Cmd+Q**) and reopen it.

**Wire it up:**

1. In Cursor, click **Customize** in the **left sidebar**.
2. Click the **MCPs** tab.
3. Click **+ New MCP Server** (or **Add a Custom MCP Server**).
4. Cursor opens `mcp.json`:
   - Windows: `C:\Users\<your-windows-username>\.cursor\mcp.json`
   - macOS / Linux: `~/.cursor/mcp.json`
5. Paste a JSON block from below.
6. **Ctrl+S** / **Cmd+S**.
7. Return to **Customize → MCPs**. **plygon-blender** should be **Connected**, green, ~13 tools. Turn the toggle **on** if it is off.

If `plygon-houdini` is already in the file, add `"plygon-blender"` next to it (comma after Houdini’s `}`). Do not replace the whole file. `{ ...leave existing... }` is not valid JSON and will empty the MCP list.

**Windows — Houdini + Blender (copy the whole file):**

```json
{
  "mcpServers": {
    "plygon-houdini": {
      "command": "cmd",
      "args": [
        "/c",
        "%USERPROFILE%\\.local\\bin\\uvx.exe",
        "--from",
        "git+https://github.com/Plygonality/Plygon-mcp.git#subdirectory=houdini-mcp",
        "plygon-houdini-mcp"
      ],
      "env": {
        "HOUDINI_HOST": "127.0.0.1",
        "HOUDINI_PORT": "9877",
        "PYTHONUTF8": "1"
      }
    },
    "plygon-blender": {
      "command": "cmd",
      "args": [
        "/c",
        "%USERPROFILE%\\.local\\bin\\uvx.exe",
        "--from",
        "git+https://github.com/Plygonality/Plygon-mcp.git#subdirectory=blender-mcp",
        "plygon-blender-mcp"
      ],
      "env": {
        "BLENDER_HOST": "127.0.0.1",
        "BLENDER_PORT": "9876",
        "PYTHONUTF8": "1"
      }
    }
  }
}
```

**macOS / Linux:**

```json
{
  "mcpServers": {
    "plygon-blender": {
      "command": "${userHome}/.local/bin/uvx",
      "args": [
        "--from",
        "git+https://github.com/Plygonality/Plygon-mcp.git#subdirectory=blender-mcp",
        "plygon-blender-mcp"
      ],
      "env": {
        "BLENDER_HOST": "127.0.0.1",
        "BLENDER_PORT": "9876"
      }
    }
  }
}
```

Red / **Needs Attention:** click the server → **Show Output**. `'uvx' is not recognized` → use the Windows JSON (it calls `%USERPROFILE%\\.local\\bin\\uvx.exe`) and fully quit Cursor. File also at [`../configs/cursor.mcp.windows.json`](../configs/cursor.mcp.windows.json).

The `--from` URLs above track the default branch. To pin release v0.2.0, replace a URL with `git+https://github.com/Plygonality/Plygon-mcp.git@v0.2.0#subdirectory=blender-mcp` or `git+https://github.com/Plygonality/Plygon-mcp.git@v0.2.0#subdirectory=houdini-mcp`. Leave the rest of the JSON unchanged.

Same-name user and project MCP definitions are merged, and project fields take precedence. Do not add this bridge under a second name; differently named entries can compete for port 9876.

Advanced editable install: run `uv venv .venv`, then `uv pip install --python .venv -e blender-mcp` from the repo root. In [`configs/cursor.mcp.pip.json`](configs/cursor.mcp.pip.json), replace the command placeholder with the absolute `.venv\Scripts\python.exe` path on Windows or `.venv/bin/python` path on macOS/Linux. The package is not currently published on PyPI.

### 3. Make something

1. Blender must still show **Online · port 9876**.
2. Open a new Cursor **Agent** chat on the desktop (not Ask, not Cloud Agent).
3. Paste: `Ping Blender. Do not call any other tools.` Approve the tool if asked.
4. Then:

> Create a studio-lit chrome Suzanne on a matte plane. Three-point lights. Frame the camera. Screenshot when it looks like a keyframe.

More copy-paste prompts: [`examples/prompts.md`](examples/prompts.md)

---

## What the agent can do

| Tool | What it’s for |
|------|----------------|
| `get_scene_info` / `list_objects` / `get_object_info` | Orient before touching anything |
| `get_viewport_screenshot` | Visual QA — the agent *looks*. If the active workspace has no 3D Viewport, the add-on temporarily turns the largest editor into one and restores it |
| `create_primitive` | Cube, sphere, cylinder, cone, torus, plane, Suzanne, ico-sphere. `scale` is `object.scale`, not baked into the mesh |
| `set_object_transform` / `set_material` / `select_objects` | Layout and look-dev |
| `delete_object` | Delete one named object |
| `execute_blender_code` | Real bpy: modifiers, nodes, animation, whatever you can script. Stdout is capped at 256 KiB |
| `export_scene` | GLB, GLTF, FBX, OBJ, BLEND |
| `ping_blender` / `get_addon_info` | “Is Blender even listening?” |

Prefer the structured tools for simple edits. Use `execute_blender_code` in small steps. Screenshot after anything that should *look* right.

---

## Repo map

| Path | What |
|------|------|
| [`addon/blender_mcp_addon.py`](addon/blender_mcp_addon.py) | Blender add-on — TCP server + N-panel |
| [`src/plygon_blender_mcp/`](src/plygon_blender_mcp/) | MCP server Cursor launches |
| [`configs/`](configs/) | Cursor MCP JSON (GitHub / local / Windows / pip) |
| [`scripts/install_addon.py`](scripts/install_addon.py) | Copies the add-on into Blender |
| [`../scripts/install-blender.cmd`](../scripts/install-blender.cmd) | Windows installer (works when `.ps1` is blocked) |
| [`../scripts/install-blender.ps1`](../scripts/install-blender.ps1) | Windows PowerShell installer (any cwd) |
| [`examples/prompts.md`](examples/prompts.md) | Prompts that make the demo hit |

---

## Environment

| Variable | Default | Meaning |
|----------|---------|---------|
| `BLENDER_HOST` | `127.0.0.1` | Addon TCP host |
| `BLENDER_PORT` | `9876` | Must match the N-panel port |

---

## Protocol

Newline-framed JSON over TCP, executed on Blender’s main thread. The listener uses `JSONDecoder.raw_decode` so concatenated parallel requests are handled one value at a time while incomplete trailing bytes stay buffered:

```json
{"type": "get_scene_info", "params": {"limit": 50}}
```

```json
{"status": "success", "result": { ... }}
```

`execute_code` stdout is truncated to 256 KiB. A longer print still returns success and ends with `…[truncated N bytes]`, so the reply stays under the 4 MiB frame limit and the next command can use the same connection.

The listener accepts newline-delimited JSON only. A connection whose first bytes are an HTTP request line (`GET`, `POST`, and the other HTTP methods) is closed immediately and not parsed.

---

## Smoke test

```bash
cd blender-mcp
uv sync --extra dev
uv run python scripts/smoke_test.py
uv run pytest -q
uv run python scripts/smoke_test.py --live   # Blender must be listening
```

---

## Security

Port `9876` is unauthenticated by design and must stay on loopback (`127.0.0.1`). The add-on binds IPv4 loopback even if a host preference says otherwise. Do not forward the port, bind it on a LAN address, or put it behind a reverse proxy.

`execute_blender_code` is full local Python execution inside Blender for whoever can open a TCP connection to that port. It has the same file and network permissions as the Blender process. Prefer the structured tools, save the `.blend` first, and review Cursor tool approvals.

Browser pages cannot use the port as an HTTP endpoint. The listener closes the connection when the first bytes are an HTTP request line, so `fetch('http://127.0.0.1:9876/', …)` is rejected and does not run `execute_code`. Other local processes can still speak the newline-delimited JSON protocol and run commands, including `execute_code`.

Tool results sent back to Cursor may be forwarded to your configured model provider. The bridge itself has no telemetry.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `spawn uvx ENOENT` / `'uvx' is not recognized` | Install [uv](https://docs.astral.sh/uv/getting-started/installation/), use `%USERPROFILE%\\.local\\bin\\uvx.exe` on Windows, fully quit Cursor (tray icon too) |
| uv installer: `uv.exe` is being used by another process | Quit Cursor from the tray, or skip reinstall if `uvx.exe --version` already works |
| `running scripts is disabled` / cannot load `.ps1` | Use `.\scripts\install-blender.cmd` |
| MCP list empties after Ctrl+S | `mcp.json` is invalid JSON. Don’t paste `{ ...leave existing... }` placeholders. Add `plygon-blender` next to `plygon-houdini` |
| `Extra data: line 1 column 51` | Reinstall add-on 1.0.3+ and restart the MCP server (concatenated JSON from parallel tools) |
| Start fails / port already in use | Another add-on may own 9876, often Blender Lab's MCP extension. Turn it off, or pick another port in the panel and set `BLENDER_PORT` to the same value. The panel stays offline |
| Green MCP, `Could not connect` | Add-on enabled? **Start MCP Server**? Panel says **Online · 9876**? Green is not enough |
| Timeouts | Keep Blender in the foreground; smaller code chunks. Do not ping from a Cloud Agent |
| Add-on missing | Restart Blender; search Preferences for “Plygon”; or run `scripts/install-blender.cmd` |
| Screenshot says no 3D viewport | The add-on temporarily changes the largest editor into a 3D Viewport, captures, and restores it. If that cannot be done, open the Layout workspace, or run `bpy.context.window.workspace = bpy.data.workspaces['Layout']` via `execute_blender_code`, then retry |
| Black screenshots | Keep a 3D Viewport visible in the workspace you want to capture |
| Stale server after a git update | `uv cache clean` then fully quit Cursor |
| User config seems ignored in this clone | Same-name project fields take precedence. Test the user config from a different local project |

---

## License

MIT. Fork it, ship it in a studio pipeline, put your name on the fork.

**If Plygon MCP saves you a night of clicking, star [Plygonality/Plygon-mcp](https://github.com/Plygonality/Plygon-mcp).**
