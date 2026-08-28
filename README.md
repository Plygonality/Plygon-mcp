<p align="center">
  <img src="blender-mcp/assets/banner.svg" alt="Plygon — local MCP bridges for Blender and Houdini" width="100%">
</p>

<p align="center">
  <strong>Tell Cursor to build in Blender or Houdini. Watch it happen on your machine.</strong>
</p>

<p align="center">
  <a href="https://github.com/Plygonality/Plygon-mcp/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-ff6a1a?style=flat-square" alt="MIT"></a>
  <a href="blender-mcp/"><img src="https://img.shields.io/badge/Blender-3.0%2B-orange?style=flat-square&logo=blender&logoColor=white" alt="Blender 3.0+"></a>
  <a href="houdini-mcp/"><img src="https://img.shields.io/badge/Houdini-19.5%2B-orange?style=flat-square" alt="Houdini 19.5+"></a>
  <a href="blender-mcp/"><img src="https://img.shields.io/badge/Cursor-MCP-111111?style=flat-square" alt="Cursor MCP"></a>
  <a href="blender-mcp/"><img src="https://img.shields.io/badge/telemetry-none-7dffa3?style=flat-square" alt="No telemetry"></a>
</p>

# Plygon

A tech-art studio repo of **local MCP bridges** you can fork, run, and actually own.

Cursor's agents already write code. **Plygon gives them hands inside your DCC** — inspect the scene, make edits, and screenshot the viewport so they can check their own work. Nothing leaves localhost. No telemetry. No cloud that trains on your `.blend` or `.hip`.

