import asyncio
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


async def test_reimport_checks_immich_and_restores_album_membership(
    tmp_path: Path, state: State, fake_immich: AsyncMock
) -> None:
    path = tmp_path / "photo.jpg"
    path.write_bytes(b"photo")
    fake_immich.upload_asset.side_effect = [
        {"id": "asset", "status": "created"},
        {"id": "asset", "status": "duplicate"},
    ]
    pipeline = IngestionPipeline(fake_immich, state, cleanup_local=False)
    item = IngestItem(1, 2, path, path.name, datetime.now(UTC), target_album="trip")

    first = await pipeline.ingest([item])
    second = await pipeline.ingest([item])

    assert (first.uploaded, second.duplicates, second.errors) == (1, 1, 0)
    assert fake_immich.upload_asset.await_count == 2
    assert fake_immich.add_to_album.await_count == 2


async def test_changed_content_from_same_source_is_imported(
    tmp_path: Path, state: State, fake_immich: AsyncMock
) -> None:
    path = tmp_path / "photo.jpg"
    path.write_bytes(b"first")
    fake_immich.upload_asset.side_effect = [
        {"id": "first", "status": "created"},
        {"id": "second", "status": "created"},
    ]
    pipeline = IngestionPipeline(fake_immich, state, cleanup_local=False)
    item = IngestItem(1, 2, path, path.name, datetime.now(UTC), target_album="trip")
    first = await pipeline.ingest([item])
    path.write_bytes(b"changed")
    second = await pipeline.ingest([item])
    assert first.new_asset_ids == ["first"]
    assert second.new_asset_ids == ["second"]
    fake_immich.add_to_album.assert_any_await("album-123", ["second"])
    checksums = [call.kwargs["checksum"] for call in fake_immich.upload_asset.await_args_list]
    assert checksums[0] != checksums[1]


async def test_concurrent_batches_reuse_identical_content(
    tmp_path: Path, state: State, fake_immich: AsyncMock
) -> None:
    first, second = tmp_path / "one.jpg", tmp_path / "two.jpg"
    first.write_bytes(b"same")
    second.write_bytes(b"same")
    entered = asyncio.Event()
    release = asyncio.Event()

    async def upload(**kwargs: Any) -> dict[str, str]:
        entered.set()
        await asyncio.wait_for(release.wait(), timeout=2)
        status = "created" if fake_immich.upload_asset.await_count == 1 else "duplicate"
        return {"id": "asset", "status": status}

    fake_immich.upload_asset.side_effect = upload
    fake_immich.get_or_create_album.side_effect = lambda name: name
    pipeline = IngestionPipeline(fake_immich, state)
    now = datetime.now(UTC)
    task1 = asyncio.create_task(
        pipeline.ingest([IngestItem(1, 1, first, first.name, now, target_album="Telegram")])
    )
    await asyncio.wait_for(entered.wait(), timeout=2)
    task2 = asyncio.create_task(
        pipeline.ingest(
            [
                IngestItem(
                    1,
                    2,
                    second,
                    second.name,
                    now,
                    target_album="Discord",
                    platform="discord",
                    attachment_id="attachment",
                )
            ]
        )
    )
    release.set()
    result1, result2 = await asyncio.gather(task1, task2)
    assert (result1.uploaded, result2.duplicates) == (1, 1)
    assert fake_immich.upload_asset.await_count == 2
    fake_immich.add_to_album.assert_any_await("Telegram", ["asset"])
    fake_immich.add_to_album.assert_any_await("Discord", ["asset"])



