from __future__ import annotations

import io
import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.filters.command import CommandObject
from aiogram.types import Message

from app.config import Settings
from app.db.mappings import CardMappingsRepository
from app.integrations.planka_client import PlankaAuthError, PlankaClient, PlankaClientError

router = Router(name="commands")
logger = logging.getLogger(__name__)
_TELEGRAM_MAX_MESSAGE_LENGTH = 4096
_CHECKLIST_POSITION_STEP = 65536.0


@router.message(Command("start"))
async def start_command(message: Message) -> None:
    await message.answer(
        "Hi! I am your Planka bot.\n"
        "Use /help to see available commands."
    )


@router.message(Command("help"))
async def help_command(message: Message) -> None:
    await message.answer(
        "Available commands:\n"
        "/start - Start the bot\n"
        "/help - Show this help message\n"
        "/boards - List your Planka boards\n"
        "/todo {task_name} - Create a task in TODO\n"
        "/todo - List TODO tasks\n"
        "/doing {id} - Move task to IN PROGRESS\n"
        "/done {id} - Move task to DONE",
        parse_mode=None,
    )


@router.message(Command("todo"))
async def todo_command(
    message: Message,
    command: CommandObject,
    planka: PlankaClient,
    mappings: CardMappingsRepository,
    settings: Settings,
) -> None:
    args = (command.args or "").strip()
    logger.info("Received /todo command args=%r", args)

    try:
        if args:
            card_name, checklist_items = _parse_todo_args(args)

            created = await planka.create_card(
                settings.planka_todo_list_id,
                name=card_name,
                card_type=settings.planka_card_type,
            )
            card_id = str(created.get("id", ""))
            if not card_id:
                await message.answer("Planka returned an invalid card response.", parse_mode=None)
                return
            short_id = await mappings.get_or_create_short_id(card_id)

            # Create checklist if items were provided
            items_created = 0
            if checklist_items:
                task_list = await planka.create_task_list(card_id, name="Checklist")
                task_list_id = str(task_list.get("id", ""))
                if task_list_id:
                    for idx, item_name in enumerate(checklist_items):
                        position = _CHECKLIST_POSITION_STEP * (idx + 1)
                        await planka.create_task(task_list_id, name=item_name, position=position)
                        items_created += 1

            # Upload photo attachment if present
            attachment_created = await _upload_photo_if_present(message, planka, card_id)

            reply = _build_create_reply(short_id, items_created, attachment_created)
            await message.answer(reply, parse_mode=None)
            return

        cards = await planka.get_cards(settings.planka_todo_list_id)
        if not cards:
            await message.answer("TODO list is empty.", parse_mode=None)
            return

        lines: list[str] = []
        for card in cards:
            card_id = str(card.get("id", ""))
            if not card_id:
                continue
            short_id = await mappings.get_or_create_short_id(card_id)
            name = str(card.get("name") or "Untitled")
            description = str(card.get("description") or "").strip()
            line = f"- {short_id} | {name}"
            if description:
                line = f"{line} - {description}"
            lines.append(line)

        if not lines:
            await message.answer("TODO list is empty.", parse_mode=None)
            return
        await _answer_chunked(message, "TODO tasks:\n", lines)
    except PlankaAuthError:
        await message.answer(
            "Planka authentication failed. Check PLANKA_USERNAME_OR_EMAIL and PLANKA_PASSWORD.",
            parse_mode=None,
        )
    except PlankaClientError as exc:
        logger.exception("Failed to handle /todo command")
        error_text = str(exc)
        if "List not found" in error_text:
            await message.answer(
                "Planka write failed: list is not writable for this account. "
                "Check PLANKA_*_LIST_ID and ensure your user is a project manager on the board.",
                parse_mode=None,
            )
            return
        await message.answer(f"Planka request failed: {exc}", parse_mode=None)


@router.message(Command("doing"))
async def doing_command(
    message: Message,
    command: CommandObject,
    planka: PlankaClient,
    mappings: CardMappingsRepository,
    settings: Settings,
) -> None:
    args = (command.args or "").strip()
    logger.info("Received /doing command args=%r", args)

    if not args:
        await message.answer("Usage: /doing {id}", parse_mode=None)
        return

    await _move_task(
        message=message,
        input_id=args.split()[0],
        target_list_id=settings.planka_doing_list_id,
        done_message="moved to IN PROGRESS",
        planka=planka,
        mappings=mappings,
    )