Local, no-telemetry fork of the [ahujasid/blender-mcp](https://github.com/ahujasid/blender-mcp) localhost-TCP + FastMCP pattern, shaped for Cursor and studio pipelines. See [`THIRD_PARTY.md`](THIRD_PARTY.md).

| Bridge | Port | Docs |
|--------|------|------|
| [Blender MCP](blender-mcp/) | `localhost:9876` | [`blender-mcp/README.md`](blender-mcp/README.md) |
| [Houdini MCP](houdini-mcp/) | `localhost:9877` | [`houdini-mcp/README.md`](houdini-mcp/README.md) |

---

## Why people fork this

| You want | You get |
|---|---|
| An agent that *sees* your scene | Viewport / Scene Viewer screenshots in the loop |
| A bridge small enough to read | One DCC package + one MCP server per app |
| Privacy | TCP on localhost only, MIT, no phone-home |
| Something you can steal for a pipeline | Fork it. Rename it. Ship it in your studio. |

This is not a 300-tool kitchen sink. It's the layer tech artists actually keep: **inspect → change → look → export**.

---

## Clone once

```bash
git clone https://github.com/Plygonality/Plygon-mcp.git
cd Plygon-mcp
```

Pick one DCC below — or set up both. The project [`.cursor/mcp.json`](.cursor/mcp.json) registers Blender and Houdini when you clone the repo.

---

## Blender MCP

```
Cursor agent  →  plygon-blender-mcp  →  localhost:9876  →  Blender add-on  →  bpy  →  your .blend
```

### Setup

**1. Install the add-on**

```bash
python blender-mcp/scripts/install_addon.py
```

Blender → Preferences → Add-ons → enable **Plygon Blender MCP**.  
3D Viewport → `N` → **PlygonMCP** → **Start MCP Server**.

**2. Connect Cursor**

[Add Blender to Cursor](https://cursor.com/link/mcp/install?name=plygon-blender&config=eyJjb21tYW5kIjoidXZ4IiwiYXJncyI6WyItLWZyb20iLCJnaXQraHR0cHM6Ly9naXRodWIuY29tL1BseWdvbmFsaXR5L1BseWdvbi1tY3AuZ2l0I3N1YmRpcmVjdG9yeT1ibGVuZGVyLW1jcCIsInBseWdvbi1ibGVuZGVyLW1jcCJdLCJlbnYiOnsiQkxFTkRFUl9IT1NUIjoibG9jYWxob3N0IiwiQkxFTkRFUl9QT1JUIjoiOTg3NiJ9fQ%3D%3D) · or paste [`blender-mcp/configs/cursor.mcp.git.json`](blender-mcp/configs/cursor.mcp.git.json) into **Settings → MCP**.

**3. Try it**

> Create a studio-lit chrome Suzanne. Screenshot when it looks like a keyframe.

### What the agent can do

| Tool | Purpose |
|------|---------|
| `get_scene_info` / `list_objects` / `get_object_info` | Orient before editing |
| `get_viewport_screenshot` | Visual QA |
| `create_primitive` / `set_material` / `set_object_transform` | Quick layout and look-dev |
| `execute_blender_code` | Full `bpy` for anything else |
| `export_scene` | GLB, GLTF, FBX, OBJ, BLEND |

Prompts: [`blender-mcp/examples/prompts.md`](blender-mcp/examples/prompts.md)

---

## Houdini MCP

```
Cursor agent  →  plygon-houdini-mcp  →  localhost:9877  →  Houdini listener  →  hou  →  your .hip
```

### Setup

**1. Install the Houdini package**

```bash
python houdini-mcp/scripts/install_package.py
```

Restart Houdini, then import the shelf:

**Shelf pane → right-click → Shelves → Import** →  
`~/houdini20.5/packages/plygon_houdini_mcp/toolbar/plygon_houdini_mcp.shelf`  
(adjust the version folder for your install)

Click **Start MCP Server**. You should see `PlygonMCP: listening on localhost:9877` in the Python shell.

Houdini needs a GUI session — batch `hython` without the listener won't accept commands.

**2. Connect Cursor**

Paste [`houdini-mcp/configs/cursor.mcp.git.json`](houdini-mcp/configs/cursor.mcp.git.json) into **Settings → MCP**, or use the project [`.cursor/mcp.json`](.cursor/mcp.json).

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
        "HOUDINI_HOST": "localhost",
        "HOUDINI_PORT": "9877"
      }
    }
  }
}
```

**3. Try it**

> Create a geo with a grid and mountain SOP. Layout the network, cook it, and screenshot the viewport when it reads as terrain.

### What the agent can do

| Tool | Purpose |
|------|---------|
| `get_scene_info` / `list_nodes` / `get_node_info` | Orient before editing |
| `get_viewport_screenshot` | Scene Viewer visual QA |
| `create_primitive` / `create_node` / `connect_nodes` | SOP networks and primitives |
| `set_node_parm` / `cook_node` / `layout_nodes` | Parameters, cooks, tidy graphs |
| `execute_houdini_code` / `execute_hscript` | Full `hou` or HScript escape hatches |
| `save_hip` | Save or save-as the current hip |

Prompts: [`houdini-mcp/examples/prompts.md`](houdini-mcp/examples/prompts.md)

---

## How it works

Both bridges share the same shape:

1. **DCC side** — a small listener inside Blender or Houdini (TCP server, main-thread dispatch)
2. **MCP side** — a Python process Cursor launches over stdio (FastMCP tools the agent calls)
3. **Loop** — agent inspects → edits → screenshots → iterates

```
You  →  Cursor agent  →  Plygon MCP  →  localhost  →  Blender / Houdini  →  your scene
```

You keep the taste. The agent keeps the clicks.

---

## Repo map

| Path | What |
|------|------|
| [`blender-mcp/`](blender-mcp/) | Blender add-on + MCP server |
| [`houdini-mcp/`](houdini-mcp/) | Houdini package + MCP server |
| [`.cursor/mcp.json`](.cursor/mcp.json) | Project-level Cursor config (both DCCs) |
| [`THIRD_PARTY.md`](THIRD_PARTY.md) | Provenance (blender-mcp pattern) |

---

## Star it, fork it, break it

If this saves you a night of clicking, **star the repo** so other tech artists find it.

Forks are the point. Plygon is a public MIT workshop for DCC tools, add-ons, and MCPs.

[github.com/Plygonality/Plygon-mcp](https://github.com/Plygonality/Plygon-mcp)
