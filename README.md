<p align="center">
  <img src="blender-mcp/assets/banner.svg" alt="Plygon — local MCP bridges for Blender and Houdini" width="100%">
</p>

<p align="center">
  <strong>Tell Cursor to build in Blender or Houdini. Watch it happen on your machine.</strong>
</p>

<p align="center">
    <a href="https://github.com/Plygonality/Plygon-mcp/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-ff6a1a?style=flat-square" alt="MIT"></a>
    <a href="blender-mcp/"><img src="https://img.shields.io/badge/Blender-3.0%2B-orange?style=flat-square&logo=blender&logoColor=white" alt="Blender 3.0+"></a>
    <a href="houdini-mcp/"><img src="https://img.shields.io/badge/Houdini-19.5%2B-orange?style=flat-square" alt="Houdini 19.5+"></a>
    <a href="blender-mcp/"><img src="https://img.shields.io/badge/Cursor-MCP-111111?style=flat-square" alt="Cursor MCP"></a>
    <a href="blender-mcp/"><img src="https://img.shields.io/badge/telemetry-none-7dffa3?style=flat-square" alt="No telemetry"></a>
</p>

# Plygon

A tech-art studio repo of **local MCP bridges** you can fork, run, and actually own.

Cursor's agents already write code. **Plygon gives them hands inside your DCC** — inspect the scene, make edits, and screenshot the viewport so they can check their own work. The bridge has no telemetry, and its DCC connection stays on IPv4 loopback by default.

The bridge is local; Cursor's model may not be. Tool results—including scene metadata and screenshots—become part of your Cursor conversation and may be sent to the model provider configured in Cursor. Check that provider's privacy settings before using sensitive production files.