@router.message(Command("done"))
async def done_command(
    message: Message,
    command: CommandObject,
    planka: PlankaClient,
    mappings: CardMappingsRepository,
    settings: Settings,
) -> None:
    args = (command.args or "").strip()
    logger.info("Received /done command args=%r", args)

    if not args:
        await message.answer("Usage: /done {id}", parse_mode=None)
        return

    await _move_task(
        message=message,
        input_id=args.split()[0],
        target_list_id=settings.planka_done_list_id,
        done_message="moved to DONE",
        planka=planka,
        mappings=mappings,
    )


@router.message(Command("boards"))
async def boards_command(message: Message, planka: PlankaClient, settings: Settings) -> None:
    if not settings.planka_username_or_email or not settings.planka_password:
        await message.answer("Planka integration is not configured yet.", parse_mode=None)
        return

    try:
        boards = await planka.list_boards()
    except PlankaAuthError:
        await message.answer(
            "Planka authentication failed. Check PLANKA_USERNAME_OR_EMAIL and PLANKA_PASSWORD.",
            parse_mode=None,
        )
        return
    except PlankaClientError as exc:
        await message.answer(f"Planka request failed: {exc}", parse_mode=None)
        return

    if not boards:
        await message.answer("No boards were found for this Planka account.", parse_mode=None)
        return

    formatted = "\n".join(
        f"- {board.get('name', 'Unnamed board')} (id: {board.get('id', 'n/a')})"
        for board in boards[:20]
    )
    await message.answer(f"Your boards:\n{formatted}", parse_mode=None)


async def _answer_chunked(message: Message, header: str, lines: list[str]) -> None:
    chunk = header
    for line in lines:
        safe_line = line
        if len(safe_line) > 1000:
            safe_line = f"{safe_line[:997]}..."
        candidate = f"{chunk}{safe_line}\n"
        if len(candidate) > _TELEGRAM_MAX_MESSAGE_LENGTH:
            await message.answer(chunk.rstrip(), parse_mode=None)
            chunk = f"{safe_line}\n"
            continue
        chunk = candidate

    if chunk.strip():
        await message.answer(chunk.rstrip(), parse_mode=None)


def _parse_todo_args(args: str) -> tuple[str, list[str]]:
    """Split multi-line ``/todo`` args into card name and checklist items.

    Returns ``(card_name, checklist_items)`` where *checklist_items* may be
    empty if no ``- `` prefixed lines are present.
    """
    raw_lines = args.split("\n")
    card_name = raw_lines[0].strip()
    checklist_items: list[str] = []
    for line in raw_lines[1:]:
        stripped = line.strip()
        if stripped.startswith("- "):
            item = stripped[2:].strip()
            if item:
                checklist_items.append(item)
    return card_name, checklist_items


async def _upload_photo_if_present(
    message: Message,
    planka: PlankaClient,
    card_id: str,
) -> bool:
    """Download the attached photo (if any) and upload it to Planka.

    Returns ``True`` if an attachment was successfully uploaded.
    """
    if not message.photo:
        return False

    # Telegram sends multiple sizes; pick the largest (last in list).
    photo = message.photo[-1]
    file_name = f"{photo.file_unique_id}.jpg"

    try:
        buf = io.BytesIO()
        await message.bot.download(photo, destination=buf)
        file_bytes = buf.getvalue()
        if not file_bytes:
            logger.warning("Downloaded photo is empty, skipping attachment upload")
            return False

        await planka.create_attachment(card_id, file_name=file_name, file_bytes=file_bytes)
        return True
    except Exception:
        logger.exception("Failed to upload photo attachment for card %s", card_id)
        return False


def _build_create_reply(short_id: int, items_count: int, has_attachment: bool) -> str:
    """Build a human-friendly reply for a newly-created card."""
    parts: list[str] = []
    if items_count:
        parts.append(f"{items_count} item{'s' if items_count != 1 else ''}")
    if has_attachment:
        parts.append("1 attachment")
    suffix = f" ({', '.join(parts)})" if parts else ""
    return f"task {short_id} created{suffix}"


async def _move_task(
    message: Message,
    input_id: str,
    target_list_id: str,
    done_message: str,
    planka: PlankaClient,
    mappings: CardMappingsRepository,
) -> None:
    try:
        card_id = await mappings.resolve_card_id(input_id)
        if not card_id:
            await message.answer(f"Task '{input_id}' was not found.", parse_mode=None)
            return

        await planka.move_card(card_id=card_id, list_id=target_list_id)
        await message.answer(f"{input_id} {done_message}", parse_mode=None)
    except PlankaAuthError:
        await message.answer(
            "Planka authentication failed. Check PLANKA_USERNAME_OR_EMAIL and PLANKA_PASSWORD.",
            parse_mode=None,
        )
    except PlankaClientError as exc:
        logger.exception("Failed to move task", extra={"input_id": input_id})
        await message.answer(f"Planka request failed: {exc}", parse_mode=None)
