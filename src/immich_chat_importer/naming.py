import logging
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

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


def extract_metadata(*args: Any, **kwargs: Any) -> MessageMetadata:
    """Compatibility entry point for Telegram metadata extraction."""
    from .adapters.telegram.metadata import extract_metadata as extract_telegram_metadata

    return extract_telegram_metadata(*args, **kwargs)
