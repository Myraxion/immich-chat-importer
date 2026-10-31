from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

from immich_tg_bot.batches import IngestBatches, IngestRequest
from immich_tg_bot.pipeline import IngestionPipeline
from immich_tg_bot.state import State


async def test_preparation_failure_is_recorded_and_isolated_by_platform():
    pipeline = IngestionPipeline(AsyncMock(), State())
    batches = IngestBatches(pipeline)

    @asynccontextmanager
    async def prepare(batch):
        batch.errors.append("download failed")
        yield

    result = await batches.run(IngestRequest("discord", 42, "chat", "message"), prepare)
    records = await batches.recent("discord", 42)
    assert result.record.status == "failed"
    assert result.record.errors == 1
    assert records[0].details == "download failed"
    assert await batches.recent("telegram", 42) == []


async def test_cleanup_failure_preserves_uploaded_asset(tmp_path):
    from datetime import UTC, datetime

    from immich_tg_bot.pipeline import IngestItem

    immich = AsyncMock()
    immich.upload_asset.return_value = {"id": "asset", "status": "created"}
    batches = IngestBatches(IngestionPipeline(immich, State(), cleanup_local=False))
    file = tmp_path / "photo.jpg"
    file.write_bytes(b"image")

    @asynccontextmanager
    async def prepare(batch):
        batch.items.append(IngestItem(1, 2, file, file.name, datetime.now(UTC)))
        batch.errors.append("another file could not download")
        try:
            yield
        finally:
            batch.stage = "photo.jpg: cleanup"
            raise OSError("cleanup failed")

    result = await batches.run(IngestRequest("discord", 42, "chat", "message"), prepare)
    assert (result.record.uploaded, result.record.errors, result.record.status) == (1, 2, "partial")
    assert "cleanup" in result.record.details
    assert (await batches.recent("discord", 42))[0].uploaded == 1


async def test_cancellation_restores_notice_without_settling():
    import asyncio

    from immich_tg_bot.retry import retry_notice

    batches = IngestBatches(IngestionPipeline(AsyncMock(), State()))

    @asynccontextmanager
    async def prepare(batch):
        assert retry_notice.get() is not None
        raise asyncio.CancelledError
        yield

    previous = retry_notice.get()
    import pytest

    with pytest.raises(asyncio.CancelledError):
        await batches.run(IngestRequest("telegram", 42, "chat", "message"), prepare)
    assert retry_notice.get() is previous
    assert (await batches.recent("telegram", 42))[0].status == "processing"


async def test_preparation_continues_while_another_batch_uploads(tmp_path):
    import asyncio
    from datetime import UTC, datetime

    from immich_tg_bot.pipeline import IngestItem

    entered = asyncio.Event()
    release = asyncio.Event()
    prepared = asyncio.Event()
    immich = AsyncMock()

    async def upload(**kwargs):
        entered.set()
        await release.wait()
        return {"id": kwargs["file_name"], "status": "created"}

    immich.upload_asset.side_effect = upload
    batches = IngestBatches(IngestionPipeline(immich, State()))

    @asynccontextmanager
    async def prepare(batch):
        path = tmp_path / str(len(await batches.recent("discord", 42)))
        path.write_bytes(b"image")
        batch.items.append(IngestItem(1, 2, path, path.name, datetime.now(UTC)))
        if entered.is_set():
            prepared.set()
        yield

    first = asyncio.create_task(batches.run(IngestRequest("discord", 42, "1", "1"), prepare))
    second = None
    try:
        await asyncio.wait_for(entered.wait(), 2)
        second = asyncio.create_task(batches.run(IngestRequest("discord", 42, "1", "2"), prepare))
        await asyncio.wait_for(prepared.wait(), 2)
        records = await batches.recent("discord", 42)
        assert [r.status for r in records] == ["waiting", "processing"]
    finally:
        release.set()
        await first
        if second is not None:
            await second
    assert [r.status for r in await batches.recent("discord", 42)] == ["completed", "completed"]
