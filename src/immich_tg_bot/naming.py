import logging
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from aiogram.types import Message

from .archives import ARCHIVE_EXTENSIONS

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class MessageMetadata:
    source: str
    source_id: str
    source_username: str
    message_id: str
    date: datetime
    sender: str
    index: int = 1
    msg_date: datetime | None = None
    forward_date: datetime | None = None
    exif_date: datetime | None = None
    media_type: str = "photo"
    file_unique_id: str = ""
    media_group_id: str = ""
    caption: str = ""
    original_name: str = ""
    msg_id: str = ""
    chat_title: str = ""
    chat_id: str = ""
    sender_id: str = ""
    forward_source: str = ""
    forward_channel: str = ""
    forward_author: str = ""
    forward_source_id: str = ""
    forward_msg_id: str = ""


class _Empty:
    def __str__(self) -> str:
        return ""

    def __format__(self, format_spec: str) -> str:
        return ""


class _SafeDict(dict[str, Any]):
    def __missing__(self, key: str) -> Any:
        log.warning("Unknown template variable %r", key)
        return _Empty()


def sanitize_stem(raw: str, max_length: int = 200) -> str:
    cleaned = re.sub(r'[/\\:*?"<>|\r\n\t]+', "_", raw)
    cleaned = re.sub(r"_+", "_", cleaned)
    cleaned = cleaned.strip(" _.")
    return cleaned[:max_length].rstrip(" _.")


def _build_template_mapping(metadata: MessageMetadata) -> _SafeDict:
    return _SafeDict(
        {
            "source": metadata.source,
            "source_id": metadata.source_id,
            "source_username": metadata.source_username,
            "username": metadata.source_username,
            "message_id": metadata.message_id,
            "date": metadata.date,
            "sender": metadata.sender,
            "index": metadata.index,
            "msg_date": metadata.msg_date or metadata.date,
            "forward_date": metadata.forward_date or _Empty(),
            "exif_date": metadata.exif_date or _Empty(),
            "media_type": metadata.media_type,
            "file_unique_id": metadata.file_unique_id,
            "media_group_id": metadata.media_group_id,
            "caption": metadata.caption,
            "original_name": metadata.original_name,
            "msg_id": metadata.msg_id,
            "chat_title": metadata.chat_title,
            "chat_id": metadata.chat_id,
            "sender_id": metadata.sender_id,
            "forward_source": metadata.forward_source,
            "forward_channel": metadata.forward_channel,
            "forward_author": metadata.forward_author,
            "forward_source_id": metadata.forward_source_id,
            "forward_msg_id": metadata.forward_msg_id,
        }
    )


def render_stem(
    template: str,
    metadata: MessageMetadata,
    default_template: str = "",
    allow_empty: bool = False,
) -> str:
    mapping = _build_template_mapping(metadata)
    try:
        rendered = template.format_map(mapping)
        stem = sanitize_stem(rendered)
        if stem:
            return stem
    except Exception as e:
        log.warning("Template rendering failed for %r: %s", template, e)

    if default_template and default_template != template:
        try:
            rendered = default_template.format_map(mapping)
            stem = sanitize_stem(rendered)
            if stem:
                return stem
        except Exception as e:
            log.warning("Default template rendering failed for %r: %s", default_template, e)

    if allow_empty:
        return ""

    fallback = f"{metadata.source}_{metadata.message_id}_{metadata.index}"
    stem = sanitize_stem(fallback)
    return stem or f"file_{metadata.index}"


def resolve_filename(
    stem_template: str,
    metadata: MessageMetadata,
    extension: str,
    default_template: str = "{source}_{message_id}_{index}",
) -> str:
    ext = extension if extension.startswith(".") or not extension else f".{extension}"
    stem = render_stem(stem_template, metadata, default_template=default_template)
    if not stem:
        stem = f"file_{metadata.index}"
    return f"{stem}{ext}"


def resolve_album_name(
    template: str,
    metadata: MessageMetadata,
    fallback_album: str | None = None,
) -> str | None:
    if not template or not template.strip():
        return fallback_album
    stem = render_stem(template, metadata, default_template="", allow_empty=True)
    if not stem or not stem.strip():
        return fallback_album
    return stem.strip()


def split_filename(filename: str) -> tuple[str, str]:
    """Split a filename, retaining known compound archive extensions and their case."""
    path = Path(filename)
    for extension in ARCHIVE_EXTENSIONS:
        if extension.count(".") > 1 and path.name.lower().endswith(extension):
            return path.name[: -len(extension)], path.name[-len(extension) :]
    return path.stem, path.suffix


def disambiguate_filenames(filenames: Sequence[str]) -> list[str]:
    counts = Counter(filenames)
    if not any(c > 1 for c in counts.values()):
        return list(filenames)

    allocated: set[str] = set()
    result: list[str] = []
    counters: dict[str, int] = {}

    for fn in filenames:
        if counts[fn] == 1 and fn not in allocated:
            allocated.add(fn)
            result.append(fn)
            continue

        stem, ext = split_filename(fn)
        idx = counters.get(fn, 1)
        candidate = f"{stem}_{idx}{ext}"
        while candidate in allocated or (candidate in counts and counts[candidate] == 1):
            idx += 1
            candidate = f"{stem}_{idx}{ext}"

        counters[fn] = idx + 1
        allocated.add(candidate)
        result.append(candidate)

    return result


