from __future__ import annotations

import importlib.util
import json
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_install_package():
    path = ROOT / "scripts" / "install_package.py"
    spec = importlib.util.spec_from_file_location("houdini_install_package", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_shelf_is_well_formed_xml():
    shelf = ROOT / "package" / "toolbar" / "plygon_houdini_mcp.shelf"
    tree = ET.parse(shelf)
    root = tree.getroot()
    assert root.tag == "shelfDocument"
    labels = [el.get("label") for el in root.findall("tool")]
    assert "Start MCP Server" in labels
    assert "Stop MCP Server" in labels
    assert "MCP Status" in labels
    text = shelf.read_text(encoding="utf-8")
    assert "</tooltool>" not in text


def test_windows_detects_houdini21_in_documents(tmp_path, monkeypatch):
    inst = _load_install_package()
    docs = tmp_path / "Documents"
    (docs / "houdini21.0").mkdir(parents=True)
    onedrive = tmp_path / "OneDrive" / "Documenten"
    (onedrive / "houdini21.0").mkdir(parents=True)
    monkeypatch.setattr(inst.platform, "system", lambda: "Windows")
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("OneDrive", raising=False)
    monkeypatch.delenv("HOUDINI_USER_PREF_DIR", raising=False)
    monkeypatch.delenv("HOUDINIMCP_PREF_DIR", raising=False)

    found = {p.name for p in inst.candidate_pref_dirs()}
    assert "houdini21.0" in found


def test_windows_does_not_require_documents_houdini_container(tmp_path, monkeypatch):
    inst = _load_install_package()
    # The old installer looked for Documents/houdini/21.0 and missed Documents/houdini21.0.
    docs = tmp_path / "Documents"
    (docs / "houdini21.0").mkdir(parents=True)
    monkeypatch.setattr(inst.platform, "system", lambda: "Windows")
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("OneDrive", raising=False)
    monkeypatch.delenv("HOUDINI_USER_PREF_DIR", raising=False)
    monkeypatch.delenv("HOUDINIMCP_PREF_DIR", raising=False)

    found = inst.candidate_pref_dirs()
    assert any(p.name == "houdini21.0" for p in found)
    assert not any(p.name == "houdini" and p.parent.name == "Documents" for p in found)


def test_linux_detects_home_houdini21(tmp_path, monkeypatch):
    inst = _load_install_package()
    (tmp_path / "houdini21.0").mkdir()
    monkeypatch.setattr(inst.platform, "system", lambda: "Linux")
    monkeypatch.setattr(inst.Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.delenv("HOUDINI_USER_PREF_DIR", raising=False)
    monkeypatch.delenv("HOUDINIMCP_PREF_DIR", raising=False)

    found = [p.name for p in inst.candidate_pref_dirs()]
    assert "houdini21.0" in found


def test_install_writes_packages_wrapper_json(tmp_path):
    inst = _load_install_package()
    package_src = ROOT / "package"
    pref = tmp_path / "houdini21.0"
    dest_root, wrapper = inst.install_package(pref, package_src)

    assert dest_root.is_dir()
    assert (dest_root / "scripts" / "python" / "plygon_houdini_mcp" / "listener.py").is_file()
    assert wrapper.is_file()
    assert wrapper.parent == pref / "packages"
    data = json.loads(wrapper.read_text(encoding="utf-8"))
    path_val = data["env"][0]["HOUDINI_PATH"]
    assert "plygon_houdini_mcp" in path_val
    assert path_val.startswith("$HOUDINI_PACKAGE_PATH/")


def test_refused_message_mentions_python_shell():
    from plygon_houdini_mcp.connection import REFUSED_MESSAGE, TIMEOUT_MESSAGE

    text = REFUSED_MESSAGE.format(host="127.0.0.1", port=9877)
    assert "connection refused" in text
    assert "listener.start_server" in text
    assert "Cloud Agent" in text
    assert "9877" in text
    assert "8100" in TIMEOUT_MESSAGE + REFUSED_MESSAGE
    assert "not responding" in TIMEOUT_MESSAGE.format(host="127.0.0.1", port=9877)
