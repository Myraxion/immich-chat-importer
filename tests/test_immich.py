from collections.abc import Callable

import httpx
import pytest

from immich_tg_bot.immich import ImmichClient


async def make_client(handler: Callable[[httpx.Request], httpx.Response]) -> ImmichClient:
    client = ImmichClient("https://immich.example/api", "key")
    await client.aclose()
    client._client = httpx.AsyncClient(
        base_url=client.base_url,
        transport=httpx.MockTransport(handler),
    )
    return client


@pytest.mark.asyncio
async def test_ping_uses_v3_endpoint_when_available() -> None:
    requested_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
        return httpx.Response(200)

    client = await make_client(handler)
    try:
        assert await client.ping() is True
    finally:
        await client.aclose()

    assert requested_paths == ["/api/server/ping"]


@pytest.mark.asyncio
async def test_ping_falls_back_to_legacy_endpoint_on_not_found() -> None:
    requested_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
        status_code = 404 if request.url.path == "/api/server/ping" else 200
        return httpx.Response(status_code)

    client = await make_client(handler)
    try:
        assert await client.ping() is True
    finally:
        await client.aclose()

    assert requested_paths == ["/api/server/ping", "/api/server-info/ping"]


@pytest.mark.asyncio
async def test_ping_does_not_fall_back_for_other_errors() -> None:
    requested_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
        return httpx.Response(503)

    client = await make_client(handler)
    try:
        assert await client.ping() is False
    finally:
        await client.aclose()

    assert requested_paths == ["/api/server/ping"]


@pytest.mark.asyncio
async def test_upload_asset_passes_custom_filename(tmp_path) -> None:
    from datetime import UTC, datetime

    dummy_file = tmp_path / "raw_file_0.jpg"
    dummy_file.write_bytes(b"content")

    captured_filenames: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/assets":
            # Inspect multipart content or header
            for part in request.read().split(b"\r\n"):
                if b'filename="' in part:
                    fn = part.split(b'filename="')[1].split(b'"')[0].decode()
                    captured_filenames.append(fn)
            return httpx.Response(201, json={"id": "asset-1", "status": "created"})
        return httpx.Response(404)

    client = await make_client(handler)
    try:
        now = datetime.now(UTC)
        await client.upload_asset(
            file_path=dummy_file,
            device_asset_id="dev-1",
            device_id="dev-id",
            file_created_at=now,
            file_modified_at=now,
            file_name="renamed_photo.jpg",
        )
    finally:
        await client.aclose()

    assert captured_filenames == ["renamed_photo.jpg"]


@pytest.mark.asyncio
async def test_get_or_create_album_uses_cache() -> None:
    get_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal get_calls
        if request.url.path == "/api/albums" and request.method == "GET":
            get_calls += 1
            return httpx.Response(200, json=[{"id": "album-1", "albumName": "MyAlbum"}])
        return httpx.Response(404)

    client = await make_client(handler)
    try:
        id1 = await client.get_or_create_album("MyAlbum")
        id2 = await client.get_or_create_album("MyAlbum")
        assert id1 == "album-1"
        assert id2 == "album-1"
        assert get_calls == 1  # Cache hit on second call
    finally:
        await client.aclose()


async def test_add_to_album_reports_individual_failures_and_accepts_duplicates() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[
            {"id": "a", "success": True},
            {"id": "b", "success": False, "error": "duplicate"},
            {"id": "c", "success": False, "error": "no_permission"},
        ])

    client = await make_client(handler)
    try:
        assert await client.add_to_album("album", ["a", "b", "c"]) == {"c": "no_permission"}
    finally:
        await client.aclose()
