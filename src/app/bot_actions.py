"""Track bot-originated Planka actions for correct author attribution in notifications."""

from __future__ import annotations

import threading
import time

_recent: dict[tuple[str, str], float] = {}
_lock = threading.Lock()
_TTL = 120  # seconds


def register_bot_action(card_id: str, action_type: str) -> None:
    """Record that the bot performed this action (called by command handlers)."""
    with _lock:
        _recent[(card_id, action_type)] = time.monotonic()


def consume_if_bot_action(card_id: str, action_type: str) -> bool:
    """Return True if this action was bot-originated (and remove from store)."""
    with _lock:
        key = (card_id, action_type)
        if key not in _recent:
            return False
        t = _recent[key]
        if time.monotonic() - t > _TTL:
            del _recent[key]
            return False
        del _recent[key]
        return True
