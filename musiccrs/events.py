"""Lightweight event bridge so non-server modules can emit Socket.IO events.

Server (musiccrs.py) should call set_emitter once with a function like:
    set_emitter(lambda event, payload: platform.socketio.emit(event, payload))

Other modules can then call emit(event, payload) safely.
"""
from typing import Callable, Optional, Any

_emitter: Optional[Callable[[str, Any], None]] = None


def set_emitter(fn: Callable[[str, Any], None]) -> None:
    global _emitter
    _emitter = fn


def emit(event: str, payload: Any) -> None:
    try:
        if _emitter is not None:
            _emitter(event, payload)
    except Exception:
        # Silently ignore emit errors to avoid breaking chat responses
        pass
