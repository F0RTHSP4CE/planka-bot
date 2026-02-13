from aiogram.types import Update
from fastapi import APIRouter, Header, HTTPException, Request, status

from app.config import Settings
from app.db.mappings import CardMappingsRepository

router = APIRouter()


@router.post("/telegram/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict[str, bool]:
    settings: Settings = request.app.state.settings
    if x_telegram_bot_api_secret_token != settings.webhook_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook secret",
        )

    data = await request.json()
    bot = request.app.state.bot
    dispatcher = request.app.state.dispatcher
    planka = request.app.state.planka
    mappings: CardMappingsRepository = request.app.state.mappings

    update = Update.model_validate(data)
    await dispatcher.feed_webhook_update(
        bot,
        update,
        planka=planka,
        mappings=mappings,
        settings=settings,
    )
    return {"ok": True}
