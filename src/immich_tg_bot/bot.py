import asyncio
import logging
import mimetypes
from collections.abc import Awaitable, Callable
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aiogram import BaseMiddleware, Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message, TelegramObject

from .config import Settings
from .i18n import resolve_language, t
from .naming import (
    disambiguate_filenames,
    resolve_album_name,
    resolve_filename,
    split_filename,
)
from .pipeline import IngestionPipeline, IngestItem, IngestSummary, _exif_datetime
from .runtime import ingestion_runtime
from .telegram_metadata import extract_metadata

log = logging.getLogger(__name__)

_MEDIA_GROUP_DEBOUNCE = 1.5


class WhitelistMiddleware(BaseMiddleware):
    def __init__(self, allowed: set[int]) -> None:
        self.allowed = allowed

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, Message):
            return await handler(event, data)
        user = event.from_user
        if user is None or user.id not in self.allowed:
            log.info(
                "Ignoring message from non-whitelisted user id=%s username=%s",
                user.id if user else None,
                user.username if user else None,
            )
            return None
        return await handler(event, data)


def _sender_language_code(message: Message) -> str | None:
    return message.from_user.language_code if message.from_user else None


def _media_info_for(message: Message) -> tuple[str | None, str, str, str]:
    if message.document:
        return (
            message.document.file_id,
            getattr(message.document, "file_unique_id", "") or "",
            "document",
            message.document.file_name or "",
        )
    if message.video:
        return (
            message.video.file_id,
            getattr(message.video, "file_unique_id", "") or "",
            "video",
            getattr(message.video, "file_name", "") or "",
        )
    if message.animation:
        return (
            message.animation.file_id,
            getattr(message.animation, "file_unique_id", "") or "",
            "animation",
            getattr(message.animation, "file_name", "") or "",
        )
    if message.audio:
        return (
            message.audio.file_id,
            getattr(message.audio, "file_unique_id", "") or "",
            "audio",
            getattr(message.audio, "file_name", "") or "",
        )
    if message.voice:
        return (
            message.voice.file_id,
            getattr(message.voice, "file_unique_id", "") or "",
            "voice",
            "",
        )
    if message.video_note:
        return (
            message.video_note.file_id,
            getattr(message.video_note, "file_unique_id", "") or "",
            "video_note",
            "",
        )
    if message.photo:
        best = message.photo[-1]
        return (
            best.file_id,
            getattr(best, "file_unique_id", "") or "",
            "photo",
            "",
        )
    return None, "", "", ""


async def _resolve_local_path(bot: Bot, file_id: str, tg_files_dir: Path) -> Path:
    """Locate a file exposed by the local Bot API through the shared volume."""
    tg_file = await bot.get_file(file_id)
    if tg_file.file_path is None:
        raise FileNotFoundError("Telegram returned no file_path")
    fp = Path(tg_file.file_path)
    if fp.is_absolute() and fp.exists():
        return fp
    # Relative paths are rooted at the local Bot API's per-bot work directory.
    candidate = tg_files_dir / bot.token / fp
    if candidate.exists():
        return candidate
    raise FileNotFoundError(f"Cannot locate downloaded file: {tg_file.file_path}")


async def _extract_ingest_item(
    bot: Bot,
    message: Message,
    tg_files_dir: Path,
    settings: Settings | None = None,
    index: int = 1,
) -> IngestItem | None:
    file_id, file_unique_id, media_type, original_name = _media_info_for(message)
    if not file_id:
        return None
    local = await _resolve_local_path(bot, file_id, tg_files_dir)
    original_file_name = original_name or local.name
    fallback_dt = message.date.astimezone(UTC) if message.date else datetime.now(UTC)

    if settings is None:
        file_name = original_name or local.name
        target_album = None
    else:
        from zoneinfo import ZoneInfo

        target_tz = ZoneInfo(settings.tz)
        ext = split_filename(original_name)[1] or split_filename(local.name)[1]
        if not ext:
            media = getattr(message, media_type, None)
            mime_type = getattr(media, "mime_type", None)
            if mime_type:
                ext = mimetypes.guess_extension(mime_type) or ""
            elif media_type == "video_note":
                ext = ".mp4"
        if not split_filename(original_file_name)[1]:
            original_file_name += ext
        exif_dt = _exif_datetime(local)
        meta = extract_metadata(
            message,
            target_tz=target_tz,
            index=index,
            file_unique_id=file_unique_id,
            media_type=media_type,
            original_name=original_name,
            exif_date=exif_dt,
        )

        if media_type == "document":
            tmpl = settings.document_name_template
            default_tmpl = "{original_name}"
        else:
            tmpl = settings.media_name_template
            default_tmpl = "{source}_{message_id}_{index}"

        file_name = resolve_filename(tmpl, meta, extension=ext, default_template=default_tmpl)
        target_album = resolve_album_name(
            settings.album_name_template,
            meta,
            fallback_album=settings.album_name,
        )

    return IngestItem(
        chat_id=message.chat.id,
        message_id=message.message_id,
        local_path=local,
        file_name=file_name,
        created_at=fallback_dt,
        target_album=target_album,
        original_file_name=original_file_name,
    )


