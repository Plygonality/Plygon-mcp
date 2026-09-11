from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LISTENER_PATH = (
    ROOT
    / "package"
    / "scripts"
    / "python"
    / "plygon_houdini_mcp"
    / "listener.py"
)


class FakeParm:
    def __init__(self, value=0):
        self.value = value

    def set(self, value):
        self.value = value

    def eval(self):
        return self.value


class FakeParmTuple:
    def __init__(self, value=()):
        self.value = tuple(value)

    def set(self, value):
        self.value = tuple(value)

    def eval(self):
        return self.value


def load_listener(monkeypatch, **hou_overrides):
    hou = types.ModuleType("hou")
    hou.GeometryPermissionError = type("GeometryPermissionError", (Exception,), {})
    hou.isUIAvailable = lambda: True
    hou.applicationVersion = lambda: (21, 0, 0)
    hou.applicationVersionString = lambda: "21.0"
    hou.frame = lambda: 1.0
    hou.ui = types.SimpleNamespace()
    for name, value in hou_overrides.items():
        setattr(hou, name, value)
    monkeypatch.setitem(sys.modules, "hou", hou)

    module_name = "plygon_houdini_mcp._listener_runtime_test"
    spec = importlib.util.spec_from_file_location(module_name, LISTENER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, module_name, module)
    spec.loader.exec_module(module)
    return module, hou


def test_start_rejects_headless_houdini(monkeypatch):
    listener, _hou = load_listener(monkeypatch, isUIAvailable=lambda: False)

    server = listener.HoudiniMCPServer()

    assert server.start() is False
    assert server.running is False
    assert server.socket is None


@pytest.mark.parametrize("host", ["", "localhost", "::1"])
def test_listener_coerces_loopback_aliases_to_ipv4(monkeypatch, host):
    listener, _hou = load_listener(monkeypatch)

    assert listener.HoudiniMCPServer(host=host).host == "127.0.0.1"


def test_listener_extracts_concatenated_commands(monkeypatch):
    listener, _hou = load_listener(monkeypatch)
    ping = {"type": "ping", "params": {}}
    scene = {"type": "get_scene_info", "params": {"limit": 5}}

    commands, leftover = listener._extract_json_objects(
        (json.dumps(ping) + json.dumps(scene)).encode("utf-8")
    )

    assert commands == [ping, scene]
    assert leftover == b""
    assert listener._encode_message(ping).endswith(b"\n")


def test_listener_recovers_after_malformed_newline_frame(monkeypatch):
    listener, _hou = load_listener(monkeypatch)
    ping = {"type": "ping", "params": {}}

    commands, leftover = listener._extract_json_objects(
        b'{"type":]\n' + json.dumps(ping).encode("utf-8") + b"\n"
    )

    assert commands == [listener._MALFORMED_JSON, ping]
    assert leftover == b""


def test_listener_protocol_work_is_bounded(monkeypatch):
    listener, _hou = load_listener(monkeypatch)
    server = listener.HoudiniMCPServer()

    assert listener.MAX_BUFFER_BYTES == 4 * 1024 * 1024
    assert listener.MAX_PENDING_COMMANDS == 128
    assert server.command_queue.maxsize == listener.MAX_PENDING_COMMANDS
    assert listener.MAX_COMMANDS_PER_TICK == 1


def test_disconnected_client_work_is_discarded(monkeypatch):
    listener, _hou = load_listener(monkeypatch)
    server = listener.HoudiniMCPServer()
    server.running = True
    executed = []
    server.execute_command = executed.append
    closed = types.SimpleNamespace(is_set=lambda: True)
    server.command_queue.put_nowait(({"type": "ping"}, object(), closed, None))

    server._drain_command_queue()

    assert executed == []
    assert server.command_queue.empty()


def test_set_node_parm_supports_tuple_names(monkeypatch):
    tuple_parm = FakeParmTuple((0.0, 0.0, 0.0))
    node = types.SimpleNamespace(
        parm=lambda name: None,
        parmTuple=lambda name: tuple_parm if name == "t" else None,
    )
    listener, _hou = load_listener(
        monkeypatch,
        node=lambda path: node if path == "/obj/geo1" else None,
    )

    result = listener.HoudiniMCPServer().set_node_parm(
        "/obj/geo1", "t", [1.0, 2.0, 3.0]
    )

    assert tuple_parm.value == (1.0, 2.0, 3.0)
    assert result["value"] == [1.0, 2.0, 3.0]


