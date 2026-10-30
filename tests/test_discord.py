from datetime import UTC, datetime
from types import SimpleNamespace

import httpx

from immich_tg_bot.config import Settings
from immich_tg_bot.discord_bot import handle_dm
from immich_tg_bot.runtime import ingestion_runtime


async def test_dm_imports_all_attachments_and_reports_skipped(tmp_path, monkeypatch):
    uploads = []

    def immich(request):
        if request.method == "POST" and request.url.path == "/assets":
            uploads.append(request.content)
            return httpx.Response(201, json={"id": str(len(uploads)), "status": "created"})
        if request.method == "GET":
            return httpx.Response(200, json=[])
        if request.method == "PUT":
            return httpx.Response(200, json=[{"id": str(i), "success": True} for i in range(1, 3)])
        return httpx.Response(200, json={"id": "album"})

    original = httpx.AsyncClient
    monkeypatch.setattr(
        "immich_tg_bot.immich.httpx.AsyncClient",
        lambda **kw: original(**kw, transport=httpx.MockTransport(immich)),
    )
    settings = Settings.model_construct(
        data_dir=tmp_path,
        immich_url="https://immich.test",
        immich_api_key="key",
        discord_allowed_user_ids=[42],
    )
    replies = []

    async def reply(text, **kwargs):
        replies.append(text)

    author = SimpleNamespace(id=42, display_name="Alice", name="alice")
    attachments = [
        SimpleNamespace(
            id=1, filename="a.jpg", size=1, url="https://cdn.test/a?sig=x", content_type=None
        ),
        SimpleNamespace(
            id=2, filename="b.mp4", size=1, url="https://cdn.test/b?sig=y", content_type=None
        ),
        SimpleNamespace(
            id=3, filename="c.txt", size=1, url="https://cdn.test/c", content_type=None
        ),
    ]
    message = SimpleNamespace(
        id=10,
        channel=SimpleNamespace(id=20),
        author=author,
        created_at=datetime.now(UTC),
        content="",
        attachments=attachments,
        reply=reply,
    )
    async with original(
        transport=httpx.MockTransport(
            lambda req: httpx.Response(200, content=req.url.path.encode())
        )
    ) as client:
        async with ingestion_runtime(settings) as pipeline:
            await handle_dm(message, settings, pipeline, client)
    assert len(uploads) == 2
    assert "2" in replies[0] and "1" in replies[0]


async def test_unauthorized_dm_never_downloads_or_replies(tmp_path):
    settings = Settings.model_construct(data_dir=tmp_path, discord_allowed_user_ids=[42])
    calls = []

    async def reply(text, **kwargs):
        calls.append(text)

    message = SimpleNamespace(author=SimpleNamespace(id=99), reply=reply)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: calls.append(request))
    ) as client:
        await handle_dm(message, settings, None, client)
    assert calls == []


async def test_limits_and_failed_download_do_not_stop_other_attachments(tmp_path, monkeypatch):
    uploaded = []
    fetched = []
    original = httpx.AsyncClient

    def immich(request):
        if request.method == "POST" and request.url.path == "/assets":
            uploaded.append(request.content)
            return httpx.Response(201, json={"id": "1", "status": "created"})
        if request.method == "GET":
            return httpx.Response(200, json=[])
        if request.method == "PUT":
            return httpx.Response(200, json=[{"id": "1", "success": True}])
        return httpx.Response(200, json={"id": "album"})

    monkeypatch.setattr(
        "immich_tg_bot.immich.httpx.AsyncClient",
        lambda **kw: original(**kw, transport=httpx.MockTransport(immich)),
    )

    def download(request):
        fetched.append(str(request.url))
        if request.url.path == "/bad":
            return httpx.Response(500)
        return httpx.Response(
            200, content=b"x" * (1048577 if request.url.path == "/large" else 1048576)
        )

    attachments = [
        SimpleNamespace(
            id=1, filename="declared.jpg", size=1048577, url="https://cdn.test/declared"
        ),
        SimpleNamespace(id=2, filename="large.jpg", size=1, url="https://cdn.test/large?sig=x"),
        SimpleNamespace(id=3, filename="bad.jpg", size=1, url="https://cdn.test/bad?sig=secret"),
        SimpleNamespace(id=4, filename="ok.jpg", size=1048576, url="https://cdn.test/ok?sig=y"),
    ]
    replies = []

    async def reply(text, **kwargs):
        replies.append(text)

    message = SimpleNamespace(
        id=10,
        channel=SimpleNamespace(id=20),
        author=SimpleNamespace(id=42, display_name="Alice", name="alice"),
        created_at=datetime.now(UTC),
        content="",
        attachments=attachments,
        reply=reply,
    )
    settings = Settings.model_construct(
        data_dir=tmp_path,
        immich_url="https://immich.test",
        immich_api_key="key",
        discord_allowed_user_ids=[42],
        discord_max_attachment_mb=1,
    )
    async with original(transport=httpx.MockTransport(download)) as client:
        async with ingestion_runtime(settings) as pipeline:
            await handle_dm(message, settings, pipeline, client)
    assert fetched == [
        "https://cdn.test/large?sig=x",
        "https://cdn.test/bad?sig=secret",
        "https://cdn.test/ok?sig=y",
    ]
    assert len(uploaded) == 1
    assert "Uploaded: 1, duplicates: 0, skipped: 0, errors: 3" in replies[0]
    assert "secret" not in replies[0]
    assert list((tmp_path / "discord-downloads").iterdir()) == []
