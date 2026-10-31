import asyncio
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from immich_tg_bot.config import Settings
from immich_tg_bot.pipeline import IngestItem
from immich_tg_bot.runtime import ingestion_runtime
from immich_tg_bot.state import State


async def test_combined_runtime_stops_both_adapters_together(tmp_path, monkeypatch):
    from immich_tg_bot.__main__ import run

    started = asyncio.Event()
    stopped = asyncio.Event()
    pipelines = []

    async def telegram(settings, pipeline):
        pipelines.append(pipeline)
        await started.wait()

    async def discord(settings, pipeline):
        pipelines.append(pipeline)
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()

    monkeypatch.setattr("immich_tg_bot.__main__.run_bot", telegram)
    monkeypatch.setattr("immich_tg_bot.discord_bot.run_discord", discord)
    settings = Settings.model_construct(
        data_dir=tmp_path,
        album_name=None,
        immich_url="https://immich.test",
        immich_api_key="key",
        enabled_platforms=["telegram", "discord"],
    )
    await asyncio.wait_for(run(settings), timeout=2)
    assert len(pipelines) == 2 and pipelines[0] is pipelines[1]
    assert stopped.is_set()


async def test_restart_interrupts_unfinished_records_without_changing_completed(tmp_path):
    settings = Settings.model_construct(
        data_dir=tmp_path, album_name=None, immich_url="https://immich.test", immich_api_key="key"
    )
    async with ingestion_runtime(settings) as pipeline:
        waiting = await pipeline.state.create_ingest_record(42, "channel", "waiting")
        running = await pipeline.state.create_ingest_record(42, "channel", "running")
        await pipeline.state.start_ingest_record(running)
        finished = await pipeline.state.create_ingest_record(99, "other", "finished")
        await pipeline.state.finish_ingest_record(finished, "completed", 1, 0, 0, 0, "saved")

    async with ingestion_runtime(settings) as pipeline:
        records = await pipeline.state.recent_ingest_records(42)
        assert [(r.id, r.message_id, r.status) for r in records] == [
            (running, "running", "interrupted"),
            (waiting, "waiting", "interrupted"),
        ]
        completed = (await pipeline.state.recent_ingest_records(99))[0]
        assert (completed.status, completed.uploaded, completed.details) == (
            "completed",
            1,
            "saved",
        )

    state = State(tmp_path / "state.sqlite")
    await state.open()
    assert all(r.status == "interrupted" for r in await state.recent_ingest_records(42))
    await state.close()


async def test_runtime_opens_shared_ingestion_and_closes_immich_on_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clients: list[httpx.AsyncClient] = []
    client_class = httpx.AsyncClient

    def make_client(**kwargs: object) -> httpx.AsyncClient:
        client = client_class(
            **kwargs,
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json={"id": "asset", "status": "created"})
            ),
        )
        clients.append(client)
        return client

    monkeypatch.setattr("immich_tg_bot.immich.httpx.AsyncClient", make_client)
    settings = Settings.model_construct(
        data_dir=tmp_path, album_name=None, immich_url="https://immich.test", immich_api_key="key"
    )
    image = tmp_path / "photo.jpg"
    image.write_bytes(b"photo")
    with pytest.raises(ValueError, match="stop"):
        async with ingestion_runtime(settings) as pipeline:
            result = await pipeline.ingest([IngestItem(1, 2, image, image.name, datetime.now(UTC))])
            assert result.uploaded == 1
            raise ValueError("stop")

    assert clients[0].is_closed
    async with ingestion_runtime(settings) as pipeline:
        image.write_bytes(b"photo")
        result = await pipeline.ingest([IngestItem(1, 2, image, image.name, datetime.now(UTC))])
        assert result.duplicates == 1
