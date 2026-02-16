"""Track bot-originated Planka actions for correct author attribution in notifications."""

from __future__ import annotations

import threading
import time

_recent: dict[tuple[str, str], tuple[float, str]] = {}
_lock = threading.Lock()
_TTL = 120  # seconds


def register_bot_action(card_id: str, action_type: str, telegram_author: str) -> None:
    """Record that the bot performed this action on behalf of a Telegram user."""
    with _lock:
        _recent[(card_id, action_type)] = (time.monotonic(), telegram_author)


def consume_if_bot_action(card_id: str, action_type: str) -> str | None:
    """Return the Telegram author if this was bot-originated, else None."""
    with _lock:
        key = (card_id, action_type)
        if key not in _recent:
            return None
        ts, author = _recent[key]
        if time.monotonic() - ts > _TTL:
            del _recent[key]
            return None
        del _recent[key]
        return author
