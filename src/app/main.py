import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from app.bot import create_bot, create_dispatcher
from app.config import Settings
from app.db.mappings import CardMappingsRepository
from app.db.pool import close_engine, create_engine, create_session_factory, ensure_schema
from app.integrations.planka_client import PlankaClient
from app.webhook import router as webhook_router


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings()
    configure_logging()

    bot = create_bot(settings.bot_token)
    dispatcher = create_dispatcher()
    planka = PlankaClient(
        base_url=str(settings.planka_base_url),
        username_or_email=settings.planka_username_or_email,
        password=settings.planka_password,
        timeout_seconds=settings.planka_request_timeout_seconds,
    )
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is required for Planka short-id mapping")
    engine = create_engine(settings.database_url)
    await ensure_schema(engine, Path(__file__).resolve().parent / "db" / "schema.sql")
    mappings = CardMappingsRepository(create_session_factory(engine))
    await planka.start()

    app.state.settings = settings
    app.state.bot = bot
    app.state.dispatcher = dispatcher
    app.state.planka = planka
    app.state.mappings = mappings
    app.state.db_engine = engine

    await bot.set_webhook(
        url=settings.webhook_url,
        secret_token=settings.webhook_secret,
        allowed_updates=dispatcher.resolve_used_update_types(),
    )

    try:
        yield
    finally:
        await bot.delete_webhook(drop_pending_updates=False)
        await planka.close()
        await close_engine(engine)
        await bot.session.close()


def create_app(enable_lifespan: bool = True) -> FastAPI:
    app = FastAPI(title="Planka Telegram Bot", lifespan=lifespan if enable_lifespan else None)
    app.include_router(webhook_router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
