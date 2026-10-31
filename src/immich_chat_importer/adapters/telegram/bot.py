import asyncio
import html
import logging
import mimetypes
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import asynccontextmanager, suppress
from dataclasses import replace
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

from ...batches import IngestBatches, IngestRequest, Preparation
from ...config import Settings
from ...errors import format_failure
from ...i18n import resolve_language, t
from ...media_metadata import inspect_media
from ...naming import (
    disambiguate_filenames,
    resolve_album_name,
    resolve_filename,
    split_filename,
)
from ...pipeline import IngestionPipeline, IngestItem, IngestSummary
from ...retry import retry
from ...runtime import ingestion_runtime
from .errors import failure_kind, retry_delay
from .metadata import extract_metadata

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


async def handle_telegram_status(
    message: Message, state: IngestBatches, default_lang: str, tz: str = "UTC"
) -> None:
    lang = _sender_language_code(message)
    if message.chat.type != "private":
        await message.reply(t("status_private_only", lang_code=lang, default_lang=default_lang))
        return
    if message.from_user is None:
        return
    records = await state.recent("telegram", message.from_user.id)
    entries = []
    for record in records:
        status = t(f"record_{record.status}", lang_code=lang, default_lang=default_lang)
        entry = (
            f"#{record.id} | {record.format_created_at(tz)} | {status} | "
            f"{record.source_id}/{record.message_id}"
        )
        if record.status in ("waiting", "processing"):
            entry += f"\n{record.progress}" if record.progress else ""
        else:
            entry += "\n" + t(
                "discord_counts",
                lang_code=lang,
                default_lang=default_lang,
                uploaded=record.uploaded,
                duplicates=record.duplicates,
                skipped=record.skipped,
                errors=record.errors,
            )
            if record.details:
                entry += f"\n{record.details}"
        entries.append(entry)
    content = (
        "\n\n".join(entries)
        if entries
        else t("status_empty", lang_code=lang, default_lang=default_lang)
    )
    for start in range(0, len(content), 500):
        await message.reply(html.escape(content[start : start + 500]))


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


async def _resolve_local_path(bot: Bot, file_id: str, telegram_files_dir: Path) -> Path:
    """Locate a file exposed by the local Bot API through the shared volume."""
    tg_file = await retry(lambda: bot.get_file(file_id), "download", delay_for=retry_delay)
    if tg_file.file_path is None:
        raise FileNotFoundError("Telegram returned no file_path")
    fp = Path(tg_file.file_path)
    if fp.is_absolute() and fp.exists():
        return fp
    # Relative paths are rooted at the local Bot API's per-bot work directory.
    candidate = telegram_files_dir / bot.token / fp
    if candidate.exists():
        return candidate
    raise FileNotFoundError(f"Cannot locate downloaded file: {tg_file.file_path}")


async def _extract_ingest_item(
    bot: Bot,
    message: Message,
    telegram_files_dir: Path,
    settings: Settings | None = None,
    index: int = 1,
) -> IngestItem | None:
    file_id, file_unique_id, media_type, original_name = _media_info_for(message)
    if not file_id:
        return None
    local = await _resolve_local_path(bot, file_id, telegram_files_dir)
    original_file_name = original_name or local.name
    fallback_dt = message.date.astimezone(UTC) if message.date else datetime.now(UTC)

    file_metadata = None
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
        file_metadata = inspect_media(local, target_tz, fallback_dt)
        meta = extract_metadata(
            message,
            target_tz=target_tz,
            index=index,
            file_unique_id=file_unique_id,
            media_type=media_type,
            original_name=original_name,
            exif_date=file_metadata.exif_date,
        )

        if media_type == "document":
            tmpl = settings.telegram_document_name_template
            default_tmpl = "{original_name}"
        else:
            tmpl = settings.telegram_media_name_template
            default_tmpl = "{source}_{message_id}_{index}"

        file_name = resolve_filename(tmpl, meta, extension=ext, default_template=default_tmpl)
        target_album = resolve_album_name(
            settings.telegram_album_name_template,
            meta,
            fallback_album=settings.telegram_album_name,
        )

    return IngestItem(
        chat_id=message.chat.id,
        message_id=message.message_id,
        local_path=local,
        file_name=file_name,
        created_at=fallback_dt,
        target_album=target_album,
        original_file_name=original_file_name,
        metadata=file_metadata,
        owns_local_file=False,
    )


def format_summary_reply(
    summary: IngestSummary,
    errors: int | None = None,
    lang_code: str | None = None,
    default_lang: str = "en",
) -> str:
    return format_summary_replies(summary, errors, lang_code, default_lang)[0]


