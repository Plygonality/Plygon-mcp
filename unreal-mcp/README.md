# Plygon Unreal MCP

A local MCP bridge for Unreal Editor. Cursor starts `plygon-unreal-mcp` over stdio. That process sends newline-delimited JSON to a Python listener inside the editor at `127.0.0.1:9879`.

The listener runs on the game thread. A background thread only accepts sockets. Commands run from a Slate post-tick callback. Editor mutations are wrapped in `unreal.ScopedEditorTransaction`, so Edit > Undo can revert them.

Target editor: Unreal Engine 5.4 or newer. This guide is written for Windows 11 and UE 5.9 Preview. v0.2.1 and earlier of this repo have no Unreal support.

```
Cursor agent  --stdio MCP-->  plygon-unreal-mcp  --TCP 127.0.0.1:9879-->  editor listener  --unreal-->  your level
```

A green MCP row only means Cursor started `uvx`. The Output Log must say `PlygonMCP: listening on 127.0.0.1:9879`. Ping from a local Agent chat. A Cloud Agent cannot see your PC.

## Epic's Unreal MCP and this bridge

UE 5.9 Preview ships an experimental Unreal MCP plugin. Epic's page [Unreal MCP in Unreal Editor](https://dev.epicgames.com/documentation/unreal-engine/unreal-mcp-in-unreal-editor) describes it as an MCP server inside the editor. With auto-start on, it binds `http://127.0.0.1:8000/mcp`. Its tools come from the Toolset Registry.

This package is a separate bridge, in the same shape as the Blender, Houdini, and SOLIDWORKS packages in this repo. It does not replace Epic's plugin and it does not talk to that HTTP server. The ports are different, so both can be enabled at the same time. Use Epic's plugin when you want its toolsets. Use this bridge when you want the same small inspect, edit, and screenshot loop as the other Plygon DCCs.

If you also generate Epic's client config, keep its `unreal-mcp` entry. Add `plygon-unreal` beside it. Do not give both servers the same name.

## Install on Windows 11 with UE 5.9 Preview

You need `uvx`, the Python listener inside the editor, and one `mcp.json` entry. `uvx` does not install anything inside Unreal.

### 1. Install uv and uvx

