# SPDX-License-Identifier: MIT
"""Plygon Unreal MCP listener. TCP command bridge for Cursor / MCP clients.

Runs inside the Unreal Editor. Accept runs on a background thread. Every
command runs on the game thread from a Slate post-tick callback.
"""

from __future__ import annotations

import errno
import inspect
import io
import json
import math
import os
import queue
import re
import socket
import sys
import tempfile
import threading
import time
import traceback
import uuid
from contextlib import redirect_stdout

try:
    import unreal
except ImportError:
    raise ImportError(
        "plygon_unreal_mcp.listener must run inside the Unreal Editor (unreal module required)."
    )

__version__ = "0.2.2"
ADDON_PROTOCOL_VERSION = 1
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9879
MAX_BUFFER_BYTES = 4 * 1024 * 1024
MAX_EXECUTE_STDOUT_BYTES = 256 * 1024
MAX_PENDING_COMMANDS = 128
MAX_COMMANDS_PER_TICK = 1
SCREENSHOT_TIMEOUT_SECONDS = 20.0
MINIMUM_ENGINE = (5, 4)
# Engine content path used when a static mesh spawn does not name a mesh.
# Not confirmed against an Epic documentation page. Pass mesh_path to override it.
DEFAULT_CUBE_MESH = "/Engine/BasicShapes/Cube"

_server = None
_MALFORMED_JSON = object()
_DEFERRED = object()
_HTTP_REQUEST_LINE = re.compile(
    rb"^\s*(GET|POST|PUT|DELETE|HEAD|OPTIONS|PATCH|CONNECT|TRACE) \S+ HTTP/"
)
_HTTP_METHODS = (
    b"GET",
    b"POST",
    b"PUT",
    b"DELETE",
    b"HEAD",
    b"OPTIONS",
    b"PATCH",
    b"CONNECT",
    b"TRACE",
)
# An undecided prefix longer than this is closed. A request line is one short
# line; a JSON command stops looking like a method on the first byte.
_HTTP_GUARD_BYTES = 8192
_HTTP_WS = b" \t\n\r\f\v"

_ACTOR_KINDS = {
    "static_mesh": "StaticMeshActor",
    "cube": "StaticMeshActor",
    "point_light": "PointLight",
    "directional_light": "DirectionalLight",
    "spot_light": "SpotLight",
    "rect_light": "RectLight",
    "camera": "CameraActor",
    "cine_camera": "CineCameraActor",
}

_PCG_SETTERS = {
    "bool": "set_bool_parameter",
    "int": "set_int32_parameter",
    "int32": "set_int32_parameter",
    "int64": "set_int64_parameter",
    "float": "set_float_parameter",
    "double": "set_double_parameter",
    "string": "set_string_parameter",
    "name": "set_name_parameter",
    "vector": "set_vector_parameter",
}


def _has_complete_json_frame(buffer: bytes) -> bool:
    """True when *buffer* already holds one protocol JSON value."""
    try:
        text = buffer.decode("utf-8")
    except UnicodeDecodeError:
        return False
    start = 0
    length = len(text)
    while start < length and text[start].isspace():
        start += 1
    if start >= length:
        return False
    try:
        _obj, end = json.JSONDecoder().raw_decode(text, start)
    except json.JSONDecodeError:
        return False
    return end > start


def _http_prefix_can_match(buffer: bytes) -> bool:
    """True if later bytes could still make _HTTP_REQUEST_LINE match."""
    index = 0
    length = len(buffer)
    while index < length and buffer[index] in _HTTP_WS:
        index += 1
    if index == length:
        return True

    method_start = index
    while index < length and buffer[index] not in _HTTP_WS:
        index += 1
    method = buffer[method_start:index]
    if index == length:
        return any(name.startswith(method) for name in _HTTP_METHODS)
    if method not in _HTTP_METHODS or buffer[index] != ord(" "):
        return False

    index += 1
    if index == length:
        return True
    if buffer[index] in _HTTP_WS:
        return False
    while index < length and buffer[index] not in _HTTP_WS:
        index += 1
    if index == length:
        return True
    if buffer[index] != ord(" "):
        return False

    index += 1
    tail = buffer[index:]
    return b"HTTP/".startswith(tail) or tail.startswith(b"HTTP/")


