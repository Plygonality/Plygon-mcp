from __future__ import annotations

import struct
import zlib

import pytest

from plygon_solidworks_mcp.session import (
    LENGTH_TO_METERS,
    SW_CM,
    SW_FEETINCHES,
    SW_INCHES,
    SW_MM,
    SW_UIN,
    ComSession,
    bmp_to_png,
    document_length_to_meters,
    extrusion_arguments,
    require_positive_length,
)


def _feature(name, type_name, nxt=None):
    class Feature:
        def __init__(self):
            self.Name = name
            self._next = nxt

        def GetTypeName2(self):
            return type_name

        def GetNextFeature(self):
            return self._next

    return Feature()


def _chain(*pairs):
    feature = None
    for name, type_name in reversed(pairs):
        feature = _feature(name, type_name, feature)
    return feature


def make_bmp(rows):
    """rows[0] is the top of the image. Each pixel is (r, g, b)."""
    height = len(rows)
    width = len(rows[0])
    row_stride = ((24 * width + 31) // 32) * 4
    pixels = bytearray()
    for src in reversed(rows):
        row = bytearray()
        for red, green, blue in src:
            row.extend((blue, green, red))
        row.extend(b"\x00" * (row_stride - width * 3))
        pixels.extend(row)
    file_size = 54 + len(pixels)
    header = struct.pack("<2sIHHI", b"BM", file_size, 0, 0, 54)
    dib = struct.pack(
        "<IiiHHIIiiII",
        40,
        width,
        height,
        1,
        24,
        0,
        len(pixels),
        2835,
        2835,
        0,
        0,
    )
    return header + dib + bytes(pixels)


def png_rows(png: bytes):
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    pos = 8
    width = height = None
    compressed = b""
    while pos + 8 <= len(png):
        length = struct.unpack(">I", png[pos : pos + 4])[0]
        tag = png[pos + 4 : pos + 8]
        payload = png[pos + 8 : pos + 8 + length]
        if tag == b"IHDR":
            width, height = struct.unpack(">II", payload[:8])
        elif tag == b"IDAT":
            compressed += payload
        elif tag == b"IEND":
            break
        pos += 12 + length
    raw = zlib.decompress(compressed)
    stride = 1 + width * 3
    rows = []
    for y in range(height):
        row = raw[y * stride : (y + 1) * stride]
        assert row[0] == 0
        rows.append([tuple(row[1 + x * 3 : 4 + x * 3]) for x in range(width)])
    return rows


class Model:
    def __init__(self, unit=SW_MM, doc_type=1, features=None):
        self.unit = unit
        self.doc_type = doc_type
        self.title = "Part1"
        self.path = ""
        self.features = features
        self.calls = []
        self.extension = Extension(self)
        self.sketch = Sketch(self)
        self.features_mgr = Features(self)
        self.saved = []
        self.bmp = None

    def GetTitle(self):
        return self.title

    def GetPathName(self):
        return self.path

    def GetType(self):
        return self.doc_type

    def GetUnits(self):
        return (self.unit, 0)

    def FirstFeature(self):
        self.calls.append("FirstFeature")
        return self.features

    def EditRebuild3(self):
        self.calls.append("EditRebuild3")
        return True

    def SaveAs3(self, path, version, options):
        self.saved.append((path, version, options))
        self.path = path
        return True

    def Save3(self, options, errors, warnings):
        self.calls.append(("Save3", options, errors, warnings))
        return True

    def SaveBMP(self, path, width, height):
        from pathlib import Path

        payload = make_bmp([[(255, 0, 0), (0, 255, 0)], [(0, 0, 255), (1, 2, 3)]])
        Path(path).write_bytes(payload)
        self.bmp = (path, width, height)
        return True

    def ViewZoomtofit2(self):
        self.calls.append("ViewZoomtofit2")

    def GraphicsRedraw2(self):
        self.calls.append("GraphicsRedraw2")

    @property
    def Extension(self):
        return self.extension

    @property
    def SketchManager(self):
        return self.sketch

    @property
    def FeatureManager(self):
        return self.features_mgr


class Extension:
    def __init__(self, model):
        self.model = model
        self.selected = []
        self.manager = Properties()
        self.mass = Mass()

    def SelectByID2(self, name, type_name, *rest):
        self.selected.append((name, type_name, rest))
        self.model.calls.append("SelectByID2")
        return True

    def CustomPropertyManager(self, config):
        assert config == ""
        return self.manager

    def CreateMassProperty(self):
        return self.mass


class Properties:
    def __init__(self):
        self.values = {"Material": "ABS"}
        self.added = []

    def GetNames(self):
        return tuple(self.values)

    def Get(self, name):
        return self.values[name]

    def Add3(self, name, field_type, value, overwrite):
        self.added.append((name, field_type, value, overwrite))
        self.values[name] = value
        return 0


class Mass:
    UseSystemUnits = False
    Mass = 0.125
    Volume = 0.000048
    SurfaceArea = 0.012
    CenterOfMass = (0.0, 0.01, 0.005)


class Sketch:
    def __init__(self, model):
        self.model = model
        self.rectangle = None

    def InsertSketch(self, value):
        self.model.calls.append(("InsertSketch", value))
        return True

    def CreateCenterRectangle(self, x1, y1, z1, x2, y2, z2):
        self.rectangle = (x1, y1, z1, x2, y2, z2)
        self.model.calls.append("CreateCenterRectangle")
        return ("line",)


class Features:
    def __init__(self, model):
        self.model = model
        self.args = None
        self.made = _feature("Boss-Extrude1", "Extrusion")

    def FeatureExtrusion3(self, *args):
        self.args = args
        self.model.calls.append("FeatureExtrusion3")
        return self.made


class App:
    def __init__(self, model=None, revision="32.0.0"):
        self.ActiveDoc = model
        self.RevisionNumber = revision
        self.templates = {
            8: r"C:\templates\part.prtdot",
            9: r"C:\templates\assembly.asmdot",
            10: r"C:\templates\drawing.drwdot",
        }
        self.created = []
        self.Visible = False

    def GetUserPreferenceStringValue(self, pref):
        return self.templates.get(pref, "")

    def NewDocument(self, template, paper, width, height):
        self.created.append((template, paper, width, height))
        model = Model()
        model.title = "Part2"
        self.ActiveDoc = model
        return model


def standard_model(**kwargs):
    features = _chain(
        ("Front Plane", "RefPlane"),
        ("Top Plane", "RefPlane"),
        ("Right Plane", "RefPlane"),
        ("Origin", "RefPoint"),
    )
    return Model(features=features, **kwargs)


def test_extrusion_argument_count_and_depth():
    args = extrusion_arguments(0.02)
    assert len(args) == 23
    assert args[5] == 0.02
    assert args[0] is True
    assert args[17] is True
    assert args[19] is True


def test_length_conversion_matches_document_units():
    assert document_length_to_meters(60, SW_MM) == pytest.approx(0.06)
    assert document_length_to_meters(1, SW_INCHES) == pytest.approx(0.0254)
    assert document_length_to_meters(2, SW_CM) == pytest.approx(0.02)
    assert document_length_to_meters(1, SW_FEETINCHES) == pytest.approx(LENGTH_TO_METERS[SW_INCHES])
    assert document_length_to_meters(1, SW_UIN) == pytest.approx(2.54e-8)


def test_non_finite_lengths_fail_before_the_model_is_touched():
    model = standard_model()
    session = ComSession(App(model))
    with pytest.raises(ValueError, match="width"):
        session.create_extruded_box(width=float("nan"), depth=10, height=10)
    with pytest.raises(ValueError, match="height"):
        session.create_extruded_box(width=10, depth=10, height=0)
    with pytest.raises(ValueError, match="plane"):
        session.create_extruded_box(width=10, depth=10, height=10, plane="left")
    assert model.calls == []
    with pytest.raises(ValueError, match="greater than 0"):
        require_positive_length("depth", "nope")


def test_box_uses_document_millimetres_and_localized_plane_type():
    model = standard_model()
    model.features = _chain(
        ("Plan de face", "RefPlane"),
        ("Plan de dessus", "RefPlane"),
        ("Plan de droite", "RefPlane"),
    )
    session = ComSession(App(model))

    result = session.create_extruded_box(width=60, depth=40, height=10, plane="top", name="Plate")

    assert result["unit"] == "mm"
    assert result["plane"] == "Plan de dessus"
    assert result["name"] == "Plate"
    assert model.sketch.rectangle == pytest.approx((0, 0, 0, 0.03, 0.02, 0))
    assert model.features_mgr.args == extrusion_arguments(0.01)
    assert model.extension.selected[0][0] == "Plan de dessus"
    assert "SelectByID2" in model.calls
    assert model.calls.index("SelectByID2") < model.calls.index("CreateCenterRectangle")
    assert model.calls.index("CreateCenterRectangle") < model.calls.index("FeatureExtrusion3")


def test_inch_part_converts_before_the_api_call():
    model = standard_model(unit=SW_INCHES)
    session = ComSession(App(model))

    session.create_extruded_box(width=2, depth=1, height=0.5)

    assert model.sketch.rectangle[3] == pytest.approx(0.0254)
    assert model.sketch.rectangle[4] == pytest.approx(0.0127)
    assert model.features_mgr.args[5] == pytest.approx(0.0127)


def test_assembly_is_rejected_before_a_sketch():
    model = standard_model(doc_type=2)
    session = ComSession(App(model))

    with pytest.raises(RuntimeError, match="part document"):
        session.create_extruded_box(width=10, depth=10, height=10)

    assert "SelectByID2" not in model.calls
    assert "CreateCenterRectangle" not in model.calls


def test_document_info_mass_and_properties():
    model = standard_model()
    model.path = r"C:\work\bracket.SLDPRT"
    session = ComSession(App(model, revision="33.1.0"))

    info = session.document_info(limit=2)
    assert info["type"] == "part"
    assert info["unit"] == "mm"
    assert info["path"].endswith("bracket.SLDPRT")
    assert info["feature_count"] == 4
    assert info["features_truncated"] is True
    assert [row["name"] for row in info["features"]] == ["Front Plane", "Top Plane"]

    listed = session.list_features(limit=10)
    assert listed["count"] == 4
    assert listed["truncated"] is False

    mass = session.mass_properties()
    assert mass["mass_kg"] == pytest.approx(0.125)
    assert mass["center_of_mass_m"] == [0.0, 0.01, 0.005]

    props = session.custom_properties()
    assert props["properties"]["Material"] == "ABS"
    updated = session.set_custom_property("Finish", "Bead blast")
    assert updated == {"name": "Finish", "value": "Bead blast"}
    assert model.extension.manager.added[0][3] is True
    with pytest.raises(ValueError, match="name"):
        session.set_custom_property("  ", "x")


def test_document_info_uses_the_chain_built_for_a_default_template():
    model = standard_model()
    info = ComSession(App(model)).document_info()
    assert [row["type"] for row in info["features"][:3]] == ["RefPlane", "RefPlane", "RefPlane"]
    assert info["solidworks_version"] == "32.0.0"


def test_new_document_uses_default_templates():
    app = App(standard_model())
    session = ComSession(app)

    created = session.new_document("assembly")

    assert created["type"] == "assembly"
    assert created["template"].endswith("assembly.asmdot")
    assert app.created[0][0].endswith("assembly.asmdot")
    with pytest.raises(ValueError, match="kind"):
        session.new_document("drawing-template")


def test_missing_template_is_explained():
    app = App()
    app.templates[8] = ""
    with pytest.raises(RuntimeError, match="Default Templates"):
        ComSession(app).new_document("part")


def test_export_rejects_unknown_suffix_before_save():
    model = standard_model()
    session = ComSession(App(model))
    with pytest.raises(ValueError, match=".step"):
        session.export_document(r"C:\out\bracket.sldprt")
    assert model.saved == []

    exported = session.export_document(r"C:\out\bracket.STEP")
    assert exported["format"] == "step"
    assert model.saved[0][0].endswith("bracket.STEP")
    assert model.saved[0][2] == 1


def test_save_in_place_uses_silent_save3():
    model = standard_model()
    model.path = r"C:\work\part.SLDPRT"
    saved = ComSession(App(model)).save_document()
    assert saved["filepath"].endswith("part.SLDPRT")
    assert model.calls[0][0] == "Save3"
    assert model.calls[0][1] == 1


def test_screenshot_converts_bmp_and_rejects_tiny_sizes(tmp_path):
    model = standard_model()
    destination = tmp_path / "view.png"
    result = ComSession(App(model)).viewport_screenshot(str(destination), max_size=1000)

    assert result["max_size"] == 1000
    assert model.bmp[1:] == (1000, 1000)
    rows = png_rows(destination.read_bytes())
    assert rows[0][0] == (255, 0, 0)
    assert rows[1][0] == (0, 0, 255)
    assert not (tmp_path / "view.bmp").exists()

    with pytest.raises(ValueError, match="at least 32"):
        ComSession(App(model)).viewport_screenshot(str(destination), max_size=8)


def test_bmp_to_png_flips_bottom_up_rows():
    bitmap = make_bmp([[(255, 0, 0)], [(0, 0, 255)]])
    rows = png_rows(bmp_to_png(bitmap))
    assert rows == [[(255, 0, 0)], [(0, 0, 255)]]


def test_execute_code_exposes_sw_and_truncates_stdout():
    app = App(standard_model())
    result = ComSession(app).execute_code("print(sw.RevisionNumber)\nprint(model.GetTitle())")
    assert "32.0.0" in result["stdout"]
    assert "Part1" in result["stdout"]

    huge = ComSession(app).execute_code("print('x' * 300000)")
    assert huge["stdout"].endswith("bytes]")
    assert "truncated" in huge["stdout"]

    with pytest.raises(RuntimeError, match="ZeroDivisionError"):
        ComSession(app).execute_code("print('before')\n1/0")


def test_no_active_document():
    session = ComSession(App(None))
    with pytest.raises(RuntimeError, match="No SOLIDWORKS document"):
        session.document_info()
    assert session.document_summary() is None
