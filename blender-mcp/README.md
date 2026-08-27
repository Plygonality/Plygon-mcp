<p align="center">
  <img src="assets/banner.svg" alt="Plygon Blender MCP" width="100%">
</p>

<p align="center"><strong>Cursor talks. Blender builds. Your files never leave the machine.</strong></p>

<p align="center">
  <a href="https://github.com/EmilvanDam/Plygon"><img src="https://img.shields.io/github/stars/EmilvanDam/Plygon?style=flat-square&color=ff6a1a" alt="GitHub stars"></a>
  <a href="../LICENSE"><img src="https://img.shields.io/badge/license-MIT-ff6a1a?style=flat-square" alt="MIT"></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-3776ab?style=flat-square&logo=python&logoColor=white" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/Blender-3.0%2B-orange?style=flat-square&logo=blender&logoColor=white" alt="Blender 3.0+">
  <img src="https://img.shields.io/badge/telemetry-none-7dffa3?style=flat-square" alt="No telemetry">
</p>

<p align="center">
  <a href="https://cursor.com/link/mcp/install?name=plygon-blender&config=eyJjb21tYW5kIjoidXZ4IiwiYXJncyI6WyItLWZyb20iLCJnaXQraHR0cHM6Ly9naXRodWIuY29tL0VtaWx2YW5EYW0vUGx5Z29uLmdpdCNzdWJkaXJlY3Rvcnk9YmxlbmRlci1tY3AiLCJwbHlnb24tYmxlbmRlci1tY3AiXSwiZW52Ijp7IkJMRU5ERVJfSE9TVCI6ImxvY2FsaG9zdCIsIkJMRU5ERVJfUE9SVCI6Ijk4NzYifX0%3D"><img src="https://cursor.com/deeplink/mcp-install-dark.svg" alt="Add Plygon Blender MCP to Cursor"></a>
</p>

# Plygon Blender MCP

Give Cursor (and its agent models) hands inside Blender.

Describe a set. The agent inspects the scene, creates meshes, assigns materials, frames a camera, and **screenshots the viewport** so it can judge its own work — the same loop you’d run as a TD, minus the clicking.

Fork it from GitHub. Run it on localhost. Own the code.

```
Cursor agent  ──stdio MCP──►  plygon-blender-mcp  ──TCP :9876──►  Blender add-on  ──bpy──►  your .blend
```

---

## Why this one

Most “AI for Blender” stacks want your scene in the cloud, or they dump 300 tools into the context window.

Plygon is the opposite:

- **Local.** The MCP and Blender talk on `localhost:9876`. That’s it.
- **No telemetry.** Prompts, screenshots, and meshes stay with you.
- **Small enough to fork.** One add-on. One Python server. Read it in an afternoon, then make it yours.
- **Built for Cursor agents.** Structured tools for the boring bits, `execute_blender_code` for the rest, viewport capture so the model can *see*.

---

## Get it from GitHub

```bash
git clone https://github.com/EmilvanDam/Plygon.git
cd Plygon
```

Or hit **Fork** — this repo is MIT on purpose.

### 1. Drop the add-on into Blender

```bash
python blender-mcp/scripts/install_addon.py
```

Manual: Blender → **Edit → Preferences → Add-ons → Install…** → `addon/blender_mcp_addon.py` → enable **Interface: Plygon Blender MCP**.

In the 3D Viewport press `N` → **PlygonMCP** → **Start MCP Server**.  
You want **Online · port 9876**.

Blender needs a GUI. `blender -b` will not run commands.

### 2. Connect Cursor

**Fastest:** [Add to Cursor](https://cursor.com/link/mcp/install?name=plygon-blender&config=eyJjb21tYW5kIjoidXZ4IiwiYXJncyI6WyItLWZyb20iLCJnaXQraHR0cHM6Ly9naXRodWIuY29tL0VtaWx2YW5EYW0vUGx5Z29uLmdpdCNzdWJkaXJlY3Rvcnk9YmxlbmRlci1tY3AiLCJwbHlnb24tYmxlbmRlci1tY3AiXSwiZW52Ijp7IkJMRU5ERVJfSE9TVCI6ImxvY2FsaG9zdCIsIkJMRU5ERVJfUE9SVCI6Ijk4NzYifX0%3D) (runs the server straight from this GitHub repo via `uvx`).

**Or paste this** into Cursor → **Settings → MCP**, or as project `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "plygon-blender": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/EmilvanDam/Plygon.git#subdirectory=blender-mcp",
        "plygon-blender-mcp"
      ],
      "env": {
        "BLENDER_HOST": "localhost",
        "BLENDER_PORT": "9876"
      }
    }
  }
}
```

Need `uv` first? [Install uv](https://docs.astral.sh/uv/getting-started/installation/) (not `pip install uv`). GUI apps often miss PATH — if Cursor says `spawn uvx ENOENT`, put the absolute path from `which uvx` / `where uvx` in `"command"`.

Windows: [`configs/cursor.mcp.windows.json`](configs/cursor.mcp.windows.json) (`cmd /c uvx --from git+…`).  
Hacking on a local clone: [`configs/cursor.mcp.json`](configs/cursor.mcp.json) or [`configs/cursor.mcp.pip.json`](configs/cursor.mcp.pip.json).

### 3. Make something

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
| [`examples/prompts.md`](examples/prompts.md) | Prompts that make the demo hit |

---

## Environment

| Variable | Default | Meaning |
|----------|---------|---------|
| `BLENDER_HOST` | `localhost` | Addon TCP host |
| `BLENDER_PORT` | `9876` | Must match the N-panel port |

---

## Protocol

JSON over TCP, executed on Blender’s main thread:

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
uv run pytest tests/ -q
uv run python scripts/smoke_test.py --live   # Blender must be listening
```

---

## Security

`execute_blender_code` is full `bpy` on your machine. Treat it like a macro with root access to the `.blend`. Save first. Don’t expose the TCP port past localhost.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `spawn uvx ENOENT` | Absolute path to `uvx`; fully quit Cursor and relaunch |
| `Could not connect to Blender` | Add-on enabled? **Start MCP Server**? Port = `BLENDER_PORT`? |
| Timeouts | Keep Blender in the foreground; smaller code chunks |
| Add-on missing | Restart Blender; search Preferences for “Plygon” |
| Black screenshots | Keep a 3D Viewport visible |

---

## License

MIT. Fork it, ship it in a studio pipeline, put your name on the fork.

**If Plygon MCP saves you a night of clicking, star [EmilvanDam/Plygon](https://github.com/EmilvanDam/Plygon).**