Local, no-telemetry fork of the [ahujasid/blender-mcp](https://github.com/ahujasid/blender-mcp) localhost-TCP + FastMCP pattern, shaped for Cursor and studio pipelines. See [`THIRD_PARTY.md`](THIRD_PARTY.md).

| Bridge | Port | Docs |
|--------|------|------|
| [Blender MCP](blender-mcp/) | `127.0.0.1:9876` | [`blender-mcp/README.md`](blender-mcp/README.md) |
| [Houdini MCP](houdini-mcp/) | `127.0.0.1:9877` | [`houdini-mcp/README.md`](houdini-mcp/README.md) |

There are **two processes** per DCC. Cursor spawning the MCP (green in **Customize → MCPs**, tools listed) is not the same as Blender or Houdini listening on that port.

```
You → local Cursor Agent  →  plygon-*-mcp (stdio / uvx)
                          →  TCP 127.0.0.1:9876 or :9877
                          →  add-on / package inside the GUI DCC
                          →  your .blend / .hip
```

A **Cloud Agent** cannot reach the DCC on your PC. `127.0.0.1` in the cloud is not your machine. Ping only from a **local Agent** chat.

---

## Why people fork this

| You want | You get |
|---|---|
| An agent that *sees* your scene | Viewport / Scene Viewer screenshots in the loop |
| A bridge small enough to read | One DCC package + one MCP server per app |
| Privacy | TCP on localhost only, MIT, no phone-home |
| Something you can steal for a pipeline | Fork it. Rename it. Ship it in your studio. |

This is not a 300-tool kitchen sink. It's the layer tech artists actually keep: **inspect → change → look → export**.

---

## Install both MCPs — exact click-by-click guide

Follow every numbered step. Cursor needs three separate pieces:

1. `uvx`, which starts each MCP client.
2. The Blender add-on and Houdini package, which run inside the DCCs.
3. One valid Cursor `mcp.json` containing both server entries.

Green rows in Cursor prove only item 1. They do not prove that Blender or Houdini is listening.

### Step 0 — Download this repository

**Without Git:**

1. Open [github.com/Plygonality/Plygon-mcp](https://github.com/Plygonality/Plygon-mcp).
2. Click the green **Code** button.
3. Click **Download ZIP**.
4. Open Downloads and extract the ZIP.
5. Move the extracted folder to a permanent location. Example: `C:\Users\<your-name>\Documents\Plygon-mcp`.
6. Open that folder and confirm it contains this `README.md`, `blender-mcp`, `houdini-mcp`, and `scripts`.

**With Git:** open PowerShell or Terminal and paste **one command at a time**. Press Enter and wait for the prompt before the next line. Never paste `cd` and another command on the same line.

```bash
git clone https://github.com/Plygonality/Plygon-mcp.git
```

Wait until cloning finishes, then:

```bash
cd Plygon-mcp
```

The extracted or cloned directory is called the **repo folder** below. A `.cursor/houdini-mcp` cache directory is not the repo. A Houdini Console error about that cache folder, `fxhoudinimcp`, or `help_menu` is a different MCP — click **Close**.

### Step 1 — Install `uv` once

Cursor uses `uvx` to download and start both Python MCP clients. `uvx` does not install anything inside Blender or Houdini.

**Windows:**

1. Open the Start menu.
2. Search for and open **PowerShell**. You can reuse the window from the clone. Paste **only** the next command — not `cd` plus this line.
3. If uv might already be installed, paste this first and press Enter:

   ```powershell
   & "$env:USERPROFILE\.local\bin\uvx.exe" --version
   ```

   If it prints a version number, skip to Step 2. Do not rerun the Astral installer.
4. Otherwise paste this command and press Enter:

   ```powershell
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```

5. If it says `uv.exe` is being used by another process: Cursor is locking the file. Right-click the Cursor tray icon → **Quit**, retry the installer, **or** skip it when the version check in step 3 already works.
6. Paste this command and press Enter:

   ```powershell
   & "$env:USERPROFILE\.local\bin\uvx.exe" --version
   ```

7. Continue only after it prints a version number.

**macOS or Linux:**

1. Open **Terminal**.
2. Paste these three lines:

   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   source "$HOME/.local/bin/env"
   "$HOME/.local/bin/uvx" --version
   ```

3. Continue only after the last line prints a version number.

Do not use `pip install uv`. The commands above put `uv` and `uvx` in the location used by the supplied Cursor configs.

### Step 2 — Install and start the Blender add-on

The manual install works on every operating system and does not require a separate Python installation:

1. Open **Blender** normally. Do not use `blender -b`.
2. Click **Edit** → **Preferences**.
3. Click **Add-ons**.
4. Click **Install from Disk…**. In versions that hide it, first open the small menu in the upper-right of the Add-ons page.
5. Browse to the repo folder.
6. Open `blender-mcp` → `addon`.
7. Select `blender_mcp_addon.py`.
8. Click **Install from Disk**.
9. In the Add-ons search box, type `Plygon`.
10. Enable the checkbox beside **Interface: Plygon Blender MCP**.
11. Close Preferences.
12. Put the mouse pointer over the 3D Viewport and press **N**.
13. Click the **PlygonMCP** tab on the right side of the viewport.
14. Leave **Port** at `9876`.
15. Click **Start MCP Server**.
16. Confirm the panel says **Online · port 9876**.
17. Leave this Blender window open.

Optional scripted install:

- Windows: open PowerShell in the repo folder and run `.\scripts\install-blender.cmd`. If PowerShell says running scripts is disabled, that `.cmd` file is the one to use, not `install-blender.ps1`.
- macOS/Linux: from the repo folder run:

  ```bash
  "$HOME/.local/bin/uv" run --no-project python blender-mcp/scripts/install_addon.py
  ```

The installer now creates a missing `scripts/addons` directory for a fresh Blender profile. Restart Blender after using the script.

### Step 3 — Install and start the Houdini package

1. Open the normal Houdini GUI once.
2. Fully quit Houdini. This creates its user preferences directory.
3. Open PowerShell/Terminal in the repo folder. Paste **one command at a time** (do not glue `cd` onto the installer):
   - Windows Explorer: open the repo folder, right-click empty space, then click **Open in Terminal**.
   - macOS Finder: right-click the repo folder and choose **New Terminal at Folder**, or use `cd`.
4. Run the installer:

   **Windows PowerShell** (this `.cmd` file works when `.ps1` scripts are blocked):

   ```powershell
   .\scripts\install-houdini.cmd
   ```

   If that file is missing, paste this instead — still one line, not combined with `cd`:

   ```powershell
   & "$env:USERPROFILE\.local\bin\uv.exe" run --no-project python houdini-mcp\scripts\install_package.py
   ```

   **macOS/Linux**

   ```bash
   "$HOME/.local/bin/uv" run --no-project python houdini-mcp/scripts/install_package.py
   ```

5. Confirm it prints both `Installed package → ...` and `Wrote Houdini packages JSON → ...` for at least one folder. If `Documents\houdini21.0` succeeds and `OneDrive\Documenten\houdini21.0` prints Access is denied, that is OK — Houdini only needs one working prefs folder. The installer overlays locked OneDrive copies instead of aborting.

If automatic detection fails, replace `21.0` with your installed Houdini version and run one matching command:

**Windows**

```powershell
.\scripts\install-houdini.cmd --pref-dir "$env:USERPROFILE\Documents\houdini21.0"
.\scripts\install-houdini.cmd --pref-dir "$env:USERPROFILE\OneDrive\Documenten\houdini21.0"
```

**macOS**

```bash
"$HOME/.local/bin/uv" run --no-project python houdini-mcp/scripts/install_package.py --pref-dir "$HOME/Library/Preferences/houdini/21.0"
```

**Linux**

```bash
"$HOME/.local/bin/uv" run --no-project python houdini-mcp/scripts/install_package.py --pref-dir "$HOME/houdini21.0"
```

On Windows, the normal folder is `Documents\houdini21.0`, not `Documents\houdini\21.0`. OneDrive may use a localized name such as `Documenten`. Fully quit Houdini before installing. If OneDrive still denies access, pause OneDrive syncing, delete `packages\plygon_houdini_mcp` in that prefs folder, and rerun.

6. Open Houdini again. If a **Houdini Console** window mentions `.cursor/houdini-mcp`, `fxhoudinimcp`, or `help_menu`, click **Close**. That is a leftover from a different MCP. Plygon is port **9877**, not **8100**.
7. Click **Windows** → **Python Shell**.
8. Click the shell input line.
9. Paste this one line and press Enter:

   ```python
   from plygon_houdini_mcp import listener; listener.start_server(port=9877)
   ```

10. Confirm the shell prints `PlygonMCP: listening on 127.0.0.1:9877`.
11. Leave Houdini open.

Optional shelf button:

1. In a Shelf pane, right-click an empty area.
2. Click **Shelves** → **Import**.
3. Select `plygon_houdini_mcp.shelf` from the installed package:
   - Windows: `Documents\houdini21.0\packages\plygon_houdini_mcp\toolbar\`
   - macOS: `~/Library/Preferences/houdini/21.0/packages/plygon_houdini_mcp/toolbar/`
   - Linux: `~/houdini21.0/packages/plygon_houdini_mcp/toolbar/`
4. Click **Start MCP Server** on the imported **PlygonMCP** shelf.

Plygon uses port `9877`. A message about port `8100` belongs to another Houdini MCP.

### Step 4 — Put both servers in Cursor Customize → MCPs

1. Fully quit Cursor so it detects the newly installed `uv`:
   - Windows: right-click the Cursor icon in the system tray near the clock → **Quit**.
   - macOS: click **Cursor** → **Quit Cursor**, or press **Cmd+Q**.
   - Linux: click **File** → **Exit** (or **Quit**) and ensure every Cursor window closes.
2. Reopen the desktop Cursor app.
3. Open the local project where you want to use Blender/Houdini.
4. Click **Customize** in the left sidebar.
5. Click the **MCPs** tab.
6. Click **+ New MCP Server** or **Add a Custom MCP Server**.
7. Cursor opens your user config:
   - Windows: `C:\Users\<your-name>\.cursor\mcp.json`
   - macOS/Linux: `~/.cursor/mcp.json`
8. If the file is empty or contains only `"mcpServers": {}`, select everything and replace it with the complete block for your operating system below.
9. If you already have unrelated MCPs, keep them. Add the two `plygon-*` properties inside the existing `"mcpServers"` object and put a comma between every neighboring property. Never paste placeholder text or a second `"mcpServers"` object.

**Windows — copy this complete file:**

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
    }
  }
}
```

**macOS/Linux — copy this complete file:**

```json
{
  "mcpServers": {
    "plygon-houdini": {
      "command": "${userHome}/.local/bin/uvx",
      "args": [
        "--from",
        "git+https://github.com/Plygonality/Plygon-mcp.git#subdirectory=houdini-mcp",
        "plygon-houdini-mcp"
      ],
      "env": {
        "HOUDINI_HOST": "127.0.0.1",
        "HOUDINI_PORT": "9877"
      }
    },
    "plygon-blender": {
      "command": "${userHome}/.local/bin/uvx",
      "args": [
        "--from",
        "git+https://github.com/Plygonality/Plygon-mcp.git#subdirectory=blender-mcp",
        "plygon-blender-mcp"
      ],
      "env": {
        "BLENDER_HOST": "127.0.0.1",
        "BLENDER_PORT": "9876"
      }
    }
  }
}
```

The same complete files are stored at [`configs/cursor.mcp.windows.json`](configs/cursor.mcp.windows.json) and [`configs/cursor.mcp.json`](configs/cursor.mcp.json).

10. Press **Ctrl+S** on Windows/Linux or **Cmd+S** on macOS.
11. If every MCP disappears immediately, the JSON is invalid. Press **Ctrl+Z**/**Cmd+Z**, check commas and braces, and save again.
12. Go back to **Customize** → **MCPs**.
13. Find **plygon-blender** and **plygon-houdini**.
14. Turn both toggles on.
15. Wait for both rows to become green and show their tool lists.
16. If a row is red, click it → **Show Output** and use the troubleshooting table below.

Opening this repository also loads its project [`.cursor/mcp.json`](.cursor/mcp.json). Cursor merges a user and project server with the same name, and project fields take precedence; it does not launch two copies under that same name. To test the user-wide config exactly, open another local project. Do not add the same bridge under a second name, because differently named entries can start competing clients on one DCC port.

### Step 5 — Ping both DCCs from a local Agent

1. Check Blender still says **Online · port 9876**.
2. Check Houdini still says **listening on 127.0.0.1:9877**.
3. In the desktop Cursor app, open a new **Agent** chat. Do not use Ask mode or a Cloud Agent.
4. Paste:

   > Ping Blender. Do not change the scene and do not call any other tool.

5. Approve the tool call if Cursor asks. Confirm it returns `pong`.
6. Paste:

   > Ping Houdini. Do not change the hip and do not call any other tool.

7. Confirm it returns `pong`.
8. Verify parallel framing without changing either scene:

   > In parallel, ping Blender and get Blender scene info. Then, in parallel, ping Houdini and get Houdini scene info. Do not modify anything.

A Cloud Agent cannot reach `127.0.0.1` on your PC. These checks must run in a local desktop Agent chat.

### Final checklist

- [ ] Blender add-on enabled; panel says **Online · port 9876**.
- [ ] Houdini package imports; shell says **listening on 127.0.0.1:9877**.
- [ ] Cursor **Customize → MCPs → plygon-blender** is green with tools.
- [ ] Cursor **Customize → MCPs → plygon-houdini** is green with tools.
- [ ] Blender ping succeeds from a local Agent.
- [ ] Houdini ping succeeds from a local Agent.
- [ ] Parallel ping + scene-info calls complete without `Extra data`.

### What the agent can do

| DCC | Main tools |
|---|---|
| Blender | Scene/object inspection, viewport screenshots, primitives, transforms, materials, selection, Python execution, and export |
| Houdini | Scene/node inspection, Scene Viewer screenshots, node creation/wiring/layout/cooking, parameters, Python/HScript execution, and hip saving |

Copy-paste task prompts: [Blender](blender-mcp/examples/prompts.md) · [Houdini](houdini-mcp/examples/prompts.md)

### Example — Houdini chess set

Once Houdini ping returns `pong`, a local Agent can build a scene like this:

<p align="center">
  <img src="houdini-mcp/assets/chess-set-example.png" alt="Cursor Agent and Houdini after building a procedural chess set: pawn, bishop, rook, and a checkerboard with a chamfered border" width="100%">
</p>

Paste these into a **local** Agent chat (not Cloud). Full copies live in [`houdini-mcp/examples/prompts.md`](houdini-mcp/examples/prompts.md).

**Chess pieces**

> Create a simple Pawn piece for your chess set using Revolve.
> Then try to make the Bishop and Rook.
>
> Tip: you don’t have to use Revolve for everything, you can build it up from different shapes, using what you learned already (last week for instance).

**Chess board**

> Create a simple procedural chess board where the user can change the number of sides in x and z direction. For the simple board, you always have an uneven amount of tiles per side (1,3, 5..). Every square is slightly extruded and beveled upwards so the divisions are clear. They change colors between black and white. Around the board is also an additional brown border, slightly thicker and chamfered, to indicate the end of the board. Bonus: A real chessboard has an even number of tiles(8x8). Try to find a solution that solves for an even number of rows and columns.

---

## Diagnose: spawn vs socket vs listener

| What you see | What it means | What to do |
|---|---|---|
| MCP row is red / `'uvx' is not recognized` | Cursor could not spawn the Python MCP | Full-path `uvx.exe` in Windows `mcp.json`; quit Cursor from the tray |
| uv installer: `uv.exe` is being used by another process | Cursor (or another uv) has the file open | Quit Cursor from the tray and retry, or skip the installer if `uvx.exe --version` already prints a version |
| `running scripts is disabled` / cannot load `.ps1` | PowerShell execution policy blocked the installer | Run `.\scripts\install-houdini.cmd` or `.\scripts\install-blender.cmd`, or the `uv.exe run --no-project python ...` line. Paste one command per line |
| `Access is denied` under `OneDrive\Documenten\...plygon_houdini_mcp` | OneDrive or Houdini locked `rmtree` | Quit Houdini, pause OneDrive, rerun. Overlay is enough. One successful prefs folder is enough |
| Houdini Console: `fxhoudinimcp` / `.cursor/houdini-mcp` / `help_menu` | A different MCP's menu XML | Click **Close**. Ignore port **8100**. Plygon is **9877** |
| Green, tools listed, **Could not connect** / connection refused | uvx is up; DCC is not listening | Start MCP Server in the DCC. Confirm port 9876 (Blender) or 9877 (Houdini) |
| Green, **Request timed out** / Houdini “not responding” after `queued ping` | TCP connected; the listener did not reply | Force-quit the DCC, reinstall the package, start the listener again, keep the GUI in front |
| ImportError: `No module named 'plygon_houdini_mcp'` | Packages JSON not loaded | Re-run `install_package.py`, confirm `packages/plygon_houdini_mcp.json` exists, restart Houdini |
| Every MCP disappears after save | `mcp.json` is invalid JSON | Undo immediately; fix the missing comma/brace; keep one top-level `mcpServers` object |
| Blender says the port is already in use | Another listener owns 9876 | Stop the old add-on/server or choose one matching free port in both Blender and `mcp.json` |
| Screenshot tool fails | Required viewport is not visible | Keep a 3D Viewport open in Blender and a Scene Viewer pane open in Houdini |
| Works in a local Agent, fails in Cloud Agent | Cloud `127.0.0.1` is not your PC | Use a desktop Agent chat |
| Something listening on **8100** | A different Houdini MCP | Ignore it for Plygon. Plygon is **9877** |

Windows port check:

```powershell
Get-NetTCPConnection -LocalPort 9876,9877 -State Listen -ErrorAction SilentlyContinue
```

Do not run `uvx` manually while Cursor is also launching it. Do not register the same bridge under two different names or point Cursor and another MCP app at the same DCC socket. Same-name user/project entries are merged, with project values taking precedence.

---

## Update an existing installation

After pulling or downloading a newer release:

1. Fully quit Blender and Houdini.
2. Replace the local repo with the new version, or run `git pull`.
3. Re-run `.\scripts\install-blender.cmd` and `.\scripts\install-houdini.cmd` on Windows. On macOS/Linux, rerun both `"$HOME/.local/bin/uv" run --no-project python ...` commands from Steps 2 and 3.
4. Reopen both DCCs and start both listeners again.
5. Fully quit and reopen Cursor. If `uvx` still runs old code, run `uv cache clean plygon-blender-mcp` and `uv cache clean plygon-houdini-mcp`, then reopen Cursor.
6. Repeat the final verification checklist above.

The DCC-side add-on/package is copied into Blender/Houdini. A Git update alone does not replace those installed copies.

---

## Privacy and security boundary

- The bridge itself has no telemetry. DCC TCP traffic binds to `127.0.0.1` by default.
- Cursor can send prompts and tool results to your configured model provider. A screenshot returned to the agent is not guaranteed to remain on your PC.
- `execute_blender_code`, `execute_houdini_code`, and `execute_hscript` run with the same file and network permissions as Blender or Houdini.
- Any local process that can connect to ports `9876` or `9877` can call the listener; the TCP protocol has no authentication.
- Save your `.blend` or `.hip`, review tool approvals, and never expose these ports to a LAN or the internet.

---

## How it works

Both bridges share the same shape:

1. **DCC side** — a small listener inside Blender or Houdini (TCP server, main-thread dispatch)
2. **MCP side** — a Python process Cursor launches over stdio (FastMCP tools the agent calls)
3. **Loop** — agent inspects → edits → screenshots → iterates

```
You  →  Cursor agent  →  Plygon MCP  →  localhost  →  Blender / Houdini  →  your scene
```

You keep the taste. The agent keeps the clicks.

---

## Repo map

| Path | What |
|------|------|
| [`blender-mcp/`](blender-mcp/) | Blender add-on + MCP server |
| [`houdini-mcp/`](houdini-mcp/) | Houdini package + MCP server |
| [`houdini-mcp/assets/chess-set-example.png`](houdini-mcp/assets/chess-set-example.png) | Install-guide example: Cursor + Houdini chess set |
| [`houdini-mcp/package/README.md`](houdini-mcp/package/README.md) | Why the packages JSON wrapper exists |
| [`scripts/install-houdini.cmd`](scripts/install-houdini.cmd) | Windows installer (works when `.ps1` is blocked) |
| [`scripts/install-blender.cmd`](scripts/install-blender.cmd) | Windows installer (works when `.ps1` is blocked) |
| [`scripts/install-houdini.ps1`](scripts/install-houdini.ps1) | Windows PowerShell installer (any cwd) |
| [`scripts/install-blender.ps1`](scripts/install-blender.ps1) | Windows PowerShell installer (any cwd) |
| [`.cursor/mcp.json`](.cursor/mcp.json) | Project-level Cursor config (both DCCs) |
| [`CHANGELOG.md`](CHANGELOG.md) | Reliability and setup changes |
| [`THIRD_PARTY.md`](THIRD_PARTY.md) | Provenance (blender-mcp pattern) |

---

## Star it, fork it, break it

If this saves you a night of clicking, **star the repo** so other tech artists find it.

Forks are the point. Plygon is a public MIT workshop for DCC tools, add-ons, and MCPs.

[github.com/Plygonality/Plygon-mcp](https://github.com/Plygonality/Plygon-mcp)
