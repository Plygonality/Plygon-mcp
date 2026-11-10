"""TCP client that talks to the Plygon Unreal MCP listener."""

from __future__ import annotations

import json
import logging
import os
import socket
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("PlygonUnrealMCP")

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9879
MAX_BUFFER_BYTES = 4 * 1024 * 1024

REFUSED_MESSAGE = (
    "Could not connect to Unreal Editor on {host}:{port} (connection refused). "
    "Cursor already spawned the MCP process. The editor listener is not running. "
    "Open the Unreal Editor (not a commandlet), enable the Python Editor Script Plugin, "
    "start the listener, and confirm the Output Log says listening on {host}:{port}. "
    "A green row in Cursor's MCP settings is not enough. "
    "Ping from a local Agent chat, not a Cloud Agent."
)

TIMEOUT_MESSAGE = (
    "Timeout waiting for Unreal Editor after connecting to {host}:{port}. "
    "Keep the editor in the foreground with a level open. "
    "Do not ping from a Cloud Agent. If the editor is frozen, close it and start the listener again."
)

_state_lock = threading.Lock()


def resolve_loopback_host(host: str) -> str:
    """Windows 'localhost' can be IPv6 (::1) while the listener binds IPv4."""
    if host in {"localhost", "::1", ""}:
        return "127.0.0.1"
    return host


def encode_message(obj: Any) -> bytes:
    """Serialize one JSON value with a newline frame."""
    return (json.dumps(obj, default=str) + "\n").encode("utf-8")


def extract_json_objects(buffer: bytes) -> Tuple[List[Any], bytes]:
    """Pull every complete JSON value off the front of *buffer*.

    Cursor agents often fire several MCP tools at once. Those requests (and
    the editor's replies) can arrive concatenated in a single TCP packet.
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
class UnrealConnection:
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
            logger.info("Connected to Unreal Editor at %s:%s", host, self.port)
            return True
        except ConnectionRefusedError as e:
            logger.error("Unreal Editor refused the connection at %s:%s: %s", self.host, self.port, e)
            self._reset_socket()
            return False
        except (TimeoutError, socket.timeout) as e:
            logger.error("Timed out connecting to Unreal Editor at %s:%s: %s", self.host, self.port, e)
            self._reset_socket()
            return False
        except Exception as e:
            logger.error("Failed to connect to Unreal Editor: %s", e)
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
                    raise ValueError(f"Unreal Editor response was not a JSON object: {obj!r}")
                return obj
            try:
                chunk = sock.recv(buffer_size)
            except socket.timeout as e:
                if not saw_data:
                    raise TimeoutError("No data received from Unreal Editor") from e
                raise TimeoutError("Incomplete JSON response from Unreal Editor: timed out") from e
            if not chunk:
                if not saw_data:
                    raise ConnectionError("Connection closed before receiving any data")
                raise ConnectionError("Incomplete JSON response from Unreal Editor: connection closed")
            saw_data = True
            self._recv_buf += chunk
            if len(self._recv_buf) > MAX_BUFFER_BYTES:
                raise ConnectionError(
                    f"Unreal Editor response exceeded {MAX_BUFFER_BYTES} buffered bytes"
                )

    def send_command(self, command_type: str, params: Optional[Dict[str, Any]] = None) -> Any:
        with self._lock:
            return self._send_command_locked(command_type, params)

    def _send_command_locked(
        self, command_type: str, params: Optional[Dict[str, Any]] = None
    ) -> Any:
        if not self.sock and not self.connect():
            raise ConnectionError(
                REFUSED_MESSAGE.format(host=resolve_loopback_host(self.host), port=self.port)
            )

        command = {"type": command_type, "params": params or {}}
        try:
            assert self.sock is not None
            self.sock.sendall(encode_message(command))
            self.sock.settimeout(180.0)
            response = self.receive_full_response(self.sock)

            if response.get("status") == "error":
                raise RuntimeError(response.get("message", "Unknown error from Unreal Editor"))
            if response.get("status") != "success":
                raise ValueError(f"Malformed response from Unreal Editor: {response!r}")
            return response["result"] if "result" in response else {}
        except (TimeoutError, socket.timeout) as e:
            self._reset_socket()
            raise TimeoutError(
                TIMEOUT_MESSAGE.format(host=resolve_loopback_host(self.host), port=self.port)
            ) from e
        except (ConnectionError, BrokenPipeError, ConnectionResetError) as e:
            self._reset_socket()
            raise ConnectionError(f"Connection to Unreal Editor lost: {e}") from e
        except (RuntimeError, ValueError):
            raise
        except Exception:
            self._reset_socket()
            raise


_unreal_connection: Optional[UnrealConnection] = None


def get_unreal_connection() -> UnrealConnection:
    global _unreal_connection

    with _state_lock:
        if _unreal_connection is not None and _unreal_connection.sock is not None:
            return _unreal_connection

        host = os.getenv("UNREAL_HOST", DEFAULT_HOST)
        port = int(os.getenv("UNREAL_PORT", str(DEFAULT_PORT)))
        _unreal_connection = UnrealConnection(host=host, port=port)
        if not _unreal_connection.connect():
            host = resolve_loopback_host(_unreal_connection.host)
            port = _unreal_connection.port
            _unreal_connection = None
            raise ConnectionError(REFUSED_MESSAGE.format(host=host, port=port))
        return _unreal_connection


def reset_connection() -> None:
    global _unreal_connection
    with _state_lock:
        if _unreal_connection:
            _unreal_connection.disconnect()
        _unreal_connection = None
