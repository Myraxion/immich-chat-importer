from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from aiogram import Bot

from immich_tg_bot.bot import _resolve_local_path


@pytest.mark.asyncio
async def test_telegram_status_only_shows_callers_telegram_records():
    from immich_tg_bot.bot import handle_telegram_status
    from immich_tg_bot.state import State

    state = State()
    record_id = await state.create_ingest_record(42, "1", "own", platform="telegram")
    await state.finish_ingest_record(record_id, "completed", 1, 0, 0, 0, "")
    discord_id = await state.create_ingest_record(42, "2", "discord-secret", platform="discord")
    other_id = await state.create_ingest_record(99, "3", "other-secret", platform="telegram")
    replies = []

    async def reply(text):
        replies.append(text)

    message = SimpleNamespace(
        chat=SimpleNamespace(type="private"),
        from_user=SimpleNamespace(id=42, language_code="en"),
        reply=reply,
    )
    await handle_telegram_status(message, state, "en")
    assert len(replies) == 1
    assert f"#{record_id}" in replies[0]
    assert f"#{discord_id}" not in replies[0]
    assert f"#{other_id}" not in replies[0]


class FakeBot:
    def __init__(self, token: str, file_path: str | None) -> None:
        self.token = token
        self.file_path = file_path

    async def get_file(self, file_id: str) -> SimpleNamespace:
        return SimpleNamespace(file_path=self.file_path)


@pytest.mark.asyncio
async def test_resolve_local_path_uses_per_bot_directory(tmp_path: Path) -> None:
    token = "123_token"
    expected = tmp_path / token / "photos" / "file_1.jpg"
    expected.parent.mkdir(parents=True)
    expected.touch()

    bot = cast(Bot, FakeBot(token, "photos/file_1.jpg"))
    actual = await _resolve_local_path(bot, "file-id", tmp_path)

    assert actual == expected


@pytest.mark.asyncio
async def test_extract_ingest_item_from_document(tmp_path: Path) -> None:
    from datetime import UTC, datetime

    from immich_tg_bot.bot import _extract_ingest_item

    token = "test_bot"
    doc_path = tmp_path / token / "docs" / "vacation.zip"
    doc_path.parent.mkdir(parents=True)
    doc_path.touch()

    bot = cast(Bot, FakeBot(token, "docs/vacation.zip"))
    msg = SimpleNamespace(
        chat=SimpleNamespace(id=12345),
        message_id=67890,
        date=datetime(2026, 9, 24, 12, 0, tzinfo=UTC),
        document=SimpleNamespace(file_id="file-doc-1", file_name="vacation.zip"),
        video=None,
        animation=None,
        audio=None,
        voice=None,
        video_note=None,
        photo=None,
    )

    item = await _extract_ingest_item(bot, cast(Any, msg), tmp_path)
    assert item is not None
    assert item.chat_id == 12345
    assert item.message_id == 67890
    assert item.file_name == "vacation.zip"
    assert item.local_path == doc_path
    assert item.created_at == datetime(2026, 9, 24, 12, 0, tzinfo=UTC)


@pytest.mark.asyncio
async def test_extract_ingest_item_returns_none_for_text_message(tmp_path: Path) -> None:
    from immich_tg_bot.bot import _extract_ingest_item

    bot = cast(Bot, FakeBot("test_bot", None))
    msg = SimpleNamespace(
        chat=SimpleNamespace(id=12345),
        message_id=67890,
        date=None,
        document=None,
        video=None,
        animation=None,
        audio=None,
        voice=None,
        video_note=None,
        photo=None,
    )
    item = await _extract_ingest_item(bot, cast(Any, msg), tmp_path)
    assert item is None