def _http_request_decision(buffer: bytes):
    """Return True to reject HTTP, False to parse, or None to keep reading.

    The first recv() may be only a prefix such as b"GE". Hold those bytes,
    under the guard cap and the socket's existing timeout, until the prefix
    is long enough to decide. That is the longest method token plus a space
    (and the rest of the line, while it still looks like a request line),
    the newline that ends the line, or one complete JSON frame.
    """
    if _HTTP_REQUEST_LINE.match(buffer):
        return True
    if _has_complete_json_frame(buffer):
        return False
    if not _http_prefix_can_match(buffer):
        return False
    if len(buffer) >= _HTTP_GUARD_BYTES:
        return True
    return None


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
            # Messages are newline terminated. Recover after a malformed
            # frame instead of letting it block every later request.
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


# Socket option helpers match blender_mcp_addon.py. Each DCC ships its own
# copy. The port-in-use sentence below is Unreal-specific.
def _configure_listener_socket(sock: socket.socket) -> None:
    """Apply listen-socket options for an exclusive DCC listener.

    POSIX SO_REUSEADDR lets a restarted listener take a port that is still in
    TIME_WAIT. Two active listeners still cannot share that port.
    Windows SO_REUSEADDR allows a second process to bind the same port, so
    use SO_EXCLUSIVEADDRUSE and leave SO_REUSEADDR unset.
    """
    if sys.platform == "win32":
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        return
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)


def _address_in_use(exc: BaseException) -> bool:
    """True for POSIX EADDRINUSE and Windows WSAEADDRINUSE (10048)."""
    if not isinstance(exc, OSError):
        return False
    wsa_addr_in_use = 10048
    if exc.errno in (errno.EADDRINUSE, wsa_addr_in_use):
        return True
    return getattr(exc, "winerror", None) in (errno.EADDRINUSE, wsa_addr_in_use)


def _port_in_use_message(host: str, port: int) -> str:
    return (
        f"Port {port} is already in use on {host}. "
        "Stop the other listener, or choose a free port and set UNREAL_PORT to the same value."
    )


def _report_start_failure(server, exc: BaseException) -> None:
    if _address_in_use(exc):
        server.start_failure = _port_in_use_message(server.host, server.port)
        print(f"PlygonMCP: {server.start_failure}")
        return
    print(f"PlygonMCP: failed to start: {exc}")


def _truncate_stdout(text: str, limit: int = MAX_EXECUTE_STDOUT_BYTES) -> str:
    """Keep captured stdout inside the TCP frame limit.

    ``limit`` is a UTF-8 byte budget. When the capture is longer, the result
    ends with a newline and ``…[truncated N bytes]``, where N is how many
    bytes were removed.
    """
    raw = text.encode("utf-8")
    if len(raw) <= limit:
        return text
    kept = raw[:limit].decode("utf-8", errors="ignore")
    dropped = len(raw) - len(kept.encode("utf-8"))
    return f"{kept}\n…[truncated {dropped} bytes]"


def _finite_vector(value, label: str):
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError(f"{label} must contain exactly three values")
    numbers = tuple(float(component) for component in value)
    if not all(math.isfinite(component) for component in numbers):
        raise ValueError(f"{label} values must be finite numbers")
    return numbers


def _as_vector(value):
    if value is None:
        return [0.0, 0.0, 0.0]
    if isinstance(value, (list, tuple)):
        return [float(component) for component in value]
    return [float(value.x), float(value.y), float(value.z)]


def _as_rotator(value):
    if value is None:
        return [0.0, 0.0, 0.0]
    if isinstance(value, (list, tuple)):
        return [float(component) for component in value]
    return [float(value.pitch), float(value.yaw), float(value.roll)]


def _png_names(directory: str):
    try:
        names = os.listdir(directory)
    except OSError:
        return set()
    return {name for name in names if name.lower().endswith(".png")}


def _file_ready(path: str) -> bool:
    try:
        return os.path.isfile(path) and os.path.getsize(path) > 0
    except OSError:
        return False


def _ready_png(filepath: str, directory: str, known) -> str:
    if _file_ready(filepath):
        return filepath
    try:
        names = _png_names(directory)
    except OSError:
        return ""
    fresh = []
    for name in names - set(known):
        candidate = os.path.join(directory, name)
        if _file_ready(candidate):
            fresh.append(candidate)
    if not fresh:
        return ""
    fresh.sort(key=lambda path: os.path.getmtime(path))
    return fresh[-1]


