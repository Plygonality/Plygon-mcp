"""Start the Plygon listener when this folder is on the editor Python path.

The editor runs every ``init_unreal.py`` it finds on ``sys.path`` at startup.
Point Additional Paths at this ``editor`` directory, or add this file under
Project Settings, Plugins, Python, Startup Scripts so it runs after the
level loads. ``start_server`` is safe to call again if both are set.
"""

from __future__ import annotations


def _log_error(message: str) -> None:
    print(message)
    try:
        import unreal
    except ImportError:
        return
    log_error = getattr(unreal, "log_error", None)
    if log_error is not None:
        log_error(message)


try:
    from plygon_unreal_mcp.listener import start_server

    started = start_server()
except Exception as exc:
    _log_error(f"PlygonMCP: failed to start: {exc}")
else:
    if started is None:
        _log_error(
            "PlygonMCP: listener did not start. "
            "After the level is open, run this in the Python console: "
            "from plygon_unreal_mcp.listener import start_server; start_server()"
        )
