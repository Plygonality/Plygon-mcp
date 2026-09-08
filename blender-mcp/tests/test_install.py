from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_install_addon():
    path = ROOT / "scripts" / "install_addon.py"
    spec = importlib.util.spec_from_file_location("blender_install_addon", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_install_copies_addon(tmp_path):
    inst = _load_install_addon()
    src = ROOT / "addon" / "blender_mcp_addon.py"
    dest = inst.install_addon(tmp_path, src)
    assert dest.is_file()
    assert dest.name == "blender_mcp_addon.py"
    assert "PlygonMCP" in dest.read_text(encoding="utf-8")


def test_windows_addon_roots_use_appdata(tmp_path, monkeypatch):
    inst = _load_install_addon()
    appdata = tmp_path / "AppData" / "Roaming"
    addons = appdata / "Blender Foundation" / "Blender" / "4.2" / "scripts" / "addons"
    addons.mkdir(parents=True)
    monkeypatch.setattr(inst.platform, "system", lambda: "Windows")
    monkeypatch.setenv("APPDATA", str(appdata))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "AppData" / "Local"))

    found = inst.candidate_addon_dirs()
    assert addons in found


def test_refused_message_mentions_n_panel():
    from plygon_blender_mcp.connection import REFUSED_MESSAGE, TIMEOUT_MESSAGE

    text = REFUSED_MESSAGE.format(host="127.0.0.1", port=9876)
    assert "connection refused" in text
    assert "Start MCP Server" in text
    assert "Cloud Agent" in text
    assert "9876" in text
    assert "Cloud Agent" in TIMEOUT_MESSAGE.format(host="127.0.0.1", port=9876)