def format_summary_replies(
    summary: IngestSummary,
    errors: int | None = None,
    lang_code: str | None = None,
    default_lang: str = "en",
    skipped: Sequence[str] = (),
) -> list[str]:
    replies = [_format_summary_counts(summary, errors, lang_code, default_lang)]
    if summary.error_messages or skipped:
        language = resolve_language(lang_code, default_lang=default_lang)
        error_lines = (
            [
                format_failure(name, stage, kind, language, default_lang)
                for name, stage, kind in summary.error_details
            ]
            if len(summary.error_details) == len(summary.error_messages)
            else summary.error_messages
        )
        lines = [
            *error_lines,
            *(f"{name}: {t('discord_skipped', lang_code=language)}" for name in skipped),
        ]
        for message in lines:
            for stage, key in (
                ("album lookup/create", "stage_album_lookup"),
                ("album association", "stage_album_association"),
                ("upload", "stage_upload"),
            ):
                message = message.replace(f": {stage}", f": {t(key, lang_code=language)}", 1)
            detail = html.escape(message[:600])
            if len((replies[-1] + "\n" + detail).encode("utf-16-le")) // 2 > 4000:
                replies.append(detail)
            else:
                replies[-1] += "\n" + detail
    return replies


def _format_summary_counts(
    summary: IngestSummary,
    errors: int | None = None,
    lang_code: str | None = None,
    default_lang: str = "en",
) -> str:
    target_lang = resolve_language(lang_code, default_lang=default_lang)
    uploaded = summary.uploaded
    duplicates = summary.duplicates
    errors = summary.errors if errors is None else errors

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
        api=TelegramAPIServer.from_base(settings.telegram_api_base, is_local=True),
    )
    bot = Bot(
        token=settings.telegram_bot_token,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.message.middleware(WhitelistMiddleware(set(settings.telegram_allowed_user_ids)))

    groups: dict[str, list[Message]] = {}
    group_tasks: dict[str, asyncio.Task[None]] = {}
    active_groups: set[asyncio.Task[None]] = set()
    group_lock = asyncio.Lock()

    async def _process_messages(messages: list[Message]) -> None:
        head = messages[0]
        head_lang = _sender_language_code(head)
        if head.from_user is None:
            return
        batches = IngestBatches(pipeline)

        @asynccontextmanager
        async def prepare(batch: Preparation) -> AsyncIterator[None]:
            raw_items: list[tuple[IngestItem, str]] = []
            for idx, m in enumerate(messages, start=1):
                try:
                    item = await _extract_ingest_item(
                        bot, m, settings.telegram_files_dir, settings=settings, index=idx
                    )
                    if item:
                        raw_items.append((item, item.file_name))
                except Exception as e:
                    log.exception("Could not get file for message %s", m.message_id)
                    error_index = len(batch.errors)
                    with suppress(Exception):
                        name = _media_info_for(m)[3] or str(m.message_id)
                        err_msg = format_failure(
                            name, "download", failure_kind(e), head_lang, settings.default_language
                        )
                        batch.errors.append(err_msg)
                        await m.reply(html.escape(err_msg))
                    if len(batch.errors) == error_index:
                        batch.errors.append(None)

            filenames = [fn for _, fn in raw_items]
            disambiguated = disambiguate_filenames(filenames)

            batch.items = [
                replace(it, file_name=final_fn)
                for (it, _), final_fn in zip(raw_items, disambiguated, strict=False)
            ]

            yield

        result = await batches.run(
            IngestRequest(
                "telegram",
                head.from_user.id,
                str(head.chat.id),
                str(head.message_id),
                head_lang,
                settings.default_language,
            ),
            prepare,
        )
        try:
            summary = replace(result.summary, error_messages=result.errors, error_details=[])
            for reply_text in format_summary_replies(
                summary,
                errors=result.record.errors,
                lang_code=head_lang,
                default_lang=settings.default_language,
                skipped=result.skipped,
            ):
                await head.reply(reply_text)
        except Exception:
            log.exception("Telegram reply failed")

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

    @dp.message(Command("status"))
    async def cmd_status(message: Message) -> None:
        await handle_telegram_status(
            message, IngestBatches(pipeline), settings.default_language, settings.tz
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
                task = group_tasks[message.media_group_id]
                active_groups.add(task)
                task.add_done_callback(active_groups.discard)
            return
        await _process_messages([message])

    log.info(
        "Bot starting (allowed users: %s, album: %s, immich: %s)",
        settings.telegram_allowed_user_ids,
        settings.telegram_album_name,
        settings.immich_url,
    )
    try:
        await dp.start_polling(bot, handle_signals=True, close_bot_session=False)
    finally:
        # Finish cancellation before closing resources used by ingestion.
        pending = list(active_groups)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        await bot.session.close()
