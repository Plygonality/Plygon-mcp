#!/usr/bin/env python3
"""Install the Plygon Houdini MCP package into Houdini's user preferences.

Usage:
  python scripts/install_package.py
  python scripts/install_package.py --pref-dir /path/to/houdini20.5
  HOUDINIMCP_PREF_DIR=... python scripts/install_package.py
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import sys
from pathlib import Path


def candidate_pref_dirs() -> list[Path]:
    home = Path.home()
    system = platform.system()
    dirs: list[Path] = []

    if system == "Darwin":
        root = home / "Library" / "Preferences" / "houdini"
    elif system == "Windows":
        docs = os.environ.get("USERPROFILE", str(home))
        root = Path(docs) / "Documents" / "houdini"
    else:
        root = home / "houdini"

    if root.exists():
        for version_dir in sorted(root.iterdir(), reverse=True):
            if version_dir.is_dir():
                dirs.append(version_dir)

    env_pref = os.environ.get("HOUDINI_USER_PREF_DIR")
    if env_pref:
        p = Path(env_pref)
        if p.is_dir() and p not in dirs:
            dirs.insert(0, p)

    return dirs


def install_package(pref_dir: Path, package_src: Path) -> Path:
    packages_dir = pref_dir / "packages"
    packages_dir.mkdir(parents=True, exist_ok=True)

    dest_root = packages_dir / "plygon_houdini_mcp"
    if dest_root.exists():
        shutil.rmtree(dest_root)

    shutil.copytree(package_src, dest_root)
    return dest_root / "plygon_houdini_mcp.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Install Plygon Houdini MCP package")
    parser.add_argument(
        "--pref-dir",
        type=Path,
        default=None,
        help="Houdini user preferences directory (e.g. ~/houdini20.5)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List detected Houdini preference directories and exit",
    )
    args = parser.parse_args()

    env_dir = os.environ.get("HOUDINIMCP_PREF_DIR") or os.environ.get("HOUDINI_USER_PREF_DIR")
    detected = candidate_pref_dirs()

    if args.list:
        if not detected:
            print("No Houdini preference folders detected.")
            return 1
        for d in detected:
            print(d)
        return 0

    package_src = Path(__file__).resolve().parents[1] / "package"
    if not (package_src / "plygon_houdini_mcp.json").is_file():
        print(f"Package source not found: {package_src}", file=sys.stderr)
        return 1

    target = Path(args.pref_dir) if args.pref_dir else (Path(env_dir) if env_dir else None)
    if target is None:
        if not detected:
            print(
                "Could not find a Houdini preferences folder. Pass --pref-dir, or set "
                "HOUDINI_USER_PREF_DIR. Example: ~/houdini20.5",
                file=sys.stderr,
            )
            return 1
        target = detected[0]
        print(f"Using detected preferences dir: {target}")

    dest = install_package(target, package_src)
    print(f"Installed package → {dest.parent}")
    print(
        "Next: restart Houdini → add shelf from "
        "packages/plygon_houdini_mcp/toolbar/plygon_houdini_mcp.shelf "
        "(Right-click shelf → Shelves → Import) → Start MCP Server."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
