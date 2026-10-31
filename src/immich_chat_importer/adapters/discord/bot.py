import logging
import mimetypes
import tempfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import discord
import httpx
from discord import app_commands

from ...archives import is_archive, is_media
from ...batches import IngestBatches, IngestRequest, Preparation
from ...config import Settings
from ...errors import failure_kind, format_failure
from ...i18n import resolve_language, t
from ...media_metadata import inspect_media
from ...naming import MessageMetadata, resolve_album_name, resolve_filename, split_filename
from ...pipeline import IngestionPipeline, IngestItem
from ...retry import retry
from ...runtime import ingestion_runtime

log = logging.getLogger(__name__)


async def _forward_source(message: Any, settings: Settings, client: httpx.AsyncClient) -> str:
    reference = getattr(message, "reference", None)
    if not reference or reference.type != discord.MessageReferenceType.forward:
        return ""
    channel_id = reference.channel_id
    if settings.discord_token:
        try:
            response = await client.get(
                f"https://discord.com/api/v10/channels/{channel_id}",
                headers={"Authorization": f"Bot {settings.discord_token}"},
            )
            response.raise_for_status()
            return response.json().get("name") or str(channel_id)
        except httpx.HTTPError:
            log.info("Discord source channel %s unavailable; using channel ID", channel_id)
    return str(channel_id)


@asynccontextmanager
async def _prepare_import(
    message: Any,
    settings: Settings,
    client: httpx.AsyncClient,
    interaction: Any,
    batch: Preparation,
) -> AsyncIterator[None]:
    locale = getattr(interaction, "locale", None) if interaction else None
    lang = resolve_language(str(locale) if locale else None, settings.default_language)
    items = batch.items
    errors = batch.errors
    skipped = batch.skipped
    limit = settings.discord_max_attachment_mb * 1024 * 1024
    author = message.author
    sender = (
        getattr(author, "display_name", None) or getattr(author, "name", None) or str(author.id)
    )
    guild_id = getattr(interaction, "guild_id", None) if interaction else None
    guild = getattr(interaction, "guild", None) if interaction else None
    channel = getattr(interaction, "channel", None) if interaction else None
    source = (
        f"{getattr(guild, 'name', None) or guild_id}_"
        f"{getattr(channel, 'name', None) or message.channel.id}"
        if guild_id
        else sender
    )
    forward_source = await _forward_source(message, settings, client)
    source = forward_source or source
    msg_date = message.created_at.astimezone(ZoneInfo(settings.tz))
    metadata = MessageMetadata(
        source=source,
        source_id=str(message.reference.channel_id) if forward_source else str(author.id),
        source_username=getattr(author, "name", "") or str(author.id),
        message_id=str(message.id),
        date=msg_date,
        msg_date=msg_date,
        msg_id=str(message.id),
        chat_title=source,
        sender=sender,
        sender_id=str(author.id),
        chat_id=str(message.channel.id),
        caption=message.content or "",
    )
    download_dir = settings.data_dir / "discord-downloads"
    download_dir.mkdir(parents=True, exist_ok=True)
    attachments = list(message.attachments)
    for snapshot in getattr(message, "message_snapshots", []):
        attachments.extend(snapshot.attachments)
    downloads: dict[Path, str] = {}
    try:
        for index, attachment in enumerate(attachments, 1):
            name = attachment.filename or str(attachment.id)
            batch.stage = f"{name}: download"
            if not (is_media(name) or is_archive(name)):
                skipped.append(name)
                continue
            if attachment.size > limit:
                errors.append(
                    f"{name}: "
                    + t(
                        "discord_too_large",
                        lang_code=lang,
                        limit=settings.discord_max_attachment_mb,
                    )
                    + ". "
                    + t("failure_size", lang_code=lang, default_lang=settings.default_language)
                )
                continue
            path = None
            try:
                with tempfile.NamedTemporaryFile(
                    dir=download_dir, prefix="discord-", delete=False
                ) as f:
                    path = Path(f.name)
                    downloads[path] = name

                async def download(download_path: Path = path, url: str = attachment.url) -> None:
                    with download_path.open("wb") as f:  # noqa: ASYNC230
                        async with client.stream("GET", url) as response:
                            response.raise_for_status()
                            size = 0
                            async for chunk in response.aiter_bytes():
                                size += len(chunk)
                                if size > limit:
                                    raise ValueError(
                                        t(
                                            "discord_too_large",
                                            lang_code=lang,
                                            limit=settings.discord_max_attachment_mb,
                                        )
                                    )
                                f.write(chunk)

                await retry(download, f"download: {name}")
                stem, extension = split_filename(name)
                file_metadata = inspect_media(
                    path, ZoneInfo(settings.tz), metadata.msg_date or metadata.date
                )
                item_metadata = replace(
                    metadata,
                    index=index,
                    media_type="video"
                    if (mimetypes.guess_type(name)[0] or "").startswith("video/")
                    else "photo",
                    original_name=stem,
                    file_unique_id=str(attachment.id),
                    exif_date=file_metadata.exif_date,
                )
                items.append(
                    IngestItem(
                        chat_id=message.channel.id,
                        message_id=message.id,
                        attachment_id=str(attachment.id),
                        platform="discord",
                        local_path=path,
                        file_name=resolve_filename(
                            settings.discord_filename_template,
                            item_metadata,
                            extension,
                            default_template="{original_name}",
                        ),
                        original_file_name=name,
                        metadata=file_metadata,
                        created_at=metadata.msg_date or metadata.date,
                        target_album=resolve_album_name(
                            settings.discord_album_name_template,
                            item_metadata,
                            fallback_album=settings.discord_album_name,
                        ),
                    )
                )
            except Exception as exc:
                if path:
                    path.unlink(missing_ok=True)
                reason = (
                    f"HTTP {exc.response.status_code}"
                    if isinstance(exc, httpx.HTTPStatusError)
                    else (
                        t("discord_network_error", lang_code=lang)
                        if isinstance(exc, httpx.HTTPError)
                        else str(exc)
                    )
                )
                log.warning("Discord download failed for %s: %s", name, reason)
                safe = format_failure(
                    name,
                    "download",
                    "failure_size" if isinstance(exc, ValueError) else failure_kind(exc),
                    lang,
                    settings.default_language,
                )
                errors.append(f"{safe} ({reason})" if isinstance(exc, ValueError) else safe)
        yield
    finally:
        if settings.cleanup_local_files:
            for path, name in downloads.items():
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    batch.stage = f"{name}: cleanup"
                    raise


