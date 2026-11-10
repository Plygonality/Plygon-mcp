# Prompts for Plygon Unreal MCP

Copy these into a local Cursor Agent chat after the MCP row is green and the Unreal Output Log says `PlygonMCP: listening on 127.0.0.1:9879`. Use a desktop Agent. A Cloud Agent cannot reach the editor.

The level should already be open. Units are centimetres. Rotation is pitch, yaw, roll in degrees.

## Quick smoke test

> Ping Unreal with ping_unreal, then call get_level_info. Do not change the level.

If that returns JSON, follow with:

> Spawn a static mesh named Crate at 200, 0, 50 using /Engine/BasicShapes/Cube. Then take a viewport screenshot. Do not delete anything.

## Lights and a camera

> Add a point light named Key above the origin at 0, 0, 300, and a cine camera named Shot at 400, -200, 160 looking back toward the origin with rotation -15, -150, 0. Screenshot the viewport. Do not delete existing actors.

## PCG

> List PCG components and graph assets. Do not generate yet. If a component is present, set one float parameter I name and then generate that component. If none are present, stop and say so.

## When ping fails

> ping_unreal failed. Classify spawn vs connection-refused vs timeout. Check: the editor is open, the Output Log says listening on 127.0.0.1:9879, and this chat is a local Agent. A green MCP row is not enough. Do not change the level.