def _extract_chat_info(chat: Any) -> tuple[str, str, str]:
    if not chat:
        return "", "", ""
    title = getattr(chat, "title", None) or getattr(chat, "username", None) or ""
    chat_id = str(chat.id) if getattr(chat, "id", None) is not None else ""
    username = getattr(chat, "username", None) or ""
    return title, chat_id, username


def extract_metadata(
    message: Message,
    target_tz: ZoneInfo,
    index: int = 1,
    file_unique_id: str = "",
    media_type: str = "photo",
    original_name: str = "",
    exif_date: datetime | None = None,
) -> MessageMetadata:
    sender = ""
    sender_id = ""
    if message.from_user:
        sender = message.from_user.full_name or message.from_user.username or ""
        sender_id = str(message.from_user.id)

    chat = message.chat
    chat_title = (getattr(chat, "title", None) or getattr(chat, "full_name", "")) or ""
    chat_id = str(chat.id) if (chat and getattr(chat, "id", None) is not None) else ""
    chat_username = getattr(chat, "username", "") or "" if chat else ""

    msg_id = str(message.message_id)
    msg_date = message.date.astimezone(target_tz) if message.date else datetime.now(target_tz)

    raw_caption = message.caption or ""
    caption = re.sub(r"[\r\n\t]+", "_", raw_caption).strip()[:50]

    forward_source = ""
    forward_channel = ""
    forward_author = ""
    forward_source_id = ""
    forward_msg_id = ""
    fwd_username = ""
    fwd_date: datetime | None = None

    origin = getattr(message, "forward_origin", None)
    if origin:
        orig_type = getattr(origin, "type", "")
        if orig_type == "channel":
            title, cid, uname = _extract_chat_info(getattr(origin, "chat", None))
            forward_channel = getattr(getattr(origin, "chat", None), "title", "") or ""
            forward_source = title
            forward_source_id = cid
            fwd_username = uname
            forward_author = getattr(origin, "author_signature", "") or ""
            if getattr(origin, "message_id", None):
                forward_msg_id = str(origin.message_id)
        elif orig_type == "chat":
            title, cid, uname = _extract_chat_info(getattr(origin, "sender_chat", None))
            forward_source = title
            forward_source_id = cid
            fwd_username = uname
            forward_author = getattr(origin, "author_signature", "") or ""
        elif orig_type == "user":
            user = getattr(origin, "sender_user", None)
            if user:
                forward_source = user.full_name or user.username or ""
                forward_source_id = str(user.id)
                fwd_username = user.username or ""
                forward_author = user.full_name or ""
        elif orig_type == "hidden_user":
            forward_source = getattr(origin, "sender_user_name", "") or ""
            forward_author = forward_source

        orig_dt = getattr(origin, "date", None)
        if orig_dt:
            fwd_date = orig_dt.astimezone(target_tz)
    else:
        # Legacy forward fields
        fwd_chat = getattr(message, "forward_from_chat", None)
        if fwd_chat:
            title, cid, uname = _extract_chat_info(fwd_chat)
            forward_channel = getattr(fwd_chat, "title", "") or ""
            forward_source = title
            forward_source_id = cid
            fwd_username = uname
            if getattr(message, "forward_from_message_id", None):
                forward_msg_id = str(message.forward_from_message_id)
        fwd_user = getattr(message, "forward_from", None)
        if fwd_user:
            forward_source = fwd_user.full_name or fwd_user.username or forward_source
            forward_source_id = str(fwd_user.id)
            fwd_username = fwd_user.username or fwd_username
        if getattr(message, "forward_signature", None):
            forward_author = message.forward_signature or ""
        if getattr(message, "forward_sender_name", None):
            forward_source = message.forward_sender_name or forward_source
        legacy_fwd_date = getattr(message, "forward_date", None)
        if legacy_fwd_date:
            fwd_date = legacy_fwd_date.astimezone(target_tz)

    source = forward_source or chat_title or sender or "telegram"
    source_id = forward_source_id or chat_id or sender_id or ""
    current_username = message.from_user.username if message.from_user else ""
    source_username = fwd_username or chat_username or current_username or ""

    message_id = forward_msg_id or msg_id
    date = fwd_date or msg_date

    exif_dt = exif_date.astimezone(target_tz) if exif_date else None

    # Strip extension from original_name if provided
    stem_original = split_filename(original_name)[0] if original_name else ""

    return MessageMetadata(
        source=source,
        source_id=source_id,
        source_username=source_username,
        message_id=message_id,
        date=date,
        sender=sender,
        index=index,
        msg_date=msg_date,
        forward_date=fwd_date,
        exif_date=exif_dt,
        media_type=media_type,
        file_unique_id=file_unique_id,
        media_group_id=message.media_group_id or "",
        caption=caption,
        original_name=stem_original,
        msg_id=msg_id,
        chat_title=chat_title,
        chat_id=chat_id,
        sender_id=sender_id,
        forward_source=forward_source,
        forward_channel=forward_channel,
        forward_author=forward_author,
        forward_source_id=forward_source_id,
        forward_msg_id=forward_msg_id,
    )
