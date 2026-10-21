from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot
from aiogram.types import Message

from immich_tg_bot.bot import _extract_ingest_item
from immich_tg_bot.config import Settings
from immich_tg_bot.pipeline import IngestionPipeline, IngestItem
from immich_tg_bot.state import State


@pytest.fixture
async def state(tmp_path: Path) -> AsyncIterator[State]:
    db_path = tmp_path / "test_state.sqlite"
    s = State(db_path)
    await s.open()
    yield s
    await s.close()


@pytest.fixture
def fake_immich() -> AsyncMock:
    client = AsyncMock()
    client.upload_asset.return_value = {"id": "asset-123", "status": "created"}
    client.add_to_album.return_value = None
    return client


@pytest.mark.parametrize(
    ("original_name", "rendered_name", "expected_upload"),
    [
        ("trip.tar.gz", "Alice_42.gz", "photo.jpg"),
        ("photo.jpg", "Alice.zip", "Alice.zip"),
    ],
)
async def test_ingest_uses_original_filename_to_identify_archives(
    tmp_path: Path,
    state: State,
    fake_immich: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
    original_name: str,
    rendered_name: str,
    expected_upload: str,
) -> None:
    cached = tmp_path / "file_0"
    cached.write_bytes(b"payload")

    async def fake_subprocess(*args: str, **kwargs: Any) -> SimpleNamespace:
        (Path(args[-1]) / "photo.jpg").write_bytes(b"extracted image")
        return SimpleNamespace(returncode=0, communicate=AsyncMock(return_value=(b"", b"")))

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_subprocess)
    item = IngestItem(
        chat_id=1001,
        message_id=2001,
        local_path=cached,
        file_name=rendered_name,
        created_at=datetime.now(UTC),
        original_file_name=original_name,
    )
    summary = await IngestionPipeline(immich=fake_immich, state=state).ingest([item])

    assert summary.uploaded == 1
    assert summary.errors == 0
    assert fake_immich.upload_asset.call_args.kwargs["file_name"] == expected_upload


@pytest.mark.parametrize(
    ("original_name", "cached_name", "mime_type"),
    [
        ("trip", "file_0.zip", None),
        ("trip", "file_0", "application/zip"),
        (None, "file_0", "application/zip"),
    ],
)
async def test_ingest_document_uses_inferred_archive_extension(
    tmp_path: Path,
    state: State,
    fake_immich: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
    original_name: str | None,
    cached_name: str,
    mime_type: str | None,
) -> None:
    cached = tmp_path / cached_name
    cached.write_bytes(b"archive payload")
    bot = cast(
        Bot,
        SimpleNamespace(get_file=AsyncMock(return_value=SimpleNamespace(file_path=str(cached)))),
    )
    message = Message.model_validate(
        {
            "message_id": 42,
            "date": 1792573200,
            "chat": {"id": 123, "type": "private", "first_name": "Alice"},
            "document": {
                "file_id": "file-id",
                "file_unique_id": "unique-id",
                "file_name": original_name,
                "mime_type": mime_type,
            },
        }
    )

    async def fake_subprocess(*args: str, **kwargs: Any) -> SimpleNamespace:
        (Path(args[-1]) / "photo.jpg").write_bytes(b"extracted image")
        return SimpleNamespace(returncode=0, communicate=AsyncMock(return_value=(b"", b"")))

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_subprocess)
    item = await _extract_ingest_item(
        bot, message, tmp_path, settings=Settings.model_construct(tz="UTC")
    )
    assert item is not None
    summary = await IngestionPipeline(immich=fake_immich, state=state).ingest([item])

    assert summary.uploaded == 1
    assert summary.errors == 0
    assert fake_immich.upload_asset.call_args.kwargs["file_name"] == "photo.jpg"


@pytest.mark.asyncio
async def test_ingest_single_file_uploads_and_updates_state(
    tmp_path: Path, state: State, fake_immich: AsyncMock
) -> None:
    # 1. 准备文件
    img_path = tmp_path / "photo.jpg"
    img_path.write_bytes(b"dummy image data")

    pipeline = IngestionPipeline(immich=fake_immich, state=state)
    item = IngestItem(
        chat_id=1001,
        message_id=2001,
        local_path=img_path,
        file_name="photo.jpg",
        created_at=datetime.now(UTC),
    )

    # 2. 执行摄取
    summary = await pipeline.ingest([item])

    # 3. 验证结果
    assert summary.uploaded == 1
    assert summary.duplicates == 0
    assert summary.errors == 0
    assert summary.new_asset_ids == ["asset-123"]

    # 4. 验证状态库更新 (Message-level and content-level)
    assert await state.already_processed(1001, 2001) is True
    fake_immich.upload_asset.assert_awaited_once()


