import asyncio
import logging
from pathlib import Path

from app.bot import create_bot, create_dispatcher
from app.config import Settings
from app.db.mappings import CardMappingsRepository
from app.db.pool import close_engine, create_engine, create_session_factory, ensure_schema
from app.integrations.planka_client import PlankaClient
from app.poller import run_action_poller


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


async def run_polling() -> None:
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

    # Polling mode does not need public webhook URL; clear webhook first.
    await bot.delete_webhook(drop_pending_updates=False)

    poller_task: asyncio.Task | None = None
    if settings.get_notification_targets() and settings.planka_board_id:
        poller_task = asyncio.create_task(run_action_poller(bot, planka, settings))

    try:
        await dispatcher.start_polling(
            bot,
            settings=settings,
            planka=planka,
            mappings=mappings,
        )
    finally:
        if poller_task is not None:
            poller_task.cancel()
            try:
                await poller_task
            except asyncio.CancelledError:
                pass
        await planka.close()
        await close_engine(engine)
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(run_polling())
