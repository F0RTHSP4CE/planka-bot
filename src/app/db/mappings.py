from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker


class CardMappingsRepository:
    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory

    async def get_or_create_short_id(self, planka_card_id: str) -> int:
        query = text(
            """
            INSERT INTO card_mappings (planka_card_id)
            VALUES (:planka_card_id)
            ON CONFLICT (planka_card_id)
            DO UPDATE SET planka_card_id = EXCLUDED.planka_card_id
            RETURNING short_id
            """
        )
        async with self._session_factory() as session:
            result = await session.execute(query, {"planka_card_id": planka_card_id})
            row = result.first()
            await session.commit()
            if row is None:
                raise RuntimeError("Failed to allocate short_id for card")
            return int(row[0])

    async def get_planka_card_id(self, short_id: int) -> str | None:
        query = text("SELECT planka_card_id FROM card_mappings WHERE short_id = :short_id")
        async with self._session_factory() as session:
            result = await session.execute(query, {"short_id": short_id})
            row = result.first()
            if row is None:
                return None
            return str(row[0])

    async def resolve_card_id(self, short_id_or_long: str) -> str | None:
        candidate = short_id_or_long.strip()
        if not candidate:
            return None

        # Long Planka IDs are already numeric and typically 16+ digits.
        if candidate.isdigit() and len(candidate) >= 16:
            return candidate

        if not candidate.isdigit():
            return None

        return await self.get_planka_card_id(int(candidate))