def test_list_nodes_keeps_disconnected_input_slots(monkeypatch):
    upstream = types.SimpleNamespace(path=lambda: "/obj/geo1/upstream")
    child_type = types.SimpleNamespace(name=lambda: "merge")
    child = types.SimpleNamespace(
        path=lambda: "/obj/geo1/merge1",
        name=lambda: "merge1",
        type=lambda: child_type,
        inputs=lambda: (None, upstream),
    )
    parent = types.SimpleNamespace(children=lambda: (child,))
    listener, _hou = load_listener(
        monkeypatch,
        node=lambda path: parent if path == "/obj/geo1" else None,
    )

    result = listener.HoudiniMCPServer().list_nodes("/obj/geo1")

    assert result["nodes"][0]["inputs"] == [None, "/obj/geo1/upstream"]


def test_get_node_info_limits_parm_evaluation_and_counts_vertices(monkeypatch):
    category = types.SimpleNamespace(name=lambda: "Sop")
    eval_count = 0

    class InfoParm:
        def __init__(self, index):
            self.index = index

        def eval(self):
            nonlocal eval_count
            eval_count += 1
            return self.index

        def name(self):
            return f"parm{self.index}"

        def description(self):
            return f"Parameter {self.index}"

    prims = (
        types.SimpleNamespace(numVertices=lambda: 3),
        types.SimpleNamespace(numVertices=lambda: 4),
    )
    geometry = types.SimpleNamespace(
        points=lambda: (object(), object()),
        prims=lambda: prims,
    )
    node_type = types.SimpleNamespace(
        name=lambda: "box",
        category=lambda: category,
    )
    node = types.SimpleNamespace(
        path=lambda: "/obj/geo1/box1",
        name=lambda: "box1",
        type=lambda: node_type,
        color=lambda: (1.0, 1.0, 1.0),
        inputs=lambda: (),
        outputs=lambda: (),
        isDisplayFlagSet=lambda: True,
        isRenderFlagSet=lambda: True,
        parms=lambda: tuple(InfoParm(index) for index in range(150)),
        children=lambda: (),
        geometry=lambda: geometry,
    )
    listener, _hou = load_listener(
        monkeypatch,
        node=lambda path: node if path == "/obj/geo1/box1" else None,
        sopNodeTypeCategory=lambda: category,
    )

    result = listener.HoudiniMCPServer().get_node_info("/obj/geo1/box1")

    assert eval_count == 100
    assert result["parm_count"] == 150
    assert result["geometry"] == {"points": 2, "prims": 2, "vertices": 7}


class FakeCreatedNode:
    def __init__(self, path: str):
        self._path = path
        self.created = []
        self.parms = {}
        self.parm_tuples = {}
        self.display = False
        self.render = False
        self.laid_out = False

    def path(self):
        return self._path

    def createNode(self, node_type, node_name):
        child = FakeCreatedNode(f"{self._path}/{node_name}")
        child.node_type = node_type
        self.created.append(child)
        return child

    def parm(self, name):
        return self.parms.setdefault(name, FakeParm())

    def parmTuple(self, name):
        return self.parm_tuples.setdefault(name, FakeParmTuple())

    def setDisplayFlag(self, value):
        self.display = value

    def setRenderFlag(self, value):
        self.render = value

    def layoutChildren(self):
        self.laid_out = True


def test_create_primitive_validates_before_mutation_and_honors_parent(monkeypatch):
    parent = FakeCreatedNode("/obj/subnet1")
    listener, _hou = load_listener(
        monkeypatch,
        node=lambda path: parent if path == "/obj/subnet1" else None,
    )
    server = listener.HoudiniMCPServer()

    with pytest.raises(ValueError, match="Unknown shape"):
        server.create_primitive("invalid", parent_path="/obj/subnet1")
    assert parent.created == []

    result = server.create_primitive(
        "box",
        name="agent_box",
        parent_path="/obj/subnet1",
        size=2.5,
        location=[1.0, 2.0, 3.0],
    )

    geo = parent.created[0]
    sop = geo.created[0]
    assert result["geo_path"] == "/obj/subnet1/agent_box"
    assert sop.parm_tuples["size"].value == (2.5, 2.5, 2.5)
    assert geo.parm_tuples["t"].value == (1.0, 2.0, 3.0)


