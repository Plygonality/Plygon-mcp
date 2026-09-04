<p align="center"><strong>Cursor talks. Houdini builds. Your files never leave the machine.</strong></p>

<p align="center">
  <a href="https://github.com/Plygonality/Plygon-mcp"><img src="https://img.shields.io/github/stars/Plygonality/Plygon-mcp?style=flat-square&color=ff6a1a" alt="GitHub stars"></a>
  <a href="../LICENSE"><img src="https://img.shields.io/badge/license-MIT-ff6a1a?style=flat-square" alt="MIT"></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-3776ab?style=flat-square&logo=python&logoColor=white" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/Houdini-19.5%2B-orange?style=flat-square" alt="Houdini 19.5+">
  <img src="https://img.shields.io/badge/telemetry-none-7dffa3?style=flat-square" alt="No telemetry">
</p>

# Plygon Houdini MCP

Give Cursor (and its agent models) hands inside SideFX Houdini.

Describe a setup. The agent inspects the hip, creates nodes, wires SOPs, sets parms, and **screenshots the Scene Viewer** so it can judge its own work — the same loop you'd run as a TD, minus the clicking.

Same localhost-TCP + FastMCP shape as the Blender bridge. See [`THIRD_PARTY.md`](../THIRD_PARTY.md).

Fork it from GitHub. Run it on localhost. Own the code.

```
Cursor agent  ──stdio MCP──►  plygon-houdini-mcp  ──TCP :9877──►  Houdini listener  ──hou──►  your .hip
```

---

## Why this one

Most "AI for Houdini" stacks want your scene in the cloud, or they dump hundreds of tools into the context window.

Plygon is the opposite:

- **Local.** The MCP and Houdini talk on `localhost:9877`. That's it.
- **No telemetry.** Prompts, screenshots, and hips stay with you.
- **Small enough to fork.** One Houdini package. One Python server. Read it in an afternoon, then make it yours.
- **Built for Cursor agents.** Structured tools for the boring bits, `execute_houdini_code` for the rest, viewport capture so the model can *see*.

---

## Get it from GitHub

```bash
git clone https://github.com/Plygonality/Plygon-mcp.git
cd Plygon-mcp
```

Or hit **Fork** — this repo is MIT on purpose.

### 1. Install the Houdini package

```bash
python houdini-mcp/scripts/install_package.py
```

Manual: copy `houdini-mcp/package/` to `~/houdini20.5/packages/plygon_houdini_mcp/` (adjust version for your install).

Restart Houdini, then import the shelf:

**Shelf pane → right-click → Shelves → Import** → select  
`~/houdini20.5/packages/plygon_houdini_mcp/toolbar/plygon_houdini_mcp.shelf`

Click **Start MCP Server** on the shelf. You should see `PlygonMCP: listening on localhost:9877` in the Python shell / console.

Houdini needs a GUI session. Batch `hython` without a listener won't accept TCP commands.

### 2. Connect Cursor

Open **Customize** (sidebar) → **MCPs** → **+ New MCP Server**. Paste this into `mcp.json`, **Ctrl+S**, and confirm **plygon-houdini** goes green. If Blender is already in the file, add this server next to it — don’t replace the whole file.

```json
{
  "mcpServers": {
    "plygon-houdini": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/Plygonality/Plygon-mcp.git#subdirectory=houdini-mcp",
        "plygon-houdini-mcp"
      ],
      "env": {
        "HOUDINI_HOST": "127.0.0.1",
        "HOUDINI_PORT": "9877"
      }
    }
  }
}
```

