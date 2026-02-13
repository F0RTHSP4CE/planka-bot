"""Format and send Planka action notifications to Telegram."""

from __future__ import annotations

import html
from typing import Any

from aiogram import Bot


def _resolve_author(user_id: str | None, users: list[dict[str, Any]]) -> str:
    if not user_id:
        return "Unknown"
    for u in users:
        if str(u.get("id")) == str(user_id):
            return str(u.get("name") or u.get("username") or "Unknown")
    return "Unknown"


def _card_link(card_name: str, card_url: str) -> str:
    """Return HTML link: card name as clickable text, URL hidden."""
    return f'<a href="{html.escape(card_url)}">{html.escape(card_name)}</a>'


def _format_card_created(
    author: str,
    card_name: str,
    card_url: str,
    to_list_name: str,
    board_name: str,
) -> str:
    return (
        f"Card Created\n\n"
        f"{author} created {_card_link(card_name, card_url)} "
        f"in {html.escape(to_list_name)} on {html.escape(board_name)}"
    )


def _format_card_moved(
    author: str,
    card_name: str,
    card_url: str,
    from_list_name: str,
    to_list_name: str,
    board_name: str,
) -> str:
    return (
        f"Card Moved\n\n"
        f"{author} moved {_card_link(card_name, card_url)} "
        f"from {html.escape(from_list_name)} to {html.escape(to_list_name)} on {html.escape(board_name)}"
    )


async def format_and_send(
    bot: Bot,
    chat_id: str,
    action: dict[str, Any],
    users: list[dict[str, Any]],
    base_url: str,
    board_name: str = "TASKS",
    message_thread_id: int | None = None,
    *,
    allowed_chat_ids: frozenset[str] | None = None,
) -> None:
    """Format a Planka action and send it to the given Telegram chat.
    Only sends to chats in allowed_chat_ids (if provided). Never broadcasts to users who started the bot.
    """
    if allowed_chat_ids is not None and str(chat_id) not in allowed_chat_ids:
        return  # Safety: never send to unconfigured chats
    action_type = action.get("type")
    card_id = str(action.get("cardId", ""))
    user_id = action.get("userId")
    data = action.get("data") or {}
    card = data.get("card") or {}
    card_name = str(card.get("name") or "Untitled")
    card_url = f"{base_url.rstrip('/')}/cards/{card_id}" if card_id else base_url

    author = _resolve_author(user_id, users)

    if action_type == "createCard":
        to_list = data.get("toList") or data.get("list") or {}
        to_list_name = str(to_list.get("name") or "?")
        text = _format_card_created(author, card_name, card_url, to_list_name, board_name)
    elif action_type == "moveCard":
        from_list = data.get("fromList") or {}
        to_list = data.get("toList") or {}
        from_list_name = str(from_list.get("name") or "?")
        to_list_name = str(to_list.get("name") or "?")
        if to_list.get("type") == "trash" or to_list_name == "?":
            to_list_name = "Trash"
        text = _format_card_moved(
            author, card_name, card_url, from_list_name, to_list_name, board_name
        )
    else:
        return

    kwargs: dict = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if message_thread_id is not None:
        kwargs["message_thread_id"] = message_thread_id
    await bot.send_message(**kwargs)
