# Houdini package layout

Houdini only loads JSON files that sit **directly** in `packages/` (it does not scan subfolders).

After `python houdini-mcp/scripts/install_package.py` you should have:

```text
houdini21.0/packages/plygon_houdini_mcp.json   ← scanned by Houdini
houdini21.0/packages/plygon_houdini_mcp/       ← add-on code, shelf, inner json
```

The wrapper JSON sets `HOUDINI_PATH` to `$HOUDINI_PACKAGE_PATH/plygon_houdini_mcp` so this import works:

```python
from plygon_houdini_mcp import listener
listener.start_server(port=9877)
```

The inner `plygon_houdini_mcp.json` is for the rare case where someone points `HOUDINI_PACKAGE_DIR` at the package folder itself. The installer always writes the wrapper; do not skip that file.

Windows prefs live at `Documents\houdini21.0` or `OneDrive\Documenten\houdini21.0`, not `Documents\houdini\21.0`.
