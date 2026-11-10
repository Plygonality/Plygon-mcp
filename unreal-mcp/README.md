# Plygon Unreal MCP

This page is the whole install for Windows 11, Unreal Editor 5.9 Preview, and Cursor. Every command is written here. Paste each block only in the app and window named above that block.

The bridge is two programs. Cursor starts `plygon-unreal-mcp` with `uvx`. That process talks to a Python listener inside the Unreal Editor on `127.0.0.1:9879`. A green row in Cursor only means `uvx` started. The editor is ready when the Output Log shows `PlygonMCP: listening on 127.0.0.1:9879`.

Use a local Cursor Agent chat. A Cloud Agent cannot reach the editor on your PC.

Epic's Unreal MCP is a different server. Its default address is `http://127.0.0.1:8000/mcp`. Leave it on if you use it. Do not point it at port 9879. The two servers can run at the same time under different names.

This package targets Unreal Engine 5.4 and newer. The clicks below are for the 5.9 Preview editor on Windows 11.

## 1. What you need

- Windows 11.
- Unreal Editor 5.9 Preview, or any Unreal Editor 5.4 or newer. Open a project you can edit. The project folder is the folder that contains the `.uproject` file.
- The Cursor desktop app, installed and signed in.
- An internet connection for the `uv` installer and for the first `uvx` download.

You do not need Git. You do not need a separate Python install for the editor. Unreal ships its own Python. `uvx` uses a different Python, only for the Cursor-side process.

## 2. Install uv and uvx

`uvx` is the program Cursor uses to start the bridge. It does not install anything inside Unreal.

1. If Cursor is open, close it first. Right-click the Cursor icon in the system tray by the clock, then click **Quit**. Cursor can lock `uv.exe`. If you skip this, the installer may say `uv.exe` is being used by another process.
2. Open the Start menu. Type `PowerShell`. Click **Windows PowerShell**. Do not click the app named only **PowerShell** if both are listed. Leave this window open. Every PowerShell block on this page is pasted into this window.
3. Check whether `uvx` is already installed. Paste this into Windows PowerShell and press Enter:

```powershell
& "$env:USERPROFILE\.local\bin\uvx.exe" --version
```

Expected when it is already installed: one line with a version, such as `uvx 0.9.2` (the numbers will differ). If you see a version, skip the installer and go to section 3.

Expected when it is missing: PowerShell reports that the path is not recognized, or that the file cannot be found. Then run the installer.

4. Paste this into the same Windows PowerShell window and press Enter:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Expected: the installer downloads `uv` and prints that it installed `uv` and `uvx` under your user folder, then returns to the prompt. If it says `uv.exe` is being used by another process, quit Cursor from the tray and run the installer again.

5. Paste the version check again:

```powershell
& "$env:USERPROFILE\.local\bin\uvx.exe" --version
```

Expected: one version line. Do not continue until you see it.

## 3. Enable plugins in Unreal

1. Open your project in Unreal Editor 5.9 Preview. Wait until the level is open.
2. In the main menu, click **Edit**, then **Plugins**.
3. Click the search box at the top of the Plugins window. The box is the search field for plugin names. Type:

```text
Python Editor Script
```

4. On the row **Python Editor Script Plugin**, turn the checkbox on.
5. Clear the search box and type:

```text
Editor Scripting Utilities
```

6. Turn that plugin's checkbox on. The Python scripting page recommends this plugin and does not name which Plugins category it sits in. Search is enough.
7. PCG tools are optional. If you want them, clear the search box and type `PCG`. Turn on **Procedural Content Generation Framework**. Skip this if you will not use PCG. The category name on the 5.9 Plugins page was not rechecked. Search for `PCG` finds it.
8. If the editor asks to restart, click **Restart Now**. If that button has different wording, click the button that restarts the editor. Wait until the project is open again.

If a checkbox was already on, leave it on. Restart only when the editor asks.

## 4. Put the listener files in the project

The editor runs `Content\Python\init_unreal.py` on startup. That file starts the listener. The folder `plygon_unreal_mcp` next to it is the listener code.

Use either the copy into `Content\Python` or the Project Settings paths in section 4b. Use one of them. If you use both, the second start prints that the server is already running. That is not a failure, but you then have two copies to update later.

### 4a. Download v0.2.2 and copy the files

Stay in the same Windows PowerShell window from section 2.