async def test_repeat_source_routes_existing_asset_after_restart(
    tmp_path: Path, fake_immich: AsyncMock
) -> None:
    path = tmp_path / "photo.jpg"
    path.write_bytes(b"photo")
    fake_immich.get_or_create_album.side_effect = lambda name: name
    fake_immich.upload_asset.side_effect = [
        {"id": "asset-123", "status": "created"},
        {"id": "asset-123", "status": "duplicate"},
    ]
    item = IngestItem(1, 2, path, path.name, datetime.now(UTC), target_album="first")
    first = await IngestionPipeline(fake_immich, State(), cleanup_local=False).ingest([item])
    second_item = IngestItem(1, 2, path, path.name, item.created_at, target_album="second")
    second = await IngestionPipeline(fake_immich, State()).ingest([second_item])
    assert (first.uploaded, second.duplicates, second.errors) == (1, 1, 0)
    assert fake_immich.upload_asset.await_count == 2
    fake_immich.add_to_album.assert_any_await("first", ["asset-123"])
    fake_immich.add_to_album.assert_any_await("second", ["asset-123"])





async def test_album_failure_can_be_retried_after_restart(
    tmp_path: Path, fake_immich: AsyncMock
) -> None:
    path = tmp_path / "photo.jpg"
    path.write_bytes(b"photo")
    fake_immich.upload_asset.side_effect = [
        {"id": "asset-123", "status": "created"},
        {"id": "asset-123", "status": "duplicate"},
    ]
    fake_immich.add_to_album.side_effect = RuntimeError("unavailable")
    item = IngestItem(1, 2, path, path.name, datetime.now(UTC), target_album="trip")
    first = await IngestionPipeline(fake_immich, State(), cleanup_local=False).ingest([item])
    assert first.uploaded == 1
    assert first.errors == 1
    assert "photo.jpg" in first.error_messages[0]
    assert "album association" in first.error_messages[0]
    fake_immich.add_to_album.side_effect = None
    second = await IngestionPipeline(fake_immich, State()).ingest([item])
    assert (second.duplicates, second.errors) == (1, 0)
    assert fake_immich.upload_asset.await_count == 2
    assert fake_immich.add_to_album.await_count == 2




async def test_partial_album_failure_retries_all_associations(
    tmp_path: Path, state: State, fake_immich: AsyncMock
) -> None:
    first, second = tmp_path / "a.jpg", tmp_path / "b.jpg"
    first.write_bytes(b"a")
    second.write_bytes(b"b")
    fake_immich.upload_asset.side_effect = [
        {"id": "asset-a", "status": "created"},
        {"id": "asset-b", "status": "created"},
        {"id": "asset-a", "status": "duplicate"},
        {"id": "asset-b", "status": "duplicate"},
    ]
    fake_immich.add_to_album.side_effect = [{"asset-b": "forbidden"}, {}]
    items = [
        IngestItem(1, 1, first, "a.jpg", datetime.now(UTC), target_album="trip"),
        IngestItem(1, 2, second, "b.jpg", datetime.now(UTC), target_album="trip"),
    ]
    pipeline = IngestionPipeline(fake_immich, state, cleanup_local=False)
    result = await pipeline.ingest(items)
    assert result.uploaded == 2
    assert result.errors == 1
    assert "b.jpg" in result.error_messages[0]
    retry = await pipeline.ingest(items)
    assert retry.errors == 0
    assert retry.duplicates == 2
    assert fake_immich.upload_asset.await_count == 4
    assert set(fake_immich.add_to_album.await_args_list[-1].args[1]) == {"asset-a", "asset-b"}


async def test_remote_duplicate_assets_are_routed(
    tmp_path: Path, state: State, fake_immich: AsyncMock
) -> None:
    fake_immich.get_or_create_album.side_effect = lambda name: name
    fake_immich.upload_asset.side_effect = [
        {"id": "remote", "status": "duplicate"},
        {"id": "remote", "status": "duplicate"},
        {"id": "other", "status": "created"},
    ]
    items = []
    for number, content in enumerate([b"same", b"same", b"different"]):
        path = tmp_path / f"{number}.jpg"
        path.write_bytes(content)
        items.append(IngestItem(1, number, path, path.name, datetime.now(UTC), target_album="trip"))
    result = await IngestionPipeline(fake_immich, state).ingest(items)
    assert result.uploaded == 1
    assert result.duplicates == 2
    assert result.errors == 0
    fake_immich.add_to_album.assert_awaited_once_with("trip", ["remote", "other"])



