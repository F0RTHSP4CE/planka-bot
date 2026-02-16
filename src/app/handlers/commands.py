from __future__ import annotations

import html
import io
import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.filters.command import CommandObject
from aiogram.types import BufferedInputFile, Message

from app.bot_actions import register_bot_action
from app.config import Settings
from app.db.mappings import CardMappingsRepository
from app.integrations.planka_client import PlankaAuthError, PlankaClient, PlankaClientError

router = Router(name="commands")
logger = logging.getLogger(__name__)
_TELEGRAM_MAX_MESSAGE_LENGTH = 4096
_CHECKLIST_POSITION_STEP = 65536.0


def _telegram_author(message: Message) -> str:
    """Build a display name from the Telegram user who sent the message."""
    user = message.from_user
    if user and user.username:
        return f"@{user.username}"
    if user and user.first_name:
        return user.first_name
    return "Someone"


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
        "/task {id} - Show full task details (title, description, checklist, images)\n"
        "/doing {id} - Move task to IN PROGRESS\n"
        "/done {id} - Move task to DONE\n"
        "/backtodo {id} - Move task back to TODO",
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
            register_bot_action(card_id, "createCard", _telegram_author(message))

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
            lines.append(f"- {short_id} | {name}")

        if not lines:
            await message.answer("TODO list is empty.", parse_mode=None)
            return
        await _answer_chunked(message, "TODO tasks:\n", lines)
    except PlankaAuthError:
        await message.answer(
            "Planka authentication failed. Check PLANKA_USERNAME_OR_EMAIL and PLANKA_PASSWORD.",
            parse_mode=None,
        )
    except PlankaClientError:
        logger.exception("Failed to handle /todo command")
        error_text = str(exc)
        if "List not found" in error_text:
            await message.answer(
                "Planka write failed: list is not writable for this account. "
                "Check PLANKA_*_LIST_ID and ensure your user is a project manager on the board.",
                parse_mode=None,
            )
            return
        await message.answer("Planka request failed. Please try again.", parse_mode=None)


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


@router.message(Command("backtodo"))
async def backtodo_command(
    message: Message,
    command: CommandObject,
    planka: PlankaClient,
    mappings: CardMappingsRepository,
    settings: Settings,
) -> None:
    args = (command.args or "").strip()
    if not args:
        await message.answer("Usage: /backtodo {id}", parse_mode=None)
        return
    await _move_task(
        message=message,
        input_id=args.split()[0],
        target_list_id=settings.planka_todo_list_id,
        done_message="moved back to TODO",
        planka=planka,
        mappings=mappings,
        position_at_top=True,
    )


@router.message(Command("task"))
async def task_command(
    message: Message,
    command: CommandObject,
    planka: PlankaClient,
    mappings: CardMappingsRepository,
) -> None:
    args = (command.args or "").strip()
    logger.info("Received /task command args=%r", args)

    if not args:
        await message.answer("Usage: /task {id}", parse_mode=None)
        return

    input_id = args.split()[0]
    card_id = await mappings.resolve_card_id(input_id)
    if not card_id:
        await message.answer(f"Task '{input_id}' was not found.", parse_mode=None)
        return

    try:
        payload = await planka.get_card(card_id)
        if not payload:
            await message.answer(f"Task '{input_id}' was not found.", parse_mode=None)
            return

        card = payload.get("item") or payload
        included = payload.get("included") or {}
        task_lists = included.get("taskLists") or []
        all_tasks = included.get("tasks") or []
        attachments = included.get("attachments") or []

        title = html.escape(str(card.get("name") or "Untitled"))
        description = html.escape((card.get("description") or "").strip())

        # Group tasks by taskListId
        tasks_by_list: dict[str, list[dict]] = {}
        for t in all_tasks:
            tl_id = str(t.get("taskListId", ""))
            if tl_id:
                tasks_by_list.setdefault(tl_id, []).append(t)

        checklist_lines: list[str] = []
        for tl in task_lists:
            tl_name = html.escape(str(tl.get("name") or "Checklist"))
            tl_id = str(tl.get("id", ""))
            if not tl_id:
                continue
            tasks = tasks_by_list.get(tl_id, [])
            if not tasks:
                checklist_lines.append(f"• {tl_name}: (empty)")
            else:
                items: list[str] = []
                for t in tasks:
                    name = html.escape(str(t.get("name") or ""))
                    is_done = t.get("isCompleted", False)
                    prefix = "☑" if is_done else "☐"
                    items.append(f"  {prefix} {name}")
                checklist_lines.append(f"• {tl_name}:")
                checklist_lines.extend(items)
        image_extensions = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
        image_attachments: list[tuple[str, str]] = []
        for att in attachments:
            att_id = str(att.get("id", ""))
            name = str(att.get("name") or "").lower()
            if att_id and any(name.endswith(ext) for ext in image_extensions):
                image_attachments.append((att_id, name or "image.jpg"))

        text_parts: list[str] = [f"<b>{title}</b>"]
        if description:
            text_parts.append(f"\n{description}")
        if checklist_lines:
            text_parts.append("\n<b>Checklist:</b>")
            text_parts.extend(checklist_lines)

        text = "\n".join(text_parts)
        if text:
            await message.answer(text, parse_mode="HTML")

        for att_id, filename in image_attachments:
            data = await planka.download_attachment(att_id, filename)
            if data:
                try:
                    await message.answer_photo(
                        BufferedInputFile(data, filename=filename or "image.jpg"),
                    )
                except Exception:
                    logger.exception("Failed to send attachment %s as photo", att_id)
    except PlankaAuthError:
        await message.answer(
            "Planka authentication failed. Check PLANKA_USERNAME_OR_EMAIL and PLANKA_PASSWORD.",
            parse_mode=None,
        )
    except PlankaClientError:
        logger.exception("Failed to handle /task command")
        await message.answer("Planka request failed. Please try again.", parse_mode=None)


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
    except PlankaClientError:
        logger.exception("Failed to list boards")
        await message.answer("Planka request failed. Please try again.", parse_mode=None)
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
    *,
    position_at_top: bool = False,
) -> None:
    try:
        card_id = await mappings.resolve_card_id(input_id)
        if not card_id:
            await message.answer(f"Task '{input_id}' was not found.", parse_mode=None)
            return

        kwargs: dict = {"card_id": card_id, "list_id": target_list_id}
        if position_at_top:
            kwargs["position"] = 0.0
        await planka.move_card(**kwargs)
        register_bot_action(card_id, "moveCard", _telegram_author(message))
        await message.answer(f"{input_id} {done_message}", parse_mode=None)
    except PlankaAuthError:
        await message.answer(
            "Planka authentication failed. Check PLANKA_USERNAME_OR_EMAIL and PLANKA_PASSWORD.",
            parse_mode=None,
        )
    except PlankaClientError:
        logger.exception("Failed to move task", extra={"input_id": input_id})
        await message.answer("Planka request failed. Please try again.", parse_mode=None)
