"""TCP client that talks to the Plygon Houdini MCP listener."""

from __future__ import annotations

import json
import logging
import os
import socket
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("PlygonHoudiniMCP")

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9877

_state_lock = threading.Lock()


def resolve_loopback_host(host: str) -> str:
    """Windows 'localhost' can be IPv6 (::1) while Houdini binds IPv4."""
    if host in {"localhost", "::1", ""}:
        return "127.0.0.1"
    return host


def encode_message(obj: Any) -> bytes:
    """Serialize one JSON value with a newline frame."""
    return (json.dumps(obj, default=str) + "\n").encode("utf-8")


def extract_json_objects(buffer: bytes) -> Tuple[List[Any], bytes]:
    """Pull every complete JSON value off the front of *buffer*.

    Cursor agents often fire several MCP tools at once. Those requests (and
    Houdini's replies) can arrive concatenated in a single TCP packet.
    ``json.loads`` then raises Extra data; ``JSONDecoder.raw_decode`` does not.
    Incomplete UTF-8 or incomplete JSON stays in the leftover bytes.
    """
    objects: List[Any] = []
    rest = buffer
    while True:
        obj, rest = extract_one_json(rest)
        if obj is None:
            return objects, rest
        objects.append(obj)


def extract_one_json(buffer: bytes) -> Tuple[Optional[Any], bytes]:
    """Return the first complete JSON value and leftover bytes."""
    try:
        text = buffer.decode("utf-8")
    except UnicodeDecodeError:
        return None, buffer

    decoder = json.JSONDecoder()
    idx = 0
    length = len(text)
    while idx < length and text[idx].isspace():
        idx += 1
    if idx >= length:
        return None, b""
    try:
        obj, end = decoder.raw_decode(text, idx)
    except json.JSONDecodeError:
        return None, buffer
    if end <= idx:
        return None, buffer
    return obj, text[end:].encode("utf-8")


@dataclass
class HoudiniConnection:
    host: str
    port: int
    sock: Optional[socket.socket] = None
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _recv_buf: bytes = field(default=b"", repr=False)

    def connect(self) -> bool:
        if self.sock:
            return True
        try:
            host = resolve_loopback_host(self.host)
            self.sock = socket.create_connection((host, self.port), timeout=10)
            self._recv_buf = b""
            logger.info("Connected to Houdini at %s:%s", host, self.port)
            return True
        except Exception as e:
            logger.error("Failed to connect to Houdini: %s", e)
            self._reset_socket()
            return False

    def disconnect(self) -> None:
        self._reset_socket()

    def _reset_socket(self) -> None:
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None
        self._recv_buf = b""

    def receive_full_response(self, sock: socket.socket, buffer_size: int = 8192) -> Dict[str, Any]:
        sock.settimeout(180.0)
        saw_data = bool(self._recv_buf)

        while True:
            obj, self._recv_buf = extract_one_json(self._recv_buf)
            if obj is not None:
                if not isinstance(obj, dict):
                    raise ValueError(f"Houdini response was not a JSON object: {obj!r}")
                return obj
            try:
                chunk = sock.recv(buffer_size)
            except socket.timeout as e:
                if not saw_data:
                    raise TimeoutError("No data received from Houdini") from e
                raise ValueError("Incomplete JSON response from Houdini: timed out") from e
            if not chunk:
                if not saw_data:
                    raise ConnectionError("Connection closed before receiving any data")
                raise ValueError("Incomplete JSON response from Houdini: connection closed")
            saw_data = True
            self._recv_buf += chunk

    def send_command(self, command_type: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        with self._lock:
            return self._send_command_locked(command_type, params)

    def _send_command_locked(
        self, command_type: str, params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        if not self.sock and not self.connect():
            raise ConnectionError(
                "Not connected to Houdini. Open Houdini, install the Plygon MCP package, "
                "and click Start MCP Server on the shelf."
            )

        command = {"type": command_type, "params": params or {}}
        try:
            assert self.sock is not None
            self.sock.sendall(encode_message(command))
            self.sock.settimeout(180.0)
            response = self.receive_full_response(self.sock)

            if response.get("status") == "error":
                raise RuntimeError(response.get("message", "Unknown error from Houdini"))
            return response.get("result") or {}
        except socket.timeout as e:
            self._reset_socket()
            raise TimeoutError(
                "Timeout waiting for Houdini. Simplify the request, or ensure Houdini "
                "is running with a GUI (not hython -c batch mode)."
            ) from e
        except (ConnectionError, BrokenPipeError, ConnectionResetError) as e:
            self._reset_socket()
            raise ConnectionError(f"Connection to Houdini lost: {e}") from e
        except RuntimeError:
            raise
        except Exception:
            self._reset_socket()
            raise


_houdini_connection: Optional[HoudiniConnection] = None


def get_houdini_connection() -> HoudiniConnection:
    global _houdini_connection

    with _state_lock:
        if _houdini_connection is not None and _houdini_connection.sock is not None:
            return _houdini_connection

        host = os.getenv("HOUDINI_HOST", DEFAULT_HOST)
        port = int(os.getenv("HOUDINI_PORT", str(DEFAULT_PORT)))
        _houdini_connection = HoudiniConnection(host=host, port=port)
        if not _houdini_connection.connect():
            _houdini_connection = None
            raise ConnectionError(
                "Could not connect to Houdini. Make sure the Plygon Houdini MCP listener "
                "is running (shelf tool: Start MCP Server)."
            )
        return _houdini_connection


def reset_connection() -> None:
    global _houdini_connection
    with _state_lock:
        if _houdini_connection:
            _houdini_connection.disconnect()
        _houdini_connection = None