async def test_archive_assets_survive_album_lookup_failure_and_restart(
    tmp_path: Path, fake_immich: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def extract_files(source: Path, dest: Path) -> None:
        (dest / "a.jpg").write_bytes(b"a")
        (dest / "b.jpg").write_bytes(b"b")

    monkeypatch.setattr("immich_tg_bot.pipeline.extract", extract_files)
    archive = tmp_path / "bundle.zip"
    archive.write_bytes(b"archive")
    fake_immich.upload_asset.side_effect = [
        {"id": "asset-a", "status": "created"},
        {"id": "asset-b", "status": "created"},
        {"id": "asset-a", "status": "duplicate"},
        {"id": "asset-b", "status": "duplicate"},
    ]
    fake_immich.get_or_create_album.side_effect = RuntimeError("offline")
    item = IngestItem(1, 2, archive, "bundle.zip", datetime.now(UTC), target_album="trip")
    result = await IngestionPipeline(fake_immich, State(), cleanup_local=False).ingest([item])
    assert (result.uploaded, result.errors) == (2, 2)
    assert all("album lookup/create" in error for error in result.error_messages)
    fake_immich.get_or_create_album.side_effect = None
    fake_immich.get_or_create_album.return_value = "album"
    retry = await IngestionPipeline(fake_immich, State()).ingest([item])
    assert (retry.duplicates, retry.errors) == (2, 0)
    assert fake_immich.upload_asset.await_count == 4
    assert set(fake_immich.add_to_album.await_args.args[1]) == {"asset-a", "asset-b"}




async def test_multiple_attachments_in_one_message_are_independent(
    tmp_path: Path, state: State, fake_immich: AsyncMock
) -> None:
    first = tmp_path / "first.jpg"
    second = tmp_path / "second.jpg"
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    pipeline = IngestionPipeline(fake_immich, state)
    items = [
        IngestItem(
            1, 2, first, "first.jpg", datetime.now(UTC), platform="discord", attachment_id="a"
        ),
        IngestItem(
            1, 2, second, "second.jpg", datetime.now(UTC), platform="discord", attachment_id="b"
        ),
    ]

    summary = await pipeline.ingest(items)

    assert summary.uploaded == 2
    assert fake_immich.upload_asset.await_count == 2


async def test_source_identity_isolated_across_platforms_and_channels(
    tmp_path: Path, state: State, fake_immich: AsyncMock
) -> None:
    pipeline = IngestionPipeline(fake_immich, state, cleanup_local=False)
    items = []
    for i, (platform, channel) in enumerate(
        [("discord", "1"), ("telegram", "1"), ("discord", "2")]
    ):
        path = tmp_path / f"{i}.jpg"
        path.write_bytes(str(i).encode())
        items.append(
            IngestItem(
                channel,
                "3",
                path,
                path.name,
                datetime.now(UTC),
                platform=platform,
                attachment_id="a",
            )
        )
    assert (await pipeline.ingest(items)).uploaded == 3
    fake_immich.upload_asset.return_value = {"id": "asset-123", "status": "duplicate"}
    assert (await pipeline.ingest(items)).duplicates == 3
    assert (
        len({call.kwargs["device_asset_id"] for call in fake_immich.upload_asset.await_args_list})
        == 3
    )







async def test_archive_member_identity_survives_reordering_and_renaming(
    tmp_path: Path, state: State, fake_immich: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = tmp_path / "bundle.zip"
    archive.write_bytes(b"archive")
    reverse = False

    async def extract_files(source: Path, dest: Path) -> None:
        entries = [("a/photo.jpg", b"one"), ("b/photo.jpg", b"two")]
        if reverse:
            entries = [("renamed/two.jpg", b"two"), ("renamed/one.jpg", b"one")]
        for name, content in entries:
            path = dest / name
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(content)

    monkeypatch.setattr("immich_tg_bot.pipeline.extract", extract_files)
    identities: dict[bytes, str] = {}

    async def fail_upload(**kwargs: Any) -> None:
        identities[kwargs["file_path"].read_bytes()] = kwargs["device_asset_id"]
        raise RuntimeError("retry")

    fake_immich.upload_asset.side_effect = fail_upload
    pipeline = IngestionPipeline(fake_immich, state)
    item = IngestItem(
        1, 2, archive, "bundle.zip", datetime.now(UTC), platform="discord", attachment_id="bundle"
    )
    await pipeline.ingest([item])
    first = identities.copy()
    identities.clear()
    reverse = True
    await pipeline.ingest([item])
    second = identities.copy()
    assert len(first) == 2
    assert first == second


@pytest.fixture
def state() -> State:
    return State()


@pytest.fixture
def fake_immich() -> AsyncMock:
    client = AsyncMock()
    client.upload_asset.return_value = {"id": "asset-123", "status": "created"}
    client.add_to_album.return_value = None
    client.get_or_create_album.return_value = "album-123"
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

    fake_immich.upload_asset.assert_awaited_once()







@pytest.mark.asyncio
async def test_ingest_uses_immich_for_identical_contents(
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
    fake_immich.upload_asset.return_value = {"id": "asset-123", "status": "duplicate"}
    summary2 = await pipeline.ingest([item2])
    assert summary2.uploaded == 0
    assert summary2.duplicates == 1
    assert summary2.errors == 0
    assert fake_immich.upload_asset.await_count == 2


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

    # 上传成功与相册失败可以同时发生。
    assert summary.uploaded == 1
    assert summary.errors == 1
    assert "album association" in summary.error_messages[0]


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


@pytest.mark.asyncio
async def test_ingest_archive_with_no_media_reports_skip(
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


@pytest.mark.asyncio
async def test_ingest_single_file_failure_isolates_other_uploads(
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
    # 第二次尝试：Immich 复用 photo1 的资产，photo2 重新上传成功。
    fake_immich.upload_asset.side_effect = [
        {"id": "asset-1", "status": "duplicate"},
        {"id": "asset-2", "status": "created"},
    ]

    summary2 = await pipeline.ingest([item])
    assert summary2.duplicates == 1
    assert summary2.uploaded == 1  # photo2 成功上传
    assert summary2.errors == 0


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

    fake_immich.upload_asset.return_value = {"id": "asset-123", "status": "duplicate"}

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


async def test_real_archive_over_limit_rejects_before_upload(tmp_path, state, fake_immich):
    import zipfile

    archive = tmp_path / "bundle.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("a.jpg", b"a")
        bundle.writestr("sub/b.jpg", b"b")
    item = IngestItem(
        1, 2, archive, archive.name, datetime.now(UTC), platform="discord", attachment_id="1"
    )
    result = await IngestionPipeline(fake_immich, state, max_archive_files=1).ingest([item])
    assert result.uploaded == 0
    assert result.errors == 1
    assert "bundle.zip" in result.error_messages[0]
    fake_immich.upload_asset.assert_not_awaited()


async def test_real_archive_entries_and_retry(tmp_path, state, fake_immich):
    import zipfile

    archive = tmp_path / "bundle.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("one/photo.jpg", b"first")
        bundle.writestr("two/photo.jpg", b"second")
        bundle.writestr("note.txt", b"note")
        bundle.writestr("nested.zip", b"nested")
    fake_immich.upload_asset.side_effect = [
        {"id": "one", "status": "created"},
        RuntimeError("offline"),
        {"id": "one", "status": "duplicate"},
        {"id": "two", "status": "created"},
    ]
    item = IngestItem(
        1,
        2,
        archive,
        archive.name,
        datetime.now(UTC),
        target_album="trip",
        platform="discord",
        attachment_id="1",
    )
    pipeline = IngestionPipeline(fake_immich, state, max_archive_files=2, cleanup_local=False)
    first = await pipeline.ingest([item])
    assert (first.uploaded, first.errors) == (1, 1)
    assert "photo.jpg" in first.error_messages[0]
    assert any("note.txt" in x for x in first.skipped_messages)
    assert any("nested.zip" in x for x in first.skipped_messages)
    second = await pipeline.ingest([item])
    assert (second.uploaded, second.duplicates, second.errors) == (1, 1, 0)
    assert all(
        call.kwargs["file_name"] == "photo.jpg" for call in fake_immich.upload_asset.await_args_list
    )


async def test_corrupt_and_empty_archive_do_not_block_other_items(tmp_path, state, fake_immich):
    import zipfile

    corrupt = tmp_path / "bad.zip"
    corrupt.write_bytes(b"broken")
    empty = tmp_path / "empty.zip"
    with zipfile.ZipFile(empty, "w"):
        pass
    photo = tmp_path / "photo.jpg"
    photo.write_bytes(b"photo")
    now = datetime.now(UTC)
    items = [
        IngestItem(1, 2, path, path.name, now, platform="discord", attachment_id=str(i))
        for i, path in enumerate((corrupt, empty, photo))
    ]
    result = await IngestionPipeline(fake_immich, state).ingest(items)
    assert (result.uploaded, result.errors) == (1, 1)
    assert "bad.zip" in result.error_messages[0]
    assert any("empty.zip" in x and "no supported media" in x for x in result.skipped_messages)


async def test_encrypted_archive_reports_failure(tmp_path, state, fake_immich):
    from shutil import copyfile

    archive = tmp_path / "encrypted.zip"
    copyfile(Path(__file__).parent / "fixtures" / "encrypted.zip", archive)
    item = IngestItem(
        1, 2, archive, archive.name, datetime.now(UTC), platform="discord", attachment_id="1"
    )
    result = await asyncio.wait_for(IngestionPipeline(fake_immich, state).ingest([item]), 10)
    assert result.errors == 1
    assert "encrypted.zip" in result.error_messages[0]
    fake_immich.upload_asset.assert_not_awaited()


async def test_archive_imports_legacy_gbk_filename(tmp_path, state, fake_immich):
    import zipfile

    archive = tmp_path / "legacy.zip"
    raw_name = "照片.png".encode("gbk")
    placeholder = "x" * len(raw_name)
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr(placeholder, b"photo")
    archive.write_bytes(archive.read_bytes().replace(placeholder.encode(), raw_name))
    item = IngestItem(
        1, 2, archive, archive.name, datetime.now(UTC), platform="discord", attachment_id="1"
    )
    result = await IngestionPipeline(fake_immich, state).ingest([item])
    assert result.uploaded == 1
    assert fake_immich.upload_asset.await_args.kwargs["file_name"] == "照片.png"


async def test_recreated_album_receives_existing_asset(tmp_path, state, fake_immich):
    path = tmp_path / "photo.jpg"
    path.write_bytes(b"photo")
    fake_immich.get_or_create_album.side_effect = ["old-album", "new-album"]
    item = IngestItem(1, 2, path, path.name, datetime.now(UTC), target_album="trip")
    pipeline = IngestionPipeline(fake_immich, state, cleanup_local=False)
    first = await pipeline.ingest([item])
    fake_immich.upload_asset.return_value = {"id": "asset-123", "status": "duplicate"}
    second = await pipeline.ingest([item])
    assert (first.uploaded, second.duplicates, second.errors) == (1, 1, 0)
    fake_immich.add_to_album.assert_any_await("new-album", ["asset-123"])
    assert fake_immich.upload_asset.await_count == 2