async def process_import(
    message: Any,
    operator_id: int,
    settings: Settings,
    pipeline: IngestionPipeline,
    client: httpx.AsyncClient,
    interaction: Any = None,
) -> str | None:
    if operator_id not in settings.discord_allowed_user_ids:
        return None
    locale = getattr(interaction, "locale", None) if interaction else None
    lang = resolve_language(str(locale) if locale else None, settings.default_language)
    result = await IngestBatches(pipeline).run(
        IngestRequest(
            "discord",
            operator_id,
            str(message.channel.id),
            str(message.id),
            str(locale) if locale else None,
            settings.default_language,
        ),
        lambda batch: _prepare_import(message, settings, client, interaction, batch),
    )
    record = result.record
    counts = t(
        "discord_counts",
        lang_code=lang,
        uploaded=record.uploaded,
        duplicates=record.duplicates,
        skipped=record.skipped,
        errors=record.errors,
    )
    details = [
        *(f"{name}: {t('discord_skipped', lang_code=lang)}" for name in result.skipped),
        *result.errors,
    ]
    return "\n".join([counts, *details])


async def handle_status(interaction: Any, settings: Settings, pipeline: IngestionPipeline) -> None:
    lang = resolve_language(
        str(interaction.locale) if interaction.locale else None, settings.default_language
    )
    if interaction.user.id not in settings.discord_allowed_user_ids:
        content = t("discord_unauthorized", lang_code=lang)
    else:
        records = await IngestBatches(pipeline).recent("discord", interaction.user.id)
        entries = []
        for record in records:
            status = t(
                f"record_{record.status}", lang_code=lang, default_lang=settings.default_language
            )
            counts = t(
                "discord_counts",
                lang_code=lang,
                uploaded=record.uploaded,
                duplicates=record.duplicates,
                skipped=record.skipped,
                errors=record.errors,
            )
            entries.append(
                f"#{record.id} | {record.format_created_at(settings.tz)} | {status} | "
                f"{record.source_id}/{record.message_id}"
                + (f"\n{record.progress}" if record.progress else "")
                + (f"\n{counts}" if record.status not in ("waiting", "processing") else "")
                + (f"\n{record.details}" if record.details else "")
            )
        content = "\n\n".join(entries) if entries else t("status_empty", lang_code=lang)
    await interaction.response.send_message(
        content[:2000], ephemeral=True, allowed_mentions=discord.AllowedMentions.none()
    )
    for start in range(2000, len(content), 2000):
        await interaction.followup.send(
            content[start : start + 2000],
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )


