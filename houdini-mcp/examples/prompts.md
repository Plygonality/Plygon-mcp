# Prompts for Plygon Houdini MCP

Copy these into a **local** Cursor Agent chat after the MCP is green **and** Houdini prints `PlygonMCP: listening on 127.0.0.1:9877`. Cloud Agent chats cannot reach your DCC.

---

## Quick smoke test

> Ping Houdini with ping_houdini, then call get_scene_info. Do not change the hip.

If that returns JSON, follow with:

> Ping Houdini, show me the current scene info, then create a red-ish box primitive and screenshot the viewport.

---

## Chess set (example from a real install)

This pair produced the screenshot in the [install guide](../README.md#4-try-it) (`assets/chess-set-example.png`): pawn / bishop / rook geos plus a procedural board with a chamfered border.

<p align="center">
  <img src="../assets/chess-set-example.png" alt="Cursor Agent and Houdini after building a procedural chess set: pawn, bishop, rook, and a checkerboard with a chamfered border" width="100%">
</p>

**Chess pieces**

> Create a simple Pawn piece for your chess set using Revolve.
> Then try to make the Bishop and Rook.
>
> Tip: you don’t have to use Revolve for everything, you can build it up from different shapes, using what you learned already (last week for instance).

**Chess board**

> Create a simple procedural chess board where the user can change the number of sides in x and z direction. For the simple board, you always have an uneven amount of tiles per side (1,3, 5..). Every square is slightly extruded and beveled upwards so the divisions are clear. They change colors between black and white. Around the board is also an additional brown border, slightly thicker and chamfered, to indicate the end of the board. Bonus: A real chessboard has an even number of tiles(8x8). Try to find a solution that solves for an even number of rows and columns.

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

> ping_houdini failed. Classify spawn vs connection-refused vs timeout. Check: Python Shell `from plygon_houdini_mcp import listener` then `listener.start_server(port=9877)`, port 9877 (not 8100), packages/plygon_houdini_mcp.json exists, local Agent not Cloud, Houdini not frozen. A Console error about fxhoudinimcp or .cursor/houdini-mcp is a different MCP — Close it. Do not change my hip.
