import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from immich_chat_importer.pipeline import IngestionPipeline, IngestItem
from immich_chat_importer.state import State


async def test_archive_input_limit_rejects_before_extraction(tmp_path):
    archive = tmp_path / "large.zip"
    archive.write_bytes(b"x" * (1024 * 1024 + 1))
    immich = AsyncMock()
    pipeline = IngestionPipeline(immich, State(), max_archive_mb=1)
    result = await pipeline.ingest([IngestItem(1, 1, archive, archive.name, datetime.now(UTC))])
    assert result.errors == 1
    assert result.error_details == [("large.zip", "extract", "failure_size")]
    immich.upload_asset.assert_not_called()


async def test_discord_cancelled_download_removes_all_temporary_files(tmp_path):
    from types import SimpleNamespace

    import httpx
    import pytest

    from immich_chat_importer.config import Settings
    from immich_chat_importer.adapters.discord.bot import process_import

    entered = asyncio.Event()

    async def respond(request):
        if request.url.path == "/second":
            entered.set()
            await asyncio.Event().wait()
        return httpx.Response(200, content=b"image")

    settings = Settings.model_construct(data_dir=tmp_path, discord_allowed_user_ids=[42])
    message = SimpleNamespace(
        id=1,
        channel=SimpleNamespace(id=42),
        author=SimpleNamespace(id=42, name="Alice"),
        created_at=datetime.now(UTC),
        content="",
        attachments=[
            SimpleNamespace(id=i, filename=f"{i}.jpg", size=5, url=f"https://cdn.test/{name}")
            for i, name in enumerate(["first", "second"])
        ],
    )
    pipeline = IngestionPipeline(AsyncMock(), State())
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        task = asyncio.create_task(process_import(message, 42, settings, pipeline, client))
        try:
            await asyncio.wait_for(entered.wait(), 5)
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
    assert list((tmp_path / "discord-downloads").iterdir()) == []


@pytest.mark.parametrize("stop_during_upload", [False, True])
async def test_telegram_shared_media_and_shutdown(tmp_path, monkeypatch, stop_during_upload):
    from aiogram import Bot, Dispatcher
    from aiogram.types import File, Message

    from immich_chat_importer.adapters.telegram.bot import run_bot
    from immich_chat_importer.config import Settings

    source = tmp_path / "shared.jpg"
    source.write_bytes(b"image")
    monkeypatch.setattr(
        Bot,
        "get_file",
        AsyncMock(
            return_value=File(file_id="file", file_unique_id="unique", file_path=str(source))
        ),
    )
    monkeypatch.setattr("immich_chat_importer.adapters.telegram.bot._MEDIA_GROUP_DEBOUNCE", 0.01)
    entered, finished, replied = asyncio.Event(), asyncio.Event(), asyncio.Event()
    immich = AsyncMock()
    uploads = []

    async def upload(**kwargs):
        uploads.append(kwargs["file_path"].read_bytes())
        entered.set()
        try:
            if stop_during_upload:
                await asyncio.Event().wait()
            return {"id": "asset", "status": "created"}
        finally:
            finished.set()

    immich.upload_asset.side_effect = upload
    pipeline = IngestionPipeline(immich, State())

    async def reply(*args, **kwargs):
        replied.set()

    monkeypatch.setattr(Message, "reply", reply)
    from aiogram.client.session.aiohttp import AiohttpSession

    original_close = AiohttpSession.close

    async def close(session):
        if stop_during_upload and entered.is_set():
            assert finished.is_set(), "close session only after ingestion has stopped"
        await original_close(session)

    monkeypatch.setattr(AiohttpSession, "close", close)

    async def poll(dispatcher, bot, **kwargs):
        handler = next(
            h.callback for h in dispatcher.message.handlers if h.callback.__name__ == "on_media"
        )
        for i in [1, 2]:
            await handler(
                Message.model_validate(
                    {
                        "message_id": i,
                        "date": datetime.now(UTC),
                        "media_group_id": "group",
                        "chat": {"id": 42, "type": "private"},
                        "from": {"id": 42, "is_bot": False, "first_name": "Alice"},
                        "document": {
                            "file_id": "file",
                            "file_unique_id": "unique",
                            "file_name": "photo.jpg",
                        },
                    }
                )
            )
        await asyncio.wait_for((entered if stop_during_upload else replied).wait(), 5)

        # Model aiogram's default session ownership at the external boundary.
        if kwargs.get("close_bot_session", True):
            await bot.session.close()

    monkeypatch.setattr(Dispatcher, "start_polling", poll)
    settings = Settings.model_construct(
        immich_url="https://immich.test",
        telegram_bot_token="123456:test-token",
        telegram_allowed_user_ids=[42],
        telegram_files_dir=tmp_path,
        data_dir=tmp_path,
    )
    await run_bot(settings, pipeline)
    if stop_during_upload:
        assert finished.is_set(), "run_bot must await running ingestion cancellation"
    else:
        record = (await pipeline.state.recent_ingest_records(42, platform="telegram"))[0]
        assert (record.uploaded, record.errors) == (2, 0)
        assert uploads == [b"image", b"image"]
        assert source.exists(), "Bot API cache belongs to the source adapter"
