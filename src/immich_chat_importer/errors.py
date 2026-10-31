import httpx
from aiogram.exceptions import (
    TelegramEntityTooLarge,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramServerError,
    TelegramUnauthorizedError,
)

from .i18n import t


def failure_kind(exc: Exception, stage: str = "") -> str:
    if stage == "extract":
        return "failure_archive"
    if isinstance(exc, TelegramEntityTooLarge):
        return "failure_size"
    if isinstance(exc, (TelegramUnauthorizedError, TelegramForbiddenError)):
        return "failure_access"
    if isinstance(exc, (TelegramNetworkError, TelegramServerError, TelegramRetryAfter)):
        return "failure_network"
    if isinstance(exc, httpx.HTTPStatusError):
        if exc.response.status_code in (401, 403):
            return "failure_access"
        if exc.response.status_code == 413:
            return "failure_size"
        if exc.response.status_code == 429 or exc.response.status_code in (500, 502, 503, 504):
            return "failure_network"
    if isinstance(exc, httpx.RequestError):
        return "failure_network"
    if "Album creation could not be confirmed" in str(exc):
        return "failure_album_uncertain"
    return "failure_unknown"


def format_failure(name: str, stage: str, kind: str, lang: str | None, default: str) -> str:
    stage_key = {
        "upload": "stage_upload",
        "album lookup/create": "stage_album_lookup",
        "album association": "stage_album_association",
        "download": "discord_download",
        "extract": "stage_extract",
    }.get(stage)
    label = t(stage_key, lang_code=lang, default_lang=default) if stage_key else stage
    return f"{name}: {label}: {t(kind, lang_code=lang, default_lang=default)}"


def format_progress(stage: str, attempt: int, delay: float, lang: str | None, default: str) -> str:
    name, _, target = stage.partition(": ")
    key = {
        "upload": "stage_upload",
        "download": "discord_download",
        "extract": "stage_extract",
        "album lookup": "stage_album_lookup",
        "album association": "stage_album_association",
        "Telegram file retrieval": "discord_download",
    }.get(name)
    label = t(key, lang_code=lang, default_lang=default) if key else name
    description = f"{label}: {target}" if target else label
    if not attempt:
        return description
    return t(
        "status_retry_wait" if delay else "status_attempt",
        lang_code=lang,
        default_lang=default,
        stage=description,
        attempt=attempt,
        delay=f"{delay:g}",
    )
