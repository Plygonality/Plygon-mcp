# SPDX-License-Identifier: MIT
"""Plygon Houdini MCP listener — TCP command bridge for Cursor / MCP clients.

Install via scripts/install_package.py, then in Houdini use the
PlygonMCP shelf tab → Start MCP Server.
"""

from __future__ import annotations

import io
import json
import os
import queue
import socket
import tempfile
import threading
import time
import traceback
from contextlib import redirect_stdout

try:
    import hou
    import hdefereval
except ImportError:
    raise ImportError(
        "plygon_houdini_mcp.listener must run inside Houdini (hou module required)."
    )

ADDON_PROTOCOL_VERSION = 1
DEFAULT_HOST = "localhost"
DEFAULT_PORT = 9877

_server = None
_event_loop_callback_registered = False


class HoudiniMCPServer:
    """Accept JSON commands over TCP and run them on Houdini's main thread."""

    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT):
        self.host = host
        self.port = port
        self.running = False
        self.socket = None
        self.server_thread = None
        self.command_queue: queue.Queue = queue.Queue()
        self._clients = set()
        self._clients_lock = threading.Lock()

    def start(self):
        global _event_loop_callback_registered

        if hou.applicationVersion()[0] < 19:
            print("PlygonMCP: Houdini 19.5+ recommended")

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

            if not _event_loop_callback_registered:
                hou.ui.addEventLoopCallback(self._drain_command_queue)
                _event_loop_callback_registered = True

            print(f"PlygonMCP: listening on {self.host}:{self.port}")
        except Exception as e:
            print(f"PlygonMCP: failed to start: {e}")
            self.stop()

    def stop(self):
        global _event_loop_callback_registered

        self.running = False

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
        _event_loop_callback_registered = False
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
            return False

        while True:
            try:
                command, client = self.command_queue.get_nowait()
            except queue.Empty:
                break

            try:
                response = hdefereval.executeInMainThreadWithResult(
                    self.execute_command, (command,), {}
                )
                payload = json.dumps(response, default=str)
            except Exception as e:
                traceback.print_exc()
                payload = json.dumps({"status": "error", "message": str(e)})

            try:
                client.sendall(payload.encode("utf-8"))
            except Exception:
                print("PlygonMCP: failed to send response (client gone)")

        return True

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
            "list_nodes": self.list_nodes,
            "get_node_info": self.get_node_info,
            "create_node": self.create_node,
            "delete_node": self.delete_node,
            "set_node_parm": self.set_node_parm,
            "connect_nodes": self.connect_nodes,
            "layout_nodes": self.layout_nodes,
            "cook_node": self.cook_node,
            "execute_code": self.execute_code,
            "execute_hscript": self.execute_hscript,
            "get_viewport_screenshot": self.get_viewport_screenshot,
            "save_hip": self.save_hip,
            "create_primitive": self.create_primitive,
        }

        handler = handlers.get(cmd_type)
        if not handler:
            return {"status": "error", "message": f"Unknown command type: {cmd_type}"}

        result = handler(**params) if cmd_type != "ping" else handlers["ping"]()
        return {"status": "success", "result": result}

    def get_addon_info(self):
        return {
            "name": "Plygon Houdini MCP",
            "addon_version": [1, 0, 0],
            "protocol_version": ADDON_PROTOCOL_VERSION,
            "houdini_version": hou.applicationVersionString(),
            "hip_file": hou.hipFile.path() or "(unsaved)",
            "capabilities": sorted(
                [
                    "ping",
                    "get_addon_info",
                    "get_scene_info",
                    "list_nodes",
                    "get_node_info",
                    "create_node",
                    "delete_node",
                    "set_node_parm",
                    "connect_nodes",
                    "layout_nodes",
                    "cook_node",
                    "execute_code",
                    "execute_hscript",
                    "get_viewport_screenshot",
                    "save_hip",
                    "create_primitive",
                ]
            ),
        }

    def get_scene_info(self, limit: int = 50):
        hip_path = hou.hipFile.path()
        obj = hou.node("/obj")
        top_level = []
        if obj:
            for i, child in enumerate(obj.children()):
                if i >= limit:
                    break
                top_level.append(
                    {
                        "path": child.path(),
                        "name": child.name(),
                        "type": child.type().name(),
                        "color": list(child.color()),
                    }
                )

        frame_range = {
            "start": hou.playbar.frameRange()[0],
            "end": hou.playbar.frameRange()[1],
            "current": hou.frame(),
        }

        selected = [n.path() for n in hou.selectedNodes()]

        return {
            "hip_file": hip_path or "(unsaved)",
            "houdini_version": hou.applicationVersionString(),
            "frame_range": frame_range,
            "fps": hou.fps(),
            "obj_count": len(obj.children()) if obj else 0,
            "top_level_objects": top_level,
            "selected_nodes": selected,
            "current_node": hou.pwd().path() if hou.pwd() else None,
        }

    def list_nodes(self, parent_path: str = "/obj", node_type: str = "", recursive: bool = False):
        parent = hou.node(parent_path)
        if not parent:
            raise ValueError(f"Node not found: {parent_path}")

        nodes = []

        def collect(node):
            for child in node.children():
                if node_type and child.type().name() != node_type:
                    if recursive:
                        collect(child)
                    continue
                nodes.append(
                    {
                        "path": child.path(),
                        "name": child.name(),
                        "type": child.type().name(),
                        "inputs": [i.path() for i in child.inputs()],
                    }
                )
                if recursive:
                    collect(child)

        collect(parent)
        return {"parent": parent_path, "nodes": nodes, "count": len(nodes)}

    def get_node_info(self, node_path: str):
        node = hou.node(node_path)
        if not node:
            raise ValueError(f"Node not found: {node_path}")

        parms = []
        for parm in node.parms():
            try:
                val = parm.eval()
                if hasattr(val, "__iter__") and not isinstance(val, (str, bytes)):
                    val = list(val)
                parms.append({"name": parm.name(), "value": val, "label": parm.description()})
            except Exception:
                parms.append({"name": parm.name(), "value": None, "label": parm.description()})

        info = {
            "path": node.path(),
            "name": node.name(),
            "type": node.type().name(),
            "category": node.type().category().name(),
            "color": list(node.color()),
            "inputs": [{"index": i, "path": inp.path()} for i, inp in enumerate(node.inputs()) if inp],
            "outputs": [out.path() for out in node.outputs()],
            "display": node.isDisplayFlagSet() if hasattr(node, "isDisplayFlagSet") else None,
            "render": node.isRenderFlagSet() if hasattr(node, "isRenderFlagSet") else None,
            "parms": parms[:100],
            "parm_count": len(node.parms()),
            "children": [c.path() for c in node.children()],
        }

        if node.type().category() == hou.sopNodeTypeCategory():
            try:
                geo = node.geometry()
                if geo:
                    info["geometry"] = {
                        "points": len(geo.points()),
                        "prims": len(geo.prims()),
                        "vertices": len(geo.iterVertices()) if hasattr(geo, "iterVertices") else None,
                    }
            except hou.GeometryPermissionError:
                info["geometry"] = {"error": "Geometry not accessible (may need cook)"}

        return info

    def create_node(self, parent_path: str, node_type: str, name: str = ""):
        parent = hou.node(parent_path)
        if not parent:
            raise ValueError(f"Parent node not found: {parent_path}")

        node = parent.createNode(node_type, node_name=name or node_type)
        return {"path": node.path(), "name": node.name(), "type": node.type().name()}

    def delete_node(self, node_path: str):
        node = hou.node(node_path)
        if not node:
            raise ValueError(f"Node not found: {node_path}")
        name = node.path()
        node.destroy()
        return {"deleted": name}

    def set_node_parm(self, node_path: str, parm_name: str, value):
        node = hou.node(node_path)
        if not node:
            raise ValueError(f"Node not found: {node_path}")
        parm = node.parm(parm_name)
        if not parm:
            raise ValueError(f"Parameter not found: {parm_name} on {node_path}")
        parm.set(value)
        return {"node": node_path, "parm": parm_name, "value": parm.eval()}

    def connect_nodes(self, output_node_path: str, input_node_path: str, input_index: int = 0):
        out_node = hou.node(output_node_path)
        in_node = hou.node(input_node_path)
        if not out_node:
            raise ValueError(f"Output node not found: {output_node_path}")
        if not in_node:
            raise ValueError(f"Input node not found: {input_node_path}")
        in_node.setInput(input_index, out_node)
        return {
            "output": output_node_path,
            "input": input_node_path,
            "input_index": input_index,
        }

    def layout_nodes(self, parent_path: str):
        parent = hou.node(parent_path)
        if not parent:
            raise ValueError(f"Node not found: {parent_path}")
        parent.layoutChildren()
        return {"layout": parent_path}

    def cook_node(self, node_path: str, block: bool = True):
        node = hou.node(node_path)
        if not node:
            raise ValueError(f"Node not found: {node_path}")
        node.cook(force=True, block=block)
        return {"cooked": node_path}

    def execute_code(self, code: str):
        namespace = {"hou": hou}
        capture = io.StringIO()
        with redirect_stdout(capture):
            exec(code, namespace)
        return {"executed": True, "result": capture.getvalue()}

    def execute_hscript(self, command: str):
        result = hou.hscript(command)
        return {"executed": True, "result": result}

    def get_viewport_screenshot(self, max_size: int = 1000, filepath: str = ""):
        if not filepath:
            filepath = os.path.join(
                tempfile.gettempdir(), f"plygon_mcp_viewport_{os.getpid()}.png"
            )

        desktop = hou.ui.curDesktop()
        scene_viewer = desktop.paneTabOfType(hou.paneTabType.SceneViewer)
        if not scene_viewer:
            return {"error": "No Scene Viewer pane found. Open a Scene Viewer in Houdini."}

        viewport = scene_viewer.curViewport()
        settings = viewport.settings()

        src_w = settings.screenWidth()
        src_h = settings.screenHeight()
        if max(src_w, src_h) > max_size:
            scale = max_size / max(src_w, src_h)
            width = max(1, int(src_w * scale))
            height = max(1, int(src_h * scale))
        else:
            width, height = src_w, src_h

        viewport.saveScreenshot(filepath, width, height)
        return {
            "success": True,
            "width": width,
            "height": height,
            "filepath": filepath,
        }

    def save_hip(self, filepath: str = ""):
        path = filepath or hou.hipFile.path()
        if not path:
            raise ValueError("No filepath provided and hip is unsaved")
        hou.hipFile.save(path, save_to_recent_files=True)
        return {"saved": path}

    def create_primitive(
        self,
        shape: str = "box",
        name: str = "",
        parent_path: str = "/obj",
        size: float = 1.0,
        location=(0.0, 0.0, 0.0),
    ):
        shape = shape.lower()
        obj = hou.node("/obj")
        if not obj:
            raise RuntimeError("/obj context not found")

        geo_name = name or f"{shape}_geo"
        geo = obj.createNode("geo", node_name=geo_name)

        sop_map = {
            "box": "box",
            "sphere": "sphere",
            "grid": "grid",
            "tube": "tube",
            "torus": "torus",
            "circle": "circle",
            "line": "line",
        }
        sop_type = sop_map.get(shape)
        if not sop_type:
            raise ValueError(f"Unknown shape: {shape}. Use one of {sorted(sop_map)}")

        sop = geo.createNode(sop_type, node_name=shape)
        if shape == "box" and sop.parm("size"):
            sop.parm("size").set(size)
        elif shape == "sphere" and sop.parm("radx"):
            sop.parm("radx").set(size / 2.0)
            sop.parm("rady").set(size / 2.0)
            sop.parm("radz").set(size / 2.0)
        elif shape == "grid" and sop.parm("sizex"):
            sop.parm("sizex").set(size)
            sop.parm("sizey").set(size)

        sop.setDisplayFlag(True)
        sop.setRenderFlag(True)
        geo.layoutChildren()

        if any(location):
            geo.parmTuple("t").set(location)

        return {
            "geo_path": geo.path(),
            "sop_path": sop.path(),
            "shape": shape,
            "location": list(location),
        }


def start_server(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT):
    """Start the MCP listener (called from shelf tool or Python Shell)."""
    global _server
    if _server and _server.running:
        print("PlygonMCP: server already running")
        return _server
    _server = HoudiniMCPServer(host=host, port=port)
    _server.start()
    return _server


def stop_server():
    """Stop the MCP listener."""
    global _server
    if _server:
        _server.stop()
        _server = None
    else:
        print("PlygonMCP: server not running")


def server_status():
    """Return whether the listener is running."""
    return {"running": bool(_server and _server.running), "port": DEFAULT_PORT if _server else None}
