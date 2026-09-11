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

1. Open **Blender** (the GUI app — not `blender -b`).
2. Click **Edit → Preferences → Add-ons → Install from Disk…** and choose [`addon/blender_mcp_addon.py`](addon/blender_mcp_addon.py).
3. Enable **Interface: Plygon Blender MCP** (search “Plygon”).
4. In the 3D Viewport press **N** → **PlygonMCP** tab → **Start MCP Server**.
5. Confirm **Online · port 9876**. Leave Blender open.

Script alternative: [`scripts/install-blender.ps1`](../scripts/install-blender.ps1) on Windows, or this from the repo on macOS/Linux:

```bash
"$HOME/.local/bin/uv" run --no-project python blender-mcp/scripts/install_addon.py
```

The script detects fresh Blender version folders even when `scripts/addons` does not exist yet.

### 2. Connect Cursor

Cursor does **not** use Settings → MCP. Use **Customize → MCPs**.

**Install uv first (one time).** Windows PowerShell:

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
| `get_viewport_screenshot` | Visual QA — the agent *looks* |
| `create_primitive` | Cube, sphere, cylinder, cone, torus, plane, Suzanne, ico-sphere |
| `set_object_transform` / `set_material` / `select_objects` | Layout and look-dev |
| `delete_object` | Delete one named object |
| `execute_blender_code` | Real bpy: modifiers, nodes, animation, whatever you can script |
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
| [`../scripts/install-blender.ps1`](../scripts/install-blender.ps1) | Windows installer (any cwd) |
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

`execute_blender_code` runs with the same permissions as Blender, including access to your files and network. The listener has no TCP authentication: any local process that reaches port 9876 can call it. Save first, review tool approvals, and never expose the port beyond localhost. Tool results sent back to Cursor may be forwarded to your configured model provider.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `spawn uvx ENOENT` / `'uvx' is not recognized` | Install [uv](https://docs.astral.sh/uv/getting-started/installation/), use `%USERPROFILE%\\.local\\bin\\uvx.exe` on Windows, fully quit Cursor (tray icon too) |
| MCP list empties after Ctrl+S | `mcp.json` is invalid JSON. Don’t paste `{ ...leave existing... }` placeholders. Add `plygon-blender` next to `plygon-houdini` |
| `Extra data: line 1 column 51` | Reinstall add-on 1.0.3+ and restart the MCP server (concatenated JSON from parallel tools) |
| Start fails / port already in use | Stop the other listener on 9876. The panel now stays offline instead of falsely showing Online |
| Green MCP, `Could not connect` | Add-on enabled? **Start MCP Server**? Panel says **Online · 9876**? Green is not enough |
| Timeouts | Keep Blender in the foreground; smaller code chunks. Do not ping from a Cloud Agent |
| Add-on missing | Restart Blender; search Preferences for “Plygon”; or run `scripts/install-blender.ps1` |
| Black screenshots | Keep a 3D Viewport visible |
| Stale server after a git update | `uv cache clean` then fully quit Cursor |
| User config seems ignored in this clone | Same-name project fields take precedence. Test the user config from a different local project |

---

## License

MIT. Fork it, ship it in a studio pipeline, put your name on the fork.

**If Plygon MCP saves you a night of clicking, star [Plygonality/Plygon-mcp](https://github.com/Plygonality/Plygon-mcp).**