class UnrealMCPServer:
    """Accept JSON commands over TCP and run them on the editor game thread."""

    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT):
        self.host = "127.0.0.1" if host in {"localhost", "::1", ""} else host
        self.port = port
        self.running = False
        self.socket = None
        self.server_thread = None
        self.start_failure: str | None = None
        self.command_queue: queue.Queue = queue.Queue(maxsize=MAX_PENDING_COMMANDS)
        self._clients = set()
        self._clients_lock = threading.Lock()
        self._stop_entered = False
        self._slate_handle = None
        self._shutdown_handle = None
        self._screenshot_wait = None
        self._deferred_client = None

    def start(self) -> bool:
        self._stop_entered = False
        self.start_failure = None
        if self.host != "127.0.0.1":
            print(
                f"PlygonMCP: refusing to bind {self.host}. "
                "The listener only binds 127.0.0.1."
            )
            return False

        checker = getattr(unreal, "is_editor", None)
        if callable(checker) and not checker():
            print(
                "PlygonMCP: cannot start outside the Unreal Editor. "
                "Open the editor UI, not a commandlet."
            )
            return False

        version = self._engine_version()
        if version is not None and version < MINIMUM_ENGINE:
            print(
                "PlygonMCP: Unreal Engine 5.4 or newer is required "
                f"(found {version[0]}.{version[1]})."
            )
            return False

        if self.running:
            print(f"PlygonMCP: server already running on {self.host}:{self.port}")
            self._ensure_callbacks()
            return True

        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            _configure_listener_socket(self.socket)
            self.socket.bind((self.host, self.port))
            self.socket.listen(5)
            bound_port = self.socket.getsockname()[1]
            if self.port == 0:
                self.port = bound_port
            self.running = True

            self.server_thread = threading.Thread(target=self._server_loop, daemon=True)
            self.server_thread.start()
            self._ensure_callbacks()
            print(f"PlygonMCP: listening on {self.host}:{self.port}")
            return True
        except Exception as exc:
            _report_start_failure(self, exc)
            self.stop()
            return False

    def stop(self):
        if self._stop_entered:
            return
        self._stop_entered = True
        self.running = False
        self._screenshot_wait = None
        self._deferred_client = None

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
            if threading.current_thread() is not self.server_thread:
                self.server_thread.join(timeout=1.0)
        self.server_thread = None
        self._unregister_callbacks()
        print("PlygonMCP: server stopped")

    def _ensure_callbacks(self):
        register_slate = getattr(unreal, "register_slate_post_tick_callback", None)
        if self._slate_handle is None and callable(register_slate):
            # Slate post-tick runs on the game thread. Do not run commands
            # from the accept thread.
            self._slate_handle = register_slate(self._drain_command_queue)
        register_shutdown = getattr(unreal, "register_python_shutdown_callback", None)
        if self._shutdown_handle is None and callable(register_shutdown):
            self._shutdown_handle = register_shutdown(self._on_editor_exit)

    def _unregister_callbacks(self):
        if self._slate_handle is not None:
            unregister = getattr(unreal, "unregister_slate_post_tick_callback", None)
            try:
                if callable(unregister):
                    unregister(self._slate_handle)
            except Exception:
                pass
            self._slate_handle = None
        if self._shutdown_handle is not None:
            unregister = getattr(unreal, "unregister_python_shutdown_callback", None)
            try:
                if callable(unregister):
                    unregister(self._shutdown_handle)
            except Exception:
                pass
            self._shutdown_handle = None

    def _on_editor_exit(self):
        self.stop()

    def _server_loop(self):
        self.socket.settimeout(1.0)
        while self.running:
            try:
                try:
                    client, address = self.socket.accept()
                    print(f"PlygonMCP: client connected {address}")
                    worker = threading.Thread(
                        target=self._handle_client, args=(client,), daemon=True
                    )
                    worker.start()
                except socket.timeout:
                    continue
                except Exception as exc:
                    if not self.running:
                        break
                    print(f"PlygonMCP: accept error: {exc}")
                    time.sleep(0.5)
            except Exception as exc:
                print(f"PlygonMCP: server loop error: {exc}")
                if not self.running:
                    break
                time.sleep(0.5)

    def _drain_command_queue(self, delta_time: float = 0.0):
        """Run at most one queued command. Called by Slate on the game thread."""
        del delta_time
        if not self.running:
            return None

        if self._screenshot_wait is not None:
            self._flush_screenshot()
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
                if response is _DEFERRED:
                    self._deferred_client = (client, client_closed)
                    return None
                payload = _encode_message(response)
            except Exception as exc:
                traceback.print_exc()
                payload = _encode_message({"status": "error", "message": str(exc)})

            self._send_payload(client, command, payload)
            processed += 1

        return None

    def _flush_screenshot(self):
        wait = self._screenshot_wait
        client_info = self._deferred_client
        if not wait or client_info is None:
            return
        client, client_closed = client_info
        if client_closed.is_set():
            self._screenshot_wait = None
            self._deferred_client = None
            return
        found = _ready_png(wait["filepath"], wait["directory"], wait["known"])
        timed_out = (time.monotonic() - wait["started"]) >= SCREENSHOT_TIMEOUT_SECONDS
        if not found and not timed_out:
            return
        if found:
            response = {
                "status": "success",
                "result": {
                    "success": True,
                    "width": wait["width"],
                    "height": wait["height"],
                    "filepath": found,
                },
            }
        else:
            response = {
                "status": "error",
                "message": (
                    "Viewport screenshot was not written before the timeout. "
                    "Keep a level viewport open and try again."
                ),
            }
        self._screenshot_wait = None
        self._deferred_client = None
        self._send_payload(client, {"type": "get_viewport_screenshot"}, _encode_message(response))

    def _send_payload(self, client, command, payload: bytes):
        try:
            client.sendall(payload)
            command_name = command.get("type") if isinstance(command, dict) else "protocol_error"
            print(f"PlygonMCP: replied {command_name}")
        except Exception:
            print("PlygonMCP: failed to send response (client gone)")

    def _handle_client(self, client):
        client.settimeout(1.0)
        with self._clients_lock:
            self._clients.add(client)
        buffer = b""
        client_closed = threading.Event()
        http_checked = False

        try:
            while self.running:
                try:
                    data = client.recv(8192)
                    if not data:
                        break
                    buffer += data
                    if not http_checked:
                        # Reject cross-protocol requests (e.g. a browser fetch()
                        # POSTing to 127.0.0.1:9879). The MCP client always sends a
                        # bare JSON object, never an HTTP request line. A split
                        # first segment ("GE" then "T / HTTP/1.1") stays buffered
                        # until that line can be accepted or rejected.
                        decision = _http_request_decision(buffer)
                        if decision is None:
                            continue
                        http_checked = True
                        if decision:
                            print("PlygonMCP: rejected HTTP request on the bridge port")
                            break
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
                except Exception as exc:
                    print(f"PlygonMCP: recv error: {exc}")
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
        except Exception as exc:
            traceback.print_exc()
            return {"status": "error", "message": str(exc)}

    def _execute_command_internal(self, command):
        cmd_type = command.get("type")
        params = command.get("params") or {}

        handlers = {
            "ping": lambda: {"pong": True},
            "get_addon_info": self.get_addon_info,
            "get_level_info": self.get_level_info,
            "list_actors": self.list_actors,
            "get_actor_info": self.get_actor_info,
            "select_actors": self.select_actors,
            "spawn_actor": self.spawn_actor,
            "set_actor_transform": self.set_actor_transform,
            "delete_actor": self.delete_actor,
            "list_assets": self.list_assets,
            "import_asset": self.import_asset,
            "get_viewport_screenshot": self.get_viewport_screenshot,
            "execute_python": self.execute_python,
            "list_pcg": self.list_pcg,
            "set_pcg_parameter": self.set_pcg_parameter,
            "generate_pcg": self.generate_pcg,
        }

        handler = handlers.get(cmd_type)
        if not handler:
            return {"status": "error", "message": f"Unknown command type: {cmd_type}"}

        result = self._invoke_handler(handler, cmd_type, params)
        if result is _DEFERRED:
            return _DEFERRED
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
            for name, param in sig.parameters.items()
            if param.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
        }
        return handler(**{key: value for key, value in params.items() if key in allowed})

    def _engine_version(self):
        text = self._engine_version_string()
        match = re.search(r"(\d+)\.(\d+)", text)
        if not match:
            return None
        return int(match.group(1)), int(match.group(2))

    def _engine_version_string(self) -> str:
        library = getattr(unreal, "SystemLibrary", None)
        getter = getattr(library, "get_engine_version", None)
        if not callable(getter):
            return ""
        return str(getter() or "")

    def _editor_world(self):
        getter = getattr(unreal, "get_editor_subsystem", None)
        subsystem_type = getattr(unreal, "UnrealEditorSubsystem", None)
        if callable(getter) and subsystem_type is not None:
            subsystem = getter(subsystem_type)
            world_getter = getattr(subsystem, "get_editor_world", None)
            if callable(world_getter):
                return world_getter()
        library = getattr(unreal, "EditorLevelLibrary", None)
        world_getter = getattr(library, "get_editor_world", None)
        if callable(world_getter):
            return world_getter()
        return None

    def _level_path(self) -> str:
        world = self._editor_world()
        if world is None:
            return ""
        if hasattr(world, "get_path_name"):
            return world.get_path_name()
        return ""

    def _actor_subsystem(self):
        getter = getattr(unreal, "get_editor_subsystem", None)
        subsystem_type = getattr(unreal, "EditorActorSubsystem", None)
        if not callable(getter) or subsystem_type is None:
            raise RuntimeError(
                "unreal.EditorActorSubsystem is not available. "
                "Enable the Editor Scripting Utilities plugin and restart the editor."
            )
        subsystem = getter(subsystem_type)
        if subsystem is None:
            raise RuntimeError("EditorActorSubsystem is not available in this editor session.")
        return subsystem

    def _all_actors(self):
        return list(self._actor_subsystem().get_all_level_actors() or [])

    def _selected_actors(self):
        return list(self._actor_subsystem().get_selected_level_actors() or [])

    def _actor_label(self, actor) -> str:
        if hasattr(actor, "get_actor_label"):
            return str(actor.get_actor_label() or "")
        if hasattr(actor, "get_name"):
            return str(actor.get_name() or "")
        return ""

    def _actor_summary(self, actor) -> dict:
        class_name = ""
        if hasattr(actor, "get_class"):
            actor_class = actor.get_class()
            if hasattr(actor_class, "get_name"):
                class_name = actor_class.get_name()
        return {
            "label": self._actor_label(actor),
            "name": actor.get_name() if hasattr(actor, "get_name") else "",
            "path": actor.get_path_name() if hasattr(actor, "get_path_name") else "",
            "class": class_name,
            "location": _as_vector(actor.get_actor_location()) if hasattr(actor, "get_actor_location") else [],
            "rotation": _as_rotator(actor.get_actor_rotation()) if hasattr(actor, "get_actor_rotation") else [],
            "scale": _as_vector(actor.get_actor_scale3d()) if hasattr(actor, "get_actor_scale3d") else [],
        }

    def _require_actor(self, name: str):
        if not name:
            raise ValueError("Actor name is required")
        for actor in self._all_actors():
            names = {
                self._actor_label(actor),
                actor.get_name() if hasattr(actor, "get_name") else "",
                actor.get_path_name() if hasattr(actor, "get_path_name") else "",
            }
            if name in names:
                return actor
        raise ValueError(f"Actor not found: {name}")

    def _transaction(self, description: str):
        ctor = getattr(unreal, "ScopedEditorTransaction", None)
        if ctor is None:
            raise RuntimeError("unreal.ScopedEditorTransaction is not available in this editor.")
        return ctor(description)

    def get_addon_info(self):
        version = self._engine_version()
        return {
            "name": "Plygon Unreal MCP",
            "addon_version": [int(part) for part in __version__.split(".")],
            "protocol_version": ADDON_PROTOCOL_VERSION,
            "engine_version": self._engine_version_string(),
            "minimum_engine": list(MINIMUM_ENGINE),
            "engine_supported": version is None or version >= MINIMUM_ENGINE,
            "level": self._level_path(),
            "pcg_available": hasattr(unreal, "PCGComponent"),
            "capabilities": sorted(
                [
                    "ping",
                    "get_addon_info",
                    "get_level_info",
                    "list_actors",
                    "get_actor_info",
                    "select_actors",
                    "spawn_actor",
                    "set_actor_transform",
                    "delete_actor",
                    "list_assets",
                    "import_asset",
                    "get_viewport_screenshot",
                    "execute_python",
                    "list_pcg",
                    "set_pcg_parameter",
                    "generate_pcg",
                ]
            ),
        }

    def get_level_info(self, limit: int = 50):
        limit = max(0, int(limit))
        actors = self._all_actors()
        selected = self._selected_actors()
        return {
            "engine_version": self._engine_version_string(),
            "level": self._level_path(),
            "actor_count": len(actors),
            "actors": [self._actor_summary(actor) for actor in actors[:limit]],
            "selected": [self._actor_summary(actor) for actor in selected[:limit]],
        }

    def _component_summaries(self, actor) -> list:
        getter = getattr(actor, "get_components_by_class", None)
        if not callable(getter):
            return []
        try:
            components = list(getter(None) or [])
        except TypeError:
            component_class = getattr(unreal, "ActorComponent", None)
            if component_class is None:
                return []
            components = list(getter(component_class) or [])
        rows = []
        for component in components:
            class_name = ""
            if hasattr(component, "get_class"):
                component_class = component.get_class()
                if component_class is not None and hasattr(component_class, "get_name"):
                    class_name = component_class.get_name()
            rows.append(
                {
                    "name": component.get_name() if hasattr(component, "get_name") else "",
                    "class": class_name,
                    "path": component.get_path_name() if hasattr(component, "get_path_name") else "",
                }
            )
        return rows

    def get_actor_info(self, name: str):
        actor = self._require_actor(name)
        summary = self._actor_summary(actor)
        return {
            "label": summary["label"],
            "class": summary["class"],
            "path": summary["path"],
            "transform": {
                "location": summary["location"],
                "rotation": summary["rotation"],
                "scale": summary["scale"],
            },
            "components": self._component_summaries(actor),
        }

    def list_actors(self, limit: int = 100):
        limit = max(0, int(limit))
        actors = self._all_actors()
        return {
            "actors": [self._actor_summary(actor) for actor in actors[:limit]],
            "count": len(actors),
        }

    def select_actors(self, names, mode: str = "REPLACE"):
        if not isinstance(names, (list, tuple)) or not names:
            raise ValueError("names must be a non-empty list of actor labels or paths")
        mode = (mode or "REPLACE").upper()
        if mode not in {"REPLACE", "ADD"}:
            raise ValueError("mode must be REPLACE or ADD")
        chosen = [self._require_actor(name) for name in names]
        with self._transaction("Plygon select actors"):
            subsystem = self._actor_subsystem()
            if mode == "ADD":
                current = list(subsystem.get_selected_level_actors() or [])
                for actor in chosen:
                    if actor not in current:
                        current.append(actor)
                subsystem.set_selected_level_actors(current)
                selected = current
            else:
                subsystem.set_selected_level_actors(chosen)
                selected = chosen
        return {
            "selected": [self._actor_summary(actor) for actor in selected],
            "mode": mode,
        }

    def spawn_actor(
        self,
        kind: str = "static_mesh",
        name: str = "",
        location=(0.0, 0.0, 0.0),
        rotation=(0.0, 0.0, 0.0),
        scale=(1.0, 1.0, 1.0),
        mesh_path: str = "",
    ):
        kind_key = (kind or "").strip().lower()
        class_name = _ACTOR_KINDS.get(kind_key)
        if not class_name:
            raise ValueError(f"Unknown kind: {kind}. Use one of {sorted(_ACTOR_KINDS)}")
        actor_class = getattr(unreal, class_name, None)
        if actor_class is None:
            raise RuntimeError(f"unreal.{class_name} is not available in this editor.")
        location = _finite_vector(location, "location")
        rotation = _finite_vector(rotation, "rotation")
        scale = _finite_vector(scale, "scale")
        if any(component == 0 for component in scale):
            raise ValueError("scale values must be non-zero")

        mesh_warning = ""
        with self._transaction("Plygon spawn actor"):
            subsystem = self._actor_subsystem()
            actor = subsystem.spawn_actor_from_class(
                actor_class,
                unreal.Vector(*location),
                unreal.Rotator(*rotation),
            )
            if actor is None:
                raise RuntimeError(f"Unreal Editor did not spawn a {class_name}")
            if name and hasattr(actor, "set_actor_label"):
                try:
                    actor.set_actor_label(name)
                except TypeError:
                    actor.set_actor_label(name, True)
            if scale != (1.0, 1.0, 1.0) and hasattr(actor, "set_actor_scale3d"):
                actor.set_actor_scale3d(unreal.Vector(*scale))
            if class_name == "StaticMeshActor":
                mesh_warning = self._assign_static_mesh(actor, mesh_path or DEFAULT_CUBE_MESH)

        summary = self._actor_summary(actor)
        summary["kind"] = kind_key
        if mesh_warning:
            summary["mesh_warning"] = mesh_warning
        return summary

    def _assign_static_mesh(self, actor, mesh_path: str) -> str:
        asset = self._load_asset(mesh_path)
        if asset is None:
            return f"Static mesh was not found: {mesh_path}"
        component = getattr(actor, "static_mesh_component", None)
        if component is None and hasattr(actor, "get_components_by_class"):
            component_class = getattr(unreal, "StaticMeshComponent", None)
            if component_class is not None:
                components = list(actor.get_components_by_class(component_class) or [])
                component = components[0] if components else None
        if component is None:
            return "Spawned actor has no static mesh component"
        if hasattr(component, "set_static_mesh"):
            component.set_static_mesh(asset)
            return ""
        if hasattr(component, "set_editor_property"):
            component.set_editor_property("static_mesh", asset)
            return ""
        return "This editor build has no documented way to assign the static mesh"

    def _load_asset(self, asset_path: str):
        library = getattr(unreal, "EditorAssetLibrary", None)
        loader = getattr(library, "load_asset", None)
        if callable(loader):
            return loader(asset_path)
        loader = getattr(unreal, "load_asset", None)
        if callable(loader):
            return loader(asset_path)
        raise RuntimeError(
            "No asset loader is available. Enable the Editor Scripting Utilities plugin and restart the editor."
        )

    def set_actor_transform(self, name: str, location=None, rotation=None, scale=None):
        actor = self._require_actor(name)
        if location is None and rotation is None and scale is None:
            raise ValueError("Provide location, rotation, or scale")
        if location is not None:
            location = _finite_vector(location, "location")
        if rotation is not None:
            rotation = _finite_vector(rotation, "rotation")
        if scale is not None:
            scale = _finite_vector(scale, "scale")
            if any(component == 0 for component in scale):
                raise ValueError("scale values must be non-zero")
        with self._transaction("Plygon transform actor"):
            if location is not None:
                actor.set_actor_location(unreal.Vector(*location), False, True)
            if rotation is not None:
                actor.set_actor_rotation(unreal.Rotator(*rotation), True)
            if scale is not None:
                actor.set_actor_scale3d(unreal.Vector(*scale))
        return self._actor_summary(actor)

    def delete_actor(self, name: str):
        actor = self._require_actor(name)
        label = self._actor_label(actor)
        with self._transaction("Plygon delete actor"):
            removed = self._actor_subsystem().destroy_actor(actor)
        if removed is False:
            raise RuntimeError(f"Unreal Editor did not delete {label or name}")
        return {"deleted": label or name}

    def list_assets(self, directory: str = "/Game", recursive: bool = True, limit: int = 100):
        library = getattr(unreal, "EditorAssetLibrary", None)
        lister = getattr(library, "list_assets", None)
        if not callable(lister):
            raise RuntimeError(
                "unreal.EditorAssetLibrary.list_assets is not available. "
                "Enable the Editor Scripting Utilities plugin and restart the editor."
            )
        limit = max(0, int(limit))
        assets = list(lister(directory, bool(recursive), False) or [])
        return {
            "directory": directory,
            "assets": assets[:limit],
            "count": len(assets),
        }

    def import_asset(
        self,
        filename: str,
        destination_path: str = "/Game",
        destination_name: str = "",
        replace_existing: bool = False,
    ):
        if not filename:
            raise ValueError("filename is required")
        task_type = getattr(unreal, "AssetImportTask", None)
        helpers = getattr(unreal, "AssetToolsHelpers", None)
        get_tools = getattr(helpers, "get_asset_tools", None)
        if task_type is None or not callable(get_tools):
            raise RuntimeError("unreal.AssetImportTask or AssetToolsHelpers is not available in this editor.")
        with self._transaction("Plygon import asset"):
            task = task_type()
            task.filename = filename
            task.destination_path = destination_path or "/Game"
            task.destination_name = destination_name or ""
            task.automated = True
            task.save = True
            task.replace_existing = bool(replace_existing)
            get_tools().import_asset_tasks([task])
            imported = list(getattr(task, "imported_object_paths", []) or [])
        return {
            "filename": filename,
            "destination_path": task.destination_path,
            "imported_object_paths": imported,
        }

    def get_viewport_screenshot(self, max_size: int = 1000, filepath: str = ""):
        max_size = int(max_size)
        if max_size < 2:
            raise ValueError("max_size must be at least 2 pixels")
        library = getattr(unreal, "AutomationLibrary", None)
        take = getattr(library, "take_high_res_screenshot", None)
        if not callable(take):
            raise RuntimeError(
                "unreal.AutomationLibrary.take_high_res_screenshot is not available in this editor."
            )
        if not filepath:
            filepath = os.path.join(
                tempfile.gettempdir(),
                f"plygon_mcp_viewport_{os.getpid()}_{uuid.uuid4().hex}.png",
            )
        directory = os.path.dirname(os.path.abspath(filepath)) or "."
        known = _png_names(directory)
        width = max_size
        height = max_size
        take(width, height, filepath, force_game_view=True)
        found = _ready_png(filepath, directory, known)
        if found:
            return {"success": True, "width": width, "height": height, "filepath": found}
        self._screenshot_wait = {
            "filepath": filepath,
            "width": width,
            "height": height,
            "directory": directory,
            "known": known,
            "started": time.monotonic(),
        }
        return _DEFERRED

    def execute_python(self, code: str):
        if not isinstance(code, str) or not code.strip():
            raise ValueError("code is required")
        capture = io.StringIO()

        def _print(*args, sep=" ", end="\n", file=None, flush=False):
            del flush
            text = sep.join(str(arg) for arg in args) + end
            if file is None:
                capture.write(text)
            else:
                file.write(text)

        namespace = {"unreal": unreal, "print": _print}
        with self._transaction("Plygon execute_python"):
            with redirect_stdout(capture):
                exec(code, namespace)
        return {"executed": True, "result": _truncate_stdout(capture.getvalue())}

    def _require_pcg_class(self):
        component_class = getattr(unreal, "PCGComponent", None)
        if component_class is None:
            raise RuntimeError(
                "unreal.PCGComponent is not available. Enable the PCG plugin and restart the editor."
            )
        return component_class

    def _pcg_on_actor(self, actor):
        component_class = self._require_pcg_class()
        if not hasattr(actor, "get_components_by_class"):
            return []
        return list(actor.get_components_by_class(component_class) or [])

    def _pcg_targets(self, actor_name: str):
        pairs = []
        if actor_name:
            actor = self._require_actor(actor_name)
            pairs = [(actor, component) for component in self._pcg_on_actor(actor)]
        else:
            for actor in self._all_actors():
                for component in self._pcg_on_actor(actor):
                    pairs.append((actor, component))
        if not pairs:
            if actor_name:
                raise ValueError(f"No PCG component on actor: {actor_name}")
            raise ValueError("No PCG components in the current level")
        return pairs

    def _pcg_summary(self, actor, component) -> dict:
        graph = component.get_graph() if hasattr(component, "get_graph") else None
        graph_path = ""
        if graph is not None and hasattr(graph, "get_path_name"):
            graph_path = graph.get_path_name()
        return {
            "actor": self._actor_label(actor),
            "actor_path": actor.get_path_name() if hasattr(actor, "get_path_name") else "",
            "graph": graph_path,
            "has_graph_instance": getattr(component, "graph_instance", None) is not None,
        }

    def list_pcg(self, limit: int = 50):
        limit = max(0, int(limit))
        pairs = []
        # _pcg_on_actor raises when the plugin class is missing. Call it once
        # up front so an empty level still reports a missing plugin.
        self._require_pcg_class()
        for actor in self._all_actors():
            for component in self._pcg_on_actor(actor):
                pairs.append(self._pcg_summary(actor, component))
        return {"components": pairs[:limit], "count": len(pairs)}

    def set_pcg_parameter(self, name: str, value, actor: str = "", value_type: str = ""):
        if not name:
            raise ValueError("name is required")
        pairs = self._pcg_targets(actor)
        if not actor and len(pairs) != 1:
            raise ValueError("Name the actor. The level has more than one PCG component.")
        _actor, component = pairs[0]
        instance = getattr(component, "graph_instance", None)
        if instance is None:
            raise RuntimeError(
                "This PCG component has no graph_instance. "
                "Epic's API sets graph parameters on the graph instance."
            )
        kind = (value_type or "").strip().lower()
        if not kind:
            if isinstance(value, bool):
                kind = "bool"
            elif isinstance(value, int) and not isinstance(value, bool):
                kind = "int"
            elif isinstance(value, float):
                kind = "float"
            elif isinstance(value, str):
                kind = "string"
            elif isinstance(value, (list, tuple)) and len(value) == 3:
                kind = "vector"
            else:
                raise ValueError(
                    "Pass value_type: bool, int, int64, float, double, string, name, or vector."
                )
        setter_name = _PCG_SETTERS.get(kind)
        helpers = getattr(unreal, "PCGGraphParametersHelpers", None)
        setter = getattr(helpers, setter_name, None) if setter_name else None
        if not callable(setter):
            raise RuntimeError(
                f"PCG parameter setter for {kind} is not available in this editor."
            )
        argument = value
        if kind == "vector":
            coords = _finite_vector(value, "value")
            argument = unreal.Vector(*coords)
        elif kind == "name":
            name_type = getattr(unreal, "Name", None)
            argument = name_type(str(value)) if name_type is not None else str(value)
        with self._transaction("Plygon set PCG parameter"):
            setter(instance, name, argument)
        return {
            "actor": self._actor_label(_actor),
            "parameter": name,
            "value_type": kind,
        }

    def generate_pcg(self, actor: str = "", force: bool = True):
        pairs = self._pcg_targets(actor)
        generated = []
        with self._transaction("Plygon generate PCG"):
            for owner, component in pairs:
                if hasattr(component, "generate"):
                    component.generate(bool(force))
                elif hasattr(component, "generate_local"):
                    component.generate_local(bool(force))
                else:
                    raise RuntimeError("PCGComponent.generate is not available in this editor.")
                generated.append(self._actor_label(owner))
        return {"generated": generated, "count": len(generated), "force": bool(force)}


def start_server(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT):
    """Start the MCP listener. Safe to call from init_unreal.py or a Startup script."""
    global _server
    if _server and _server.running:
        print(f"PlygonMCP: server already running on {_server.host}:{_server.port}")
        return _server
    _server = UnrealMCPServer(host=host, port=port)
    if not _server.start():
        _server = None
        return None
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
    running = bool(_server and _server.running)
    return {
        "running": running,
        "host": _server.host if _server else None,
        "port": _server.port if _server else None,
    }
