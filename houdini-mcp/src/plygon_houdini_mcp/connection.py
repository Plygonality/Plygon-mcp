"""TCP client that talks to the Plygon Houdini MCP listener."""

from __future__ import annotations

import json
import logging
import os
import socket
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

logger = logging.getLogger("PlygonHoudiniMCP")

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 9877


@dataclass
class HoudiniConnection:
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
            logger.info("Connected to Houdini at %s:%s", self.host, self.port)
            return True
        except Exception as e:
            logger.error("Failed to connect to Houdini: %s", e)
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
            raise TimeoutError("No data received from Houdini")
        data = b"".join(chunks)
        try:
            json.loads(data.decode("utf-8"))
            return data
        except json.JSONDecodeError as e:
            raise ValueError(f"Incomplete JSON response from Houdini: {e}") from e

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
            self.sock.sendall(json.dumps(command).encode("utf-8"))
            self.sock.settimeout(180.0)
            response_data = self.receive_full_response(self.sock)
            response = json.loads(response_data.decode("utf-8"))

            if response.get("status") == "error":
                raise RuntimeError(response.get("message", "Unknown error from Houdini"))
            return response.get("result") or {}
        except socket.timeout as e:
            self.sock = None
            raise TimeoutError(
                "Timeout waiting for Houdini. Simplify the request, or ensure Houdini "
                "is running with a GUI (not hython -c batch mode)."
            ) from e
        except (ConnectionError, BrokenPipeError, ConnectionResetError) as e:
            self.sock = None
            raise ConnectionError(f"Connection to Houdini lost: {e}") from e
        except Exception:
            self.sock = None
            raise


_houdini_connection: Optional[HoudiniConnection] = None


def get_houdini_connection() -> HoudiniConnection:
    global _houdini_connection

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
    if _houdini_connection:
        _houdini_connection.disconnect()
    _houdini_connection = None
