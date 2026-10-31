from collections.abc import Callable

import httpx
import pytest

from immich_tg_bot.immich import ImmichClient


@pytest.mark.asyncio
async def test_rate_limit_with_long_http_date_does_not_retry(tmp_path):
    from datetime import UTC, datetime, timedelta
    from email.utils import format_datetime

    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        retry_after = format_datetime(datetime.now(UTC) + timedelta(minutes=2), usegmt=True)
        return httpx.Response(429, headers={"Retry-After": retry_after})

    file = tmp_path / "photo.jpg"
    file.write_bytes(b"image")
    client = await make_client(handler)
    try:
        now = datetime.now(UTC)
        with pytest.raises(httpx.HTTPStatusError):
            await client.upload_asset(
                file_path=file,
                device_asset_id="1",
                device_id="1",
                file_created_at=now,
                file_modified_at=now,
            )
        assert calls == 1
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_uncertain_album_creation_is_reconciled_without_repeating_post():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.method)
        if request.method == "POST":
            raise httpx.ReadTimeout("response lost", request=request)
        albums = [] if len(calls) == 1 else [{"id": "existing", "albumName": "Photos"}]
        return httpx.Response(200, json=albums)

    client = await make_client(handler)
    try:
        assert await client.get_or_create_album("Photos") == "existing"
        assert calls == ["GET", "POST", "GET"]
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_upload_retries_transient_server_error_with_same_file(tmp_path, monkeypatch):
    from datetime import UTC, datetime

    import immich_tg_bot.retry as retry

    async def no_wait(seconds):
        pass

    monkeypatch.setattr(retry.asyncio, "sleep", no_wait)
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.read())
        return httpx.Response(503) if len(calls) < 3 else httpx.Response(201, json={"id": "a"})

    file = tmp_path / "photo.jpg"
    file.write_bytes(b"image content")
    client = await make_client(handler)
    try:
        now = datetime.now(UTC)
        result = await client.upload_asset(
            file_path=file,
            device_asset_id="1",
            device_id="1",
            file_created_at=now,
            file_modified_at=now,
            checksum="abc",
        )
        assert result["id"] == "a"
        assert len(calls) == 3
        assert all(b"image content" in body for body in calls)
    finally:
        await client.aclose()


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
async def test_get_or_create_album_refreshes_album_list() -> None:
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
        assert get_calls == 2
    finally:
        await client.aclose()


async def test_add_to_album_reports_individual_failures_and_accepts_duplicates() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {"id": "a", "success": True},
                {"id": "b", "success": False, "error": "duplicate"},
                {"id": "c", "success": False, "error": "no_permission"},
            ],
        )

    client = await make_client(handler)
    try:
        assert await client.add_to_album("album", ["a", "b", "c"]) == {"c": "no_permission"}
    finally:
        await client.aclose()
