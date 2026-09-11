# SPDX-License-Identifier: MIT
"""Plygon Blender MCP addon — TCP command bridge for Cursor / MCP clients.

Install via Edit → Preferences → Add-ons → Install… → select this file,
then enable "Interface: Plygon Blender MCP".

In the 3D Viewport press N → PlygonMCP tab → Start MCP Server.
"""

from __future__ import annotations

import bpy
import inspect
import io
import json
import mathutils
import os
import queue
import socket
import tempfile
import threading
import time
import traceback
import uuid
from contextlib import redirect_stdout
from bpy.props import IntProperty, BoolProperty, StringProperty

bl_info = {
    "name": "Plygon Blender MCP",
    "author": "Plygon",
    "version": (1, 0, 3),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar > PlygonMCP",
    "description": "Local MCP bridge so Cursor agents can drive Blender via bpy",
    "category": "Interface",
}

ADDON_PROTOCOL_VERSION = 1
DEFAULT_PORT = 9876
MAX_BUFFER_BYTES = 4 * 1024 * 1024
MAX_PENDING_COMMANDS = 128
MAX_COMMANDS_PER_TICK = 1

_server = None
_MALFORMED_JSON = object()


def _encode_message(obj) -> bytes:
    return (json.dumps(obj, default=str) + "\n").encode("utf-8")


def _extract_json_objects(buffer: bytes):
    """Split concatenated JSON values. Agents often send two commands in one packet."""
    objects = []
    try:
        text = buffer.decode("utf-8")
    except UnicodeDecodeError:
        return objects, buffer
    decoder = json.JSONDecoder()
    idx = 0
    length = len(text)
    while idx < length:
        while idx < length and text[idx].isspace():
            idx += 1
        if idx >= length:
            return objects, b""
        try:
            obj, end = decoder.raw_decode(text, idx)
        except json.JSONDecodeError:
            # Every message we emit is newline terminated. If decoding fails
            # before a newline, discard that malformed frame so one bad
            # request cannot block every later request on this connection.
            newline = text.find("\n", idx)
            if newline < 0:
                break
            objects.append(_MALFORMED_JSON)
            idx = newline + 1
            continue
        if end <= idx:
            break
        objects.append(obj)
        idx = end
    return objects, text[idx:].encode("utf-8")


def _find_view3d_context():
    """Return one coherent window/scene/view-layer context for bpy.ops."""
    window_manager = getattr(bpy.context, "window_manager", None)
    for window in getattr(window_manager, "windows", ()):
        screen = window.screen
        for area in screen.areas:
            if area.type != "VIEW_3D":
                continue
            region = next((item for item in area.regions if item.type == "WINDOW"), None)
            if region is not None:
                return {
                    "window": window,
                    "workspace": getattr(window, "workspace", None),
                    "screen": screen,
                    "scene": getattr(window, "scene", None),
                    "view_layer": getattr(window, "view_layer", None),
                    "area": area,
                    "region": region,
                }
    return None


def _run_operator(operator, *, view3d_context=None, **kwargs):
    """Run an operator with a stable 3D-view context on Blender 3.x and 4.x."""
    context_parts = view3d_context or _find_view3d_context()
    if context_parts is None:
        return operator(**kwargs)

    override = {key: value for key, value in context_parts.items() if value is not None}
    if hasattr(bpy.context, "temp_override"):
        with bpy.context.temp_override(**override):
            return operator(**kwargs)

    # Blender 3.0/3.1 used a positional override dictionary.
    legacy_override = bpy.context.copy()
    legacy_override.update(override)
    return operator(legacy_override, **kwargs)


def _ensure_object_mode(view3d_context=None):
    context_parts = view3d_context or _find_view3d_context()
    view_layer = context_parts.get("view_layer") if context_parts else None
    objects = getattr(view_layer, "objects", None)
    active = getattr(objects, "active", None)
    mode = getattr(active, "mode", getattr(bpy.context, "mode", "OBJECT"))
    if mode != "OBJECT":
        _run_operator(
            bpy.ops.object.mode_set,
            view3d_context=context_parts,
            mode="OBJECT",
        )


