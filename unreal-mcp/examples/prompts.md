# Prompts for Plygon Unreal MCP

Copy these into a local Cursor Agent chat after the MCP row is green and the Unreal Output Log says `PlygonMCP: listening on 127.0.0.1:9879`. A Cloud Agent cannot reach the editor.

## Ping

> Ping Unreal. Do not change the level and do not call any other tool.

## List actors

> List the actors in the current Unreal level. Do not change anything.

## Spawn a cube

> Spawn a static mesh cube named PlygonCube at the origin in the current Unreal level. Do not call any other tool.

## Screenshot

> Take one viewport screenshot of the Unreal level. Do not change the level.

## PCG

> List PCG components in the level. If there is one, set a float graph parameter you can see on it, then generate that component. Do not spawn or delete actors.

## Undo

After a spawn or a generate, click the Unreal Editor window and use Edit > Undo. On Windows the usual shortcut is Ctrl+Z. One tool call is one transaction.
