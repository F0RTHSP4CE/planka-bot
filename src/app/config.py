from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    bot_token: str = Field(alias="BOT_TOKEN")
    webhook_secret: str | None = Field(default=None, alias="WEBHOOK_SECRET")
    database_url: str | None = Field(default=None, alias="DATABASE_URL")

    planka_base_url: AnyHttpUrl = Field(alias="PLANKA_BASE_URL")
    planka_username_or_email: str = Field(alias="PLANKA_USERNAME_OR_EMAIL")
    planka_password: str = Field(alias="PLANKA_PASSWORD")
    planka_card_type: str = Field(default="project", alias="PLANKA_CARD_TYPE")
    planka_todo_list_id: str = Field(alias="PLANKA_TODO_LIST_ID")
    planka_doing_list_id: str = Field(alias="PLANKA_DOING_LIST_ID")
    planka_done_list_id: str = Field(alias="PLANKA_DONE_LIST_ID")
    planka_request_timeout_seconds: float = 10.0

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    @property
    def webhook_path(self) -> str:
        return "/telegram/webhook"