@pytest.mark.asyncio
async def test_extract_ingest_item_from_photo_uses_dynamic_naming(tmp_path: Path) -> None:
    from datetime import UTC, datetime

    from immich_tg_bot.bot import _extract_ingest_item
    from immich_tg_bot.config import Settings

    token = "test_bot"
    photo_path = tmp_path / token / "photos" / "file_0.jpg"
    photo_path.parent.mkdir(parents=True)
    photo_path.touch()

    bot = cast(Bot, FakeBot(token, "photos/file_0.jpg"))
    msg = SimpleNamespace(
        chat=SimpleNamespace(id=12345, title="MyChat", full_name="MyChat"),
        message_id=999,
        date=datetime(2026, 9, 24, 12, 0, tzinfo=UTC),
        from_user=SimpleNamespace(id=1, full_name="User", username="user"),
        caption=None,
        media_group_id=None,
        forward_origin=None,
        photo=[SimpleNamespace(file_id="photo-1", file_unique_id="uniq-1")],
        document=None,
        video=None,
        animation=None,
        audio=None,
        voice=None,
        video_note=None,
    )

    settings = Settings.model_construct(
        tz="UTC",
        telegram_media_name_template="{source}_{message_id}_{index}",
        telegram_document_name_template="{original_name}",
        telegram_album_name_template="{source}",
        telegram_album_name="DefaultAlbum",
    )

    item = await _extract_ingest_item(bot, cast(Any, msg), tmp_path, settings=settings, index=1)
    assert item is not None
    assert item.file_name == "MyChat_999_1.jpg"
    assert item.target_album == "MyChat"


@pytest.mark.parametrize(
    ("media_type", "original_name", "mime_type", "cached_name", "expected_suffix"),
    [
        ("video", "clip.mp4", "video/mp4", "file_154", ".mp4"),
        ("video", None, "video/mp4", "file_154", ".mp4"),
        ("video", "clip.mov", "video/quicktime", "file_154.mp4", ".mov"),
        ("animation", None, "image/gif", "file_154", ".gif"),
        ("video_note", None, None, "file_154", ".mp4"),
    ],
)
async def test_extract_ingest_item_preserves_media_extension(
    tmp_path: Path,
    media_type: str,
    original_name: str | None,
    mime_type: str | None,
    cached_name: str,
    expected_suffix: str,
) -> None:
    from aiogram.types import Message

    from immich_tg_bot.bot import _extract_ingest_item
    from immich_tg_bot.config import Settings

    cached = tmp_path / cached_name
    cached.touch()
    media = {
        "file_id": "file-id",
        "file_unique_id": "unique-id",
        "width": 1,
        "height": 1,
        "length": 1,
        "duration": 1,
        "file_name": original_name,
        "mime_type": mime_type,
    }
    message = Message.model_validate(
        {
            "message_id": 341,
            "date": 1792573200,
            "chat": {"id": 123, "type": "private", "first_name": "Test"},
            media_type: media,
        }
    )
    bot = cast(Bot, FakeBot("test_bot", str(cached)))
    item = await _extract_ingest_item(
        bot, message, tmp_path, settings=Settings.model_construct(tz="UTC")
    )

    assert item is not None
    assert Path(item.file_name).suffix == expected_suffix


