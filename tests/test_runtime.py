from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from immich_tg_bot.config import Settings
from immich_tg_bot.pipeline import IngestItem
from immich_tg_bot.runtime import ingestion_runtime


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