class BlenderMCPServer:
    """Accept JSON commands over TCP and run them on Blender's main thread."""

    def __init__(self, host: str = "127.0.0.1", port: int = DEFAULT_PORT):
        self.host = "127.0.0.1" if host in {"localhost", "::1", ""} else host
        self.port = port
        self.running = False
        self.socket = None
        self.server_thread = None
        self.command_queue: queue.Queue = queue.Queue(maxsize=MAX_PENDING_COMMANDS)
        self._clients = set()
        self._clients_lock = threading.Lock()

    def start(self) -> bool:
        if bpy.app.background:
            print(
                "PlygonMCP: cannot start in background mode (blender -b). "
                "Run Blender with a GUI, or: xvfb-run -a blender"
            )
            return False

        if self.running:
            print("PlygonMCP: server already running")
            return True

        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.bind((self.host, self.port))
            self.socket.listen(5)
            self.running = True

            self.server_thread = threading.Thread(target=self._server_loop, daemon=True)
            self.server_thread.start()

            if not bpy.app.timers.is_registered(self._drain_command_queue):
                bpy.app.timers.register(self._drain_command_queue, persistent=True)

            print(f"PlygonMCP: listening on {self.host}:{self.port}")
            return True
        except Exception as e:
            print(f"PlygonMCP: failed to start: {e}")
            self.stop()
            return False

    def stop(self):
        self.running = False

        try:
            if bpy.app.timers.is_registered(self._drain_command_queue):
                bpy.app.timers.unregister(self._drain_command_queue)
        except Exception:
            pass

        if self.socket:
            try:
                self.socket.close()
            except Exception:
                pass
            self.socket = None

        with self._clients_lock:
            clients = list(self._clients)
            self._clients.clear()
        for client in clients:
            try:
                client.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                client.close()
            except Exception:
                pass

        while True:
            try:
                self.command_queue.get_nowait()
            except queue.Empty:
                break

        if self.server_thread and self.server_thread.is_alive():
            self.server_thread.join(timeout=1.0)
        self.server_thread = None
        print("PlygonMCP: server stopped")

    def _server_loop(self):
        self.socket.settimeout(1.0)
        while self.running:
            try:
                try:
                    client, address = self.socket.accept()
                    print(f"PlygonMCP: client connected {address}")
                    t = threading.Thread(target=self._handle_client, args=(client,), daemon=True)
                    t.start()
                except socket.timeout:
                    continue
                except Exception as e:
                    print(f"PlygonMCP: accept error: {e}")
                    time.sleep(0.5)
            except Exception as e:
                print(f"PlygonMCP: server loop error: {e}")
                if not self.running:
                    break
                time.sleep(0.5)

    def _drain_command_queue(self):
        if not self.running:
            return None

        processed = 0
        while processed < MAX_COMMANDS_PER_TICK:
            try:
                command, client, client_closed, protocol_error = self.command_queue.get_nowait()
            except queue.Empty:
                break

            if client_closed.is_set():
                continue

            try:
                if protocol_error:
                    response = {"status": "error", "message": protocol_error}
                else:
                    response = self.execute_command(command)
                payload = _encode_message(response)
            except Exception as e:
                traceback.print_exc()
                payload = _encode_message({"status": "error", "message": str(e)})

            try:
                client.sendall(payload)
            except Exception:
                print("PlygonMCP: failed to send response (client gone)")
            processed += 1

        return 0.05

    def _handle_client(self, client):
        client.settimeout(1.0)
        with self._clients_lock:
            self._clients.add(client)
        buffer = b""
        client_closed = threading.Event()

        try:
            while self.running:
                try:
                    data = client.recv(8192)
                    if not data:
                        break
                    buffer += data
                    if len(buffer) > MAX_BUFFER_BYTES:
                        print(
                            f"PlygonMCP: closing client with more than "
                            f"{MAX_BUFFER_BYTES} buffered bytes"
                        )
                        break
                    commands, buffer = _extract_json_objects(buffer)
                    for command in commands:
                        if command is _MALFORMED_JSON:
                            item = (
                                None,
                                client,
                                client_closed,
                                "Malformed newline-delimited JSON command",
                            )
                        elif not isinstance(command, dict):
                            item = (
                                None,
                                client,
                                client_closed,
                                "Command must be a JSON object",
                            )
                        else:
                            print(f"PlygonMCP: queued {command.get('type')}")
                            item = (command, client, client_closed, None)
                        try:
                            self.command_queue.put_nowait(item)
                        except queue.Full:
                            print(
                                f"PlygonMCP: closing client because {MAX_PENDING_COMMANDS} "
                                "commands are already pending"
                            )
                            client_closed.set()
                            return
                except socket.timeout:
                    continue
                except Exception as e:
                    print(f"PlygonMCP: recv error: {e}")
                    break
        finally:
            client_closed.set()
            with self._clients_lock:
                self._clients.discard(client)
            try:
                client.close()
            except Exception:
                pass

    def execute_command(self, command):
        try:
            return self._execute_command_internal(command)
        except Exception as e:
            traceback.print_exc()
            return {"status": "error", "message": str(e)}

    def _execute_command_internal(self, command):
        cmd_type = command.get("type")
        params = command.get("params") or {}

        handlers = {
            "ping": lambda: {"pong": True},
            "get_addon_info": self.get_addon_info,
            "get_scene_info": self.get_scene_info,
            "get_object_info": self.get_object_info,
            "get_viewport_screenshot": self.get_viewport_screenshot,
            "execute_code": self.execute_code,
            "list_objects": self.list_objects,
            "create_primitive": self.create_primitive,
            "delete_object": self.delete_object,
            "set_object_transform": self.set_object_transform,
            "set_material": self.set_material,
            "select_objects": self.select_objects,
            "export_scene": self.export_scene,
        }

        handler = handlers.get(cmd_type)
        if not handler:
            return {"status": "error", "message": f"Unknown command type: {cmd_type}"}

        result = self._invoke_handler(handler, cmd_type, params)
        return {"status": "success", "result": result}

    def _invoke_handler(self, handler, cmd_type, params):
        if cmd_type == "ping":
            return handler()
        params = params or {}
        try:
            sig = inspect.signature(handler)
        except (TypeError, ValueError):
            return handler(**params)
        if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()):
            return handler(**params)
        allowed = {
            name
            for name, p in sig.parameters.items()
            if p.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
        }
        return handler(**{k: v for k, v in params.items() if k in allowed})

    def get_addon_info(self):
        return {
            "name": bl_info["name"],
            "addon_version": list(bl_info["version"]),
            "protocol_version": ADDON_PROTOCOL_VERSION,
            "blender_version": bpy.app.version_string,
            "capabilities": sorted(
                [
                    "ping",
                    "get_addon_info",
                    "get_scene_info",
                    "get_object_info",
                    "get_viewport_screenshot",
                    "execute_code",
                    "list_objects",
                    "create_primitive",
                    "delete_object",
                    "set_object_transform",
                    "set_material",
                    "select_objects",
                    "export_scene",
                ]
            ),
        }

    def get_scene_info(self, limit: int = 50):
        scene = bpy.context.scene
        objects = []
        for i, obj in enumerate(scene.objects):
            if i >= limit:
                break
            objects.append(
                {
                    "name": obj.name,
                    "type": obj.type,
                    "location": [round(float(c), 4) for c in obj.location],
                    "rotation_euler": [round(float(c), 4) for c in obj.rotation_euler],
                    "scale": [round(float(c), 4) for c in obj.scale],
                    "visible": bool(obj.visible_get()),
                    "parent": obj.parent.name if obj.parent else None,
                }
            )

        cameras = [o.name for o in scene.objects if o.type == "CAMERA"]
        lights = [o.name for o in scene.objects if o.type == "LIGHT"]
        materials = [m.name for m in bpy.data.materials]

        return {
            "name": scene.name,
            "frame_current": scene.frame_current,
            "frame_start": scene.frame_start,
            "frame_end": scene.frame_end,
            "unit_system": scene.unit_settings.system,
            "render_engine": scene.render.engine,
            "resolution": [scene.render.resolution_x, scene.render.resolution_y],
            "object_count": len(scene.objects),
            "objects": objects,
            "cameras": cameras,
            "lights": lights,
            "materials": materials[:100],
            "active_object": bpy.context.view_layer.objects.active.name
            if bpy.context.view_layer.objects.active
            else None,
            "selected": [o.name for o in bpy.context.selected_objects],
        }

    def list_objects(self, object_type: str = ""):
        objs = []
        for obj in bpy.context.scene.objects:
            if object_type and obj.type != object_type.upper():
                continue
            objs.append({"name": obj.name, "type": obj.type})
        return {"objects": objs, "count": len(objs)}

    def _aabb(self, obj):
        bbox_corners = [obj.matrix_world @ mathutils.Vector(corner) for corner in obj.bound_box]
        min_c = [min(c[i] for c in bbox_corners) for i in range(3)]
        max_c = [max(c[i] for c in bbox_corners) for i in range(3)]
        return {"min": min_c, "max": max_c}

    def get_object_info(self, name: str):
        obj = bpy.data.objects.get(name)
        if not obj:
            raise ValueError(f"Object not found: {name}")

        info = {
            "name": obj.name,
            "type": obj.type,
            "location": list(obj.location),
            "rotation_euler": list(obj.rotation_euler),
            "scale": list(obj.scale),
            "visible": bool(obj.visible_get()),
            "materials": [s.material.name for s in obj.material_slots if s.material],
            "modifiers": [m.name for m in obj.modifiers],
            "parent": obj.parent.name if obj.parent else None,
            "children": [c.name for c in obj.children],
        }

        if obj.type == "MESH" and obj.data:
            mesh = obj.data
            info["mesh"] = {
                "vertices": len(mesh.vertices),
                "edges": len(mesh.edges),
                "polygons": len(mesh.polygons),
            }
            info["world_bounding_box"] = self._aabb(obj)
        elif obj.type == "LIGHT" and obj.data:
            info["light"] = {
                "type": obj.data.type,
                "energy": float(obj.data.energy),
                "color": list(obj.data.color),
            }
        elif obj.type == "CAMERA" and obj.data:
            info["camera"] = {
                "lens": float(obj.data.lens),
                "type": obj.data.type,
            }

        return info

    def get_viewport_screenshot(self, max_size: int = 1000, filepath: str = "", format: str = "png"):
        max_size = int(max_size)
        if max_size < 2:
            raise ValueError("max_size must be at least 2 pixels")
        if not filepath:
            filepath = os.path.join(
                tempfile.gettempdir(),
                f"plygon_mcp_viewport_{os.getpid()}_{uuid.uuid4().hex}.png",
            )

        view3d_context = _find_view3d_context()
        if view3d_context is None:
            raise ValueError("No 3D viewport found. Keep a 3D Viewport visible.")
        area = view3d_context["area"]
        region = view3d_context["region"]
        space = area.spaces.active

        method = "offscreen"
        width = height = 0
        try:
            import gpu
            import numpy as np

            r3d = space.region_3d
            src_w, src_h = region.width, region.height
            if src_w < 1 or src_h < 1:
                raise ValueError("The 3D Viewport has no drawable pixel area")
            if max(src_w, src_h) > max_size:
                s = max_size / max(src_w, src_h)
                width, height = max(1, int(src_w * s)), max(1, int(src_h * s))
            else:
                width, height = src_w, src_h

            offscreen = gpu.types.GPUOffScreen(width, height)
            try:
                offscreen.draw_view3d(
                    view3d_context["scene"],
                    view3d_context["view_layer"],
                    space,
                    region,
                    r3d.view_matrix,
                    r3d.window_matrix,
                    do_color_management=True,
                )
                buf = offscreen.texture_color.read()
            finally:
                offscreen.free()

            buf.dimensions = width * height * 4
            pixels = np.asarray(buf, dtype=np.float32) / 255.0

            image = bpy.data.images.new("plygon_mcp_viewport", width, height, alpha=True)
            try:
                image.pixels.foreach_set(pixels.ravel())
                image.filepath_raw = filepath
                image.file_format = format.upper()
                image.save()
            finally:
                bpy.data.images.remove(image)
        except Exception as offscreen_err:
            print(f"PlygonMCP: offscreen capture failed ({offscreen_err}); using window grab")
            method = "window_grab"
            _run_operator(
                bpy.ops.screen.screenshot_area,
                view3d_context=view3d_context,
                filepath=filepath,
            )
            img = bpy.data.images.load(filepath)
            try:
                width, height = img.size
                if width < 1 or height < 1:
                    raise ValueError("Blender captured an empty screenshot")
                if max(width, height) > max_size:
                    s = max_size / max(width, height)
                    width, height = max(1, int(width * s)), max(1, int(height * s))
                    img.scale(width, height)
                    img.file_format = format.upper()
                    img.save()
            finally:
                bpy.data.images.remove(img)

        return {
            "success": True,
            "width": width,
            "height": height,
            "filepath": filepath,
            "method": method,
        }

    def execute_code(self, code: str):
        namespace = {"bpy": bpy, "mathutils": mathutils}
        capture = io.StringIO()
        with redirect_stdout(capture):
            exec(code, namespace)
        return {"executed": True, "result": capture.getvalue()}

    def create_primitive(
        self,
        shape: str = "CUBE",
        name: str = "",
        location=(0.0, 0.0, 0.0),
        rotation=(0.0, 0.0, 0.0),
        scale=(1.0, 1.0, 1.0),
        size: float = 2.0,
    ):
        shape = shape.upper()
        ops = {
            "CUBE": bpy.ops.mesh.primitive_cube_add,
            "SPHERE": bpy.ops.mesh.primitive_uv_sphere_add,
            "CYLINDER": bpy.ops.mesh.primitive_cylinder_add,
            "CONE": bpy.ops.mesh.primitive_cone_add,
            "TORUS": bpy.ops.mesh.primitive_torus_add,
            "PLANE": bpy.ops.mesh.primitive_plane_add,
            "MONKEY": bpy.ops.mesh.primitive_monkey_add,
            "ICO_SPHERE": bpy.ops.mesh.primitive_ico_sphere_add,
        }
        op = ops.get(shape)
        if not op:
            raise ValueError(f"Unknown shape: {shape}. Use one of {sorted(ops)}")

        kwargs = {
            "location": tuple(location),
            "rotation": tuple(rotation),
            "scale": tuple(scale),
        }
        # Blender ops use different size/radius parameter names per primitive.
        if shape in {"CUBE", "PLANE", "MONKEY"}:
            kwargs["size"] = size
        elif shape in {"SPHERE", "ICO_SPHERE"}:
            kwargs["radius"] = size / 2.0
        elif shape == "CYLINDER":
            kwargs["radius"] = size / 2.0
            kwargs["depth"] = size
        elif shape == "CONE":
            kwargs["radius1"] = size / 2.0
            kwargs["depth"] = size
        elif shape == "TORUS":
            kwargs["major_radius"] = size / 2.0
            kwargs["minor_radius"] = size / 8.0

        view3d_context = _find_view3d_context()
        _ensure_object_mode(view3d_context)
        _run_operator(op, view3d_context=view3d_context, **kwargs)
        view_layer = view3d_context.get("view_layer") if view3d_context else bpy.context.view_layer
        obj = view_layer.objects.active
        if obj is None:
            raise RuntimeError(f"Blender created no active object for {shape}")
        if name:
            obj.name = name
            if obj.data:
                obj.data.name = name
        return {"name": obj.name, "type": obj.type, "shape": shape}

    def delete_object(self, name: str):
        obj = bpy.data.objects.get(name)
        if not obj:
            raise ValueError(f"Object not found: {name}")
        bpy.data.objects.remove(obj, do_unlink=True)
        return {"deleted": name}

    def set_object_transform(
        self,
        name: str,
        location=None,
        rotation=None,
        scale=None,
    ):
        obj = bpy.data.objects.get(name)
        if not obj:
            raise ValueError(f"Object not found: {name}")
        if location is not None:
            obj.location = mathutils.Vector(location)
        if rotation is not None:
            obj.rotation_euler = mathutils.Euler(rotation)
        if scale is not None:
            obj.scale = mathutils.Vector(scale)
        return {
            "name": obj.name,
            "location": list(obj.location),
            "rotation_euler": list(obj.rotation_euler),
            "scale": list(obj.scale),
        }

    def set_material(
        self,
        object_name: str,
        material_name: str = "",
        color=(0.8, 0.8, 0.8, 1.0),
        metallic: float = 0.0,
        roughness: float = 0.5,
        create_new: bool = True,
    ):
        obj = bpy.data.objects.get(object_name)
        if not obj:
            raise ValueError(f"Object not found: {object_name}")

        mat_name = material_name or f"{object_name}_Material"
        if create_new:
            mat = bpy.data.materials.new(name=mat_name)
        else:
            mat = bpy.data.materials.get(mat_name)
            if mat is None:
                raise ValueError(
                    f"Material not found: {mat_name}. Set create_new=true to create it."
                )
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        bsdf = nodes.get("Principled BSDF")
        if bsdf:
            bsdf.inputs["Base Color"].default_value = tuple(color)
            if "Metallic" in bsdf.inputs:
                bsdf.inputs["Metallic"].default_value = float(metallic)
            if "Roughness" in bsdf.inputs:
                bsdf.inputs["Roughness"].default_value = float(roughness)

        if obj.data and hasattr(obj.data, "materials"):
            if obj.data.materials:
                obj.data.materials[0] = mat
            else:
                obj.data.materials.append(mat)

        return {
            "object": object_name,
            "material": mat.name,
            "color": list(color),
            "metallic": metallic,
            "roughness": roughness,
        }

    def select_objects(self, names=None, mode: str = "REPLACE"):
        names = names or []
        mode = mode.upper()
        if mode not in {"REPLACE", "ADD"}:
            raise ValueError("mode must be REPLACE or ADD")
        view3d_context = _find_view3d_context()
        _ensure_object_mode(view3d_context)
        if mode == "REPLACE":
            _run_operator(
                bpy.ops.object.select_all,
                view3d_context=view3d_context,
                action="DESELECT",
            )

        selected = []
        not_found = []
        view_layer = view3d_context.get("view_layer") if view3d_context else bpy.context.view_layer
        for name in names:
            obj = bpy.data.objects.get(name)
            if not obj:
                not_found.append(name)
                continue
            obj.select_set(True)
            selected.append(name)
            view_layer.objects.active = obj

        return {
            "selected": selected,
            "not_found": not_found,
            "active": view_layer.objects.active.name
            if view_layer.objects.active
            else None,
        }

    def export_scene(self, filepath: str, format: str = "GLB"):
        format = format.upper()
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
        view3d_context = _find_view3d_context()

        if format in {"GLB", "GLTF"}:
            export_format = "GLB" if format == "GLB" else "GLTF_SEPARATE"
            _run_operator(
                bpy.ops.export_scene.gltf,
                view3d_context=view3d_context,
                filepath=filepath,
                export_format=export_format,
            )
        elif format == "FBX":
            _run_operator(
                bpy.ops.export_scene.fbx,
                view3d_context=view3d_context,
                filepath=filepath,
            )
        elif format == "OBJ":
            if hasattr(bpy.ops.wm, "obj_export"):
                _run_operator(
                    bpy.ops.wm.obj_export,
                    view3d_context=view3d_context,
                    filepath=filepath,
                )
            else:
                _run_operator(
                    bpy.ops.export_scene.obj,
                    view3d_context=view3d_context,
                    filepath=filepath,
                )
        elif format == "BLEND":
            _run_operator(
                bpy.ops.wm.save_as_mainfile,
                view3d_context=view3d_context,
                filepath=filepath,
            )
        else:
            raise ValueError(f"Unsupported export format: {format}")

        return {"filepath": filepath, "format": format, "exists": os.path.exists(filepath)}


