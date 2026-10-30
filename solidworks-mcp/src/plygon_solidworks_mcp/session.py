# SPDX-License-Identifier: MIT
"""SOLIDWORKS COM session used by the Plygon listener.

The MCP server never imports this module's COM path. Tests construct
``ComSession`` with a stand-in application object. ``attach_running_solidworks``
is the only function that loads pywin32, and only on Windows.
"""

from __future__ import annotations

import io
import struct
import sys
import zlib
from contextlib import redirect_stdout
from pathlib import Path

# swUserPreferenceStringValue_e
SW_DEFAULT_TEMPLATE_PART = 8
SW_DEFAULT_TEMPLATE_ASSEMBLY = 9
SW_DEFAULT_TEMPLATE_DRAWING = 10

# swDocumentTypes_e
SW_DOC_PART = 1
SW_DOC_ASSEMBLY = 2
SW_DOC_DRAWING = 3

# swLengthUnit_e, as returned by IModelDoc2.GetUnits()[0]
SW_MM = 0
SW_CM = 1
SW_METER = 2
SW_INCHES = 3
SW_FEET = 4
SW_FEETINCHES = 5
SW_ANGSTROM = 6
SW_NANOMETER = 7
SW_MICRON = 8
SW_MIL = 9
SW_UIN = 10

# swCustomInfoType_e.swCustomInfoText
SW_CUSTOM_INFO_TEXT = 30
# swCustomInfoAddResult_e.swCustomInfoAddResult_AddedOrChanged
SW_CUSTOM_INFO_ADDED_OR_CHANGED = 0
# IModelDoc2.Save3 / SaveAs3 silent option (swSaveAsOptions_Silent)
SW_SAVE_AS_SILENT = 1

STDOUT_LIMIT = 256 * 1024
FEATURE_WALK_CAP = 5000
MIN_SCREENSHOT_PIXELS = 32
MAX_SCREENSHOT_PIXELS = 4096

DOC_TYPES = {
    SW_DOC_PART: "part",
    SW_DOC_ASSEMBLY: "assembly",
    SW_DOC_DRAWING: "drawing",
}
TEMPLATE_PREFERENCES = {
    "part": SW_DEFAULT_TEMPLATE_PART,
    "assembly": SW_DEFAULT_TEMPLATE_ASSEMBLY,
    "drawing": SW_DEFAULT_TEMPLATE_DRAWING,
}
UNIT_NAMES = {
    SW_MM: "mm",
    SW_CM: "cm",
    SW_METER: "m",
    SW_INCHES: "in",
    SW_FEET: "ft",
    SW_FEETINCHES: "ft-in",
    SW_ANGSTROM: "angstrom",
    SW_NANOMETER: "nm",
    SW_MICRON: "micron",
    SW_MIL: "mil",
    SW_UIN: "uin",
}
# Feet-and-inches documents report swFEETINCHES. A single number cannot carry
# both feet and inches, so the listener treats that number as inches. That is
# the same factor SOLIDWORKS macro examples use for swFEETINCHES.
LENGTH_TO_METERS = {
    SW_MM: 0.001,
    SW_CM: 0.01,
    SW_METER: 1.0,
    SW_INCHES: 0.0254,
    SW_FEET: 0.3048,
    SW_FEETINCHES: 0.0254,
    SW_ANGSTROM: 1e-10,
    SW_NANOMETER: 1e-9,
    SW_MICRON: 1e-6,
    SW_MIL: 0.0000254,
    SW_UIN: 2.54e-8,
}
PLANE_ORDER = ("front", "top", "right")
EXPORT_SUFFIXES = {".step", ".stp", ".iges", ".igs", ".stl", ".pdf", ".x_t", ".x_b", ".3mf"}

WINDOWS_ONLY_MESSAGE = (
    "SOLIDWORKS runs on Windows. Start this listener on the PC where SOLIDWORKS is open."
)


class SolidWorksUnavailable(RuntimeError):
    """The listener cannot attach to a running SOLIDWORKS session."""