Use [Step 1 of the repo guide](../README.md#step-1--install-uv-once). On Windows, check the existing install before running the Astral installer again:

```powershell
& "$env:USERPROFILE\.local\bin\uvx.exe" --version
```

If that prints a version, do not rerun the installer. Cursor often locks `uv.exe`.

### 2. Enable the Python plugins

These steps follow Epic's current page [Scripting the Unreal Editor Using Python](https://dev.epicgames.com/documentation/en-us/unreal-engine/scripting-the-unreal-editor-using-python).

1. Open the project in Unreal Editor 5.9 Preview.
2. In the main menu, select **Edit > Plugins**.
3. In the Plugins window, go to the **Scripting** section.
4. Find **Python Editor Script Plugin** and select its checkbox.
5. Also enable **Editor Scripting Utilities**. Asset listing and actor edits use `EditorAssetLibrary` and `EditorActorSubsystem`, which that plugin provides. The current Python page recommends the plugin and does not name its category in the Plugins window. If it is not under Scripting, use the Plugins search field. The search field itself is documented on Epic's Unreal MCP page ("Search for Unreal MCP"), not on the Python page.
6. Restart Unreal Editor when it asks you to. The Python page says: restart Unreal Editor.

The embedded interpreter is Python 3.11.8. You do not install a separate Python for the editor. The MCP process uses the Python that `uvx` provides, which is a different interpreter.

### 3. Add the listener

The listener files in this repo are:

- `unreal-mcp/editor/init_unreal.py`
- `unreal-mcp/editor/plygon_unreal_mcp/` (the package directory next to that file)

Use one of the two setups below. Do not run both against the same port.

**Option A. `Content/Python/init_unreal.py`**

Epic's page says the editor runs `init_unreal.py` when it finds that file in a configured Python path, and that `Content/Python` under the project is one of those paths.

1. In the project folder, create `Content/Python` if it does not exist.
2. Copy `init_unreal.py` into `Content/Python/`.
3. Copy the `plygon_unreal_mcp` directory into `Content/Python/`, so the path is `Content/Python/plygon_unreal_mcp/listener.py`.
4. Restart Unreal Editor.

`init_unreal.py` inserts its own directory on `sys.path` and calls `start_server()`.

**Option B. Project Settings**

Epic's page says: select **Edit > Project Settings**. Under the **Plugins** list, select **Python**.

Startup scripts run after the default startup level is loaded. Additional Paths are import paths. They do not run a file by themselves.

1. Select **Edit > Project Settings**.
2. Under **Plugins**, select **Python**.
3. Add the absolute path of `unreal-mcp/editor` to **Additional Paths**. That directory is the parent of `plygon_unreal_mcp`.
4. Add the absolute path of `unreal-mcp/editor/init_unreal.py` to **Startup scripts**.
5. Restart Unreal Editor. The Python page says to restart after changing either setting.

### 4. Confirm the listener in the Output Log

Epic's Python page says `print()` output goes to the Output Log panel. Epic's [editor interface](https://dev.epicgames.com/documentation/unreal-engine/unreal-editor-interface) page documents Output Log on the bottom toolbar. Epic's USD page documents **Window > Output Log**. The 5.9 release notes do not rename that panel.

1. Open the Output Log from the bottom toolbar, or select **Window > Output Log**.
2. Find this line:

```text
PlygonMCP: listening on 127.0.0.1:9879
```

3. Leave the editor open.

If the line is missing, use the troubleshooting table below. Do not continue to Cursor until the line is there.

### 5. Add the server in Cursor

Quit Cursor from the tray icon so it sees `uv`, then reopen it.

The menu path **Settings > MCP** is the path for this guide. It is not an Unreal Editor menu and it is not taken from Epic's docs. Other pages in this repo still say **Customize → MCPs** for the same `mcp.json` file. Use the screen that opens `C:\Users\<your-name>\.cursor\mcp.json`.

1. Open **Settings > MCP**.
2. Open `mcp.json`.
3. If the file already has other servers, keep them. Add `plygon-unreal` inside the existing `"mcpServers"` object, with a comma between neighboring properties.
4. If the file is empty, paste this block.

```json
{
  "mcpServers": {
    "plygon-unreal": {
      "command": "cmd",
      "args": [
        "/c",
        "%USERPROFILE%\\.local\\bin\\uvx.exe",
        "--from",
        "git+https://github.com/Plygonality/Plygon-mcp.git#subdirectory=unreal-mcp",
        "plygon-unreal-mcp"
      ],
      "env": {
        "UNREAL_HOST": "127.0.0.1",
        "UNREAL_PORT": "9879",
        "PYTHONUTF8": "1"
      }
    }
  }
}
```

5. Save the file.
6. Turn **plygon-unreal** on.
7. Wait until the row is green and lists tools.

The `--from` URL tracks the default branch. To pin release v0.2.2, use `git+https://github.com/Plygonality/Plygon-mcp.git@v0.2.2#subdirectory=unreal-mcp` in that same position. The package version is 0.2.2. Tags before v0.2.2 have no `unreal-mcp` directory. Leave the rest of the JSON unchanged.

`UNREAL_HOST` and `UNREAL_PORT` must match the listener. The listener refuses any bind that is not `127.0.0.1`.

### 6. First use

The editor Output Log still says `listening on 127.0.0.1:9879`. Open a new local Agent chat. Do not use a Cloud Agent.

Paste one prompt at a time. Approve the tool call if Cursor asks.

1. Ping. Do not change the level.

> Ping Unreal. Do not change the level and do not call any other tool.

The result contains `"pong": true`.

2. List actors.

> List the actors in the current Unreal level. Do not change anything.

3. Spawn a cube.

> Spawn a static mesh cube named PlygonCube at the origin in the current Unreal level. Do not call any other tool.

The listener spawns a `StaticMeshActor` and assigns `/Engine/BasicShapes/Cube` when you do not pass another mesh path. That asset path was not confirmed on an Epic documentation page. If the mesh is missing, the actor is still created and the result includes `mesh_warning`.

4. Screenshot.

> Take one viewport screenshot of the Unreal level. Do not change the level.

Keep a level viewport open. The capture is requested with `AutomationLibrary.take_high_res_screenshot` and the reply waits until the PNG exists.

5. PCG.

Enable the PCG plugin first if `list_pcg` reports that `PCGComponent` is missing. This guide did not re-check that plugin's category label on the 5.9 Plugins page. The class name in the Python API is `PCGComponent`.

> List PCG components in the level. If there is one, set a float graph parameter you can see on it, then generate that component. Do not spawn or delete actors.

If the level has no PCG component, the tool returns an error that says so. That is the expected result for an empty level.

6. Undo.

Click the Unreal Editor window. Use **Edit > Undo**. On Windows the usual shortcut is Ctrl+Z. This guide did not re-check the 5.9 keybind page. The spawn, the transform, the import, the PCG edit, and `execute_python` are each one `ScopedEditorTransaction`, so one undo reverts that call.

More prompts: [`examples/prompts.md`](examples/prompts.md).

### 7. Troubleshooting

| What you see | What to do |
|---|---|
| Output Log never prints `listening on 127.0.0.1:9879` | The Python Editor Script Plugin is off, or the startup file is not on a Python path. Repeat step 2, restart the editor, and confirm `init_unreal.py` is in `Content/Python` or listed under **Startup scripts**. |
| `Port 9879 is already in use` | Another listener already bound 9879. Stop it, or pick another port in `start_server(port=...)` and set `UNREAL_PORT` to that same value. |
| MCP row is green, tool says connection refused | `uvx` is up and the editor listener is not. Go back to the Output Log line. |
| MCP row says `'uvx' is not recognized` | The command must be `cmd`, `/c`, and `%USERPROFILE%\.local\bin\uvx.exe`. Quit Cursor from the tray and reopen it. |
| Epic's Unreal MCP is also running | That is allowed. Epic's default URL is `http://127.0.0.1:8000/mcp`. This bridge uses TCP `127.0.0.1:9879`. They do not share a port unless you changed one of them. Keep the Cursor entries under different names. |
| Windows Defender Firewall prompts for Unreal Editor | The listener binds loopback only. If Windows asks, allow Unreal Editor on private networks. This dialog is Windows, not an Epic menu, and the exact wording was not taken from Epic's docs. Blocking Unreal Editor can make a later ping time out instead of refusing the connection. |
| `PCGComponent is not available` | The PCG plugin is not loaded. Enable it, restart the editor, and start the listener again. |
| Screenshot times out | A level viewport has to be open. The editor writes the PNG on a later tick. The tool waits up to 20 seconds. |
| Ping works in a local Agent and fails in a Cloud Agent | Cloud `127.0.0.1` is not your PC. Use a desktop Agent chat. |

Port check in PowerShell:

```powershell
Get-NetTCPConnection -LocalPort 9879 -State Listen -ErrorAction SilentlyContinue
```

## Tools

| Tool | What it does |
|---|---|
| `ping_unreal` | Listener is up |
| `get_addon_info` | Listener version, engine version, capabilities |
| `get_level_info` / `list_actors` | Current level and loaded actors |
| `get_actor_info` | One actor: label, class, path, transform, and components |
| `select_actors` | Select by label, object name, or path. `REPLACE` or `ADD` |
| `spawn_actor` | Static mesh, point light, directional light, spot light, rect light, camera, or cine camera |
| `set_actor_transform` | Location (x, y, z), rotation (pitch, yaw, roll in degrees), scale |
| `delete_actor` | Destroy one actor |
| `list_assets` / `import_asset` | Content Browser list, and an automated import |
| `get_viewport_screenshot` | Level viewport PNG |
| `execute_python` | Python in the editor, with `unreal` in scope and stdout captured |
| `list_pcg` | PCG components and their graph paths |
| `set_pcg_parameter` | One graph-instance parameter |
| `generate_pcg` | `PCGComponent.generate` |

`execute_python` truncates captured stdout at 256 KiB and appends `…[truncated N bytes]`, same as Blender's `execute_code`.

## Checked API names

Used from Epic's Python API docs for 5.4 or later, and guarded with `hasattr` when a plugin may be absent:

- `register_slate_post_tick_callback`, `unregister_slate_post_tick_callback`
- `register_python_shutdown_callback`, `unregister_python_shutdown_callback`
- `is_editor`, `get_editor_subsystem`, `SystemLibrary.get_engine_version`
- `EditorActorSubsystem`: `get_all_level_actors`, `get_selected_level_actors`, `set_selected_level_actors`, `spawn_actor_from_class`, `destroy_actor`
- `Actor`: `get_actor_label`, `set_actor_label`, `get_actor_location`, `set_actor_location`, `get_actor_rotation`, `set_actor_rotation`, `get_actor_scale3d`, `set_actor_scale3d`, `get_components_by_class`
- `EditorAssetLibrary.list_assets`, `EditorAssetLibrary.load_asset`, `load_asset`
- `AssetImportTask`, `AssetToolsHelpers.get_asset_tools`, `AssetTools.import_asset_tasks`
- `AutomationLibrary.take_high_res_screenshot`
- `PCGComponent.generate`, `PCGComponent.get_graph`, `graph_instance`
- `PCGGraphParametersHelpers` setters for bool, int32, int64, float, double, string, name, and vector
- Class names: `StaticMeshActor`, `PointLight`, `DirectionalLight`, `SpotLight`, `RectLight`, `CameraActor`, `CineCameraActor`, `ActorComponent`, `ScopedEditorTransaction`

Not verified, so this bridge does not call them or marks them in the result:

- The 5.9 release notes mention new script functions that add and validate PCG graph edges. The notes do not give the Python names. No edge API is called.
- `/Engine/BasicShapes/Cube` is the default mesh path. It was not confirmed on a documentation page. Pass `mesh_path` to use another asset.
- `set_static_mesh` is called only when the component has that method. Otherwise the listener uses `set_editor_property("static_mesh")`. The editor-property pattern is documented. The property string `static_mesh` was not re-read from the `StaticMeshComponent` property table.
- `ScopedEditorTransaction` is in the 5.4 Python API index. This bridge uses it as a context manager. An `__enter__` page was not opened.

The UE 5.9 Preview notes used for this pass are [Unreal Engine 5.9 Preview Release Notes](https://dev.epicgames.com/documentation/en-us/unreal-engine/unreal-engine-5-9-release-notes), last updated 11/9/26 on that page.

## Privacy

The listener binds `127.0.0.1:9879` only. The port is unauthenticated. Do not forward it. `execute_python` runs any Python that can open that port, inside the editor. A browser `fetch` is rejected. Other local programs that speak newline-delimited JSON are not.

Cursor can send tool results, including screenshots, to the configured model provider.

## Tests

Unreal Editor is not available in CI. The tests mock the `unreal` module and a TCP peer.

```bash
cd unreal-mcp && uv sync --extra dev --locked && uv run pytest -q
uv run python scripts/smoke_test.py
```

`scripts/smoke_test.py --live` pings a listener that is already running.