Paste this block and press Enter. It downloads the v0.2.2 source zip and extracts it under your user folder.

```powershell
$zip = "$env:TEMP\Plygon-mcp-v0.2.2.zip"
$dest = "$env:USERPROFILE\Plygon-mcp-0.2.2"
Invoke-WebRequest -Uri "https://github.com/Plygonality/Plygon-mcp/archive/refs/tags/v0.2.2.zip" -OutFile $zip
if (Test-Path $dest) { Remove-Item $dest -Recurse -Force }
Expand-Archive -Path $zip -DestinationPath "$env:USERPROFILE" -Force
Get-ChildItem "$dest\unreal-mcp\editor"
```

The zip's top folder is `Plygon-mcp-0.2.2`, so `$dest` is `%USERPROFILE%\Plygon-mcp-0.2.2`.

Expected: the last command lists `init_unreal.py` and a directory `plygon_unreal_mcp`. If `Get-ChildItem` says the path does not exist, look in `%USERPROFILE%` for `Plygon-mcp-0.2.2` and set `$dest` to that folder before the copy block.

Clicks, if you prefer not to download from PowerShell:

1. Open https://github.com/Plygonality/Plygon-mcp in the browser.
2. Click the branch control that shows `main`.
3. Click **Tags**.
4. Click **v0.2.2**.
5. Click the green **Code** button.
6. Click **Download ZIP**.
7. In File Explorer, open Downloads, right-click `Plygon-mcp-0.2.2.zip`, click **Extract All**, then **Extract**.
8. You should see `Downloads\Plygon-mcp-0.2.2\unreal-mcp\editor\init_unreal.py`.

Set the project folder. In File Explorer, open the folder that contains your `.uproject` file. Click the address bar and copy that path. Paste it between the quotes below, in the same Windows PowerShell window, and press Enter.

```powershell
$Project = "C:\Users\YourName\Documents\Unreal Projects\MyProject"
```

Replace that example with your path. `$Project` is a folder, not the `.uproject` file. Expected: the prompt returns and prints nothing.

Paste this copy block in the same window and press Enter. If you used **Extract All** instead of the download block, change `$dest` in the first line to the extracted folder, for example `C:\Users\YourName\Downloads\Plygon-mcp-0.2.2`.

```powershell
$dest = "$env:USERPROFILE\Plygon-mcp-0.2.2"
New-Item -ItemType Directory -Force -Path "$Project\Content\Python" | Out-Null
Copy-Item "$dest\unreal-mcp\editor\init_unreal.py" "$Project\Content\Python\init_unreal.py" -Force
Copy-Item "$dest\unreal-mcp\editor\plygon_unreal_mcp" "$Project\Content\Python\plygon_unreal_mcp" -Recurse -Force
Test-Path "$Project\Content\Python\init_unreal.py"
Test-Path "$Project\Content\Python\plygon_unreal_mcp\listener.py"
```

Expected: the two `Test-Path` lines each print `True`. If either prints `False`, `$Project` or `$dest` is wrong. Fix the path and run the block again.

### 4b. Alternative: Project Settings paths

Use this only if you did not copy the files into `Content\Python`.

The extracted editor folder must already be on disk from section 4a. Example path: `C:\Users\YourName\Plygon-mcp-0.2.2\unreal-mcp\editor`.

1. In Unreal, click **Edit**, then **Project Settings**.
2. On the left, under **Plugins**, click **Python**.
3. In **Additional Paths**, add the full path of the `editor` folder (the folder that contains `init_unreal.py` and `plygon_unreal_mcp`). Additional Paths does not run a script. It only lets Python import the listener.
4. In **Startup scripts**, add the full path of `init_unreal.py` in that same `editor` folder. Startup scripts run after the startup level loads.
5. Close Project Settings.

Those two field names are **Additional Paths** and **Startup scripts**.

## 5. Confirm the listener in the Output Log

1. Close Unreal Editor if it is open, then open the same project again. `init_unreal.py` runs on startup.
2. In the main menu, click **Window**, then **Output Log**. The same panel is also on the bottom toolbar. The menu item **Window > Output Log** is the one to use if the panel is hidden.
3. In the Output Log filter field, type:

```text
PlygonMCP
```

The filter field is the box that hides lines which do not match. Its label was not rechecked.

4. Expected line:

```text
PlygonMCP: listening on 127.0.0.1:9879
```

