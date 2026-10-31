from datetime import UTC, datetime
from types import SimpleNamespace

import httpx
import pytest

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
            from immich_tg_bot.discord_bot import handle_status

            status_replies = []

            async def send_message(content, **kwargs):
                status_replies.append((content, kwargs))

            interaction = SimpleNamespace(
                user=author, locale="en-US", response=SimpleNamespace(send_message=send_message)
            )
            await handle_status(interaction, settings, pipeline)
            assert "Uploaded: 2" in status_replies[0][0]
            assert status_replies[0][1]["ephemeral"] is True
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


@pytest.mark.parametrize(
    "guild_id, guild_name, channel_name, source",
    [
        (8, None, "photos", "8_photos"),
        (8, "Guild", None, "Guild_20"),
        (None, None, None, "Alice"),  # bot DM, another DM, and group DM share this payload
    ],
)
async def test_menu_private_response_uses_original_author_and_context(
    tmp_path, guild_id, guild_name, channel_name, source
):
    from immich_tg_bot.discord_bot import handle_menu
    from immich_tg_bot.pipeline import IngestSummary

    events = []

    from immich_tg_bot.state import State

    state = State(tmp_path / "state.sqlite")
    await state.open()

    class Pipeline:
        async def ingest(self, items, record_id=None, summary=None):
            events.append((items[0].file_name, items[0].target_album, items[0].chat_id))
            return IngestSummary(uploaded=1)

    class Response:
        async def defer(self, **kwargs):
            events.append(kwargs)

    async def edit_original_response(**kwargs):
        events.append(kwargs)

    interaction = SimpleNamespace(
        user=SimpleNamespace(id=42),
        locale="zh-CN",
        response=Response(),
        edit_original_response=edit_original_response,
        guild=SimpleNamespace(id=8, name=guild_name) if guild_id else None,
        guild_id=guild_id,
        channel=SimpleNamespace(id=20, name=channel_name),
    )
    message = SimpleNamespace(
        id=10,
        channel=SimpleNamespace(id=20),
        author=SimpleNamespace(id=99, display_name="Alice", name="alice"),
        created_at=datetime(2024, 1, 2, tzinfo=UTC),
        content="",
        attachments=[SimpleNamespace(id=1, filename="a.jpg", size=1, url="https://cdn.test/a")],
    )
    settings = Settings.model_construct(
        data_dir=tmp_path,
        discord_allowed_user_ids=[42],
        discord_filename_template="{source}_{sender}_{message_id}",
        discord_album_name_template="{source}",
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda req: httpx.Response(200, content=b"a"))
    ) as client:
        pipeline = Pipeline()
        pipeline.state = state
        await handle_menu(interaction, message, settings, pipeline, client)
    assert len(await state.recent_ingest_records(42)) == 1
    assert await state.recent_ingest_records(99) == []
    await state.close()
    assert events[0] == {"ephemeral": True, "thinking": True}
    assert events[1] == (f"{source}_Alice_10.jpg", source, 20)
    assert "已上传：1" in events[2]["content"]


async def test_menu_denies_caller_even_when_author_is_allowed(tmp_path):
    from immich_tg_bot.discord_bot import handle_menu

    events = []

    class Response:
        async def defer(self, **kwargs):
            events.append(kwargs)

    async def edit_original_response(**kwargs):
        events.append(kwargs["content"])

    interaction = SimpleNamespace(
        user=SimpleNamespace(id=99),
        locale="en-US",
        response=Response(),
        edit_original_response=edit_original_response,
    )
    message = SimpleNamespace(author=SimpleNamespace(id=42))
    settings = Settings.model_construct(data_dir=tmp_path, discord_allowed_user_ids=[42])
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda req: events.append(req))
    ) as client:
        await handle_menu(interaction, message, settings, None, client)
    assert events == [
        {"ephemeral": True, "thinking": True},
        "You are not authorized to import media.",
    ]


async def test_dm_imports_real_archive(tmp_path, monkeypatch):
    import io
    import zipfile

    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as bundle:
        bundle.writestr("sub/photo.jpg", b"photo")
        bundle.writestr("readme.txt", b"readme")
    uploads = []
    replies = []
    original = httpx.AsyncClient

    def immich(request):
        if request.method == "POST" and request.url.path == "/assets":
            uploads.append(request.content)
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

    async def reply(text, **kwargs):
        replies.append(text)

    message = SimpleNamespace(
        id=10,
        channel=SimpleNamespace(id=20),
        author=SimpleNamespace(id=42, display_name="Alice", name="alice"),
        created_at=datetime.now(UTC),
        content="",
        reply=reply,
        attachments=[
            SimpleNamespace(
                id=1,
                filename="bundle.zip",
                size=len(data.getvalue()),
                url="https://cdn.test/bundle",
            )
        ],
    )
    settings = Settings.model_construct(
        data_dir=tmp_path,
        immich_url="https://immich.test",
        immich_api_key="key",
        discord_allowed_user_ids=[42],
    )
    async with original(
        transport=httpx.MockTransport(lambda req: httpx.Response(200, content=data.getvalue()))
    ) as client:
        async with ingestion_runtime(settings) as pipeline:
            await handle_dm(message, settings, pipeline, client)
    assert len(uploads) == 1
    assert b"photo.jpg" in uploads[0]
    assert "readme.txt" in replies[0]
    assert "Uploaded: 1" in replies[0]

