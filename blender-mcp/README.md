# Plygon Blender MCP

Local **Model Context Protocol** bridge between **Cursor** (and its agent models) and **Blender**.

```
Cursor Agent  ──stdio MCP──►  plygon-blender-mcp  ──TCP JSON :9876──►  Blender addon  ──bpy──►  scene
```

No telemetry. No cloud. Everything runs on your machine.

---

## What's included

| Path | Purpose |
|------|---------|
| `addon/blender_mcp_addon.py` | Blender add-on (TCP command server + N-panel UI) |
| `src/plygon_blender_mcp/` | MCP server package Cursor launches |
| `configs/cursor.mcp.*.json` | Ready Cursor MCP configs (uv / Windows / pip) |
| `scripts/install_addon.py` | Copies the add-on into Blender's addons folder |
| `scripts/smoke_test.py` | Import + optional live ping checks |

---

## Prerequisites

- **Blender** 3.0+ (4.x recommended)
- **Python** 3.10+
- **[uv](https://docs.astral.sh/uv/)** *(recommended)* — or plain pip

```bash
# macOS
brew install uv

# Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

---

## 1. Install the Blender add-on

**Option A — helper script**

```bash
cd blender-mcp
python scripts/install_addon.py
# or list detected folders:
python scripts/install_addon.py --list
```

**Option B — manual**

1. Open Blender → **Edit → Preferences → Add-ons → Install…**
2. Select `addon/blender_mcp_addon.py`
3. Enable **Interface: Plygon Blender MCP**

Then in the **3D Viewport** press `N` → **PlygonMCP** tab → **Start MCP Server**.  
Status should show *Online · port 9876*.

> Blender must be running with a GUI. `blender -b` will not execute commands.

---

## 2. Wire it into Cursor

### Project MCP (recommended)

Copy a config into your project as `.cursor/mcp.json`, then replace the path placeholder with the **absolute** path to this `blender-mcp` folder.

**macOS / Linux** (`configs/cursor.mcp.json`):

```json
{
  "mcpServers": {
    "plygon-blender": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/ABSOLUTE/PATH/TO/blender-mcp",
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

**Windows** (`configs/cursor.mcp.windows.json`):

```json
{
  "mcpServers": {
    "plygon-blender": {
      "command": "cmd",
      "args": [
        "/c",
        "uv",
        "run",
        "--directory",
        "C:\\ABSOLUTE\\PATH\\TO\\blender-mcp",
        "plygon-blender-mcp"
      ],
      "env": {
        "BLENDER_HOST": "localhost",
        "BLENDER_PORT": "9876",
        "PYTHONUTF8": "1"
      }
    }
  }
}
```

### Global MCP

Cursor → **Settings → MCP → Add new global MCP server** → paste the same JSON.

### Without uv (pip)

```bash
cd blender-mcp
python -m pip install -e .
```

Then use `configs/cursor.mcp.pip.json` (set absolute paths for `cwd` and `PYTHONPATH`).

If Cursor can't find `uv` (`spawn uv ENOENT`), use the full path from `which uv` / `where uv` as `"command"`.

---

## 3. Use it

1. Blender running + **Start MCP Server** clicked  
2. Cursor MCP shows `plygon-blender` as connected  
3. Ask the agent, for example:
   - *“What’s in my Blender scene?”*
   - *“Create a red metallic monkey and frame the camera”*
   - *“Screenshot the viewport and tell me what looks off”*

---

## MCP tools

| Tool | Description |
|------|-------------|
| `ping_blender` | Liveness check |
| `get_addon_info` | Addon / Blender version + capabilities |
| `get_scene_info` | Scene topology, selection, render settings |
| `list_objects` | Object list (optional type filter) |
| `get_object_info` | Transform, materials, mesh stats |
| `get_viewport_screenshot` | Viewport image for visual QA |
| `execute_blender_code` | Run arbitrary `bpy` Python in Blender |
| `create_primitive` | Cube / sphere / cylinder / monkey / … |
| `delete_object` | Delete by name |
| `set_object_transform` | Location / rotation / scale |
| `set_material` | Principled BSDF color / metal / roughness |
| `select_objects` | Selection control |
| `export_scene` | Export GLB / GLTF / FBX / OBJ / BLEND |

---

## Environment variables

| Variable | Default | Meaning |
|----------|---------|---------|
| `BLENDER_HOST` | `localhost` | Addon TCP host |
| `BLENDER_PORT` | `9876` | Addon TCP port (must match the N-panel port) |

---

## Protocol

Commands are JSON over TCP:

```json
{"type": "get_scene_info", "params": {"limit": 50}}
```

Responses:

```json
{"status": "success", "result": { ... }}
```

or

```json
{"status": "error", "message": "..."}
```

Commands are queued and executed on Blender’s **main thread** (required for `bpy`).

---

## Smoke test

```bash
cd blender-mcp
python scripts/smoke_test.py          # imports + tool registration
python scripts/smoke_test.py --live   # requires addon listening
```

---

## Security

`execute_blender_code` runs arbitrary Python inside Blender with full `bpy` access.  
Only connect Cursor to Blender on a trusted local machine. **Save your work** before agent sessions.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Cursor: `spawn uv ENOENT` | Use absolute path to `uv` in MCP config; fully quit + relaunch Cursor |
| `Could not connect to Blender` | Addon enabled? **Start MCP Server** clicked? Port matches `BLENDER_PORT`? |
| Timeouts | Keep Blender in the foreground; break huge scripts into smaller `execute_blender_code` calls |
| Addon missing after install | Restart Blender; search Preferences for “Plygon” |
| Black screenshots | Keep a 3D Viewport visible; offscreen path needs a GPU context |

---

## License

MIT — see [LICENSE](LICENSE).
