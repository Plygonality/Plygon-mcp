# SPDX-License-Identifier: MIT
"""Plygon Blender MCP addon — TCP command bridge for Cursor / MCP clients.

Install via Edit → Preferences → Add-ons → Install… → select this file,
then enable "Interface: Plygon Blender MCP".

In the 3D Viewport press N → PlygonMCP tab → Start MCP Server.
"""

from __future__ import annotations

import bpy
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
from contextlib import redirect_stdout
from bpy.props import IntProperty, BoolProperty, StringProperty

bl_info = {
    "name": "Plygon Blender MCP",
    "author": "Plygon",
    "version": (1, 0, 0),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar > PlygonMCP",
    "description": "Local MCP bridge so Cursor agents can drive Blender via bpy",
    "category": "Interface",
}

ADDON_PROTOCOL_VERSION = 1
DEFAULT_PORT = 9876

_server = None


class BlenderMCPServer:
    """Accept JSON commands over TCP and run them on Blender's main thread."""

    def __init__(self, host: str = "localhost", port: int = DEFAULT_PORT):
        self.host = host
        self.port = port
        self.running = False
        self.socket = None
        self.server_thread = None
        self.command_queue: queue.Queue = queue.Queue()
        self._clients = set()
        self._clients_lock = threading.Lock()

    def start(self):
        if bpy.app.background:
            print(
                "PlygonMCP: cannot start in background mode (blender -b). "
                "Run Blender with a GUI, or: xvfb-run -a blender"
            )
            return

        if self.running:
            print("PlygonMCP: server already running")
            return

        self.running = True
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.bind((self.host, self.port))
            self.socket.listen(5)

            self.server_thread = threading.Thread(target=self._server_loop, daemon=True)
            self.server_thread.start()

            if not bpy.app.timers.is_registered(self._drain_command_queue):
                bpy.app.timers.register(self._drain_command_queue, persistent=True)

            print(f"PlygonMCP: listening on {self.host}:{self.port}")
        except Exception as e:
            print(f"PlygonMCP: failed to start: {e}")
            self.stop()

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

        while True:
            try:
                command, client = self.command_queue.get_nowait()
            except queue.Empty:
                break

            try:
                response = self.execute_command(command)
                payload = json.dumps(response)
            except Exception as e:
                traceback.print_exc()
                payload = json.dumps({"status": "error", "message": str(e)})

            try:
                client.sendall(payload.encode("utf-8"))
            except Exception:
                print("PlygonMCP: failed to send response (client gone)")

        return 0.05

    def _handle_client(self, client):
        client.settimeout(1.0)
        with self._clients_lock:
            self._clients.add(client)
        buffer = b""

        try:
            while self.running:
                try:
                    data = client.recv(8192)
                    if not data:
                        break
                    buffer += data
                    try:
                        command = json.loads(buffer.decode("utf-8"))
                        buffer = b""
                        print(f"PlygonMCP: queued {command.get('type')}")
                        self.command_queue.put((command, client))
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        pass
                except socket.timeout:
                    continue
                except Exception as e:
                    print(f"PlygonMCP: recv error: {e}")
                    break
        finally:
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

        result = handler(**params) if cmd_type != "ping" else handlers["ping"]()
        return {"status": "success", "result": result}

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
        if not filepath:
            filepath = os.path.join(
                tempfile.gettempdir(), f"plygon_mcp_viewport_{os.getpid()}.png"
            )

        area = region = space = None
        for a in bpy.context.screen.areas:
            if a.type == "VIEW_3D":
                area = a
                space = a.spaces.active
                region = next((r for r in a.regions if r.type == "WINDOW"), None)
                break

        if not area or region is None or space is None:
            return {"error": "No 3D viewport found"}

        method = "offscreen"
        width = height = 0
        try:
            import gpu
            import numpy as np

            r3d = space.region_3d
            src_w, src_h = region.width, region.height
            if max(src_w, src_h) > max_size:
                s = max_size / max(src_w, src_h)
                width, height = max(1, int(src_w * s)), max(1, int(src_h * s))
            else:
                width, height = src_w, src_h

            offscreen = gpu.types.GPUOffScreen(width, height)
            try:
                offscreen.draw_view3d(
                    bpy.context.scene,
                    bpy.context.view_layer,
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
            image.pixels.foreach_set(pixels.ravel())
            image.filepath_raw = filepath
            image.file_format = format.upper()
            image.save()
            bpy.data.images.remove(image)
        except Exception as offscreen_err:
            print(f"PlygonMCP: offscreen capture failed ({offscreen_err}); using window grab")
            method = "window_grab"
            with bpy.context.temp_override(area=area):
                bpy.ops.screen.screenshot_area(filepath=filepath)
            img = bpy.data.images.load(filepath)
            width, height = img.size
            if max(width, height) > max_size:
                s = max_size / max(width, height)
                width, height = int(width * s), int(height * s)
                img.scale(width, height)
                img.file_format = format.upper()
                img.save()
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

        op(**kwargs)
        obj = bpy.context.active_object
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
        mat = bpy.data.materials.get(mat_name) if not create_new else None
        if mat is None:
            mat = bpy.data.materials.new(name=mat_name)
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
        if mode == "REPLACE":
            bpy.ops.object.select_all(action="DESELECT")

        selected = []
        for name in names:
            obj = bpy.data.objects.get(name)
            if not obj:
                continue
            obj.select_set(True)
            selected.append(name)
            bpy.context.view_layer.objects.active = obj

        return {"selected": selected, "active": bpy.context.view_layer.objects.active.name if bpy.context.view_layer.objects.active else None}

    def export_scene(self, filepath: str, format: str = "GLB"):
        format = format.upper()
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)

        if format in {"GLB", "GLTF"}:
            export_format = "GLB" if format == "GLB" else "GLTF_SEPARATE"
            bpy.ops.export_scene.gltf(filepath=filepath, export_format=export_format)
        elif format == "FBX":
            bpy.ops.export_scene.fbx(filepath=filepath)
        elif format == "OBJ":
            if hasattr(bpy.ops.wm, "obj_export"):
                bpy.ops.wm.obj_export(filepath=filepath)
            else:
                bpy.ops.export_scene.obj(filepath=filepath)
        elif format == "BLEND":
            bpy.ops.wm.save_as_mainfile(filepath=filepath)
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
            self.report({"INFO"}, "MCP server already running")
            return {"FINISHED"}

        _server = BlenderMCPServer(host="localhost", port=scene.plygonmcp_port)
        _server.start()
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
        layout.prop(scene, "plygonmcp_port")

        if not scene.plygonmcp_server_running:
            layout.operator("plygonmcp.start_server", text="Start MCP Server", icon="PLAY")
        else:
            layout.operator("plygonmcp.stop_server", text="Stop MCP Server", icon="PAUSE")
            layout.label(text=f"Online · port {scene.plygonmcp_port}", icon="CHECKMARK")

        box = layout.box()
        box.label(text="Setup")
        col = box.column(align=True)
        col.label(text="1. Start server here")
        col.label(text="2. Enable MCP in Cursor")
        col.label(text="3. Ask the agent to build")


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
    bpy.types.Scene.plygonmcp_server_running = BoolProperty(default=False)
    bpy.types.Scene.plygonmcp_host = StringProperty(default="localhost")


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