async def test_status_remains_responsive_during_upload_and_waiting_batch(tmp_path, monkeypatch):
    import asyncio

    from immich_tg_bot.discord_bot import handle_status

    entered = asyncio.Event()
    release = asyncio.Event()
    original = httpx.AsyncClient

    async def immich(request):
        if request.method == "POST" and request.url.path == "/assets":
            entered.set()
            await release.wait()
            return httpx.Response(201, json={"id": "1", "status": "created"})
        return httpx.Response(200, json=[])

    monkeypatch.setattr(
        "immich_tg_bot.immich.httpx.AsyncClient",
        lambda **kw: original(**kw, transport=httpx.MockTransport(immich)),
    )
    settings = Settings.model_construct(
        data_dir=tmp_path, immich_url="https://immich.test", immich_api_key="key",
        discord_allowed_user_ids=[42],
    )
    author = SimpleNamespace(id=42, display_name="Alice", name="alice")

    async def reply(*args, **kwargs):
        pass

    def message(number):
        return SimpleNamespace(
            id=number, channel=SimpleNamespace(id=20), author=author,
            created_at=datetime.now(UTC), content="", reply=reply,
            attachments=[SimpleNamespace(id=number, filename="a.jpg", size=1,
                                         url="https://cdn.test/a")],
        )

    responses = []

    async def send_message(content, **kwargs):
        responses.append(content)

    interaction = SimpleNamespace(
        user=author, locale="en-US", response=SimpleNamespace(send_message=send_message)
    )
    async with original(
        transport=httpx.MockTransport(lambda req: httpx.Response(200, content=b"a"))
    ) as client:
        async with ingestion_runtime(settings) as pipeline:
            first = asyncio.create_task(handle_dm(message(1), settings, pipeline, client))
            try:
                await asyncio.wait_for(entered.wait(), 2)
                second = asyncio.create_task(handle_dm(message(2), settings, pipeline, client))
                try:
                    for _ in range(100):
                        records = await pipeline.state.recent_ingest_records(42)
                        if len(records) == 2 and any(r.status == "waiting" for r in records):
                            break
                        await asyncio.sleep(0.01)
                    await asyncio.wait_for(handle_status(interaction, settings, pipeline), 2)
                    assert "waiting" in responses[0]
                    assert "processing" in responses[0]
                finally:
                    release.set()
                    await asyncio.wait_for(second, 2)
            finally:
                release.set()
                await asyncio.wait_for(first, 2)

async def test_status_denies_unlisted_users_and_reports_empty_history(tmp_path):
    from immich_tg_bot.discord_bot import handle_status
    from immich_tg_bot.state import State

    state = State(tmp_path / "state.sqlite")
    await state.open()
    try:
        record = await state.create_ingest_record(42, "20", "secret")
        await state.finish_ingest_record(record, "failed", 0, 0, 0, 1, "photo.jpg: upload")
        replies = []

        async def send_message(content, **kwargs):
            replies.append((content, kwargs))

        settings = Settings.model_construct(discord_allowed_user_ids=[42, 43])
        interaction = SimpleNamespace(
            user=SimpleNamespace(id=43), locale="en-US",
            response=SimpleNamespace(send_message=send_message),
        )
        pipeline = SimpleNamespace(state=state)
        await handle_status(interaction, settings, pipeline)
        interaction.user.id = 99
        await handle_status(interaction, settings, pipeline)
        assert replies[0][0] == "No import records yet."
        assert "not authorized" in replies[1][0]
        assert all(reply[1]["ephemeral"] for reply in replies)
    finally:
        await state.close()


