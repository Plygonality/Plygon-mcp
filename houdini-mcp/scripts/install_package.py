#!/usr/bin/env python3
"""Install the Plygon Houdini MCP package into Houdini's user preferences.

This script is located via __file__, so you can run it from any working
directory:

  uv run python houdini-mcp/scripts/install_package.py
  uv run python C:\\Users\\you\\Documents\\Plygon-mcp\\houdini-mcp\\scripts\\install_package.py
  uv run python scripts/install_package.py --pref-dir "C:\\Users\\you\\Documents\\houdini21.0"

On Windows, Houdini stores prefs in Documents\\houdini21.0 (not Documents\\houdini\\21.0).
Dutch / OneDrive machines often use OneDrive\\Documenten\\houdini21.0 instead.
Houdini only loads JSON files sitting directly in the packages folder, so this
installer writes packages/plygon_houdini_mcp.json next to the copied package.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import sys
from pathlib import Path

PACKAGE_DIR_NAME = "plygon_houdini_mcp"
WRAPPER_JSON_NAME = "plygon_houdini_mcp.json"
HOUDINI_PREF_NAME = re.compile(r"^houdini\d", re.IGNORECASE)
HOUDINI_NUMERIC_PREF_NAME = re.compile(r"^\d+(?:\.\d+)+$")

# Houdini only scans packages/*.json (not nested JSON). This wrapper points
# HOUDINI_PATH at the copied package so `from plygon_houdini_mcp import listener` works.
PACKAGE_WRAPPER = {
    "env": [
        {
            "HOUDINI_PATH": "$HOUDINI_PACKAGE_PATH/plygon_houdini_mcp;&",
        }
    ]
}


def is_houdini_pref_dir(path: Path) -> bool:
    return path.is_dir() and bool(HOUDINI_PREF_NAME.match(path.name))


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


def _scan_parent_for_prefs(parent: Path, *, allow_numeric: bool = False) -> list[Path]:
    """Find houdini21.0-style folders, plus a houdini/20.5 container if present."""
    found: list[Path] = []
    if not parent.is_dir():
        return found
    try:
        children = list(parent.iterdir())
    except OSError:
        return found
    for child in children:
        if is_houdini_pref_dir(child) or (
            allow_numeric
            and child.is_dir()
            and HOUDINI_NUMERIC_PREF_NAME.match(child.name)
        ):
            found.append(child)
    container = parent / "houdini"
    if container.is_dir():
        try:
            nested = list(container.iterdir())
        except OSError:
            nested = []
        for child in nested:
            if not child.is_dir():
                continue
            if is_houdini_pref_dir(child) or HOUDINI_NUMERIC_PREF_NAME.match(child.name):
                found.append(child)
    return found


def _windows_document_roots() -> list[Path]:
    home = Path(os.environ.get("USERPROFILE") or Path.home())
    roots = [
        home / "Documents",
        home / "OneDrive" / "Documents",
        home / "OneDrive" / "Documenten",
        home / "OneDrive" / "Documentos",
        home / "OneDrive" / "Dokumente",
    ]
    one_drive = os.environ.get("OneDrive")
    if one_drive:
        od = Path(one_drive)
        roots.extend(
            [
                od / "Documents",
                od / "Documenten",
                od / "Documentos",
                od / "Dokumente",
            ]
        )
    return unique_dirs(roots)


def candidate_pref_dirs() -> list[Path]:
    """Return Houdini user preference directories, newest-looking first."""
    dirs: list[Path] = []
    system = platform.system()
    home = Path.home()

    if system == "Darwin":
        dirs.extend(
            _scan_parent_for_prefs(
                home / "Library" / "Preferences" / "houdini",
                allow_numeric=True,
            )
        )
        # Some Houdini/macOS configurations still use ~/houdini21.0.
        dirs.extend(_scan_parent_for_prefs(home))
    elif system == "Windows":
        for root in _windows_document_roots():
            dirs.extend(_scan_parent_for_prefs(root))
    else:
        dirs.extend(_scan_parent_for_prefs(home))

    env_pref = os.environ.get("HOUDINI_USER_PREF_DIR") or os.environ.get("HOUDINIMCP_PREF_DIR")
    if env_pref:
        p = Path(env_pref)
        if p.is_dir():
            dirs.insert(0, p)

    return unique_dirs(dirs)


def write_package_wrapper(packages_dir: Path) -> Path:
    wrapper = packages_dir / WRAPPER_JSON_NAME
    wrapper.write_text(json.dumps(PACKAGE_WRAPPER, indent=2) + "\n", encoding="utf-8")
    return wrapper


def install_package(pref_dir: Path, package_src: Path) -> tuple[Path, Path]:
    packages_dir = pref_dir / "packages"
    packages_dir.mkdir(parents=True, exist_ok=True)

    dest_root = packages_dir / PACKAGE_DIR_NAME
    if dest_root.exists():
        shutil.rmtree(dest_root)

    shutil.copytree(package_src, dest_root)
    wrapper = write_package_wrapper(packages_dir)
    return dest_root, wrapper


def _missing_pref_help() -> str:
    return (
        "Could not find a Houdini preferences folder (houdini21.0, houdini20.5, …).\n"
        "Open Houdini once so it creates that folder, then rerun — or pass --pref-dir.\n\n"
        "Windows examples:\n"
        '  uv run python houdini-mcp/scripts/install_package.py --pref-dir "%USERPROFILE%\\Documents\\houdini21.0"\n'
        '  uv run python houdini-mcp/scripts/install_package.py --pref-dir "%USERPROFILE%\\OneDrive\\Documenten\\houdini21.0"\n\n'
        "macOS example:\n"
        "  uv run python houdini-mcp/scripts/install_package.py --pref-dir ~/Library/Preferences/houdini/21.0\n"
        "Linux example:\n"
        "  uv run python houdini-mcp/scripts/install_package.py --pref-dir ~/houdini21.0"
    )


def _next_steps(dest_root: Path) -> str:
    shelf = dest_root / "toolbar" / "plygon_houdini_mcp.shelf"
    return (
        "Next:\n"
        "  1. Fully quit Houdini and reopen it (so the packages JSON loads).\n"
        f"  2. Optional shelf: right-click a shelf → Shelves → Import →\n     {shelf}\n"
        "  3. Start the listener in Windows → Python Shell:\n"
        "       from plygon_houdini_mcp import listener\n"
        "       listener.start_server(port=9877)\n"
        "     You want: PlygonMCP: listening on 127.0.0.1:9877\n"
        "  4. Ping from a local Cursor Agent chat (not a Cloud Agent).\n"
        "A green row in Customize → MCPs only means Cursor spawned uvx;\n"
        "it does not mean Houdini is listening."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Install Plygon Houdini MCP package")
    parser.add_argument(
        "--pref-dir",
        type=Path,
        default=None,
        help="Houdini user preferences directory (e.g. Documents/houdini21.0)",
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
            print(_missing_pref_help())
            return 1
        for d in detected:
            print(d)
        return 0

    package_src = Path(__file__).resolve().parents[1] / "package"
    if not (package_src / "plygon_houdini_mcp.json").is_file():
        print(f"Package source not found: {package_src}", file=sys.stderr)
        print(
            "Run this from a Plygon-mcp checkout (the folder that contains houdini-mcp/), "
            "or pass the full path to this script. A Cursor folder named houdini-mcp is not the repo.",
            file=sys.stderr,
        )
        return 1

    if args.pref_dir is not None:
        targets = [Path(args.pref_dir)]
    elif env_dir:
        targets = [Path(env_dir)]
    elif not detected:
        print(_missing_pref_help(), file=sys.stderr)
        return 1
    else:
        # Documents + OneDrive\\Documenten can both exist; install into each.
        targets = detected

    installed: list[Path] = []
    for target in unique_dirs(targets):
        target.mkdir(parents=True, exist_ok=True)
        dest_root, wrapper = install_package(target, package_src)
        print(f"Installed package → {dest_root}")
        print(f"Wrote Houdini packages JSON → {wrapper}")
        installed.append(dest_root)

    print()
    print(_next_steps(installed[0]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