def attach_running_solidworks():
    """Attach to the SOLIDWORKS window the user already opened.

    This does not call Dispatch, so it will not launch a second session or
    take another license.
    """
    if sys.platform != "win32":
        raise SolidWorksUnavailable(WINDOWS_ONLY_MESSAGE)
    try:
        import win32com.client
    except ImportError as exc:
        raise SolidWorksUnavailable(
            "pywin32 is not installed. On the SOLIDWORKS PC run scripts\\start-solidworks.cmd."
        ) from exc
    try:
        app = win32com.client.GetActiveObject("SldWorks.Application")
    except Exception as exc:
        raise SolidWorksUnavailable(
            "SOLIDWORKS is not running. Open the SOLIDWORKS window first, then start "
            "the listener. This listener attaches to that window. It does not launch "
            "a second SOLIDWORKS."
        ) from exc
    try:
        app.Visible = True
    except Exception:
        pass
    return ComSession(app)


def require_positive_length(name: str, value) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite length greater than 0") from exc
    if number != number or number in (float("inf"), float("-inf")) or number <= 0:
        raise ValueError(f"{name} must be a finite length greater than 0")
    return number


def document_length_to_meters(value: float, unit_code: int) -> float:
    try:
        factor = LENGTH_TO_METERS[int(unit_code)]
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Unsupported SOLIDWORKS length unit code: {unit_code}") from exc
    return float(value) * factor


def extrusion_arguments(depth_m: float) -> tuple:
    """IFeatureManager.FeatureExtrusion3 arguments for one blind boss.

    The flag pattern matches the documented single-ended blind extrude:
    merge on, feature scope off, auto-select on, start at the sketch plane.
    ``depth_m`` is meters, which is the API unit regardless of the document.
    """
    depth = float(depth_m)
    return (
        True,  # Sd: single ended
        False,  # Flip
        False,  # Dir
        0,  # T1: swEndCondBlind
        0,  # T2
        depth,  # D1
        0.0,  # D2
        False,  # Dchk1
        False,  # Dchk2
        False,  # Ddir1
        True,  # Ddir2
        0.0,  # Dang1
        0.0,  # Dang2
        False,  # OffsetReverse1
        False,  # OffsetReverse2
        False,  # TranslateSurface1
        False,  # TranslateSurface2
        True,  # Merge
        False,  # UseFeatScope
        True,  # UseAutoSelect
        0,  # T0: sketch plane
        0.0,  # StartOffset
        False,  # FlipStartOffset
    )


def length_unit_code(model) -> int:
    units = model.GetUnits
    if callable(units):
        units = units()
    if isinstance(units, (list, tuple)):
        if not units:
            raise ValueError("GetUnits returned no length unit")
        return int(units[0])
    return int(units)


def reference_plane_name(model, plane: str) -> str:
    key = str(plane or "").strip().lower()
    if key not in PLANE_ORDER:
        raise ValueError("plane must be front, top, or right")
    index = PLANE_ORDER.index(key)
    found: list[str] = []
    feature = model.FirstFeature()
    seen = 0
    while feature is not None and len(found) < 3 and seen < FEATURE_WALK_CAP:
        seen += 1
        type_name = feature.GetTypeName2()
        if type_name == "RefPlane":
            found.append(str(feature.Name))
        feature = feature.GetNextFeature()
    if index >= len(found):
        raise ValueError(
            f"Could not find the {key} reference plane. Open a part whose first "
            "reference planes are the standard Front, Top, and Right planes."
        )
    return found[index]


def _truncate_output(text: str, limit: int = STDOUT_LIMIT) -> str:
    raw = text.encode("utf-8")
    if len(raw) <= limit:
        return text
    kept = raw[:limit].decode("utf-8", errors="ignore")
    dropped = len(raw) - len(kept.encode("utf-8"))
    return f"{kept}\n…[truncated {dropped} bytes]"


def _as_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    try:
        return list(value)
    except TypeError:
        return [value]


def _com_nothing():
    """Optional COM object argument. Tests pass None. pywin32 wants a VARIANT."""
    try:
        import pythoncom
        import win32com.client
    except ImportError:
        return None
    return win32com.client.VARIANT(pythoncom.VT_DISPATCH, None)


def _property_value(manager, name: str) -> str:
    getter = getattr(manager, "Get", None)
    if callable(getter):
        try:
            value = getter(name)
        except TypeError:
            value = None
        else:
            if isinstance(value, str):
                return value
            if isinstance(value, (list, tuple)):
                texts = [item for item in value if isinstance(item, str)]
                if texts:
                    return texts[-1]
    get2 = getattr(manager, "Get2", None)
    if callable(get2):
        try:
            result = get2(name, "", "")
        except TypeError:
            result = get2(name)
        if isinstance(result, str):
            return result
        if isinstance(result, (list, tuple)):
            texts = [item for item in result if isinstance(item, str)]
            if texts:
                return texts[-1]
    return ""