@pytest.mark.asyncio
async def test_ingest_skips_when_message_already_processed(
    tmp_path: Path, state: State, fake_immich: AsyncMock
) -> None:
    img_path = tmp_path / "photo.jpg"
    img_path.write_bytes(b"dummy image data")

    await state.mark_processed(1001, 2001, 0, "done", None)

    pipeline = IngestionPipeline(immich=fake_immich, state=state)
    item = IngestItem(
        chat_id=1001,
        message_id=2001,
        local_path=img_path,
        file_name="photo.jpg",
        created_at=datetime.now(UTC),
    )

    summary = await pipeline.ingest([item])

    assert summary.uploaded == 0
    assert summary.duplicates == 1
    assert summary.errors == 0
    fake_immich.upload_asset.assert_not_awaited()


@pytest.mark.asyncio
async def test_ingest_skips_upload_when_sha1_matches(
    tmp_path: Path, state: State, fake_immich: AsyncMock
) -> None:
    # 第一次上传
    img_path_1 = tmp_path / "photo1.jpg"
    img_path_1.write_bytes(b"identical image bytes")

    pipeline = IngestionPipeline(immich=fake_immich, state=state)
    item1 = IngestItem(
        chat_id=1001,
        message_id=2001,
        local_path=img_path_1,
        file_name="photo1.jpg",
        created_at=datetime.now(UTC),
    )
    summary1 = await pipeline.ingest([item1])
    assert summary1.uploaded == 1
    assert fake_immich.upload_asset.await_count == 1

    # 第二次从不同消息上传相同内容
    img_path_2 = tmp_path / "photo2.jpg"
    img_path_2.write_bytes(b"identical image bytes")
    item2 = IngestItem(
        chat_id=1001,
        message_id=2002,  # 不同的 message_id
        local_path=img_path_2,
        file_name="photo2.jpg",
        created_at=datetime.now(UTC),
    )
    summary2 = await pipeline.ingest([item2])
    assert summary2.uploaded == 0
    assert summary2.duplicates == 1
    assert summary2.errors == 0
    # 没有发起第二次上传
    assert fake_immich.upload_asset.await_count == 1
    # 但第二次的消息也顺利标记为已完成
    assert await state.already_processed(1001, 2002) is True


@pytest.mark.asyncio
async def test_ingest_adds_new_assets_to_album(
    tmp_path: Path, state: State, fake_immich: AsyncMock
) -> None:
    img1 = tmp_path / "img1.jpg"
    img1.write_bytes(b"image 1")
    img2 = tmp_path / "img2.jpg"
    img2.write_bytes(b"image 2")

    fake_immich.upload_asset.side_effect = [
        {"id": "asset-1", "status": "created"},
        {"id": "asset-2", "status": "created"},
    ]

    pipeline = IngestionPipeline(immich=fake_immich, state=state, album_id="album-999")
    items = [
        IngestItem(1001, 2001, img1, "img1.jpg", datetime.now(UTC)),
        IngestItem(1001, 2002, img2, "img2.jpg", datetime.now(UTC)),
    ]

    summary = await pipeline.ingest(items)

    assert summary.uploaded == 2
    assert summary.new_asset_ids == ["asset-1", "asset-2"]
    fake_immich.add_to_album.assert_awaited_once_with("album-999", ["asset-1", "asset-2"])


@pytest.mark.asyncio
async def test_ingest_album_failure_does_not_fail_upload(
    tmp_path: Path, state: State, fake_immich: AsyncMock
) -> None:
    img = tmp_path / "img.jpg"
    img.write_bytes(b"image content")
    fake_immich.upload_asset.return_value = {"id": "asset-1", "status": "created"}
    fake_immich.add_to_album.side_effect = RuntimeError("Immich album service unavailable")

    pipeline = IngestionPipeline(immich=fake_immich, state=state, album_id="album-999")
    item = IngestItem(1001, 2001, img, "img.jpg", datetime.now(UTC))

    summary = await pipeline.ingest([item])

    # 软降级：资产依然计入 uploaded，消息依然成功完成标记
    assert summary.uploaded == 1
    assert summary.errors == 0
    assert await state.already_processed(1001, 2001) is True