Need `uv` first? [Install uv](https://docs.astral.sh/uv/getting-started/installation/). GUI apps often miss PATH — on Windows use [`../configs/cursor.mcp.windows.json`](../configs/cursor.mcp.windows.json).

**Local clone:** [`configs/cursor.mcp.json`](configs/cursor.mcp.json)  
**Windows:** [`../configs/cursor.mcp.windows.json`](../configs/cursor.mcp.windows.json)  
**pip install:** [`configs/cursor.mcp.pip.json`](configs/cursor.mcp.pip.json)

### 3. Make something

> Create a geo with a grid and a mountain SOP. Layout the network, cook it, and screenshot the viewport when it looks like terrain.

More copy-paste prompts: [`examples/prompts.md`](examples/prompts.md)

---

## What the agent can do

| Tool | What it's for |
|------|----------------|
| `get_scene_info` / `list_nodes` / `get_node_info` | Orient before touching anything |
| `get_viewport_screenshot` | Visual QA — the agent *looks* |
| `create_primitive` | box, sphere, grid, tube, torus, circle, line (new geo + SOP) |
| `create_node` / `delete_node` / `connect_nodes` / `layout_nodes` | Network graph edits |
| `set_node_parm` / `cook_node` | Parameters and geometry refresh |
| `execute_houdini_code` | Full `hou` — VEX wrangles, DOPs, LOPs, whatever you can script |
| `execute_hscript` | HScript escape hatch |
| `save_hip` | Save or save-as the current hip |
| `ping_houdini` / `get_addon_info` | "Is Houdini even listening?" |

Prefer structured tools for simple edits. Use `execute_houdini_code` in small steps. Screenshot after anything that should *look* right.

---

## Repo map

| Path | What |
|------|------|
| [`package/scripts/python/plygon_houdini_mcp/listener.py`](package/scripts/python/plygon_houdini_mcp/listener.py) | Houdini listener — TCP + main-thread dispatch |
| [`package/toolbar/plygon_houdini_mcp.shelf`](package/toolbar/plygon_houdini_mcp.shelf) | Start / Stop / Status shelf tools |
| [`package/plygon_houdini_mcp.json`](package/plygon_houdini_mcp.json) | Houdini package manifest |
| [`src/plygon_houdini_mcp/`](src/plygon_houdini_mcp/) | MCP server Cursor launches |
| [`configs/`](configs/) | Cursor MCP JSON (GitHub / local / Windows / pip) |
| [`scripts/install_package.py`](scripts/install_package.py) | Copies package into Houdini prefs |
| [`examples/prompts.md`](examples/prompts.md) | Prompts that make the demo hit |

---

## Environment

| Variable | Default | Meaning |
|----------|---------|---------|
| `HOUDINI_HOST` | `127.0.0.1` | Listener TCP host (MCP server side) |
| `HOUDINI_PORT` | `9877` | Must match the shelf / listener port |

---

## Protocol

JSON over TCP, executed on Houdini's main thread via `hdefereval`:

```json
{"type": "get_scene_info", "params": {"limit": 50}}
```

```json
{"status": "success", "result": { ... }}
```

---

## Smoke test

```bash
cd houdini-mcp
uv sync --extra dev
uv run python scripts/smoke_test.py
uv run pytest tests/ -q
uv run python scripts/smoke_test.py --live   # Houdini listener must be running
```

---

## Security

`execute_houdini_code` is full `hou` on your machine. Treat it like a macro with root access to the hip. Save first. Don't expose the TCP port past localhost.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `spawn uvx ENOENT` / `'uvx' is not recognized` | Use `%USERPROFILE%\\.local\\bin\\uvx.exe`; fully quit Cursor |
| `Could not connect to Houdini` | Package installed? Shelf **Start MCP Server** clicked? Port = `9877`? |
| Timeouts | Keep Houdini in the foreground; smaller code chunks |
| Import errors in shelf | Restart Houdini after install; check `packages/plygon_houdini_mcp/` exists |
| Black / missing screenshots | Keep a Scene Viewer pane open |

---

## License

MIT. Fork it, ship it in a studio pipeline, put your name on the fork.

**If Plygon Houdini MCP saves you a night of clicking, star [Plygonality/Plygon-mcp](https://github.com/Plygonality/Plygon-mcp).**
