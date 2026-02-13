from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from aiogram.filters.command import CommandObject

from app.handlers.commands import (
    _build_create_reply,
    _parse_todo_args,
    doing_command,
    done_command,
    help_command,
    todo_command,
)


def _message_mock(photo=None) -> AsyncMock:
    message = AsyncMock()
    message.answer = AsyncMock()
    message.photo = photo
    message.bot = AsyncMock()
    return message


def _settings(**overrides):
    defaults = dict(
        planka_todo_list_id="todo-list",
        planka_doing_list_id="doing-list",
        planka_done_list_id="done-list",
        planka_card_type="story",
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


# ---------------------------------------------------------------------------
# _parse_todo_args unit tests
# ---------------------------------------------------------------------------


def test_parse_todo_args_single_line() -> None:
    name, items = _parse_todo_args("Ship webhook wrappers")
    assert name == "Ship webhook wrappers"
    assert items == []


def test_parse_todo_args_with_checklist() -> None:
    name, items = _parse_todo_args("Deploy\n- build image\n- run migrations\n- smoke test")
    assert name == "Deploy"
    assert items == ["build image", "run migrations", "smoke test"]


def test_parse_todo_args_skips_empty_items() -> None:
    name, items = _parse_todo_args("Title\n- \n- valid\n-\n- also valid")
    assert name == "Title"
    assert items == ["valid", "also valid"]


# ---------------------------------------------------------------------------
# _build_create_reply unit tests
# ---------------------------------------------------------------------------


def test_build_reply_plain() -> None:
    assert _build_create_reply(42, 0, False) == "task 42 created"


def test_build_reply_with_items() -> None:
    assert _build_create_reply(7, 3, False) == "task 7 created (3 items)"


def test_build_reply_with_attachment() -> None:
    assert _build_create_reply(7, 0, True) == "task 7 created (1 attachment)"


def test_build_reply_with_items_and_attachment() -> None:
    assert _build_create_reply(7, 1, True) == "task 7 created (1 item, 1 attachment)"


# ---------------------------------------------------------------------------
# todo_command tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_todo_command_with_task_name_creates_task_and_short_id() -> None:
    message = _message_mock()
    command = CommandObject(command="todo", args="Ship webhook wrappers")
    planka = AsyncMock()
    planka.create_card.return_value = {"id": "1573340758063187370"}
    mappings = AsyncMock()
    mappings.get_or_create_short_id.return_value = 45
    settings = _settings()

    await todo_command(message, command, planka=planka, mappings=mappings, settings=settings)

    planka.create_card.assert_awaited_once_with(
        "todo-list", name="Ship webhook wrappers", card_type="story",
    )
    mappings.get_or_create_short_id.assert_awaited_once_with("1573340758063187370")
    message.answer.assert_awaited_once_with("task 45 created", parse_mode=None)


@pytest.mark.asyncio
async def test_todo_command_with_checklist_creates_task_list_and_tasks() -> None:
    message = _message_mock()
    command = CommandObject(command="todo", args="Deploy\n- build image\n- run migrations")
    planka = AsyncMock()
    planka.create_card.return_value = {"id": "card-1"}
    planka.create_task_list.return_value = {"id": "tl-1"}
    planka.create_task.return_value = {"id": "task-x"}
    mappings = AsyncMock()
    mappings.get_or_create_short_id.return_value = 10
    settings = _settings()

    await todo_command(message, command, planka=planka, mappings=mappings, settings=settings)

    planka.create_card.assert_awaited_once_with("todo-list", name="Deploy", card_type="story")
    planka.create_task_list.assert_awaited_once_with("card-1", name="Checklist")
    assert planka.create_task.await_count == 2
    planka.create_task.assert_any_await("tl-1", name="build image", position=65536.0)
    planka.create_task.assert_any_await("tl-1", name="run migrations", position=131072.0)
    message.answer.assert_awaited_once_with("task 10 created (2 items)", parse_mode=None)


@pytest.mark.asyncio
async def test_todo_command_with_photo_uploads_attachment() -> None:
    photo_obj = SimpleNamespace(file_unique_id="abc123")
    message = _message_mock(photo=[photo_obj])
    # Simulate bot.download writing bytes into the BytesIO buffer
    async def fake_download(file, destination):
        destination.write(b"\xff\xd8\xff\xe0fake-jpeg")
    message.bot.download.side_effect = fake_download

    command = CommandObject(command="todo", args="Task with image")
    planka = AsyncMock()
    planka.create_card.return_value = {"id": "card-2"}
    planka.create_attachment.return_value = {"id": "att-1"}
    mappings = AsyncMock()
    mappings.get_or_create_short_id.return_value = 11
    settings = _settings()

    await todo_command(message, command, planka=planka, mappings=mappings, settings=settings)

    planka.create_card.assert_awaited_once()
    planka.create_attachment.assert_awaited_once()
    call_kwargs = planka.create_attachment.await_args
    assert call_kwargs[0][0] == "card-2"  # card_id
    assert call_kwargs[1]["file_name"] == "abc123.jpg"
    message.answer.assert_awaited_once_with("task 11 created (1 attachment)", parse_mode=None)


@pytest.mark.asyncio
async def test_todo_command_with_checklist_and_photo() -> None:
    photo_obj = SimpleNamespace(file_unique_id="xyz789")
    message = _message_mock(photo=[photo_obj])
    async def fake_download(file, destination):
        destination.write(b"\xff\xd8\xff\xe0fake-jpeg")
    message.bot.download.side_effect = fake_download

    command = CommandObject(command="todo", args="Full task\n- item one\n- item two\n- item three")
    planka = AsyncMock()
    planka.create_card.return_value = {"id": "card-3"}
    planka.create_task_list.return_value = {"id": "tl-2"}
    planka.create_task.return_value = {"id": "task-x"}
    planka.create_attachment.return_value = {"id": "att-2"}
    mappings = AsyncMock()
    mappings.get_or_create_short_id.return_value = 42
    settings = _settings()

    await todo_command(message, command, planka=planka, mappings=mappings, settings=settings)

    planka.create_card.assert_awaited_once_with("todo-list", name="Full task", card_type="story")
    planka.create_task_list.assert_awaited_once()
    assert planka.create_task.await_count == 3
    planka.create_attachment.assert_awaited_once()
    message.answer.assert_awaited_once_with(
        "task 42 created (3 items, 1 attachment)", parse_mode=None,
    )


@pytest.mark.asyncio
async def test_todo_command_without_args_returns_planka_list() -> None:
    message = _message_mock()
    command = CommandObject(command="todo", args=None)
    planka = AsyncMock()
    planka.get_cards.return_value = [
        {"id": "1573340758063187370", "name": "Prepare sprint sync"},
        {"id": "1573340758063187371", "name": "Review onboarding flow", "description": "Critical"},
    ]
    mappings = AsyncMock()
    mappings.get_or_create_short_id.side_effect = [1, 2]
    settings = _settings()

    await todo_command(message, command, planka=planka, mappings=mappings, settings=settings)

    message.answer.assert_awaited_once_with(
        "TODO tasks:\n"
        "- 1 | Prepare sprint sync\n"
        "- 2 | Review onboarding flow - Critical",
        parse_mode=None,
    )


@pytest.mark.asyncio
async def test_doing_command_with_task_id_moves_to_doing_list() -> None:
    message = _message_mock()
    command = CommandObject(command="doing", args="1001 extra text")
    planka = AsyncMock()
    mappings = AsyncMock()
    mappings.resolve_card_id.return_value = "1573340758063187370"
    settings = _settings()

    await doing_command(message, command, planka=planka, mappings=mappings, settings=settings)

    planka.move_card.assert_awaited_once_with(
        card_id="1573340758063187370",
        list_id="doing-list",
    )
    message.answer.assert_awaited_once_with("1001 moved to IN PROGRESS", parse_mode=None)


@pytest.mark.asyncio
async def test_doing_command_without_task_id_returns_usage() -> None:
    message = _message_mock()
    command = CommandObject(command="doing", args=None)
    planka = AsyncMock()
    mappings = AsyncMock()
    settings = _settings()

    await doing_command(message, command, planka=planka, mappings=mappings, settings=settings)

    message.answer.assert_awaited_once_with("Usage: /doing {id}", parse_mode=None)


@pytest.mark.asyncio
async def test_done_command_with_unknown_task_returns_not_found() -> None:
    message = _message_mock()
    command = CommandObject(command="done", args="999")
    planka = AsyncMock()
    mappings = AsyncMock()
    mappings.resolve_card_id.return_value = None
    settings = _settings()

    await done_command(message, command, planka=planka, mappings=mappings, settings=settings)

    planka.move_card.assert_not_awaited()
    message.answer.assert_awaited_once_with("Task '999' was not found.", parse_mode=None)


@pytest.mark.asyncio
async def test_done_command_without_task_id_returns_usage() -> None:
    message = _message_mock()
    command = CommandObject(command="done", args=None)
    planka = AsyncMock()
    mappings = AsyncMock()
    settings = _settings()

    await done_command(message, command, planka=planka, mappings=mappings, settings=settings)

    message.answer.assert_awaited_once_with("Usage: /done {id}", parse_mode=None)


@pytest.mark.asyncio
async def test_help_command_includes_wrapper_commands() -> None:
    message = _message_mock()

    await help_command(message)

    message.answer.assert_awaited_once()
    payload = message.answer.await_args.args[0]
    assert "/todo {task_name} - Create a task in TODO" in payload
    assert "/doing {id} - Move task to IN PROGRESS" in payload
    assert "/done {id} - Move task to DONE" in payload