@pytest.mark.asyncio
async def test_ingest_archive_extracts_and_uploads_media(
    tmp_path: Path, state: State, fake_immich: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    zip_path = tmp_path / "bundle.zip"
    zip_path.touch()

    async def fake_extract(archive: Path, dest: Path) -> None:
        (dest / "photo1.jpg").write_bytes(b"content 1")
        (dest / "photo2.png").write_bytes(b"content 2")
        (dest / "readme.txt").write_bytes(b"skip me")

    monkeypatch.setattr("immich_tg_bot.pipeline.extract", fake_extract)

    fake_immich.upload_asset.side_effect = [
        {"id": "asset-1", "status": "created"},
        {"id": "asset-2", "status": "created"},
    ]

    pipeline = IngestionPipeline(immich=fake_immich, state=state)
    item = IngestItem(1001, 2001, zip_path, "bundle.zip", datetime.now(UTC))

    summary = await pipeline.ingest([item])

    assert summary.uploaded == 2
    assert summary.duplicates == 0
    assert summary.errors == 0
    assert summary.new_asset_ids == ["asset-1", "asset-2"]
    assert await state.already_processed(1001, 2001) is True


@pytest.mark.asyncio
async def test_ingest_archive_extract_failure_records_error(
    tmp_path: Path, state: State, fake_immich: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    corrupt_zip = tmp_path / "corrupt.zip"
    corrupt_zip.touch()

    async def fail_extract(archive: Path, dest: Path) -> None:
        raise RuntimeError("Corrupt archive data")

    monkeypatch.setattr("immich_tg_bot.pipeline.extract", fail_extract)

    pipeline = IngestionPipeline(immich=fake_immich, state=state)
    item = IngestItem(1001, 2001, corrupt_zip, "corrupt.zip", datetime.now(UTC))

    summary = await pipeline.ingest([item])

    assert summary.uploaded == 0
    assert summary.errors == 1
    assert "Corrupt archive data" in summary.error_messages[0]
    # 解压失败绝对不能将消息标记为已处理！
    assert await state.already_processed(1001, 2001) is False


@pytest.mark.asyncio
async def test_ingest_archive_with_no_media_marks_processed(
    tmp_path: Path, state: State, fake_immich: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    empty_zip = tmp_path / "empty.zip"
    empty_zip.touch()

    async def fake_extract(archive: Path, dest: Path) -> None:
        (dest / "readme.txt").write_bytes(b"no photos here")

    monkeypatch.setattr("immich_tg_bot.pipeline.extract", fake_extract)

    pipeline = IngestionPipeline(immich=fake_immich, state=state)
    item = IngestItem(1001, 2001, empty_zip, "empty.zip", datetime.now(UTC))

    summary = await pipeline.ingest([item])

    assert summary.uploaded == 0
    assert summary.errors == 0
    assert await state.already_processed(1001, 2001) is True


@pytest.mark.asyncio
async def test_ingest_single_file_failure_isolates_and_does_not_mark_processed(
    tmp_path: Path, state: State, fake_immich: AsyncMock
) -> None:
    img1 = tmp_path / "img1.jpg"
    img1.write_bytes(b"image 1")
    img2 = tmp_path / "img2.jpg"
    img2.write_bytes(b"image 2")

    fake_immich.upload_asset.side_effect = [
        RuntimeError("Network timeout on img1"),
        {"id": "asset-2", "status": "created"},
    ]

    pipeline = IngestionPipeline(immich=fake_immich, state=state)
    item1 = IngestItem(1001, 2001, img1, "img1.jpg", datetime.now(UTC))
    item2 = IngestItem(1001, 2002, img2, "img2.jpg", datetime.now(UTC))

    summary = await pipeline.ingest([item1, item2])

    assert summary.uploaded == 1
    assert summary.errors == 1
    assert summary.new_asset_ids == ["asset-2"]
    # 失败的消息 2001 未完成标记，成功的消息 2002 已完成标记
    assert await state.already_processed(1001, 2001) is False
    assert await state.already_processed(1001, 2002) is True


@pytest.mark.asyncio
async def test_ingest_archive_partial_failure_allows_safe_retry(
    tmp_path: Path, state: State, fake_immich: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    zip_path = tmp_path / "photos.zip"
    zip_path.touch()

    async def fake_extract(archive: Path, dest: Path) -> None:
        (dest / "photo1.jpg").write_bytes(b"content 1")
        (dest / "photo2.jpg").write_bytes(b"content 2")

    monkeypatch.setattr("immich_tg_bot.pipeline.extract", fake_extract)

    # 第一次尝试：photo1 成功，photo2 失败
    fake_immich.upload_asset.side_effect = [
        {"id": "asset-1", "status": "created"},
        RuntimeError("Temporary upload error on photo2"),
    ]

    pipeline = IngestionPipeline(immich=fake_immich, state=state)
    item = IngestItem(1001, 2001, zip_path, "photos.zip", datetime.now(UTC))

    summary1 = await pipeline.ingest([item])
    assert summary1.uploaded == 1
    assert summary1.errors == 1
    # 消息因为有部分失败，不能标记为已处理
    assert await state.already_processed(1001, 2001) is False

    # 第二次尝试（用户重试）：photo1 命中 SHA-1 缓存，photo2 重新上传成功
    fake_immich.upload_asset.side_effect = [
        {"id": "asset-2", "status": "created"},
    ]

    summary2 = await pipeline.ingest([item])
    assert summary2.duplicates == 1  # photo1 走 SHA-1 缓存跳过
    assert summary2.uploaded == 1  # photo2 成功上传
    assert summary2.errors == 0
    # 全部无错后，消息成功标记完成
    assert await state.already_processed(1001, 2001) is True


@pytest.mark.asyncio
async def test_ingest_passes_custom_file_name_to_upload_asset(
    tmp_path: Path, state: State, fake_immich: AsyncMock
) -> None:
    img_path = tmp_path / "raw_temp_name.jpg"
    img_path.write_bytes(b"dummy image data")

    pipeline = IngestionPipeline(immich=fake_immich, state=state)
    item = IngestItem(
        chat_id=1001,
        message_id=2001,
        local_path=img_path,
        file_name="custom_rendered_name.jpg",
        created_at=datetime.now(UTC),
    )

    await pipeline.ingest([item])

    fake_immich.upload_asset.assert_awaited_once()
    kwargs = fake_immich.upload_asset.call_args.kwargs
    assert kwargs.get("file_name") == "custom_rendered_name.jpg"


@pytest.mark.asyncio
async def test_ingest_dynamic_album_routing_groups_assets(
    tmp_path: Path, state: State, fake_immich: AsyncMock
) -> None:
    img1 = tmp_path / "img1.jpg"
    img1.write_bytes(b"data 1")
    img2 = tmp_path / "img2.jpg"
    img2.write_bytes(b"data 2")
    img3 = tmp_path / "img3.jpg"
    img3.write_bytes(b"data 3")

    fake_immich.upload_asset.side_effect = [
        {"id": "asset-1", "status": "created"},
        {"id": "asset-2", "status": "created"},
        {"id": "asset-3", "status": "created"},
    ]
    fake_immich.get_or_create_album.side_effect = lambda name: f"id-{name}"

    pipeline = IngestionPipeline(immich=fake_immich, state=state)
    item1 = IngestItem(
        chat_id=1001,
        message_id=2001,
        local_path=img1,
        file_name="img1.jpg",
        created_at=datetime.now(UTC),
        target_album="Channel_A",
    )
    item2 = IngestItem(
        chat_id=1001,
        message_id=2002,
        local_path=img2,
        file_name="img2.jpg",
        created_at=datetime.now(UTC),
        target_album="Channel_B",
    )
    item3 = IngestItem(
        chat_id=1001,
        message_id=2003,
        local_path=img3,
        file_name="img3.jpg",
        created_at=datetime.now(UTC),
        target_album="Channel_A",
    )

    summary = await pipeline.ingest([item1, item2, item3])
    assert summary.uploaded == 3

    # Channel_A should have asset-1 and asset-3; Channel_B should have asset-2
    fake_immich.add_to_album.assert_any_await("id-Channel_A", ["asset-1", "asset-3"])
    fake_immich.add_to_album.assert_any_await("id-Channel_B", ["asset-2"])


@pytest.mark.asyncio
async def test_ingest_cleans_up_local_file_on_success(
    tmp_path: Path, state: State, fake_immich: AsyncMock
) -> None:
    img_path = tmp_path / "photo.jpg"
    img_path.write_bytes(b"dummy image data")

    pipeline = IngestionPipeline(immich=fake_immich, state=state, cleanup_local=True)
    item = IngestItem(
        chat_id=1001,
        message_id=2001,
        local_path=img_path,
        file_name="photo.jpg",
        created_at=datetime.now(UTC),
    )

    summary = await pipeline.ingest([item])
    assert summary.uploaded == 1
    assert not img_path.exists()


@pytest.mark.asyncio
async def test_ingest_cleans_up_local_file_on_duplicate(
    tmp_path: Path, state: State, fake_immich: AsyncMock
) -> None:
    img_path = tmp_path / "photo.jpg"
    img_path.write_bytes(b"dummy image data")

    await state.mark_processed(1001, 2001, 0, "done", None)

    pipeline = IngestionPipeline(immich=fake_immich, state=state, cleanup_local=True)
    item = IngestItem(
        chat_id=1001,
        message_id=2001,
        local_path=img_path,
        file_name="photo.jpg",
        created_at=datetime.now(UTC),
    )

    summary = await pipeline.ingest([item])
    assert summary.duplicates == 1
    assert not img_path.exists()


@pytest.mark.asyncio
async def test_ingest_retains_local_file_on_failure(
    tmp_path: Path, state: State, fake_immich: AsyncMock
) -> None:
    img_path = tmp_path / "photo.jpg"
    img_path.write_bytes(b"dummy image data")

    fake_immich.upload_asset.side_effect = RuntimeError("network error")

    pipeline = IngestionPipeline(immich=fake_immich, state=state, cleanup_local=True)
    item = IngestItem(
        chat_id=1001,
        message_id=2001,
        local_path=img_path,
        file_name="photo.jpg",
        created_at=datetime.now(UTC),
    )

    summary = await pipeline.ingest([item])
    assert summary.errors == 1
    assert img_path.exists()


@pytest.mark.asyncio
async def test_ingest_retains_local_file_when_cleanup_disabled(
    tmp_path: Path, state: State, fake_immich: AsyncMock
) -> None:
    img_path = tmp_path / "photo.jpg"
    img_path.write_bytes(b"dummy image data")

    pipeline = IngestionPipeline(immich=fake_immich, state=state, cleanup_local=False)
    item = IngestItem(
        chat_id=1001,
        message_id=2001,
        local_path=img_path,
        file_name="photo.jpg",
        created_at=datetime.now(UTC),
    )

    summary = await pipeline.ingest([item])
    assert summary.uploaded == 1
    assert img_path.exists()


@pytest.mark.asyncio
async def test_ingest_archive_cleans_up_archive_file_on_success(
    tmp_path: Path, state: State, fake_immich: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive_path = tmp_path / "bundle.zip"
    archive_path.write_bytes(b"dummy zip data")

    async def fake_extract(archive: Path, dest: Path) -> None:
        (dest / "photo.jpg").write_bytes(b"jpeg bytes")

    monkeypatch.setattr("immich_tg_bot.pipeline.extract", fake_extract)

    pipeline = IngestionPipeline(immich=fake_immich, state=state, cleanup_local=True)
    item = IngestItem(
        chat_id=1001,
        message_id=2001,
        local_path=archive_path,
        file_name="bundle.zip",
        created_at=datetime.now(UTC),
    )

    summary = await pipeline.ingest([item])
    assert summary.uploaded == 1
    assert not archive_path.exists()


@pytest.mark.asyncio
async def test_ingest_cleanup_handles_os_error_gracefully(
    tmp_path: Path, state: State, fake_immich: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    img_path = tmp_path / "photo.jpg"
    img_path.write_bytes(b"dummy image data")

    def mock_unlink(self: Path, missing_ok: bool = False) -> None:
        raise OSError("Permission denied")

    monkeypatch.setattr(Path, "unlink", mock_unlink)

    pipeline = IngestionPipeline(immich=fake_immich, state=state, cleanup_local=True)
    item = IngestItem(
        chat_id=1001,
        message_id=2001,
        local_path=img_path,
        file_name="photo.jpg",
        created_at=datetime.now(UTC),
    )

    summary = await pipeline.ingest([item])
    assert summary.uploaded == 1