def _walk_features(model, limit: int) -> tuple[list[dict], int, bool]:
    cap = max(0, int(limit))
    rows: list[dict] = []
    feature = model.FirstFeature()
    total = 0
    while feature is not None and total < FEATURE_WALK_CAP:
        total += 1
        if len(rows) < cap:
            try:
                type_name = feature.GetTypeName2()
            except Exception:
                type_name = ""
            rows.append({"name": str(feature.Name), "type": str(type_name)})
        feature = feature.GetNextFeature()
    truncated = len(rows) < total or feature is not None
    return rows, total, truncated


def bmp_to_png(data: bytes) -> bytes:
    """Convert a 24-bit or 32-bit uncompressed BMP into an RGB PNG.

    SOLIDWORKS ``SaveBMP`` writes a bitmap. The MCP client wants a PNG.
    """
    if len(data) < 54 or data[:2] != b"BM":
        raise ValueError("SOLIDWORKS did not write a BMP screenshot")
    pixel_offset = struct.unpack_from("<I", data, 10)[0]
    header_size, width, height, _planes, bit_count, compression = struct.unpack_from(
        "<IiiHHI", data, 14
    )
    if header_size < 40 or compression != 0 or bit_count not in (24, 32) or width <= 0:
        raise ValueError(
            f"Unsupported BMP screenshot (header={header_size}, {width}x{height}, "
            f"{bit_count}-bit, compression={compression})"
        )
    top_down = height < 0
    height = abs(height)
    if height <= 0:
        raise ValueError("BMP screenshot has no rows")
    row_stride = ((bit_count * width + 31) // 32) * 4
    channels = 4 if bit_count == 32 else 3
    raw = bytearray()
    for y in range(height):
        src_y = y if top_down else height - 1 - y
        row = pixel_offset + src_y * row_stride
        raw.append(0)
        for x in range(width):
            start = row + x * channels
            pixel = data[start : start + 3]
            if len(pixel) < 3:
                raise ValueError("BMP screenshot is truncated")
            blue, green, red = pixel
            raw.extend((red, green, blue))
    compressed = zlib.compress(bytes(raw), 9)

    def chunk(tag: bytes, payload: bytes) -> bytes:
        crc = zlib.crc32(tag + payload) & 0xFFFFFFFF
        return struct.pack(">I", len(payload)) + tag + payload + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", compressed) + chunk(b"IEND", b"")


def _pixel_size(max_size: int) -> int:
    try:
        size = int(max_size)
    except (TypeError, ValueError) as exc:
        raise ValueError("max_size must be at least 32") from exc
    if size < MIN_SCREENSHOT_PIXELS:
        raise ValueError("max_size must be at least 32")
    return min(size, MAX_SCREENSHOT_PIXELS)


class ComSession:
    """One attached SOLIDWORKS application. Call it from a single STA thread."""

    def __init__(self, app):
        self.app = app

    def solidworks_version(self) -> str:
        revision = getattr(self.app, "RevisionNumber", None)
        try:
            if callable(revision):
                revision = revision()
        except Exception:
            revision = None
        if revision:
            return str(revision)
        return "unknown"

    def document_summary(self):
        model = self.app.ActiveDoc
        if model is None:
            return None
        return {
            "title": str(model.GetTitle()),
            "type": DOC_TYPES.get(int(model.GetType()), "unknown"),
        }

    def _active_model(self):
        model = self.app.ActiveDoc
        if model is None:
            raise RuntimeError("No SOLIDWORKS document is open.")
        return model

    def document_info(self, limit: int = 50) -> dict:
        model = self._active_model()
        unit = length_unit_code(model)
        features, total, truncated = _walk_features(model, limit)
        path = model.GetPathName()
        return {
            "title": str(model.GetTitle()),
            "path": str(path) if path else "(unsaved)",
            "type": DOC_TYPES.get(int(model.GetType()), "unknown"),
            "unit": UNIT_NAMES.get(unit, str(unit)),
            "unit_code": unit,
            "feature_count": total,
            "features_truncated": truncated,
            "features": features,
            "solidworks_version": self.solidworks_version(),
        }

    def list_features(self, limit: int = 50) -> dict:
        model = self._active_model()
        features, total, truncated = _walk_features(model, limit)
        return {
            "features": features,
            "count": total,
            "returned": len(features),
            "truncated": truncated,
        }

    def mass_properties(self) -> dict:
        model = self._active_model()
        extension = model.Extension
        mass = extension.CreateMassProperty()
        if mass is None:
            raise RuntimeError(
                "This document has no mass properties. Rebuild a part that contains a solid body."
            )
        try:
            mass.UseSystemUnits = True
        except Exception:
            pass
        center = mass.CenterOfMass
        if center is None:
            center_m = None
        else:
            center_m = [float(center[0]), float(center[1]), float(center[2])]
        return {
            "mass_kg": float(mass.Mass),
            "volume_m3": float(mass.Volume),
            "surface_area_m2": float(mass.SurfaceArea),
            "center_of_mass_m": center_m,
        }

    def custom_properties(self) -> dict:
        model = self._active_model()
        manager = model.Extension.CustomPropertyManager("")
        names = _as_list(manager.GetNames())
        properties = {str(name): _property_value(manager, str(name)) for name in names}
        return {"properties": properties, "count": len(properties)}

    def set_custom_property(self, name: str, value: str) -> dict:
        field = str(name or "").strip()
        if not field:
            raise ValueError("name is required")
        model = self._active_model()
        manager = model.Extension.CustomPropertyManager("")
        status = manager.Add3(field, SW_CUSTOM_INFO_TEXT, str(value), True)
        if isinstance(status, int) and status != SW_CUSTOM_INFO_ADDED_OR_CHANGED:
            raise RuntimeError(f"Could not set custom property {field!r} (Add3 status {status})")
        return {"name": field, "value": str(value)}

    def new_document(self, kind: str = "part") -> dict:
        key = str(kind or "").strip().lower()
        if key not in TEMPLATE_PREFERENCES:
            raise ValueError("kind must be part, assembly, or drawing")
        template = self.app.GetUserPreferenceStringValue(TEMPLATE_PREFERENCES[key])
        if not template:
            raise RuntimeError(
                f"SOLIDWORKS has no default {key} template. "
                "Set it in Tools > Options > Default Templates, then try again."
            )
        model = self.app.NewDocument(str(template), 0, 0.0, 0.0)
        if model is None:
            model = self.app.ActiveDoc
        if model is None:
            raise RuntimeError(f"NewDocument did not open a {key}.")
        return {
            "title": str(model.GetTitle()),
            "type": key,
            "template": str(template),
        }

    def create_extruded_box(
        self,
        width: float,
        depth: float,
        height: float,
        plane: str = "front",
        name: str = "",
    ) -> dict:
        width_u = require_positive_length("width", width)
        depth_u = require_positive_length("depth", depth)
        height_u = require_positive_length("height", height)
        plane_key = str(plane or "front").strip().lower()
        if plane_key not in PLANE_ORDER:
            raise ValueError("plane must be front, top, or right")

        model = self._active_model()
        if int(model.GetType()) != SW_DOC_PART:
            raise RuntimeError(
                "create_extruded_box needs a part document. "
                "Open a part, or call new_document with kind part."
            )
        unit = length_unit_code(model)
        width_m = document_length_to_meters(width_u, unit)
        depth_m = document_length_to_meters(depth_u, unit)
        height_m = document_length_to_meters(height_u, unit)
        plane_name = reference_plane_name(model, plane_key)

        selected = model.Extension.SelectByID2(
            plane_name, "PLANE", 0, 0, 0, False, 0, _com_nothing(), 0
        )
        if not selected:
            raise RuntimeError(f"Could not select reference plane {plane_name!r}.")
        sketch = model.SketchManager
        sketch.InsertSketch(True)
        segments = sketch.CreateCenterRectangle(0, 0, 0, width_m / 2.0, depth_m / 2.0, 0)
        if not segments:
            raise RuntimeError("CreateCenterRectangle failed.")
        feature = model.FeatureManager.FeatureExtrusion3(*extrusion_arguments(height_m))
        if feature is None:
            raise RuntimeError(
                "FeatureExtrusion3 returned nothing. The sketch may be invalid. "
                "Use execute_solidworks_code for a different feature."
            )
        if str(name or "").strip():
            feature.Name = str(name).strip()
        rebuilt = model.EditRebuild3()
        if rebuilt is False:
            raise RuntimeError("The box was created, but EditRebuild3 failed.")
        self._frame_model(model)
        return {
            "name": str(feature.Name),
            "plane": plane_name,
            "width": width_u,
            "depth": depth_u,
            "height": height_u,
            "unit": UNIT_NAMES.get(unit, str(unit)),
            "width_m": width_m,
            "depth_m": depth_m,
            "height_m": height_m,
        }

    def rebuild(self) -> dict:
        model = self._active_model()
        rebuilt = model.EditRebuild3()
        if rebuilt is False:
            raise RuntimeError("EditRebuild3 failed.")
        return {"rebuilt": True, "title": str(model.GetTitle())}

    def save_document(self, filepath: str = "") -> dict:
        model = self._active_model()
        target = str(filepath or "").strip()
        if target:
            ok = model.SaveAs3(target, 0, SW_SAVE_AS_SILENT)
            if ok is False:
                raise RuntimeError(f"SaveAs3 failed for {target}")
            return {"filepath": target}
        ok = self._save_in_place(model)
        if ok is False:
            raise RuntimeError(
                "Save failed. The document may never have been saved. Pass a filepath."
            )
        path = model.GetPathName()
        return {"filepath": str(path) if path else "(unsaved)"}

    def _save_in_place(self, model):
        save3 = getattr(model, "Save3", None)
        if callable(save3):
            try:
                return save3(SW_SAVE_AS_SILENT, 0, 0)
            except TypeError:
                import pythoncom
                import win32com.client

                errors = win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
                warnings = win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
                return save3(SW_SAVE_AS_SILENT, errors, warnings)
        return model.Save()

    def export_document(self, filepath: str) -> dict:
        target = str(filepath or "").strip()
        suffix = Path(target).suffix.lower()
        if suffix not in EXPORT_SUFFIXES:
            allowed = ", ".join(sorted(EXPORT_SUFFIXES))
            raise ValueError(f"export extension must be one of: {allowed}")
        model = self._active_model()
        ok = model.SaveAs3(target, 0, SW_SAVE_AS_SILENT)
        if ok is False:
            raise RuntimeError(f"SaveAs3 failed for {target}")
        return {"filepath": target, "format": suffix.lstrip(".")}

    def viewport_screenshot(self, filepath: str, max_size: int = 1000) -> dict:
        size = _pixel_size(max_size)
        destination = Path(str(filepath))
        if not destination.suffix:
            raise ValueError("filepath needs a .png suffix")
        model = self._active_model()
        self._frame_model(model)
        bitmap = destination.with_suffix(".bmp")
        ok = model.SaveBMP(str(bitmap), size, size)
        if ok is False or not bitmap.is_file():
            raise RuntimeError(
                "SaveBMP did not write a viewport image. Keep the SOLIDWORKS model window visible."
            )
        try:
            png = bmp_to_png(bitmap.read_bytes())
        finally:
            if bitmap != destination:
                try:
                    bitmap.unlink()
                except OSError:
                    pass
        destination.write_bytes(png)
        return {"filepath": str(destination), "max_size": size}

    def _frame_model(self, model) -> None:
        for method_name in ("GraphicsRedraw2", "ViewZoomtofit2"):
            method = getattr(model, method_name, None)
            if not callable(method):
                continue
            try:
                method()
            except Exception:
                pass

    def execute_code(self, code: str) -> dict:
        if not isinstance(code, str) or not code.strip():
            raise ValueError("code is required")
        try:
            model = self.app.ActiveDoc
        except Exception:
            model = None
        stdout = io.StringIO()
        namespace = {"sw": self.app, "model": model}
        try:
            with redirect_stdout(stdout):
                exec(code, namespace)  # noqa: S102 - local listener, same trust boundary as the other DCC bridges
        except Exception as exc:
            printed = _truncate_output(stdout.getvalue())
            detail = f"{exc.__class__.__name__}: {exc}"
            if printed:
                detail = f"{detail}\n{printed}"
            raise RuntimeError(detail) from exc
        return {
            "stdout": _truncate_output(stdout.getvalue()),
            "executed": True,
        }
