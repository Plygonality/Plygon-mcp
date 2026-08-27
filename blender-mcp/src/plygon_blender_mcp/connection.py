"""TCP client that talks to the Plygon Blender MCP addon."""

from __future__ import annotations

import json
import logging
import os
import socket
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

logger = logging.getLogger("PlygonBlenderMCP")

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 9876


@dataclass
class BlenderConnection:
    host: str
    port: int
    sock: Optional[socket.socket] = None
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def connect(self) -> bool:
        if self.sock:
            return True
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((self.host, self.port))
            logger.info("Connected to Blender at %s:%s", self.host, self.port)
            return True
        except Exception as e:
            logger.error("Failed to connect to Blender: %s", e)
            self.sock = None
            return False

    def disconnect(self) -> None:
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None

    def receive_full_response(self, sock: socket.socket, buffer_size: int = 8192) -> bytes:
        chunks: list[bytes] = []
        sock.settimeout(180.0)

        while True:
            try:
                chunk = sock.recv(buffer_size)
                if not chunk:
                    if not chunks:
                        raise ConnectionError("Connection closed before receiving any data")
                    break
                chunks.append(chunk)
                data = b"".join(chunks)
                try:
                    json.loads(data.decode("utf-8"))
                    return data
                except json.JSONDecodeError:
                    continue
            except socket.timeout:
                break

        if not chunks:
            raise TimeoutError("No data received from Blender")
        data = b"".join(chunks)
        try:
            json.loads(data.decode("utf-8"))
            return data
        except json.JSONDecodeError as e:
            raise ValueError(f"Incomplete JSON response from Blender: {e}") from e

    def send_command(self, command_type: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        with self._lock:
            return self._send_command_locked(command_type, params)

    def _send_command_locked(
        self, command_type: str, params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        if not self.sock and not self.connect():
            raise ConnectionError(
                "Not connected to Blender. Open Blender, enable the Plygon MCP addon, "
                "and click Start MCP Server in the N-panel (PlygonMCP tab)."
            )

        command = {"type": command_type, "params": params or {}}
        try:
            assert self.sock is not None
            self.sock.sendall(json.dumps(command).encode("utf-8"))
            self.sock.settimeout(180.0)
            response_data = self.receive_full_response(self.sock)
            response = json.loads(response_data.decode("utf-8"))

            if response.get("status") == "error":
                raise RuntimeError(response.get("message", "Unknown error from Blender"))
            return response.get("result") or {}
        except socket.timeout as e:
            self.sock = None
            raise TimeoutError(
                "Timeout waiting for Blender. Simplify the request, or ensure Blender "
                "is running with a GUI (not blender -b)."
            ) from e
        except (ConnectionError, BrokenPipeError, ConnectionResetError) as e:
            self.sock = None
            raise ConnectionError(f"Connection to Blender lost: {e}") from e
        except Exception:
            self.sock = None
            raise


_blender_connection: Optional[BlenderConnection] = None


def get_blender_connection() -> BlenderConnection:
    global _blender_connection

    if _blender_connection is not None and _blender_connection.sock is not None:
        return _blender_connection

    host = os.getenv("BLENDER_HOST", DEFAULT_HOST)
    port = int(os.getenv("BLENDER_PORT", str(DEFAULT_PORT)))
    _blender_connection = BlenderConnection(host=host, port=port)
    if not _blender_connection.connect():
        _blender_connection = None
        raise ConnectionError(
            "Could not connect to Blender. Make sure the Plygon Blender MCP addon "
            "is enabled and Start MCP Server has been clicked."
        )
    return _blender_connection


def reset_connection() -> None:
    global _blender_connection
    if _blender_connection:
        _blender_connection.disconnect()
    _blender_connection = None
