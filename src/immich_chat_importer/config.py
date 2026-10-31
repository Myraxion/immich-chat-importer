import json
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from .i18n import SUPPORTED_LANGUAGES


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    telegram_bot_token: str = ""
    telegram_api_id: int | None = None
    telegram_api_hash: str = ""
    immich_url: str
    immich_api_key: str
    telegram_allowed_user_ids: Annotated[list[int], NoDecode] = Field(default_factory=list)
    enabled_platforms: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["telegram"])
    discord_token: str = ""
    discord_allowed_user_ids: Annotated[list[int], NoDecode] = Field(default_factory=list)
    discord_album_name: str = "Discord Inbox"
    discord_album_name_template: str = ""
    discord_filename_template: str = "{original_name}"
    discord_max_attachment_mb: int = Field(default=2000, gt=0)

    telegram_album_name: str | None = None
    telegram_album_name_template: str = ""
    telegram_media_name_template: str = "{source}_{message_id}_{index}"
    telegram_document_name_template: str = "{original_name}"
    tz: str = "UTC"
    default_language: str = "en"

    max_archive_mb: int = 2000
    max_archive_files: int = 1000
    log_level: str = "INFO"

    data_dir: Path = Path("/data")
    telegram_files_dir: Path = Path("/var/lib/telegram-bot-api")
    telegram_api_base: str = "http://telegram-bot-api:8081"
    cleanup_local_files: bool = True

    @field_validator("telegram_allowed_user_ids", "discord_allowed_user_ids", mode="before")
    @classmethod
    def _parse_user_ids(cls, v: object) -> list[int]:
        if isinstance(v, str):
            try:
                decoded = json.loads(v)
            except json.JSONDecodeError:
                v = v.split(",")
            else:
                v = decoded if isinstance(decoded, list) else [decoded]
        if not isinstance(v, list):
            raise ValueError(
                "telegram_allowed_user_ids must be a comma-separated list or JSON array"
            )
        return [int(x) for x in v if str(x).strip()]

    @field_validator("enabled_platforms", mode="before")
    @classmethod
    def _parse_platforms(cls, v: object) -> object:
        return [part.strip().lower() for part in v.split(",")] if isinstance(v, str) else v

    @field_validator("telegram_api_id", mode="before")
    @classmethod
    def _empty_telegram_api_id(cls, v: object) -> object:
        return None if v == "" else v

    @model_validator(mode="after")
    def _validate_platform_credentials(self) -> "Settings":
        if not self.enabled_platforms or set(self.enabled_platforms) - {"telegram", "discord"}:
            raise ValueError("enabled_platforms must contain telegram and/or discord")
        if "telegram" in self.enabled_platforms and not (
            self.telegram_bot_token and self.telegram_api_id and self.telegram_api_hash
        ):
            raise ValueError("Telegram credentials are required when Telegram is enabled")
        if "discord" in self.enabled_platforms and not self.discord_token:
            raise ValueError("Discord token is required when Discord is enabled")
        return self

    @field_validator("immich_url")
    @classmethod
    def _strip_trailing_slash(cls, v: str) -> str:
        return v.rstrip("/")

    @field_validator("tz")
    @classmethod
    def _validate_tz(cls, v: str) -> str:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError) as e:
            raise ValueError(f"Invalid timezone: {v}") from e
        return v

    @field_validator("default_language")
    @classmethod
    def _validate_default_language(cls, v: str) -> str:
        lang = v.strip().lower()
        if lang not in SUPPORTED_LANGUAGES:
            supported_str = ", ".join(SUPPORTED_LANGUAGES)
            raise ValueError(f"Invalid default_language: {v!r}. Must be one of: {supported_str}")
        return lang