# --- UI / operators ---------------------------------------------------------

class PLYGONMCP_OT_StartServer(bpy.types.Operator):
    bl_idname = "plygonmcp.start_server"
    bl_label = "Start MCP Server"
    bl_description = "Start the local TCP server so Cursor can connect"

    def execute(self, context):
        global _server
        scene = context.scene
        if _server and _server.running:
            scene.plygonmcp_server_running = True
            self.report({"INFO"}, "MCP server already running")
            return {"FINISHED"}

        _server = BlenderMCPServer(host="127.0.0.1", port=scene.plygonmcp_port)
        if not _server.start():
            _server = None
            scene.plygonmcp_server_running = False
            self.report(
                {"ERROR"},
                f"Could not start PlygonMCP on port {scene.plygonmcp_port}. "
                "Check the system console; the port may already be in use.",
            )
            return {"CANCELLED"}
        scene.plygonmcp_server_running = True
        self.report({"INFO"}, f"PlygonMCP listening on port {scene.plygonmcp_port}")
        return {"FINISHED"}


class PLYGONMCP_OT_StopServer(bpy.types.Operator):
    bl_idname = "plygonmcp.stop_server"
    bl_label = "Stop MCP Server"

    def execute(self, context):
        global _server
        if _server:
            _server.stop()
            _server = None
        context.scene.plygonmcp_server_running = False
        self.report({"INFO"}, "PlygonMCP stopped")
        return {"FINISHED"}


