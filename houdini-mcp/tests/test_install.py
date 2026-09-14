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


def test_macos_detects_numeric_preferences_folder(tmp_path, monkeypatch):
    inst = _load_install_package()
    numeric = tmp_path / "Library" / "Preferences" / "houdini" / "21.0"
    numeric.mkdir(parents=True)
    legacy = tmp_path / "houdini20.5"
    legacy.mkdir()
    monkeypatch.setattr(inst.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(inst.Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.delenv("HOUDINI_USER_PREF_DIR", raising=False)
    monkeypatch.delenv("HOUDINIMCP_PREF_DIR", raising=False)

    found = inst.candidate_pref_dirs()

    assert numeric in found
    assert legacy in found


def test_install_writes_packages_wrapper_json(tmp_path):
    inst = _load_install_package()
    package_src = ROOT / "package"
    pref = tmp_path / "houdini21.0"
    dest_root, wrapper, mode = inst.install_package(pref, package_src)

    assert mode == "copied"
    assert dest_root.is_dir()
    assert (dest_root / "scripts" / "python" / "plygon_houdini_mcp" / "listener.py").is_file()
    assert wrapper.is_file()
    assert wrapper.parent == pref / "packages"
    data = json.loads(wrapper.read_text(encoding="utf-8"))
    path_val = data["env"][0]["HOUDINI_PATH"]
    assert "plygon_houdini_mcp" in path_val
    assert path_val.startswith("$HOUDINI_PACKAGE_PATH/")


def test_windows_detects_documents_and_onedrive_documenten(tmp_path, monkeypatch):
    inst = _load_install_package()
    docs = tmp_path / "Documents" / "houdini21.0"
    onedrive = tmp_path / "OneDrive" / "Documenten" / "houdini21.0"
    docs.mkdir(parents=True)
    onedrive.mkdir(parents=True)
    monkeypatch.setattr(inst.platform, "system", lambda: "Windows")
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("OneDrive", raising=False)
    monkeypatch.delenv("HOUDINI_USER_PREF_DIR", raising=False)
    monkeypatch.delenv("HOUDINIMCP_PREF_DIR", raising=False)

    found = {p.resolve() for p in inst.candidate_pref_dirs()}
    assert docs.resolve() in found
    assert onedrive.resolve() in found


def test_install_overlays_when_rmtree_denied(tmp_path, monkeypatch):
    inst = _load_install_package()
    pref = tmp_path / "houdini21.0"
    dest = pref / "packages" / "plygon_houdini_mcp"
    dest.mkdir(parents=True)
    (dest / "stale.txt").write_text("keep", encoding="utf-8")

    def deny(path, *args, **kwargs):
        raise PermissionError(5, "Access is denied", str(path))

    monkeypatch.setattr(inst.shutil, "rmtree", deny)
    dest_root, wrapper, mode = inst.install_package(pref, ROOT / "package")

    assert mode == "overlaid"
    assert (dest_root / "scripts" / "python" / "plygon_houdini_mcp" / "listener.py").is_file()
    assert (dest_root / "stale.txt").read_text(encoding="utf-8") == "keep"
    assert wrapper.is_file()


def test_main_succeeds_when_one_of_two_prefs_is_locked(tmp_path, monkeypatch, capsys):
    inst = _load_install_package()
    docs = tmp_path / "Documents" / "houdini21.0"
    locked = tmp_path / "OneDrive" / "Documenten" / "houdini21.0"
    docs.mkdir(parents=True)
    locked.mkdir(parents=True)
    real = inst.install_package

    def flaky(pref_dir, package_src):
        if "OneDrive" in pref_dir.parts:
            raise PermissionError(
                5,
                "Access is denied",
                str(pref_dir / "packages" / "plygon_houdini_mcp"),
            )
        return real(pref_dir, package_src)

    monkeypatch.setattr(inst, "install_package", flaky)
    monkeypatch.setattr(inst, "candidate_pref_dirs", lambda: [docs, locked])
    monkeypatch.setattr(inst.sys, "argv", ["install_package.py"])
    monkeypatch.delenv("HOUDINI_USER_PREF_DIR", raising=False)
    monkeypatch.delenv("HOUDINIMCP_PREF_DIR", raising=False)

    assert inst.main() == 0
    captured = capsys.readouterr()
    assert "Installed package" in captured.out
    assert "Could not install" in captured.err
    assert "fxhoudinimcp" in captured.err
    assert (docs / "packages" / "plygon_houdini_mcp.json").is_file()
    assert not (locked / "packages" / "plygon_houdini_mcp.json").exists()


def test_main_fails_when_every_pref_is_locked(tmp_path, monkeypatch, capsys):
    inst = _load_install_package()
    pref = tmp_path / "houdini21.0"
    pref.mkdir()

    def boom(pref_dir, package_src):
        raise PermissionError(5, "Access is denied", str(pref_dir))

    monkeypatch.setattr(inst, "install_package", boom)
    monkeypatch.setattr(inst, "candidate_pref_dirs", lambda: [pref])
    monkeypatch.setattr(inst.sys, "argv", ["install_package.py"])
    monkeypatch.delenv("HOUDINI_USER_PREF_DIR", raising=False)
    monkeypatch.delenv("HOUDINIMCP_PREF_DIR", raising=False)

    assert inst.main() == 1
    assert "No Houdini prefs folder accepted" in capsys.readouterr().err


def test_windows_cmd_wrapper_invokes_python_installer():
    cmd = ROOT.parent / "scripts" / "install-houdini.cmd"
    text = cmd.read_text(encoding="utf-8")
    assert "install_package.py" in text
    assert "execution policy" in text.lower()
    assert "uv.exe" in text


def test_refused_message_mentions_python_shell():
    from plygon_houdini_mcp.connection import REFUSED_MESSAGE, TIMEOUT_MESSAGE

    text = REFUSED_MESSAGE.format(host="127.0.0.1", port=9877)
    assert "connection refused" in text
    assert "listener.start_server" in text
    assert "Cloud Agent" in text
    assert "9877" in text
    assert "8100" in TIMEOUT_MESSAGE + REFUSED_MESSAGE
    assert "not responding" in TIMEOUT_MESSAGE.format(host="127.0.0.1", port=9877)
