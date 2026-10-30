import logging
import tempfile
from pathlib import Path
from typing import Any

import discord
import httpx

from .archives import is_media
from .config import Settings
from .i18n import t
from .naming import MessageMetadata
from .pipeline import IngestionPipeline, IngestItem, IngestSummary
from .runtime import ingestion_runtime

log = logging.getLogger(__name__)


async def process_import(
    message: Any,
    operator_id: int,
    settings: Settings,
    pipeline: IngestionPipeline,
    client: httpx.AsyncClient,
) -> str | None:
    """Process a Discord message on behalf of an authorized operator."""
    if operator_id not in settings.discord_allowed_user_ids:
        return None
    items: list[IngestItem] = []
    errors: list[str] = []
    skipped: list[str] = []
    limit = settings.discord_max_attachment_mb * 1024 * 1024
    author = message.author
    sender = (
        getattr(author, "display_name", None) or getattr(author, "name", None) or str(author.id)
    )
    metadata = MessageMetadata(
        source=sender,
        source_id=str(author.id),
        source_username=getattr(author, "name", "") or str(author.id),
        message_id=str(message.id),
        date=message.created_at,
        msg_date=message.created_at,
        sender=sender,
        sender_id=str(author.id),
        chat_id=str(message.channel.id),
        caption=message.content or "",
    )
    download_dir = settings.data_dir / "discord-downloads"
    download_dir.mkdir(parents=True, exist_ok=True)
    for attachment in message.attachments:
        name = attachment.filename or str(attachment.id)
        if not is_media(name):
            skipped.append(name)
            continue
        if attachment.size > limit:
            errors.append(f"{name}: exceeds {settings.discord_max_attachment_mb} MiB")
            continue
        path = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=download_dir, prefix="discord-", delete=False
            ) as f:
                path = Path(f.name)
                async with client.stream("GET", attachment.url) as response:
                    response.raise_for_status()
                    size = 0
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > limit:
                            raise ValueError(f"exceeds {settings.discord_max_attachment_mb} MiB")
                        f.write(chunk)
            items.append(
                IngestItem(
                    chat_id=message.channel.id,
                    message_id=message.id,
                    attachment_id=str(attachment.id),
                    platform="discord",
                    local_path=path,
                    file_name=name,
                    original_file_name=name,
                    created_at=metadata.msg_date or metadata.date,
                    target_album=settings.discord_album_name,
                )
            )
        except Exception as exc:
            if path:
                path.unlink(missing_ok=True)
            reason = (
                f"HTTP {exc.response.status_code}"
                if isinstance(exc, httpx.HTTPStatusError)
                else ("network error" if isinstance(exc, httpx.HTTPError) else str(exc))
            )
            log.warning("Discord download failed for %s: %s", name, reason)
            errors.append(f"{name}: download: {reason}")
    try:
        summary = await pipeline.ingest(items) if items else IngestSummary()
    finally:
        if settings.cleanup_local_files:
            for item in items:
                item.local_path.unlink(missing_ok=True)
    errors.extend(summary.error_messages)
    lang = settings.default_language
    counts = t(
        "discord_counts",
        lang_code=lang,
        uploaded=summary.uploaded,
        duplicates=summary.duplicates,
        skipped=len(skipped),
        errors=summary.errors + len(errors) - len(summary.error_messages),
    )
    details = [*(f"{name}: {t('discord_skipped', lang_code=lang)}" for name in skipped), *errors]
    return "\n".join([counts, *details])


async def handle_dm(
    message: Any, settings: Settings, pipeline: IngestionPipeline, client: httpx.AsyncClient
) -> None:
    result = await process_import(message, message.author.id, settings, pipeline, client)
    if result:
        for start in range(0, len(result), 1900):
            await message.reply(
                result[start : start + 1900], allowed_mentions=discord.AllowedMentions.none()
            )


async def run_discord(settings: Settings, pipeline: IngestionPipeline | None = None) -> None:
    if pipeline is None:
        async with ingestion_runtime(settings) as shared_pipeline:
            await run_discord(settings, shared_pipeline)
        return
    intents = discord.Intents.none()
    intents.dm_messages = True
    bot = discord.Client(intents=intents)
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(600, connect=30), follow_redirects=True
    ) as client:

        @bot.event
        async def on_message(message: discord.Message) -> None:
            if isinstance(message.channel, discord.DMChannel) and not message.author.bot:
                await handle_dm(message, settings, pipeline, client)

        try:
            await bot.start(settings.discord_token)
        finally:
            await bot.close()
