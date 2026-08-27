# Prompts for Plygon Houdini MCP

Copy these into Cursor after the MCP is connected and the Houdini listener is running.

---

## Quick smoke test

> Ping Houdini, show me the current scene info, then create a red-ish box primitive and screenshot the viewport.

---

## Procedural layout

> In Houdini, create a geo with a grid, then a mountain SOP on top with height 2. Layout the nodes, cook, and send me a viewport screenshot.

---

## Node graph from scratch

> Create a new geo at /obj called `agent_test`. Inside it, wire box → transform (scale 1.5) → color (random). Set display/render flags on color. Layout and screenshot.

---

## Inspection first

> Before changing anything: get_scene_info, list_nodes under /obj, and tell me what's in the hip. Don't modify until I confirm.

---

## VEX via code

> Use execute_houdini_code to add a point wrangle after a grid that sets `@P.y = sin(@P.x * 3) * 0.2`. Cook and screenshot.

---

## Save before destroy

> Save the hip to ~/Desktop/agent_backup.hip, then create a test sphere. If anything fails, tell me before retrying.

---

## HScript escape hatch

> Run HScript to print the current `$HIP` and frame range, then summarize in plain English.

---

## Material / look dev (via code)

> Inside /obj/agent_lookdev geo: create a sphere, add a material SOP or use execute_houdini_code to assign a basic Karma/Redshift/Mantra-agnostic diffuse if available. Screenshot when it reads as a hero prop.

---

## DOPs (advanced)

> Only if the scene is empty: sketch a minimal RBD setup (or tell me what's missing). Use small execute_houdini_code steps and verify after each.

---

## Troubleshooting prompt

> ping_houdini failed — walk me through checking shelf server, port 9877, and Cursor MCP config without changing my hip yet.
