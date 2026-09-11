#!/usr/bin/env python3
"""Copy the Plygon Blender MCP addon into Blender's scripts/addons folder.

This script is located via __file__, so you can run it from any working directory.

  uv run python blender-mcp/scripts/install_addon.py
  uv run python blender-mcp/scripts/install_addon.py --addons-dir "C:\\Users\\you\\AppData\\Roaming\\Blender Foundation\\Blender\\4.2\\scripts\\addons"

uvx / Cursor MCP does not install this add-on. Green in Customize → MCPs is not enough;
you still have to enable the add-on and click Start MCP Server (Online · port 9876).
"""

from __future__ import annotations

import argparse
import os
import platform
import re
import shutil
import sys
from pathlib import Path

BLENDER_VERSION_NAME = re.compile(r"^\d+(?:\.\d+)+$")


def unique_dirs(dirs: list[Path]) -> list[Path]:
    seen: set[str] = set()
    out: list[Path] = []
    for path in dirs:
        try:
            key = str(path.resolve())
        except OSError:
            key = str(path)
        if key not in seen:
            seen.add(key)
            out.append(path)
    return out


def blender_root_candidates() -> list[Path]:
    home = Path.home()
    system = platform.system()
    roots: list[Path] = []

    if system == "Darwin":
        roots.append(home / "Library/Application Support/Blender")
    elif system == "Windows":
        appdata = os.environ.get("APPDATA", "")
        local = os.environ.get("LOCALAPPDATA", "")
        if appdata:
            roots.append(Path(appdata) / "Blender Foundation" / "Blender")
        if local:
            roots.append(Path(local) / "Blender Foundation" / "Blender")
    else:
        roots.append(home / ".config" / "blender")

    return roots


def candidate_addon_dirs() -> list[Path]:
    found: list[Path] = []
    for root in blender_root_candidates():
        if not root.exists():
            continue
        try:
            versions = list(root.iterdir())
        except OSError:
            continue
        for version_dir in sorted(versions, reverse=True):
            if not version_dir.is_dir() or not BLENDER_VERSION_NAME.match(version_dir.name):
                continue
            addons = version_dir / "scripts" / "addons"
            # A fresh Blender profile has the version folder but may not have
            # created scripts/addons yet. install_addon() creates it safely.
            found.append(addons)
    return unique_dirs(found)


def install_addon(target_root: Path, addon_src: Path) -> Path:
    target_root.mkdir(parents=True, exist_ok=True)
    dest = target_root / "blender_mcp_addon.py"
    if dest.exists():
        bak = dest.with_suffix(".py.bak")
        shutil.copy2(dest, bak)
        print(f"Backed up existing addon → {bak}")
    shutil.copy2(addon_src, dest)
    return dest


def main() -> int:
    parser = argparse.ArgumentParser(description="Install Plygon Blender MCP addon")
    parser.add_argument(
        "--addons-dir",
        type=Path,
        default=None,
        help="Target Blender scripts/addons directory",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List detected addon directories and exit",
    )
    args = parser.parse_args()

    env_dir = os.environ.get("BLENDERMCP_ADDONS_DIR") or os.environ.get("PLYGON_BLENDER_ADDONS_DIR")
    detected = candidate_addon_dirs()

    if args.list:
        if not detected:
            print("No Blender addons folders detected.")
            return 1
        for d in detected:
            print(d)
        return 0

    addon_src = Path(__file__).resolve().parents[1] / "addon" / "blender_mcp_addon.py"
    if not addon_src.is_file():
        print(f"Addon source not found: {addon_src}", file=sys.stderr)
        print(
            "Run this from a Plygon-mcp checkout (the folder that contains blender-mcp/).",
            file=sys.stderr,
        )
        return 1

    if args.addons_dir is not None:
        targets = [Path(args.addons_dir)]
    elif env_dir:
        targets = [Path(env_dir)]
    elif not detected:
        print(
            "Could not find a Blender addons folder. Pass --addons-dir, or install "
            "manually: Blender → Edit → Preferences → Add-ons → Install from Disk… "
            "→ blender-mcp/addon/blender_mcp_addon.py",
            file=sys.stderr,
        )
        return 1
    else:
        targets = detected

    for target_root in unique_dirs(targets):
        dest = install_addon(target_root, addon_src)
        print(f"Installed addon → {dest}")

    print(
        "Next: open Blender (GUI, not blender -b) → Preferences → Add-ons → enable "
        "'Interface: Plygon Blender MCP' → 3D Viewport N-panel → PlygonMCP → "
        "Start MCP Server. Confirm Online · port 9876. Leave Blender open.\n"
        "A green row in Customize → MCPs only means Cursor spawned uvx; ping from a "
        "local Agent chat, not a Cloud Agent."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
