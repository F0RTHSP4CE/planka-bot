from __future__ import annotations

from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine


def create_engine(database_url: str) -> AsyncEngine:
    return create_async_engine(database_url, pool_pre_ping=True)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker:
    return async_sessionmaker(engine, expire_on_commit=False)


async def close_engine(engine: AsyncEngine | None) -> None:
    if engine is not None:
        await engine.dispose()


async def ensure_schema(engine: AsyncEngine, schema_path: Path) -> None:
    schema_sql = schema_path.read_text(encoding="utf-8")
    statements = [statement.strip() for statement in schema_sql.split(";") if statement.strip()]
    async with engine.begin() as conn:
        for statement in statements:
            await conn.execute(text(statement))
