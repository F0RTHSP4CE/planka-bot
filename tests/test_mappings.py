from unittest.mock import AsyncMock

import pytest

from app.db.mappings import CardMappingsRepository


@pytest.mark.asyncio
async def test_resolve_card_id_returns_long_planka_id_as_is() -> None:
    repo = CardMappingsRepository(session_factory=AsyncMock())

    resolved = await repo.resolve_card_id("1573340758063187370")

    assert resolved == "1573340758063187370"


@pytest.mark.asyncio
async def test_resolve_card_id_returns_none_for_non_numeric_short_id() -> None:
    repo = CardMappingsRepository(session_factory=AsyncMock())

    resolved = await repo.resolve_card_id("TASK-123")

    assert resolved is None


@pytest.mark.asyncio
async def test_resolve_card_id_uses_lookup_for_short_id() -> None:
    repo = CardMappingsRepository(session_factory=AsyncMock())
    repo.get_planka_card_id = AsyncMock(return_value="1573340758063187370")  # type: ignore[method-assign]

    resolved = await repo.resolve_card_id("45")

    repo.get_planka_card_id.assert_awaited_once_with(45)
    assert resolved == "1573340758063187370"