def format_summary_reply(
    summary: IngestSummary,
    resolve_errors: int = 0,
    lang_code: str | None = None,
    default_lang: str = "en",
) -> str:
    target_lang = resolve_language(lang_code, default_lang=default_lang)
    uploaded = summary.uploaded
    duplicates = summary.duplicates
    errors = summary.errors + resolve_errors

    if errors and not uploaded and not duplicates:
        return t("status_errors_only", lang_code=target_lang, errors=errors)
    if errors:
        return t(
            "status_mixed",
            lang_code=target_lang,
            uploaded=uploaded,
            duplicates=duplicates,
            errors=errors,
        )
    if duplicates and not uploaded:
        return t(
            "status_duplicates_only",
            lang_code=target_lang,
            duplicates=duplicates,
        )
    if duplicates:
        return t(
            "status_uploaded_duplicates",
            lang_code=target_lang,
            uploaded=uploaded,
            duplicates=duplicates,
        )
    if uploaded:
        return t(
            "status_uploaded_only",
            lang_code=target_lang,
            uploaded=uploaded,
        )
    return t("status_no_media", lang_code=target_lang)


async def run_bot(settings: Settings, pipeline: IngestionPipeline | None = None) -> None:
    if pipeline is None:
        async with ingestion_runtime(settings) as shared_pipeline:
            await run_bot(settings, shared_pipeline)
        return

    session = AiohttpSession(
        api=TelegramAPIServer.from_base(settings.tg_api_base, is_local=True),
    )
    bot = Bot(
        token=settings.bot_token,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.message.middleware(WhitelistMiddleware(set(settings.allowed_user_ids)))

    groups: dict[str, list[Message]] = {}
    group_tasks: dict[str, asyncio.Task[None]] = {}
    group_lock = asyncio.Lock()

    async def _process_messages(messages: list[Message]) -> None:
        head = messages[0]
        head_lang = _sender_language_code(head)
        raw_items: list[tuple[IngestItem, str]] = []
        resolve_errors = 0
        for idx, m in enumerate(messages, start=1):
            try:
                item = await _extract_ingest_item(
                    bot, m, settings.tg_files_dir, settings=settings, index=idx
                )
                if item:
                    raw_items.append((item, item.file_name))
            except Exception as e:
                log.exception("Could not get file for message %s", m.message_id)
                with suppress(Exception):
                    err_msg = t(
                        "error_file_fetch",
                        lang_code=head_lang,
                        default_lang=settings.default_language,
                        error=e,
                    )
                    await m.reply(err_msg)
                resolve_errors += 1

        filenames = [fn for _, fn in raw_items]
        disambiguated = disambiguate_filenames(filenames)

        items = [
            IngestItem(
                chat_id=it.chat_id,
                message_id=it.message_id,
                local_path=it.local_path,
                file_name=final_fn,
                created_at=it.created_at,
                target_album=it.target_album,
                original_file_name=it.original_file_name,
            )
            for (it, _), final_fn in zip(raw_items, disambiguated, strict=False)
        ]

        summary = await pipeline.ingest(items)
        reply_text = format_summary_reply(
            summary,
            resolve_errors=resolve_errors,
            lang_code=head_lang,
            default_lang=settings.default_language,
        )
        await head.reply(reply_text)

    async def _flush_group(mg_id: str) -> None:
        try:
            await asyncio.sleep(_MEDIA_GROUP_DEBOUNCE)
        except asyncio.CancelledError:
            return
        async with group_lock:
            messages = groups.pop(mg_id, [])
            group_tasks.pop(mg_id, None)
        if messages:
            messages.sort(key=lambda m: m.message_id)
            await _process_messages(messages)

    @dp.message(Command("start"))
    async def cmd_start(message: Message) -> None:
        sender_lang = _sender_language_code(message)
        await message.reply(
            t("start", lang_code=sender_lang, default_lang=settings.default_language)
        )

    @dp.message(Command("help"))
    async def cmd_help(message: Message) -> None:
        sender_lang = _sender_language_code(message)
        await message.reply(
            t("help", lang_code=sender_lang, default_lang=settings.default_language)
        )

    media_filter = F.photo | F.video | F.document | F.animation | F.audio | F.voice | F.video_note

    @dp.message(media_filter)
    async def on_media(message: Message) -> None:
        if message.media_group_id:
            async with group_lock:
                groups.setdefault(message.media_group_id, []).append(message)
                existing = group_tasks.get(message.media_group_id)
                if existing:
                    existing.cancel()
                group_tasks[message.media_group_id] = asyncio.create_task(
                    _flush_group(message.media_group_id)
                )
            return
        await _process_messages([message])

    log.info(
        "Bot starting (allowed users: %s, album: %s, immich: %s)",
        settings.allowed_user_ids,
        settings.album_name,
        settings.immich_url,
    )
    try:
        await dp.start_polling(bot, handle_signals=True)
    finally:
        # Drain any pending media-group flushes
        for task in list(group_tasks.values()):
            task.cancel()
        await bot.session.close()