class PLYGONMCP_PT_Panel(bpy.types.Panel):
    bl_label = "Plygon Blender MCP"
    bl_idname = "PLYGONMCP_PT_Panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "PlygonMCP"

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        layout.label(text="Local Cursor bridge", icon="LINKED")
        running = bool(_server and _server.running)
        port_row = layout.row()
        port_row.enabled = not running
        port_row.prop(scene, "plygonmcp_port")

        if not running:
            layout.operator("plygonmcp.start_server", text="Start MCP Server", icon="PLAY")
        else:
            layout.operator("plygonmcp.stop_server", text="Stop MCP Server", icon="PAUSE")
            layout.label(text=f"Online · port {_server.port}", icon="CHECKMARK")

        box = layout.box()
        box.label(text="Setup")
        col = box.column(align=True)
        col.label(text="1. This panel must say Online")
        col.label(text="2. Cursor green is not enough")
        col.label(text="3. Ping from a local Agent chat")


classes = (
    PLYGONMCP_OT_StartServer,
    PLYGONMCP_OT_StopServer,
    PLYGONMCP_PT_Panel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.plygonmcp_port = IntProperty(
        name="Port",
        description="TCP port for the MCP bridge",
        default=DEFAULT_PORT,
        min=1024,
        max=65535,
    )
    bpy.types.Scene.plygonmcp_server_running = BoolProperty(
        default=False,
        options={"SKIP_SAVE"},
    )
    bpy.types.Scene.plygonmcp_host = StringProperty(default="127.0.0.1")


def unregister():
    global _server
    if _server:
        _server.stop()
        _server = None

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

    for attr in ("plygonmcp_port", "plygonmcp_server_running", "plygonmcp_host"):
        if hasattr(bpy.types.Scene, attr):
            delattr(bpy.types.Scene, attr)


if __name__ == "__main__":
    register()
