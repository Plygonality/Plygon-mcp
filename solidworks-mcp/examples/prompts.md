# Prompts for Plygon SOLIDWORKS MCP

Copy these into a **local** Cursor Agent chat after the MCP is green **and** the listener window prints `PlygonMCP: listening on 127.0.0.1:9878`. SOLIDWORKS must already be open on that Windows PC. Cloud Agent chats cannot reach it.

Lengths below assume an MMGS part, where `60` means 60 mm.

---

## Quick smoke test

> Ping SOLIDWORKS with ping_solidworks, then call get_document_info. Do not change the part.

If that returns JSON, follow with:

> On the active part, create a 60 by 40 by 12 mm box on the front plane named Plate. Rebuild, then screenshot the viewport. Do not export.

---

## Bracket

> Create a new part. Make a 80 by 50 by 6 mm plate on the front plane. Then use execute_solidworks_code, in small steps, to add four M6 clearance holes (6.6 mm) inset 8 mm from the corners. Rebuild and screenshot after the plate and again after the holes. Set a custom property Description to "Mounting plate".

---

## Export

> Export the active document to STEP at C:\Temp\plygon-part.step. Do not overwrite my saved part. Tell me the path the tool returned.

---

## When ping fails

> ping_solidworks failed. Classify spawn vs connection-refused vs timeout. Check: SOLIDWORKS is open, scripts\start-solidworks.cmd is still running, it printed listening on 127.0.0.1:9878, and this chat is a local Agent. A green MCP row is not enough. Do not change my part.
