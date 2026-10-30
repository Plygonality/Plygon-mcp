# SPDX-License-Identifier: MIT
"""Plygon SOLIDWORKS MCP listener — TCP command bridge for Cursor / MCP clients.

SOLIDWORKS has no embedded Python shell. This process attaches to a running
SOLIDWORKS window over COM and speaks the same newline-delimited JSON protocol
as the Blender and Houdini listeners.

Start it from the repo with scripts/start-solidworks.cmd and leave the window open.
"""

from __future__ import annotations

import errno
import inspect
import json
import queue
import re
import socket
import sys
import threading
import time
import traceback

from . import __version__
from .session import WINDOWS_ONLY_MESSAGE, SolidWorksUnavailable, attach_running_solidworks

ADDON_PROTOCOL_VERSION = 1
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9878
MAX_BUFFER_BYTES = 4 * 1024 * 1024
MAX_PENDING_COMMANDS = 128
MAX_COMMANDS_PER_TICK = 1

COMMANDS = (
    "ping",
    "get_addon_info",
    "get_document_info",
    "list_features",
    "get_mass_properties",
    "get_custom_properties",
    "set_custom_property",
    "new_document",
    "create_extruded_box",
    "rebuild",
    "save_document",
    "export_document",
    "execute_code",
    "get_viewport_screenshot",
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
# copy. The port-in-use sentence below stays generic.
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


class SolidWorksMCPServer:
    """Accept JSON commands over TCP and run them on one COM thread."""

    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT):
        self.host = "127.0.0.1" if host in {"localhost", "::1", ""} else host
        self.port = port
        self.running = False
        self.socket = None
        self.server_thread = None
        self.worker_thread = None
        self.start_failure: str | None = None
        self.session = None
        self._com_owned = False
        self._attached = threading.Event()
        self.command_queue: queue.Queue = queue.Queue(maxsize=MAX_PENDING_COMMANDS)
        self._clients = set()
        self._clients_lock = threading.Lock()

    def start(self, session=None) -> bool:
        self.start_failure = None
        if self.running:
            print(f"PlygonMCP: server already running on {self.host}:{self.port}")
            return True

        self._com_owned = session is None
        self.session = session
        self._attached.clear()
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            _configure_listener_socket(self.socket)
            self.socket.bind((self.host, self.port))
            self.socket.listen(5)
            if self.port == 0:
                self.port = self.socket.getsockname()[1]
            self.running = True
            self.worker_thread = threading.Thread(target=self._worker, daemon=True)
            self.worker_thread.start()
            self.server_thread = threading.Thread(target=self._server_loop, daemon=True)
            self.server_thread.start()
        except Exception as exc:
            _report_start_failure(self, exc)
            self.stop()
            return False

        if not self._attached.wait(60):
            self.start_failure = "Timed out attaching to SOLIDWORKS."
            print(f"PlygonMCP: {self.start_failure}")
            self.stop()
            return False
        if self.start_failure or self.session is None:
            if not self.start_failure:
                self.start_failure = "Could not attach to SOLIDWORKS."
                print(f"PlygonMCP: {self.start_failure}")
            self.stop()
            return False
        print(f"PlygonMCP: listening on {self.host}:{self.port}")
        return True

    def stop(self):
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
        if self.worker_thread and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=1.0)
        self.worker_thread = None
        print("PlygonMCP: server stopped")

    def _worker(self):
        if not self._com_owned:
            self._attached.set()
            self._drain_loop()
            return
        if sys.platform != "win32":
            self.start_failure = WINDOWS_ONLY_MESSAGE
            print(f"PlygonMCP: {self.start_failure}")
            self.running = False
            self._attached.set()
            return
        try:
            import pythoncom
        except ImportError:
            self.start_failure = (
                "pywin32 is not installed. On the SOLIDWORKS PC run scripts\\start-solidworks.cmd."
            )
            print(f"PlygonMCP: {self.start_failure}")
            self.running = False
            self._attached.set()
            return
        pythoncom.CoInitialize()
        try:
            try:
                self.session = attach_running_solidworks()
            except SolidWorksUnavailable as exc:
                self.start_failure = str(exc)
                print(f"PlygonMCP: {exc}")
                self.running = False
                self._attached.set()
                return
            self._attached.set()
            self._drain_loop()
        finally:
            pythoncom.CoUninitialize()

    def _drain_loop(self):
        while self.running:
            self._drain_command_queue()
            time.sleep(0.01)

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
                    print(f"PlygonMCP: accept error: {exc}")
                    time.sleep(0.5)
            except Exception as exc:
                print(f"PlygonMCP: server loop error: {exc}")
                if not self.running:
                    break
                time.sleep(0.5)

    def _drain_command_queue(self):
        if not self.running:
            return False

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
                    # COM calls stay on this worker thread. The accept thread
                    # only queues. SolidWorks proxies are apartment-threaded.
                    response = self.execute_command(command)
                payload = _encode_message(response)
            except Exception as exc:
                traceback.print_exc()
                payload = _encode_message({"status": "error", "message": str(exc)})

            try:
                client.sendall(payload)
                command_name = command.get("type") if isinstance(command, dict) else "protocol_error"
                print(f"PlygonMCP: replied {command_name}")
            except Exception:
                print("PlygonMCP: failed to send response (client gone)")
            processed += 1

        return True

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
                        # POSTing to 127.0.0.1:9878). The MCP client always sends a
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
        if cmd_type == "ping":
            return {"status": "success", "result": {"pong": True}}

        if cmd_type not in COMMANDS:
            return {"status": "error", "message": f"Unknown command type: {cmd_type}"}

        session = self.session
        if session is None:
            return {
                "status": "error",
                "message": "The listener is not attached to SOLIDWORKS.",
            }

        session_methods = {
            "get_document_info": "document_info",
            "list_features": "list_features",
            "get_mass_properties": "mass_properties",
            "get_custom_properties": "custom_properties",
            "set_custom_property": "set_custom_property",
            "new_document": "new_document",
            "create_extruded_box": "create_extruded_box",
            "rebuild": "rebuild",
            "save_document": "save_document",
            "export_document": "export_document",
            "execute_code": "execute_code",
            "get_viewport_screenshot": "viewport_screenshot",
        }
        if cmd_type == "get_addon_info":
            handler = self.get_addon_info
        else:
            handler = getattr(session, session_methods[cmd_type])

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
            and name != "self"
        }
        return handler(**{key: value for key, value in params.items() if key in allowed})

    def get_addon_info(self):
        summary = None
        version = "unknown"
        if self.session is not None:
            version = self.session.solidworks_version()
            try:
                summary = self.session.document_summary()
            except Exception:
                summary = None
        return {
            "name": "Plygon SOLIDWORKS MCP",
            "addon_version": [int(part) for part in __version__.split(".")],
            "protocol_version": ADDON_PROTOCOL_VERSION,
            "solidworks_version": version,
            "active_document": summary,
            "capabilities": sorted(COMMANDS),
        }


def main() -> int:
    global _server
    server = SolidWorksMCPServer(
        host=DEFAULT_HOST,
        port=DEFAULT_PORT,
    )
    _server = server
    if not server.start():
        return 1
    print("Leave this window open. Ctrl-C stops the listener. SOLIDWORKS stays open.")
    try:
        while server.running:
            time.sleep(0.2)
    except KeyboardInterrupt:
        print()
    finally:
        server.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
