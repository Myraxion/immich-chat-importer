import re
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from ...naming import MessageMetadata, split_filename
from .message import Message


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