async def test_expired_menu_reply_keeps_upload_and_status(tmp_path, monkeypatch):
    import asyncio

    import discord

    from immich_tg_bot.discord_bot import handle_menu, handle_status

    entered, release = asyncio.Event(), asyncio.Event()
    original = httpx.AsyncClient

    async def immich(request):
        if request.method == "POST" and request.url.path == "/assets":
            entered.set()
            await release.wait()
            return httpx.Response(201, json={"id": "1", "status": "created"})
        return httpx.Response(200, json=[])

    monkeypatch.setattr(
        "immich_tg_bot.immich.httpx.AsyncClient",
        lambda **kw: original(**kw, transport=httpx.MockTransport(immich)),
    )
    settings = Settings.model_construct(
        data_dir=tmp_path, immich_url="https://immich.test", immich_api_key="key",
        album_name=None, discord_album_name=None, discord_allowed_user_ids=[42],
    )
    responses = []

    async def defer(**kwargs):
        responses.append(kwargs)

    async def expired(**kwargs):
        response = SimpleNamespace(status=404, reason="Not Found")
        raise discord.NotFound(response, {"message": "Unknown interaction", "code": 10062})

    async def send(content, **kwargs):
        responses.append(content)

    async def send_reply(**kwargs):
        responses.append(kwargs["content"])

    author = SimpleNamespace(id=42, display_name="Alice", name="alice")
    interaction = SimpleNamespace(
        user=author, locale="en-US", response=SimpleNamespace(defer=defer, send_message=send),
        edit_original_response=expired, guild_id=None,
    )
    message = SimpleNamespace(
        id=10, channel=SimpleNamespace(id=20), author=author, created_at=datetime.now(UTC),
        content="", attachments=[SimpleNamespace(id=1, filename="a.jpg", size=1,
                                                  url="https://cdn.test/a")],
    )
    async with original(
        transport=httpx.MockTransport(lambda req: httpx.Response(200, content=b"a"))
    ) as client:
        async with ingestion_runtime(settings) as pipeline:
            task = asyncio.create_task(
                handle_menu(interaction, message, settings, pipeline, client)
            )
            try:
                await asyncio.wait_for(entered.wait(), 2)
                await handle_status(interaction, settings, pipeline)
                assert "processing" in responses[-1]
            finally:
                release.set()
                await asyncio.wait_for(task, 2)
            await handle_status(interaction, settings, pipeline)
            assert "completed" in responses[-1]
            assert "Uploaded: 1" in responses[-1]
            assert responses[0] == {"ephemeral": True, "thinking": True}
            pending = await pipeline.state.create_ingest_record(42, "20", "10")
            await pipeline.state.start_ingest_record(pending)

        async with ingestion_runtime(settings) as pipeline:
            await handle_status(interaction, settings, pipeline)
            assert "interrupted" in responses[-1]
            interaction.edit_original_response = send_reply
            await handle_menu(interaction, message, settings, pipeline, client)
            records = await pipeline.state.recent_ingest_records(42)
            assert [r.status for r in records] == ["completed", "interrupted", "completed"]
            assert records[0].duplicates == 1


async def test_restart_does_not_replay_and_manual_retry_finishes_album(tmp_path, monkeypatch):
    import asyncio

    from immich_tg_bot.discord_bot import handle_menu, handle_status

    album_entered = asyncio.Event()
    calls = []
    original = httpx.AsyncClient
    block_album = True

    async def immich(request):
        calls.append((request.method, request.url.path))
        if request.url.path == "/assets":
            return httpx.Response(201, json={"id": "asset", "status": "created"})
        if request.method == "GET":
            return httpx.Response(200, json=[{"id": "album", "albumName": "Discord Inbox"}])
        if request.method == "PUT":
            if block_album:
                album_entered.set()
                await asyncio.Event().wait()
            return httpx.Response(200, json=[{"id": "asset", "success": True}])
        raise AssertionError(request.url)

    def download(request):
        calls.append((request.method, request.url.path))
        return httpx.Response(200, content=b"photo")

    monkeypatch.setattr(
        "immich_tg_bot.immich.httpx.AsyncClient",
        lambda **kw: original(**kw, transport=httpx.MockTransport(immich)),
    )
    settings = Settings.model_construct(
        data_dir=tmp_path, immich_url="https://immich.test", immich_api_key="key",
        album_name=None, discord_allowed_user_ids=[42],
    )
    replies = []

    async def defer(**kwargs):
        pass

    async def edit(**kwargs):
        replies.append(kwargs["content"])

    async def send(content, **kwargs):
        replies.append(content)

    author = SimpleNamespace(id=42, display_name="Alice", name="alice")
    interaction = SimpleNamespace(
        user=author, locale="en-US", guild_id=None, edit_original_response=edit,
        response=SimpleNamespace(defer=defer, send_message=send),
    )
    message = SimpleNamespace(
        id=10, channel=SimpleNamespace(id=20), author=author, created_at=datetime.now(UTC),
        content="", attachments=[SimpleNamespace(id=1, filename="a.jpg", size=5,
                                                  url="https://cdn.test/photo")],
    )
    async with original(transport=httpx.MockTransport(download)) as client:
        async with ingestion_runtime(settings) as pipeline:
            task = asyncio.create_task(
                handle_menu(interaction, message, settings, pipeline, client)
            )
            await asyncio.wait_for(album_entered.wait(), 2)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        before_restart = list(calls)
        block_album = False
        async with ingestion_runtime(settings) as pipeline:
            await handle_status(interaction, settings, pipeline)
            assert "interrupted" in replies[-1]
            assert calls == before_restart
            await handle_menu(interaction, message, settings, pipeline, client)
            records = await pipeline.state.recent_ingest_records(42)
            assert [r.status for r in records] == ["completed", "interrupted"]
            assert records[0].duplicates == 1
            assert calls.count(("POST", "/assets")) == 1
            assert calls.count(("GET", "/photo")) == 2
            assert calls.count(("PUT", "/albums/album/assets")) == 2
