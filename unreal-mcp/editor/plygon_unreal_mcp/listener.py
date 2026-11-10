# SPDX-License-Identifier: MIT
"""Plygon Unreal MCP listener. TCP command bridge for Cursor / MCP clients.

Runs inside the Unreal Editor. The accept thread only reads sockets. Every
editor call runs from ``unreal.register_slate_post_tick_callback``, which
Epic documents as a game-thread callback. Do not call ``unreal`` from the
accept thread.

Start it from ``init_unreal.py`` or the editor Python console:

    from plygon_unreal_mcp.listener import start_server
    start_server(port=9879)
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
from contextlib import contextmanager, redirect_stdout

from . import __version__

try:
    import unreal
except ImportError:
    raise ImportError(
        "plygon_unreal_mcp.listener must run inside the Unreal Editor (unreal module required)."
    )

ADDON_PROTOCOL_VERSION = 1
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9879
MAX_BUFFER_BYTES = 4 * 1024 * 1024
MAX_PENDING_COMMANDS = 128
MAX_COMMANDS_PER_TICK = 1
MAX_EXECUTE_STDOUT_BYTES = 256 * 1024
MIN_ENGINE = (5, 4)
SCREENSHOT_TIMEOUT_SECONDS = 20.0
DEFAULT_CUBE = "/Engine/BasicShapes/Cube"
_DEFERRED = object()

ACTOR_KINDS = {
    "static_mesh": "StaticMeshActor",
    "point_light": "PointLight",
    "spot_light": "SpotLight",
    "directional_light": "DirectionalLight",
    "rect_light": "RectLight",
    "camera": "CameraActor",
    "cine_camera": "CineCameraActor",
}

PCG_SETTERS = {
    "bool": "set_bool_parameter",
    "float": "set_float_parameter",
    "double": "set_double_parameter",
    "int": "set_int32_parameter",
    "int32": "set_int32_parameter",
    "int64": "set_int64_parameter",
    "string": "set_string_parameter",
    "name": "set_name_parameter",
    "vector": "set_vector_parameter",
}

COMMANDS = (
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
    "execute_code",
    "get_viewport_screenshot",
    "list_pcg",
    "set_pcg_parameter",
    "generate_pcg",
)

_server = None
_MALFORMED_JSON = object()
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
# copy. The port-in-use sentence below stays generic for Unreal.
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
        "Stop the other listener or choose a free port."
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


def _engine_version_tuple(text: str):
    match = re.match(r"\s*(\d+)\.(\d+)(?:\.(\d+))?", str(text))
    if not match:
        return None
    return tuple(int(part) for part in match.groups() if part is not None)


def _finite_triple(values, label: str):
    if values is None:
        return None
    if len(values) != 3:
        raise ValueError(f"{label} must contain exactly three numbers")
    numbers = tuple(float(item) for item in values)
    if not all(math.isfinite(number) for number in numbers):
        raise ValueError(f"{label} values must be finite numbers")
    return numbers


def _vector_list(value):
    if value is None:
        return None
    if hasattr(value, "x"):
        return [float(value.x), float(value.y), float(value.z)]
    return [float(value[0]), float(value[1]), float(value[2])]


def _rotator_list(value):
    """Return pitch, yaw, roll in degrees."""
    if value is None:
        return None
    if hasattr(value, "pitch"):
        return [float(value.pitch), float(value.yaw), float(value.roll)]
    return [float(value[0]), float(value[1]), float(value[2])]


def _make_vector(values, label: str):
    numbers = _finite_triple(values, label)
    if numbers is None:
        return None
    return unreal.Vector(x=numbers[0], y=numbers[1], z=numbers[2])


def _make_rotator(values):
    """Interpret ``values`` as pitch, yaw, roll degrees.

    ``unreal.Rotator``'s positional constructor is ``(roll, pitch, yaw)``.
    Callers of this bridge pass pitch, yaw, roll, so the constructor is
    always called with keywords.
    """
    numbers = _finite_triple(values, "rotation")
    if numbers is None:
        return unreal.Rotator()
    pitch, yaw, roll = numbers
    return unreal.Rotator(roll=roll, pitch=pitch, yaw=yaw)


def _limit(value, default: int = 50, ceiling: int = 500) -> int:
    if value is None:
        return default
    count = int(value)
    if count < 0:
        raise ValueError("limit must be zero or greater")
    return min(count, ceiling)


def _asset_class_text(data) -> str:
    if data is None:
        return ""
    for name in ("asset_class_path", "asset_class"):
        if hasattr(data, name):
            value = getattr(data, name)
            if value:
                return str(value)
        getter = getattr(data, "get_editor_property", None)
        if getter is None:
            continue
        try:
            value = getter(name)
        except Exception:
            continue
        if value:
            return str(value)
    return ""


def _is_pcg_graph_class(text: str) -> bool:
    cleaned = str(text).strip().strip("'\"")
    leaf = cleaned.rsplit(".", 1)[-1].rsplit("/", 1)[-1]
    return leaf == "PCGGraph"


@contextmanager
def _editor_transaction(description: str):
    """Wrap one editor mutation so the user can undo it.

    ``ScopedEditorTransaction.__exit__`` ends the transaction. On failure,
    ``cancel`` runs first so a partial edit is not left on the undo stack.
    """
    transaction = unreal.ScopedEditorTransaction(description)
    transaction.__enter__()
    try:
        yield transaction
    except Exception:
        cancel = getattr(transaction, "cancel", None)
        if callable(cancel):
            try:
                cancel()
            except Exception:
                traceback.print_exc()
        raise
    finally:
        transaction.__exit__(None, None, None)


class UnrealMCPServer:
    """Accept JSON commands over TCP and run them on the editor game thread."""

    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT):
        self.host = "127.0.0.1" if host in {"localhost", "::1", ""} else host
        self.port = int(port)
        self.running = False
        self.socket = None
        self.server_thread = None
        self.start_failure: str | None = None
        self.command_queue: queue.Queue = queue.Queue(maxsize=MAX_PENDING_COMMANDS)
        self._clients = set()
        self._clients_lock = threading.Lock()
        self._tick_handle = None
        self._shutdown_handle = None
        self._game_thread_id = None
        self._pending_capture = None
        self._closing_from_shutdown = False

    def start(self) -> bool:
        self.start_failure = None
        if hasattr(unreal, "is_editor") and not unreal.is_editor():
            print(
                "PlygonMCP: cannot start outside the Unreal Editor. "
                "Open the editor GUI, not a commandlet or -game process."
            )
            return False

        version_text = self._read_engine_version()
        parsed = _engine_version_tuple(version_text) if version_text else None
        if parsed is not None and parsed < MIN_ENGINE:
            self.start_failure = (
                f"Unreal Engine {version_text} is older than 5.4. "
                "Plygon Unreal MCP targets 5.4 and newer."
            )
            print(f"PlygonMCP: {self.start_failure}")
            return False

        if self.host != "127.0.0.1":
            self.start_failure = (
                f"Refusing to bind {self.host}. The listener only binds 127.0.0.1."
            )
            print(f"PlygonMCP: {self.start_failure}")
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
            self.running = True
            self.server_thread = threading.Thread(
                target=self._server_loop, name="plygon-unreal-mcp", daemon=True
            )
            self.server_thread.start()
            self._ensure_callbacks()
            bound_host, bound_port = self.socket.getsockname()[:2]
            print(f"PlygonMCP: listening on {bound_host}:{bound_port}")
            return True
        except Exception as exc:
            _report_start_failure(self, exc)
            self.stop()
            return False

    def stop(self, from_shutdown: bool = False):
        self.running = False
        self._pending_capture = None
        self._closing_from_shutdown = from_shutdown

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
            if threading.get_ident() != self.server_thread.ident:
                self.server_thread.join(timeout=1.0)
        self.server_thread = None

        tick_handle = self._tick_handle
        self._tick_handle = None
        if tick_handle is not None:
            try:
                unreal.unregister_slate_post_tick_callback(tick_handle)
            except Exception:
                pass

        if not from_shutdown:
            shutdown_handle = self._shutdown_handle
            self._shutdown_handle = None
            if shutdown_handle is not None:
                try:
                    unreal.unregister_python_shutdown_callback(shutdown_handle)
                except Exception:
                    pass
        print("PlygonMCP: server stopped")

    def _on_python_shutdown(self):
        if self._closing_from_shutdown:
            return
        self.stop(from_shutdown=True)

    def _ensure_callbacks(self):
        if self._tick_handle is None:
            self._tick_handle = unreal.register_slate_post_tick_callback(
                self._drain_command_queue
            )
        if self._shutdown_handle is None:
            self._shutdown_handle = unreal.register_python_shutdown_callback(
                self._on_python_shutdown
            )

    def _read_engine_version(self) -> str:
        try:
            return str(unreal.SystemLibrary.get_engine_version())
        except Exception as exc:
            print(f"PlygonMCP: could not read the engine version: {exc}")
            return ""

    def _server_loop(self):
        self.socket.settimeout(1.0)
        while self.running:
            try:
                try:
                    client, address = self.socket.accept()
                    print(f"PlygonMCP: client connected {address}")
                    thread = threading.Thread(
                        target=self._handle_client, args=(client,), daemon=True
                    )
                    thread.start()
                except socket.timeout:
                    continue
                except Exception as exc:
                    if not self.running:
                        break
                    print(f"PlygonMCP: accept error: {exc}")
                    time.sleep(0.5)
            except Exception as exc:
                if not self.running:
                    break
                print(f"PlygonMCP: server loop error: {exc}")
                time.sleep(0.5)

    def _note_game_thread(self):
        current = threading.get_ident()
        if self._game_thread_id is None:
            self._game_thread_id = current
            return
        if self._game_thread_id != current:
            raise RuntimeError("Editor commands must run on the game thread")

    def _drain_command_queue(self, delta_time=0.0):
        del delta_time
        if not self.running and self._pending_capture is None:
            return

        try:
            self._note_game_thread()
        except RuntimeError as exc:
            print(f"PlygonMCP: {exc}")
            return

        if self._pending_capture is not None:
            ready = self._poll_capture()
            if ready is not None:
                pending = ready.pop("_pending")
                self._send_response(pending["client"], ready, pending.get("command"))
            return

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
                if response is None and self._pending_capture is not None:
                    self._pending_capture["client"] = client
                    self._pending_capture["client_closed"] = client_closed
                    self._pending_capture["command"] = command
                    ready = self._poll_capture()
                    if ready is None:
                        return
                    ready.pop("_pending", None)
                    response = ready
                payload = _encode_message(response)
            except Exception as exc:
                traceback.print_exc()
                payload = _encode_message({"status": "error", "message": str(exc)})

            self._send_payload(client, payload, command)
            processed += 1

    def _send_response(self, client, response, command):
        try:
            payload = _encode_message(response)
        except Exception as exc:
            payload = _encode_message({"status": "error", "message": str(exc)})
        self._send_payload(client, payload, command)

    def _send_payload(self, client, payload, command):
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
        if (
            self._game_thread_id is not None
            and threading.get_ident() != self._game_thread_id
        ):
            return {
                "status": "error",
                "message": "Refusing to run an editor command off the game thread",
            }
        try:
            return self._execute_command_internal(command)
        except Exception as exc:
            if self._pending_capture is not None and "client" not in self._pending_capture:
                self._pending_capture = None
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
            "execute_code": self.execute_code,
            "get_viewport_screenshot": self.get_viewport_screenshot,
            "list_pcg": self.list_pcg,
            "set_pcg_parameter": self.set_pcg_parameter,
            "generate_pcg": self.generate_pcg,
        }
        handler = handlers.get(cmd_type)
        if not handler:
            return {"status": "error", "message": f"Unknown command type: {cmd_type}"}

        result = self._invoke_handler(handler, cmd_type, params)
        if result is _DEFERRED:
            return None
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
            if param.kind
            in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
        }
        return handler(**{key: value for key, value in params.items() if key in allowed})

    def _subsystem(self, cls):
        subsystem = unreal.get_editor_subsystem(cls)
        if subsystem is None:
            name = getattr(cls, "__name__", str(cls))
            raise RuntimeError(
                f"{name} is not available yet. Wait until the editor has finished opening a level."
            )
        return subsystem

    def _actors(self):
        return self._subsystem(unreal.EditorActorSubsystem)

    def _assets(self):
        return self._subsystem(unreal.EditorAssetSubsystem)

    def _editor(self):
        return self._subsystem(unreal.UnrealEditorSubsystem)

    def _find_actor(self, name: str):
        label = str(name or "").strip()
        if not label:
            raise ValueError("Actor name is required")
        subsystem = self._actors()
        found = subsystem.get_actor_reference(label)
        if found:
            return found
        actors = list(subsystem.get_all_level_actors() or [])
        exact = [actor for actor in actors if actor.get_path_name() == label]
        if len(exact) == 1:
            return exact[0]
        labeled = [actor for actor in actors if actor.get_actor_label() == label]
        if len(labeled) == 1:
            return labeled[0]
        if len(labeled) > 1:
            paths = ", ".join(actor.get_path_name() for actor in labeled[:8])
            raise ValueError(f"Multiple actors are labeled {label!r}: {paths}")
        suffix = "." + label
        matched = [
            actor
            for actor in actors
            if actor.get_path_name().endswith(suffix) or actor.get_name() == label
        ]
        if len(matched) == 1:
            return matched[0]
        if len(matched) > 1:
            paths = ", ".join(actor.get_path_name() for actor in matched[:8])
            raise ValueError(f"Multiple actors match {label!r}: {paths}")
        raise ValueError(f"Actor not found: {label}")

    def _actor_record(self, actor) -> dict:
        class_name = ""
        actor_class = actor.get_class()
        if actor_class is not None:
            class_name = actor_class.get_name()
        return {
            "label": actor.get_actor_label(),
            "name": actor.get_name(),
            "path": actor.get_path_name(),
            "class": class_name,
            "location": _vector_list(actor.get_actor_location()),
            "rotation": _rotator_list(actor.get_actor_rotation()),
            "scale": _vector_list(actor.get_actor_scale3d()),
        }

    def get_addon_info(self):
        version_text = self._read_engine_version()
        return {
            "name": "Plygon Unreal MCP",
            "addon_version": [int(part) for part in __version__.split(".")],
            "protocol_version": ADDON_PROTOCOL_VERSION,
            "engine_version": version_text,
            "engine_version_tuple": list(_engine_version_tuple(version_text) or []),
            "capabilities": sorted(COMMANDS),
        }

    def get_level_info(self, limit: int = 50):
        limit = _limit(limit)
        editor = self._editor()
        world = editor.get_editor_world()
        if world is None:
            raise RuntimeError("No editor world is open. Open a level and try again.")
        actors = list(self._actors().get_all_level_actors() or [])
        selected = list(self._actors().get_selected_level_actors() or [])
        camera = None
        info = editor.get_level_viewport_camera_info()
        if info:
            location, rotation = info[0], info[1]
            camera = {
                "location": _vector_list(location),
                "rotation": _rotator_list(rotation),
            }
        return {
            "engine_version": self._read_engine_version(),
            "world_name": world.get_name(),
            "world_path": world.get_path_name(),
            "actor_count": len(actors),
            "actors": [self._actor_record(actor) for actor in actors[:limit]],
            "selected": [self._actor_record(actor) for actor in selected[:limit]],
            "viewport_camera": camera,
        }

    def list_actors(self, class_filter: str = "", limit: int = 50):
        limit = _limit(limit)
        needle = str(class_filter or "").strip().lower()
        rows = []
        for actor in list(self._actors().get_all_level_actors() or []):
            record = self._actor_record(actor)
            if needle and needle not in record["class"].lower() and needle not in record["label"].lower():
                continue
            rows.append(record)
            if len(rows) >= limit:
                break
        return {"actors": rows, "count": len(rows)}

    def get_actor_info(self, name: str):
        return self._actor_record(self._find_actor(name))

    def select_actors(self, names=None, mode: str = "REPLACE"):
        requested = list(names or [])
        selection_mode = str(mode or "REPLACE").upper()
        if selection_mode not in {"REPLACE", "ADD"}:
            raise ValueError("mode must be REPLACE or ADD")
        subsystem = self._actors()
        chosen = [self._find_actor(name) for name in requested]
        with _editor_transaction("Plygon MCP select actors"):
            if selection_mode == "REPLACE":
                if chosen:
                    subsystem.set_selected_level_actors(chosen)
                else:
                    subsystem.select_nothing()
            else:
                for actor in chosen:
                    subsystem.set_actor_selection_state(actor, True)
        return {
            "selected": [self._actor_record(actor) for actor in chosen],
            "mode": selection_mode,
        }

    def spawn_actor(
        self,
        kind: str = "static_mesh",
        name: str = "",
        location=None,
        rotation=None,
        scale=None,
        mesh: str = "",
    ):
        key = str(kind or "").strip().lower().replace("-", "_").replace(" ", "_")
        class_name = ACTOR_KINDS.get(key)
        if not class_name:
            raise ValueError(f"Unknown actor kind: {kind}. Use one of {sorted(ACTOR_KINDS)}")
        actor_class = getattr(unreal, class_name, None)
        if actor_class is None:
            raise RuntimeError(f"unreal.{class_name} is not available in this editor build.")

        origin = _make_vector(location or [0.0, 0.0, 0.0], "location")
        rotator = _make_rotator(rotation or [0.0, 0.0, 0.0])
        scale_vector = _make_vector(scale, "scale") if scale is not None else None
        mesh_path = str(mesh or "").strip()
        if key == "static_mesh" and not mesh_path:
            mesh_path = DEFAULT_CUBE

        with _editor_transaction(f"Plygon MCP spawn {key}"):
            actor = self._actors().spawn_actor_from_class(actor_class, origin, rotator, False)
            if actor is None:
                raise RuntimeError(f"spawn_actor_from_class returned no actor for {class_name}")
            if name:
                actor.set_actor_label(str(name), True)
            if scale_vector is not None:
                actor.set_actor_scale3d(scale_vector)
            assigned_mesh = ""
            if key == "static_mesh" and mesh_path:
                if self._assets().does_asset_exist(mesh_path):
                    self._assign_static_mesh(actor, mesh_path)
                    assigned_mesh = mesh_path
                elif mesh:
                    raise ValueError(f"Static mesh asset not found: {mesh_path}")
        record = self._actor_record(actor)
        record["kind"] = key
        record["mesh"] = assigned_mesh
        return record

    def _assign_static_mesh(self, actor, mesh_path: str):
        mesh_asset = self._assets().load_asset(mesh_path)
        if mesh_asset is None:
            raise ValueError(f"Could not load static mesh: {mesh_path}")
        component = None
        getter = getattr(actor, "get_editor_property", None)
        if getter is not None:
            try:
                component = getter("static_mesh_component")
            except Exception:
                component = None
        if component is None and hasattr(unreal, "StaticMeshComponent"):
            component = actor.get_component_by_class(unreal.StaticMeshComponent)
        if component is None or not hasattr(component, "set_static_mesh"):
            raise RuntimeError("Spawned actor has no static mesh component")
        if component.set_static_mesh(mesh_asset) is False:
            raise RuntimeError(f"set_static_mesh rejected {mesh_path}")

    def set_actor_transform(
        self,
        name: str,
        location=None,
        rotation=None,
        scale=None,
    ):
        if location is None and rotation is None and scale is None:
            raise ValueError("Pass location, rotation, or scale")
        actor = self._find_actor(name)
        with _editor_transaction("Plygon MCP transform actor"):
            if location is not None:
                actor.set_actor_location(_make_vector(location, "location"), False, True)
            if rotation is not None:
                actor.set_actor_rotation(_make_rotator(rotation), True)
            if scale is not None:
                actor.set_actor_scale3d(_make_vector(scale, "scale"))
        return self._actor_record(actor)

    def delete_actor(self, name: str):
        actor = self._find_actor(name)
        record = self._actor_record(actor)
        with _editor_transaction("Plygon MCP delete actor"):
            removed = self._actors().destroy_actor(actor)
        if removed is False:
            raise RuntimeError(f"destroy_actor rejected {record['path']}")
        return {"deleted": record["path"], "label": record["label"]}

    def list_assets(
        self,
        directory: str = "/Game",
        recursive: bool = True,
        limit: int = 50,
        class_filter: str = "",
    ):
        limit = _limit(limit)
        folder = str(directory or "/Game")
        needle = str(class_filter or "").strip().lower()
        paths = list(self._assets().list_assets(folder, bool(recursive), False) or [])
        rows = []
        for path in paths:
            row = {"path": str(path)}
            if needle:
                data = self._assets().find_asset_data(path)
                class_text = _asset_class_text(data)
                if needle not in class_text.lower():
                    continue
                row["class"] = class_text
            rows.append(row)
            if len(rows) >= limit:
                break
        return {"directory": folder, "assets": rows, "count": len(rows)}

    def import_asset(
        self,
        filename: str,
        destination_path: str = "/Game/PlygonImport",
        destination_name: str = "",
        replace_existing: bool = True,
        save: bool = True,
    ):
        source = str(filename or "").strip()
        if not source:
            raise ValueError("filename is required")
        if not os.path.isfile(source):
            raise ValueError(f"File not found: {source}")
        destination = str(destination_path or "/Game/PlygonImport")
        task = unreal.AssetImportTask()
        task.set_editor_property("filename", source)
        task.set_editor_property("destination_path", destination)
        if destination_name:
            task.set_editor_property("destination_name", str(destination_name))
        task.set_editor_property("automated", True)
        task.set_editor_property("replace_existing", bool(replace_existing))
        task.set_editor_property("save", bool(save))
        with _editor_transaction("Plygon MCP import asset"):
            if not self._assets().does_directory_exist(destination):
                self._assets().make_directory(destination)
            unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
        imported = task.get_editor_property("imported_object_paths")
        paths = [str(item) for item in list(imported or [])]
        return {
            "filename": source,
            "destination_path": destination,
            "imported_object_paths": paths,
        }

    def execute_code(self, code: str):
        namespace = {"unreal": unreal, "__name__": "__plygon_unreal_mcp__"}
        capture = io.StringIO()
        with _editor_transaction("Plygon MCP execute_python"):
            with redirect_stdout(capture):
                exec(code, namespace)
        return {"executed": True, "result": _truncate_stdout(capture.getvalue())}

    def get_viewport_screenshot(self, max_size: int = 1000, filepath: str = ""):
        size = int(max_size)
        if size < 2:
            raise ValueError("max_size must be at least 2 pixels")
        library = getattr(unreal, "AutomationLibrary", None)
        take = getattr(library, "take_high_res_screenshot", None) if library else None
        if take is None:
            raise RuntimeError(
                "unreal.AutomationLibrary.take_high_res_screenshot is not available "
                "in this editor build."
            )
        if not filepath:
            filepath = os.path.join(
                tempfile.gettempdir(),
                f"plygon_mcp_viewport_{os.getpid()}_{uuid.uuid4().hex}.png",
            )
        # The 5.4 signature is (res_x, res_y, filename, camera, mask_enabled,
        # capture_hdr, comparison_tolerance, comparison_notes, delay,
        # force_game_view). The middle comparison arguments keep their defaults.
        # force_game_view stays false so the shot matches the open editor view.
        task = take(size, size, filepath, None, False, False, delay=0.0, force_game_view=False)
        self._pending_capture = {
            "path": filepath,
            "task": task,
            "width": size,
            "height": size,
            "deadline": time.monotonic() + SCREENSHOT_TIMEOUT_SECONDS,
        }
        return _DEFERRED

    def _poll_capture(self):
        pending = self._pending_capture
        if pending is None:
            return None
        client_closed = pending.get("client_closed")
        if client_closed is not None and client_closed.is_set():
            self._pending_capture = None
            return None
        path = pending["path"]
        if os.path.isfile(path) and os.path.getsize(path) > 0:
            self._pending_capture = None
            return {
                "status": "success",
                "result": {
                    "success": True,
                    "width": pending["width"],
                    "height": pending["height"],
                    "filepath": path,
                },
                "_pending": pending,
            }
        if time.monotonic() < pending["deadline"]:
            return None
        self._pending_capture = None
        task = pending.get("task")
        invalid = False
        if task is not None and hasattr(task, "is_valid_task"):
            try:
                invalid = not bool(task.is_valid_task())
            except Exception:
                invalid = False
        if invalid:
            message = (
                "AutomationLibrary.take_high_res_screenshot did not accept the request. "
                "Open a level viewport and try again."
            )
        else:
            message = (
                f"Viewport screenshot was not written to {path} within "
                f"{int(SCREENSHOT_TIMEOUT_SECONDS)} seconds. "
                "Keep a level viewport open. The capture finishes on a later editor tick."
            )
        return {"status": "error", "message": message, "_pending": pending}

    def _require_pcg(self):
        if not hasattr(unreal, "PCGComponent") or not hasattr(unreal, "PCGGraphParametersHelpers"):
            raise RuntimeError(
                "PCG Python types are not available. Enable the PCG plugin and restart the editor."
            )

    def _pcg_components(self, actor):
        self._require_pcg()
        components = actor.get_components_by_class(unreal.PCGComponent)
        return list(components or [])

    def _component_graph(self, component):
        """Return ``(graph_instance, graph_asset)``.

        ``PCGComponent.graph_instance`` and ``PCGGraphInstance.graph`` are on
        the 5.4 class pages. ``PCGComponent.get_graph`` is on the 5.8 page and
        is not on the 5.4 page, so it is used only when the build has it.
        Parameter writes go to the graph instance, which is what the 5.8
        ``get_graph`` note says to use.
        """
        graph = None
        if hasattr(component, "get_graph"):
            try:
                graph = component.get_graph()
            except Exception:
                graph = None
        instance = getattr(component, "graph_instance", None)
        if instance is None:
            getter = getattr(component, "get_editor_property", None)
            if getter is not None:
                try:
                    instance = getter("graph_instance")
                except Exception:
                    instance = None
        if graph is None and instance is not None:
            graph = getattr(instance, "graph", None)
            if graph is None:
                getter = getattr(instance, "get_editor_property", None)
                if getter is not None:
                    try:
                        graph = getter("graph")
                    except Exception:
                        graph = None
        return instance, graph

    def _graph_summary(self, graph) -> dict:
        if graph is None:
            return {"path": "", "name": "", "node_count": 0}
        nodes = []
        getter = getattr(graph, "get_editor_property", None)
        if getter is not None:
            try:
                nodes = list(getter("nodes") or [])
            except Exception:
                nodes = []
        if not nodes and hasattr(graph, "nodes"):
            try:
                nodes = list(graph.nodes or [])
            except Exception:
                nodes = []
        return {
            "path": graph.get_path_name(),
            "name": graph.get_name(),
            "node_count": len(nodes),
            "nodes": [node.get_name() for node in nodes[:50]],
        }

    def list_pcg(self, directory: str = "/Game", limit: int = 50, include_assets: bool = True):
        self._require_pcg()
        limit = _limit(limit)
        components = []
        for actor in list(self._actors().get_all_level_actors() or []):
            for index, component in enumerate(self._pcg_components(actor)):
                instance, graph = self._component_graph(component)
                components.append(
                    {
                        "actor_label": actor.get_actor_label(),
                        "actor_path": actor.get_path_name(),
                        "component_index": index,
                        "component_path": component.get_path_name(),
                        "has_graph_instance": instance is not None,
                        "graph": self._graph_summary(graph),
                    }
                )
                if len(components) >= limit:
                    break
            if len(components) >= limit:
                break

        graphs = []
        if include_assets:
            folder = str(directory or "/Game")
            paths = list(self._assets().list_assets(folder, True, False) or [])
            for path in paths:
                data = self._assets().find_asset_data(path)
                class_text = _asset_class_text(data)
                if not _is_pcg_graph_class(class_text):
                    continue
                graphs.append({"path": str(path), "class": class_text})
                if len(graphs) >= limit:
                    break
        return {"components": components, "graphs": graphs}

    def _pcg_target(self, name: str, component_index: int = 0):
        actor = self._find_actor(name)
        components = self._pcg_components(actor)
        if not components:
            raise ValueError(f"{actor.get_actor_label()} has no PCG component")
        index = int(component_index)
        if index < 0 or index >= len(components):
            raise ValueError(
                f"component_index {index} is outside 0..{len(components) - 1} "
                f"on {actor.get_actor_label()}"
            )
        component = components[index]
        instance, graph = self._component_graph(component)
        target = instance or graph
        if target is None:
            raise RuntimeError(
                f"{actor.get_actor_label()} PCG component {index} has no graph instance"
            )
        return actor, component, target, graph

    def set_pcg_parameter(
        self,
        name: str,
        parameter: str,
        value,
        value_type: str = "float",
        component_index: int = 0,
    ):
        self._require_pcg()
        parameter_name = str(parameter or "").strip()
        if not parameter_name:
            raise ValueError("parameter name is required")
        kind = str(value_type or "float").strip().lower()
        setter_name = PCG_SETTERS.get(kind)
        if not setter_name:
            raise ValueError(
                f"Unsupported value_type {value_type!r}. Use one of {sorted(set(PCG_SETTERS))}"
            )
        setter = getattr(unreal.PCGGraphParametersHelpers, setter_name, None)
        if setter is None:
            raise RuntimeError(f"unreal.PCGGraphParametersHelpers.{setter_name} is not available")
        _actor, _component, target, _graph = self._pcg_target(name, component_index)
        converted = self._pcg_value(kind, value)
        with _editor_transaction("Plygon MCP set PCG parameter"):
            setter(target, parameter_name, converted)
        return {
            "actor": _actor.get_actor_label(),
            "component_index": int(component_index),
            "parameter": parameter_name,
            "value_type": kind,
            "graph": target.get_path_name() if hasattr(target, "get_path_name") else "",
        }

    def _pcg_value(self, kind: str, value):
        if kind == "bool":
            return bool(value)
        if kind in {"float", "double"}:
            number = float(value)
            if not math.isfinite(number):
                raise ValueError("parameter value must be a finite number")
            return number
        if kind in {"int", "int32", "int64"}:
            return int(value)
        if kind in {"string", "name"}:
            return str(value)
        if kind == "vector":
            return _make_vector(value, "value")
        raise ValueError(f"Unsupported value_type {kind}")

    def generate_pcg(self, name: str, force: bool = True, component_index: int = 0):
        self._require_pcg()
        actor, component, _target, graph = self._pcg_target(name, component_index)
        with _editor_transaction("Plygon MCP generate PCG"):
            component.generate(bool(force))
        in_progress = None
        if hasattr(component, "generation_in_progress"):
            in_progress = bool(component.generation_in_progress)
        return {
            "actor": actor.get_actor_label(),
            "actor_path": actor.get_path_name(),
            "component_index": int(component_index),
            "force": bool(force),
            "generation_in_progress": in_progress,
            "graph": self._graph_summary(graph),
        }


def start_server(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT):
    """Start the MCP listener. Called from init_unreal.py or the Python console."""
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
    """Stop the MCP listener and unregister its editor callbacks."""
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
