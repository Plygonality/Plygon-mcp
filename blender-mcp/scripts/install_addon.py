#!/usr/bin/env python3
"""Copy the Plygon Blender MCP addon into Blender's scripts/addons folder.

Usage:
  python scripts/install_addon.py
  python scripts/install_addon.py --addons-dir /path/to/scripts/addons
  BLENDERMCP_ADDONS_DIR=... python scripts/install_addon.py
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import sys
from pathlib import Path


def candidate_addon_dirs() -> list[Path]:
    home = Path.home()
    system = platform.system()
    dirs: list[Path] = []

    if system == "Darwin":
        dirs.append(home / "Library/Application Support/Blender")
    elif system == "Windows":
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            dirs.append(Path(appdata) / "Blender Foundation" / "Blender")
    else:
        dirs.append(home / ".config" / "blender")

    found: list[Path] = []
    for root in dirs:
        if not root.exists():
            continue
        for version_dir in sorted(root.iterdir(), reverse=True):
            addons = version_dir / "scripts" / "addons"
            if addons.is_dir():
                found.append(addons)
    return found


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
        return 1

    target_root = Path(args.addons_dir) if args.addons_dir else (Path(env_dir) if env_dir else None)
    if target_root is None:
        if not detected:
            print(
                "Could not find a Blender addons folder. Pass --addons-dir, or install "
                "manually: Blender → Edit → Preferences → Add-ons → Install…",
                file=sys.stderr,
            )
            return 1
        target_root = detected[0]
        print(f"Using detected addons dir: {target_root}")

    target_root.mkdir(parents=True, exist_ok=True)
    dest = target_root / "blender_mcp_addon.py"
    if dest.exists():
        bak = dest.with_suffix(".py.bak")
        shutil.copy2(dest, bak)
        print(f"Backed up existing addon → {bak}")

    shutil.copy2(addon_src, dest)
    print(f"Installed addon → {dest}")
    print(
        "Next: open Blender → Preferences → Add-ons → enable "
        "'Interface: Plygon Blender MCP' → N-panel → PlygonMCP → Start MCP Server."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