async def handle_dm(
    message: Any, settings: Settings, pipeline: IngestionPipeline, client: httpx.AsyncClient
) -> None:
    result = await process_import(message, message.author.id, settings, pipeline, client)
    if result:
        for start in range(0, len(result), 1900):
            await message.reply(
                result[start : start + 1900], allowed_mentions=discord.AllowedMentions.none()
            )


async def handle_menu(
    interaction: Any,
    message: Any,
    settings: Settings,
    pipeline: IngestionPipeline,
    client: httpx.AsyncClient,
) -> None:
    await interaction.response.defer(ephemeral=True, thinking=True)
    result = await process_import(
        message, interaction.user.id, settings, pipeline, client, interaction
    )
    if result is None:
        result = t(
            "discord_unauthorized",
            lang_code=resolve_language(
                str(interaction.locale) if interaction.locale else None, settings.default_language
            ),
        )
    try:
        await interaction.edit_original_response(
            content=result[:2000], allowed_mentions=discord.AllowedMentions.none()
        )
        for start in range(2000, len(result), 2000):
            await interaction.followup.send(
                result[start : start + 2000],
                ephemeral=True,
                allowed_mentions=discord.AllowedMentions.none(),
            )
    except discord.HTTPException:
        log.warning("Could not update Discord interaction response", exc_info=True)


class CommandTranslator(app_commands.Translator):
    async def translate(
        self,
        string: app_commands.locale_str,
        locale: discord.Locale,
        context: app_commands.TranslationContext,
    ) -> str | None:
        if string.message == "Save to Immich" and locale in (
            discord.Locale.chinese,
            discord.Locale.taiwan_chinese,
        ):
            return "保存到 Immich"
        return None


async def run_discord(settings: Settings, pipeline: IngestionPipeline | None = None) -> None:
    if pipeline is None:
        async with ingestion_runtime(settings) as shared_pipeline:
            await run_discord(settings, shared_pipeline)
        return
    intents = discord.Intents.none()
    intents.dm_messages = True
    bot = discord.Client(intents=intents)
    tree = app_commands.CommandTree(bot)
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(600, connect=30), follow_redirects=True
    ) as client:

        @app_commands.allowed_installs(guilds=True, users=True)
        @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
        @tree.context_menu(name="Save to Immich")
        async def save_to_immich(
            interaction: discord.Interaction, message: discord.Message
        ) -> None:
            await handle_menu(interaction, message, settings, pipeline, client)

        @app_commands.allowed_installs(guilds=True, users=True)
        @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
        @tree.command(name="status", description="Show your recent imports")
        async def status(interaction: discord.Interaction) -> None:
            await handle_status(interaction, settings, pipeline)

        @bot.event
        async def on_ready() -> None:
            await tree.set_translator(CommandTranslator())
            await tree.sync()

        @bot.event
        async def on_message(message: discord.Message) -> None:
            if isinstance(message.channel, discord.DMChannel) and not message.author.bot:
                await handle_dm(message, settings, pipeline, client)

        try:
            await bot.start(settings.discord_token)
        finally:
            await bot.close()