def test_format_summary_reply_languages() -> None:
    from immich_tg_bot.bot import format_summary_reply
    from immich_tg_bot.pipeline import IngestSummary

    # 1. uploaded only
    s1 = IngestSummary(uploaded=3, duplicates=0, errors=0)
    assert "已上传：3" in format_summary_reply(s1, lang_code="zh-Hans")
    assert "Uploaded: 3" in format_summary_reply(s1, lang_code="en")
    assert "アップロード済み: 3" in format_summary_reply(s1, lang_code="ja")
    assert "Загружено: 3" in format_summary_reply(s1, lang_code="ru")

    # 2. duplicates only
    s2 = IngestSummary(uploaded=0, duplicates=2, errors=0)
    assert "已存在于 Immich（重复项：2）" in format_summary_reply(s2, lang_code="zh")
    assert "Already in Immich (duplicates: 2)" in format_summary_reply(s2, lang_code="en")

    # 3. uploaded and duplicates
    s3 = IngestSummary(uploaded=2, duplicates=1, errors=0)
    assert "已上传：2，重复项：1" in format_summary_reply(s3, lang_code="zh")
    assert "Uploaded: 2, duplicates: 1" in format_summary_reply(s3, lang_code="en")

    # 4. errors only
    s4 = IngestSummary(uploaded=0, duplicates=0, errors=2)
    assert "失败：2" in format_summary_reply(s4, lang_code="zh")
    assert "Errors: 2" in format_summary_reply(s4, lang_code="en")

    # 5. mixed
    s5 = IngestSummary(uploaded=1, duplicates=1, errors=1)
    assert "已上传：1，重复项：1，失败：1" in format_summary_reply(s5, lang_code="zh")
    assert "Uploaded: 1, duplicates: 1, errors: 1" in format_summary_reply(s5, lang_code="en")

    # 6. no media
    s6 = IngestSummary(uploaded=0, duplicates=0, errors=0)
    assert "未找到可供上传的媒体文件" in format_summary_reply(s6, lang_code="zh")
    assert "No media found in this message to upload" in format_summary_reply(s6, lang_code="en")

    # 7. fallback when unsupported or None
    assert "Uploaded: 3" in format_summary_reply(s1, lang_code="fr", default_lang="en")
    assert "Загружено: 3" in format_summary_reply(s1, lang_code=None, default_lang="ru")


def test_summary_reply_includes_escaped_stage_and_file_context() -> None:
    from immich_tg_bot.bot import format_summary_reply
    from immich_tg_bot.pipeline import IngestSummary

    summary = IngestSummary(
        uploaded=1, errors=1, error_messages=["photo<1>.jpg: album association: unavailable"]
    )
    reply = format_summary_reply(summary, lang_code="en")
    assert "Uploaded: 1" in reply
    assert "photo&lt;1&gt;.jpg: album association: unavailable" in reply
    assert "关联相册" in format_summary_reply(summary, lang_code="zh")


def test_large_summary_is_split_into_valid_telegram_messages() -> None:
    from immich_tg_bot.bot import format_summary_replies
    from immich_tg_bot.pipeline import IngestSummary

    errors = [f"photo-{i}.jpg: album association: unavailable" for i in range(300)]
    replies = format_summary_replies(IngestSummary(uploaded=300, errors=300, error_messages=errors))
    assert len(replies) > 1
    assert all(len(reply) <= 4000 for reply in replies)
    assert "Uploaded: 300" in replies[0]
    assert all(error in "\n".join(replies) for error in errors)


@pytest.mark.parametrize(
    ("original_name", "template", "expected"),
    [
        ("trip.tar.gz", "{source}_{message_id}", "Alice_42.tar.gz"),
        ("trip.tar.bz2", "{source}_{message_id}", "Alice_42.tar.bz2"),
        ("trip.TAR.XZ", "{source}_{message_id}", "Alice_42.TAR.XZ"),
        ("trip.tar.gz", "{original_name}", "trip.tar.gz"),
        ("trip.tar.gz", "{source}_{original_name}", "Alice_trip.tar.gz"),
        ("holiday.2026.jpg", "{original_name}", "holiday.2026.jpg"),
    ],
)
async def test_extract_ingest_item_preserves_document_extension(
    tmp_path: Path, original_name: str, template: str, expected: str
) -> None:
    from aiogram.types import Message

    from immich_tg_bot.bot import _extract_ingest_item
    from immich_tg_bot.config import Settings

    cached = tmp_path / "file_0"
    cached.touch()
    message = Message.model_validate(
        {
            "message_id": 42,
            "date": 1792573200,
            "chat": {"id": 123, "type": "private", "first_name": "Alice"},
            "document": {
                "file_id": "file-id",
                "file_unique_id": "unique-id",
                "file_name": original_name,
            },
        }
    )
    bot = cast(Bot, FakeBot("test_bot", str(cached)))
    item = await _extract_ingest_item(
        bot,
        message,
        tmp_path,
        settings=Settings.model_construct(tz="UTC", telegram_document_name_template=template),
    )

    assert item is not None
    assert item.file_name == expected
    assert item.original_file_name == original_name