@pytest.mark.parametrize(
    ("size", "location", "message"),
    [
        (float("nan"), [0.0, 0.0, 0.0], "size must be a finite"),
        (float("inf"), [0.0, 0.0, 0.0], "size must be a finite"),
        (1.0, [0.0, float("nan"), 0.0], "location values must be finite"),
        (1.0, [0.0, float("inf"), 0.0], "location values must be finite"),
    ],
)
def test_create_primitive_rejects_non_finite_values_before_mutation(
    monkeypatch, size, location, message
):
    parent = FakeCreatedNode("/obj")
    listener, _hou = load_listener(
        monkeypatch,
        node=lambda path: parent if path == "/obj" else None,
    )

    with pytest.raises(ValueError, match=message):
        listener.HoudiniMCPServer().create_primitive(
            "box", parent_path="/obj", size=size, location=location
        )

    assert parent.created == []


@pytest.mark.parametrize(
    ("shape", "parm_name", "expected"),
    [
        ("sphere", "rad", (2.0, 2.0, 2.0)),
        ("grid", "size", (4.0, 4.0)),
        ("tube", "rad", (2.0, 2.0)),
        ("torus", "rad", (2.0, 0.5)),
        ("circle", "rad", (2.0, 2.0)),
    ],
)
def test_create_primitive_applies_size_to_tuple_shapes(
    monkeypatch, shape, parm_name, expected
):
    parent = FakeCreatedNode("/obj")
    listener, _hou = load_listener(
        monkeypatch,
        node=lambda path: parent if path == "/obj" else None,
    )

    listener.HoudiniMCPServer().create_primitive(
        shape, parent_path="/obj", size=4.0
    )

    sop = parent.created[0].created[0]
    assert sop.parm_tuples[parm_name].value == expected
    if shape == "tube":
        assert sop.parms["height"].value == 4.0


def test_create_line_applies_size(monkeypatch):
    parent = FakeCreatedNode("/obj")
    listener, _hou = load_listener(
        monkeypatch,
        node=lambda path: parent if path == "/obj" else None,
    )

    listener.HoudiniMCPServer().create_primitive(
        "line", parent_path="/obj", size=4.0
    )

    sop = parent.created[0].created[0]
    assert sop.parms["dist"].value == 4.0


def test_viewport_screenshot_uses_supported_flipbook_api(monkeypatch, tmp_path):
    output_calls = {}

    class Settings:
        def stash(self):
            return self

        def frameRange(self, value):
            output_calls["frame_range"] = value

        def output(self, value):
            output_calls["path"] = value

        def outputToMPlay(self, value):
            output_calls["mplay"] = value

        def useResolution(self, value):
            output_calls["use_resolution"] = value

        def resolution(self, value):
            output_calls["resolution"] = value

    viewport = types.SimpleNamespace(resolutionInPixels=lambda: (1920, 1080))
    settings = Settings()

    class SceneViewer:
        def curViewport(self):
            return viewport

        def flipbookSettings(self):
            return settings

        def flipbook(self, selected_viewport, selected_settings):
            assert selected_viewport is viewport
            assert selected_settings is settings
            Path(output_calls["path"]).write_bytes(b"png")

    scene_viewer = SceneViewer()
    desktop = types.SimpleNamespace(
        paneTabOfType=lambda pane_type: scene_viewer,
    )
    ui = types.SimpleNamespace(curDesktop=lambda: desktop)
    pane_tab_type = types.SimpleNamespace(SceneViewer=object())
    listener, _hou = load_listener(
        monkeypatch,
        ui=ui,
        paneTabType=pane_tab_type,
    )
    output = tmp_path / "viewport.png"

    result = listener.HoudiniMCPServer().get_viewport_screenshot(
        max_size=1000, filepath=str(output)
    )

    assert result["success"] is True
    assert output.read_bytes() == b"png"
    assert output_calls["resolution"] == (1000, 562)
    assert output_calls["mplay"] is False


def test_viewport_screenshot_rejects_too_small_max_size(monkeypatch):
    listener, _hou = load_listener(monkeypatch)

    with pytest.raises(ValueError, match="at least 2"):
        listener.HoudiniMCPServer().get_viewport_screenshot(max_size=1)
