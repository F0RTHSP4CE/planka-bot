"""Background poller for Planka board actions; sends notifications to Telegram."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from aiogram import Bot

from app.bot_actions import consume_if_bot_action
from app.config import Settings
from app.integrations.planka_client import PlankaClient, PlankaClientError
from app.notifications import format_and_send

logger = logging.getLogger(__name__)

_RELEVANT_TYPES = frozenset({"createCard", "moveCard"})


async def run_action_poller(
    bot: Bot,
    planka: PlankaClient,
    settings: Settings,
) -> None:
    """Poll Planka board actions and send notifications to Telegram."""
    targets = settings.get_notification_targets()
    board_id = settings.planka_board_id
    if not targets or not board_id:
        logger.info(
            "Action poller disabled: TELEGRAM_NOTIFICATION_CHAT_IDS/CHAT_ID or PLANKA_BOARD_ID not set"
        )
        return

    base_url = str(settings.planka_base_url)
    interval = settings.planka_poll_interval_seconds
    last_seen_id: str | None = None

    # Safety: only send to explicitly configured chats, never to arbitrary users
    allowed_chat_ids = frozenset(str(cid) for cid, _ in targets)
    logger.info(
        "Action poller started: notifications only to %s",
        sorted(allowed_chat_ids),
    )

    while True:
        try:
            payload = await planka.get_board_actions(board_id)
            items = payload.get("items")
            if not isinstance(items, list):
                await asyncio.sleep(interval)
                continue

            included = payload.get("included") or {}
            users = included.get("users")
            if not isinstance(users, list):
                users = []

            # Actions are returned newest first; process only those newer than last_seen_id
            for action in items:
                if not isinstance(action, dict):
                    continue
                aid = str(action.get("id", ""))
                if not aid:
                    continue

                if last_seen_id is None:
                    last_seen_id = aid
                    break

                if not _action_newer(aid, last_seen_id):
                    break

                if action.get("type") not in _RELEVANT_TYPES:
                    last_seen_id = aid
                    continue

                card_id = str(action.get("cardId", ""))
                tg_author = consume_if_bot_action(card_id, action.get("type", ""))

                for chat_id, thread_id in targets:
                    try:
                        await format_and_send(
                            bot=bot,
                            chat_id=chat_id,
                            action=action,
                            users=users,
                            base_url=base_url,
                            board_name="TASKS",
                            message_thread_id=thread_id,
                            allowed_chat_ids=allowed_chat_ids,
                            author_override=tg_author,
                        )
                    except Exception:
                        logger.exception(
                            "Failed to send notification for action %s to %s", aid, chat_id
                        )

                last_seen_id = aid

            if items and isinstance(items[0], dict):
                newest_id = str(items[0].get("id", ""))
                if newest_id:
                    last_seen_id = newest_id

        except PlankaClientError as exc:
            logger.warning("Action poller Planka error: %s", exc)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Action poller error")

        await asyncio.sleep(interval)


def _action_newer(aid: str, last_id: str) -> bool:
    """Planka IDs are snowflake-like; larger = newer."""
    try:
        return int(aid) > int(last_id)
    except (ValueError, TypeError):
        return aid != last_id
