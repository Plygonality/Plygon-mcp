<p align="center">
  <img src="blender-mcp/assets/banner.svg" alt="Plygon Blender MCP — talk to Blender from Cursor" width="100%">
</p>

<p align="center">
  <strong>Tell Cursor to build in Blender. Watch it happen on your machine.</strong>
</p>

<p align="center">
  <a href="https://github.com/EmilvanDam/plygon-mcp/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-ff6a1a?style=flat-square" alt="MIT"></a>
  <a href="blender-mcp/"><img src="https://img.shields.io/badge/Blender-3.0%2B-orange?style=flat-square&logo=blender&logoColor=white" alt="Blender 3.0+"></a>
  <a href="blender-mcp/"><img src="https://img.shields.io/badge/Cursor-MCP-111111?style=flat-square" alt="Cursor MCP"></a>
  <a href="blender-mcp/"><img src="https://img.shields.io/badge/telemetry-none-7dffa3?style=flat-square" alt="No telemetry"></a>
</p>

<p align="center">
  <a href="https://cursor.com/link/mcp/install?name=plygon-blender&config=eyJjb21tYW5kIjoidXZ4IiwiYXJncyI6WyItLWZyb20iLCJnaXQraHR0cHM6Ly9naXRodWIuY29tL0VtaWx2YW5EYW0vcGx5Z29uLW1jcC5naXQjc3ViZGlyZWN0b3J5PWJsZW5kZXItbWNwIiwicGx5Z29uLWJsZW5kZXItbWNwIl0sImVudiI6eyJCTEVOREVSX0hPU1QiOiJsb2NhbGhvc3QiLCJCTEVOREVSX1BPUlQiOiI5ODc2In19"><img src="https://cursor.com/deeplink/mcp-install-dark.svg" alt="Add to Cursor"></a>
</p>

# plygon-mcp

A tech-art studio repo. First drop: a **local Blender MCP** you can fork, run, and actually own.

Cursor’s agents already write code. **Plygon lets them model.** Describe a shot, a prop, a material — the agent inspects your scene, moves objects, assigns shaders, frames the camera, and sends you a viewport screenshot to check its work.

Nothing leaves localhost. No telemetry. No “free” cloud that trains on your `.blend`.

---

## Why people fork this

| You want | You get |
|---|---|
| An agent that *sees* Blender | Viewport screenshots in the loop |
| A bridge small enough to read | One add-on + one MCP server |
| Privacy | TCP on `localhost:9876`, MIT, no phone-home |
| Something you can steal for a pipeline | Fork it. Rename it. Ship it in your studio. |

This is not a 300-tool kitchen sink. It’s the layer tech artists actually keep: inspect → change → look → export.

---

## 60-second setup

**1. Clone**

```bash
git clone https://github.com/EmilvanDam/plygon-mcp.git
cd plygon-mcp
```

**2. Install the Blender add-on**

```bash
python blender-mcp/scripts/install_addon.py
```

Blender → Preferences → Add-ons → enable **Plygon Blender MCP**.  
3D Viewport → `N` → **PlygonMCP** → **Start MCP Server**.

**3. Connect Cursor**

[Add to Cursor](https://cursor.com/link/mcp/install?name=plygon-blender&config=eyJjb21tYW5kIjoidXZ4IiwiYXJncyI6WyItLWZyb20iLCJnaXQraHR0cHM6Ly9naXRodWIuY29tL0VtaWx2YW5EYW0vcGx5Z29uLW1jcC5naXQjc3ViZGlyZWN0b3J5PWJsZW5kZXItbWNwIiwicGx5Z29uLWJsZW5kZXItbWNwIl0sImVudiI6eyJCTEVOREVSX0hPU1QiOiJsb2NhbGhvc3QiLCJCTEVOREVSX1BPUlQiOiI5ODc2In19) · or paste [`blender-mcp/configs/cursor.mcp.git.json`](blender-mcp/configs/cursor.mcp.git.json) into **Settings → MCP**.

**4. Say this**

> Create a studio-lit chrome Suzanne. Screenshot when it looks like a keyframe.

Full protocol, tools, and local-path configs: **[`blender-mcp/README.md`](blender-mcp/README.md)**  
Steal-these prompts: **[`blender-mcp/examples/prompts.md`](blender-mcp/examples/prompts.md)**

---

## How it works

```
You  →  Cursor agent  →  Plygon MCP  →  localhost:9876  →  Blender  →  your scene
```

The agent never needs your Blender Python muscle memory. You keep the taste. It keeps the clicks.

---

## Star it, fork it, break it

If this saves you a night of clicking, **star the repo** so other tech artists find it.

Forks are the point. Plygon is a public MIT workshop for bpy tools, add-ons, and MCPs — this Blender bridge is the first thing worth stealing.

[github.com/EmilvanDam/plygon-mcp](https://github.com/EmilvanDam/plygon-mcp)