Leave the editor open. If the line is missing, use section 9. Do not continue until the line is there.

## 6. Add the server in Cursor

1. Quit Cursor from the system tray if it is open: right-click the Cursor icon, then **Quit**. Open Cursor again so it sees `uvx`.
2. Open Cursor. Open **Settings**, then **MCP**. Some Cursor builds label this screen **Customize**, then **MCPs**. It is the same screen. That label is not an Unreal menu.
3. Open `mcp.json`. The full path is:

```text
%USERPROFILE%\.cursor\mcp.json
```

For a user named `YourName`, that is `C:\Users\YourName\.cursor\mcp.json`.

4. If the file is empty, or it is only `"mcpServers": {}`, select all of the text and replace it with this block. Paste it into `mcp.json`, not into PowerShell and not into Unreal.

```json
{
  "mcpServers": {
    "plygon-unreal": {
      "command": "cmd",
      "args": [
        "/c",
        "%USERPROFILE%\\.local\\bin\\uvx.exe",
        "--from",
        "git+https://github.com/Plygonality/Plygon-mcp.git@v0.2.2#subdirectory=unreal-mcp",
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

5. If `plygon-blender` or `plygon-houdini` is already in the file, do not delete those entries. Add `plygon-unreal` inside the same `"mcpServers"` object, with a comma between entries. This complete file is a valid example with Blender, Houdini, and Unreal. The Unreal URL is pinned to `v0.2.2`. The Blender and Houdini URLs in this example are the unpinned ones. If your file already has those two, keep their existing URLs and only add the `plygon-unreal` object. If you also have `plygon-solidworks`, keep it and add a comma before `plygon-unreal`.

```json
{
  "mcpServers": {
    "plygon-houdini": {
      "command": "cmd",
      "args": [
        "/c",
        "%USERPROFILE%\\.local\\bin\\uvx.exe",
        "--from",
        "git+https://github.com/Plygonality/Plygon-mcp.git#subdirectory=houdini-mcp",
        "plygon-houdini-mcp"
      ],
      "env": {
        "HOUDINI_HOST": "127.0.0.1",
        "HOUDINI_PORT": "9877",
        "PYTHONUTF8": "1"
      }
    },
    "plygon-blender": {
      "command": "cmd",
      "args": [
        "/c",
        "%USERPROFILE%\\.local\\bin\\uvx.exe",
        "--from",
        "git+https://github.com/Plygonality/Plygon-mcp.git#subdirectory=blender-mcp",
        "plygon-blender-mcp"
      ],
      "env": {
        "BLENDER_HOST": "127.0.0.1",
        "BLENDER_PORT": "9876",
        "PYTHONUTF8": "1"
      }
    },
    "plygon-unreal": {
      "command": "cmd",
      "args": [
        "/c",
        "%USERPROFILE%\\.local\\bin\\uvx.exe",
        "--from",
        "git+https://github.com/Plygonality/Plygon-mcp.git@v0.2.2#subdirectory=unreal-mcp",
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

6. Press **Ctrl+S**.
7. Return to the MCP screen. Turn **plygon-unreal** on.
8. Wait until the **plygon-unreal** row is green and lists tools. `ping_unreal` should be in the list.

If every MCP row disappears after you save, the JSON is invalid. Press **Ctrl+Z**, check commas and braces, and save again. There must be one `"mcpServers"` object.

A green row still does not prove the editor is listening. The Output Log line from section 5 has to be there too.

## 7. First use

In Cursor, open a new **Agent** chat on the desktop app. Do not use Ask mode. Do not use a Cloud Agent.

The Unreal Editor window stays open, with the Output Log line from section 5 still showing.

Paste one prompt at a time into the Agent chat input. Press Enter. If Cursor asks to approve a tool, approve it.

Each prompt is a chat message, not a PowerShell command and not an Unreal console command.

### Ping

```text
Ping Unreal. Do not change the level and do not call any other tool.
```

Expected: a tool result that contains `"pong": true`.

### Level info

```text
Get Unreal level info. Do not change the level and do not call any other tool.
```

Expected: the level path, the engine version, and an actor count. Nothing in the level moves.

### List actors

```text
List the actors in the current Unreal level. Do not change anything.
```

Expected: a list of actor labels. Use one of those labels if you need a name before the spawn step.

### Spawn a cube, a light, and a camera

```text
In the current Unreal level, spawn a static mesh cube named PlygonCube at 0,0,0, a point light named PlygonKey at 0,0,300, and a camera named PlygonCam at 400,-400,200. Do not delete anything.
```

Expected: three new actors in the level. `PlygonCube` uses the engine cube mesh when no other mesh path is given. That asset path, `/Engine/BasicShapes/Cube`, was not confirmed on a documentation page. If the mesh is missing, the actor still exists and the result includes `mesh_warning`.

### Select

```text
Select the Unreal actor named PlygonCube. Do not move or delete it.
```

Expected: `PlygonCube` is the selected actor in the editor.

### Actor info

```text
Get info for the Unreal actor named PlygonCube. Do not change the level.
```

Expected: the label `PlygonCube`, the class, the path, a transform with location, rotation, and scale, and a components list.

### Move

```text
Move the Unreal actor PlygonCube to 100, 0, 0. Do not spawn or delete anything.
```

Expected: the cube's location is about 100, 0, 0.

### Delete

Do this only after you have the screenshot you want, or undo it afterward.

```text
Delete the Unreal actor named PlygonCube. Do not change any other actor.
```

Expected: `PlygonCube` is gone. `PlygonKey` and `PlygonCam` remain.

### List assets

```text
List Unreal assets under /Game. Do not import or delete anything.
```

Expected: asset paths under `/Game`. A new project can return a short list. That is normal.

### Import an asset

Replace the file path with a real `.fbx` or `.obj` on your PC before you paste. The example path below is only a shape. The file is not included with this bridge.

```text
Import the file C:\Users\Public\box.obj into /Game/Imported in Unreal. If that file does not exist, stop and say the file is missing. Do not spawn actors.
```

Expected when the file exists: one or more imported asset paths under `/Game/Imported`. Expected when it does not: an error that names the missing file, and no new asset.

### Screenshot

Keep a level viewport open in Unreal.

```text
Take one viewport screenshot of the Unreal level. Do not change the level.
```

Expected: an image in the chat. The capture can take up to 20 seconds because the editor writes the PNG on a later tick.

### Python

```text
In Unreal, run only this Python and do not change actors:

import unreal
print("plygon execute_python ok")
unreal.log("plygon execute_python ok")
```

Expected: the tool result contains `plygon execute_python ok`. The same text appears in the Output Log. This call is one undo step.

### PCG

Skip this if you did not enable the PCG plugin in section 3.

```text
List PCG components in the Unreal level. If there is exactly one, and it has a float parameter named Density, set Density to 0.5 and generate that component. If there is no PCG component, stop and say so. Do not spawn or delete actors.
```

Expected with no PCG actor: a result that says there is no PCG component. Expected with the plugin off: a result that says `PCGComponent` is not available. Enable the PCG plugin, restart the editor, and confirm the listening line again before you retry.

### Undo

Click the Unreal Editor window. In the main menu, click **Edit**, then **Undo**.

The usual Windows shortcut is Ctrl+Z. The 5.9 keybind page was not rechecked.

Spawn, move, delete, import, PCG edits, and `execute_python` are each one editor transaction. One undo reverts that call. A read such as ping, list, or screenshot does not add an undo step.

## 8. Update later, or stop and remove the listener

### Update the listener and the Cursor package

1. Quit Unreal Editor: **File**, then **Exit**. If that menu item differs, close the editor window.
2. Quit Cursor from the system tray: right-click the Cursor icon, then **Quit**.
3. In Windows PowerShell, repeat the download block and the copy block from section 4. For a newer tag, change `v0.2.2` in the zip URL and change `$dest` to `%USERPROFILE%\Plygon-mcp-` plus the version without the leading `v`. Tag `v0.2.3` extracts to `Plygon-mcp-0.2.3`.
4. In `%USERPROFILE%\.cursor\mcp.json`, change `@v0.2.2` in the Unreal URL to the same new tag. Save the file.
5. Paste this in Windows PowerShell and press Enter:

```powershell
& "$env:USERPROFILE\.local\bin\uv.exe" cache clean plygon-unreal-mcp
```

Expected: the command returns to the prompt without an error. If it says the package is not in the cache, that is fine.

6. Open the project in Unreal. Confirm `PlygonMCP: listening on 127.0.0.1:9879` in the Output Log.
7. Open Cursor. Confirm **plygon-unreal** is green.

### Stop the listener and leave the files in place

The listener starts again the next time the editor opens `init_unreal.py`.

1. In Unreal, open **Window > Output Log**.
2. On the command line at the bottom of the Output Log, open the mode dropdown. It reads **Cmd** when it runs console commands. Set it to **Python**. If the dropdown wording differs, choose the mode that runs Python.
3. Paste this into that command line and press Enter:

```python
from plygon_unreal_mcp.listener import stop_server
stop_server()
```

Expected line in the Output Log:

```text
PlygonMCP: server stopped
```

### Remove the listener

1. Quit Unreal Editor.
2. In File Explorer, delete these two items if you used section 4a:

```text
<Project>\Content\Python\init_unreal.py
<Project>\Content\Python\plygon_unreal_mcp
```

`<Project>` is the folder that contains the `.uproject` file. If you used section 4b instead, open **Edit > Project Settings > Plugins > Python** and clear the **Additional Paths** entry and the **Startup scripts** entry you added.

3. Quit Cursor from the tray. Open `%USERPROFILE%\.cursor\mcp.json`. Delete the `plygon-unreal` object, including the comma that would otherwise leave invalid JSON. Save.
4. Open Cursor. The **plygon-unreal** row should be gone.

## 9. Troubleshooting

| What you see | Cause | What to do |
|---|---|---|
| PowerShell says `uvx.exe` is not recognized after the installer | The installer did not finish, or Cursor locked `uv.exe` | Quit Cursor from the tray. Run the installer in section 2 again. Then run `& "$env:USERPROFILE\.local\bin\uvx.exe" --version` and wait for a version line. |
| No `PlygonMCP: listening on 127.0.0.1:9879` line | The Python plugin is off, the editor was not restarted, or `init_unreal.py` is not in `Content\Python` and is not a Startup script | In **Edit > Plugins**, search `Python Editor Script` and turn **Python Editor Script Plugin** on. Click **Restart Now**. Then check `Test-Path` from section 4. Clear the Output Log filter and type `PlygonMCP` again. |
| Output Log says `PlygonMCP: listener did not start` | `start_server()` returned nothing. The lines above that error say why | Read the previous `PlygonMCP:` line. The usual cause is the port, or the editor is older than 5.4. |
| `Port 9879 is already in use` | Another program is listening on 9879 | In Windows PowerShell, paste `netstat -ano | findstr 9879` and press Enter. Expected when the port is busy: a line with `127.0.0.1:9879` and `LISTENING`. The last number is the PID. Paste `tasklist /FI "PID eq 1234"` and replace `1234` with that PID. Quit that program, then restart Unreal. To use another port, change `start_server()` in `init_unreal.py` to `start_server(port=9880)` and set `UNREAL_PORT` in `mcp.json` to `9880`. Restart the editor and Cursor. |
| **plygon-unreal** is red, or the row says `'uvx' is not recognized` | Cursor did not run the `cmd` / `uvx.exe` command | The command in `mcp.json` must be `cmd`, then `/c`, then `%USERPROFILE%\.local\bin\uvx.exe`, as in section 6. Quit Cursor from the tray and open it again. |
| **plygon-unreal** is green, and the tool says connection refused | `uvx` is running and the editor listener is not | Go back to section 5. The Output Log must show the listening line. A green row is not enough. |
| Windows asks whether to allow Unreal Editor through the firewall | The listener opened a socket, even though it is only on `127.0.0.1` | Allow Unreal Editor on private networks. The dialog text is Windows, not an Unreal menu, and the wording was not taken from Epic. If you block it, a later ping can time out instead of refusing the connection. |
| Epic's Unreal MCP is also enabled | That server is separate. Its default URL is `http://127.0.0.1:8000/mcp` | Leave it. Do not set its port to 9879. In Cursor, keep the name `unreal-mcp` for Epic's entry and `plygon-unreal` for this one. Check Epic's port under **Edit > Editor Preferences**, then **Agentic Workflows**, then **Model Context Protocol**. |
| Ping works in a local Agent chat and fails in a Cloud Agent | The cloud machine's `127.0.0.1` is not your PC | Use a local Agent chat in the desktop app. |
| Screenshot tool returns a timeout | No level viewport is open, or the PNG was not written within 20 seconds | Open a level viewport and run the screenshot prompt again. |
| `PCGComponent is not available` | The PCG plugin is off | Enable it as in section 3, restart the editor, and confirm the listening line. |
