from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    bot_token: str = Field(alias="BOT_TOKEN")
    database_url: str | None = Field(default=None, alias="DATABASE_URL")

    planka_base_url: AnyHttpUrl = Field(alias="PLANKA_BASE_URL")
    planka_username_or_email: str = Field(alias="PLANKA_USERNAME_OR_EMAIL")
    planka_password: str = Field(alias="PLANKA_PASSWORD")
    planka_card_type: str = Field(default="project", alias="PLANKA_CARD_TYPE")
    planka_todo_list_id: str = Field(alias="PLANKA_TODO_LIST_ID")
    planka_doing_list_id: str = Field(alias="PLANKA_DOING_LIST_ID")
    planka_done_list_id: str = Field(alias="PLANKA_DONE_LIST_ID")
    planka_request_timeout_seconds: float = 10.0

    telegram_notification_chat_id: str | None = Field(default=None, alias="TELEGRAM_NOTIFICATION_CHAT_ID")
    telegram_notification_chat_ids: str | None = Field(
        default=None,
        alias="TELEGRAM_NOTIFICATION_CHAT_IDS",
        description="Comma-separated: chat_id or chat_id:thread_id for topics",
    )
    planka_board_id: str | None = Field(default=None, alias="PLANKA_BOARD_ID")
    planka_poll_interval_seconds: float = Field(default=5.0, alias="PLANKA_POLL_INTERVAL_SECONDS")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    def get_notification_targets(self) -> list[tuple[str, int | None]]:
        """Return [(chat_id, thread_id or None), ...] from TELEGRAM_NOTIFICATION_CHAT_IDS."""
        targets: list[tuple[str, int | None]] = []
        raw = self.telegram_notification_chat_ids or self.telegram_notification_chat_id
        if raw:
            for part in raw.split(","):
                part = part.strip()
                if ":" in part:
                    cid, tid = part.split(":", 1)
                    try:
                        targets.append((cid.strip(), int(tid.strip())))
                    except ValueError:
                        targets.append((part, None))
                else:
                    targets.append((part, None))
        return targets
