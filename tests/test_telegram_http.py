import json

import httpx
import pytest

from immich_chat_importer.adapters.telegram.client import TelegramClient
from immich_chat_importer.adapters.telegram.errors import TelegramError


async def test_http_client_preserves_local_api_routes_and_reply_context():
    calls = []

    def respond(request):
        calls.append((request.url.path, json.loads(request.content)))
        return httpx.Response(200, json={"ok": True, "result": {"id": 42, "username": "test_bot"}})

    async with TelegramClient(
        "TEST", "http://local.test", transport=httpx.MockTransport(respond)
    ) as client:
        await client.call("getUpdates", offset=4, timeout=30, allowed_updates=["message"])
        await client.send_message(42, "hello", 7)
    assert calls == [
        ("/botTEST/getUpdates", {"offset": 4, "timeout": 30, "allowed_updates": ["message"]}),
        (
            "/botTEST/sendMessage",
            {
                "chat_id": 42,
                "text": "hello",
                "parse_mode": "HTML",
                "reply_parameters": {"message_id": 7},
            },
        ),
    ]


@pytest.mark.parametrize("code", [401, 403, 409, 413, 429, 500, 502])
async def test_http_client_reports_api_failures(code):
    async with TelegramClient(
        "SECRET",
        "http://local.test",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                code,
                json={
                    "ok": False,
                    "error_code": code,
                    "description": "failed",
                    "parameters": {"retry_after": 5},
                },
            )
        ),
    ) as client:
        with pytest.raises(TelegramError) as exc:
            await client.call("getFile", file_id="f")
        assert exc.value.code == code
        assert exc.value.retry_after == 5
        assert "SECRET" not in str(exc.value)


async def test_polling_advances_offset_recovers_and_redacts_network_errors(monkeypatch):
    calls = []
    waits = []

    async def sleep(delay):
        waits.append(delay)

    monkeypatch.setattr("immich_chat_importer.adapters.telegram.client.asyncio.sleep", sleep)

    def respond(request):
        if request.url.path.endswith("/getMe"):
            return httpx.Response(200, json={"ok": True, "result": {"username": "TestBot"}})
        body = json.loads(request.content)
        calls.append(body)
        if len(calls) == 1:
            raise httpx.ConnectError("URL contains SECRET", request=request)
        if len(calls) == 2:
            return httpx.Response(
                200, json={"ok": True, "result": [{"update_id": 10}, {"update_id": 12}]}
            )
        return httpx.Response(
            401, json={"ok": False, "error_code": 401, "description": "unauthorized"}
        )

    async with TelegramClient(
        "SECRET", "http://local.test", transport=httpx.MockTransport(respond)
    ) as client:
        stream = client.updates()
        assert (await anext(stream))["update_id"] == 10
        assert (await anext(stream))["update_id"] == 12
        with pytest.raises(TelegramError, match="unauthorized"):
            await anext(stream)
    assert [call["offset"] for call in calls] == [0, 0, 13]
    assert waits == [2]


@pytest.mark.parametrize("status_field", ["text", "caption"])
async def test_run_bot_http_import_and_status_stays_responsive(tmp_path, monkeypatch, status_field):
    import asyncio

    from immich_chat_importer.adapters.telegram.bot import run_bot
    from immich_chat_importer.config import Settings
    from immich_chat_importer.runtime import ingestion_runtime

    image = tmp_path / "photo.jpg"
    image.write_bytes(b"original photo content")
    uploading, release, status_replied, done = (asyncio.Event() for _ in range(4))
    replies, offsets, file_ids = [], [], []
    message = {
        "message_id": 1,
        "date": 1700000000,
        "chat": {"id": 42, "type": "private"},
        "from": {"id": 42, "first_name": "Alice", "language_code": "en"},
        "photo": [
            {"file_id": "small", "file_unique_id": "s"},
            {"file_id": "best", "file_unique_id": "b"},
        ],
    }

    async def respond(request):
        method = request.url.path.rsplit("/", 1)[-1]
        if method == "getMe":
            result = {"username": "TestBot"}
        elif method == "getUpdates":
            offset = json.loads(request.content)["offset"]
            offsets.append(offset)
            if offset == 0:
                result = [
                    {"update_id": 1, "message": {**message, "from": {"id": 99}}},
                    {"update_id": 2, "message": message},
                ]
            elif offset == 3:
                await uploading.wait()
                status = {
                    k: v for k, v in message.items() if k != "photo" or status_field == "caption"
                }
                result = [
                    {
                        "update_id": 3,
                        "message": {**status, "message_id": 2, status_field: "/status@TestBot"},
                    }
                ]
            else:
                await asyncio.Event().wait()
        elif method == "getFile":
            file_ids.append(json.loads(request.content)["file_id"])
            result = {"file_path": str(image)}
        elif method == "sendMessage":
            body = json.loads(request.content)
            replies.append(body)
            if body["reply_parameters"]["message_id"] == 2:
                status_replied.set()
            else:
                done.set()
            result = {"message_id": 3}
        elif method == "assets":
            assert image.read_bytes() in await request.aread()
            uploading.set()
            await release.wait()
            return httpx.Response(201, json={"id": "asset", "status": "created"})
        else:
            raise AssertionError(method)
        return httpx.Response(200, json={"ok": True, "result": result})

    original = httpx.AsyncClient
    clients = []

    def client(**kwargs):
        created = original(**{**kwargs, "transport": httpx.MockTransport(respond)})
        clients.append(created)
        return created

    monkeypatch.setattr(httpx, "AsyncClient", client)
    settings = Settings.model_construct(
        immich_url="https://immich.test/api",
        immich_api_key="key",
        telegram_api_base="http://telegram.test",
        telegram_bot_token="TEST",
        telegram_allowed_user_ids=[42],
    )
    async with ingestion_runtime(settings) as pipeline:
        task = asyncio.create_task(run_bot(settings, pipeline))
        try:
            await asyncio.wait_for(status_replied.wait(), 5)
            assert not done.is_set()
            assert "Processing" in replies[0]["text"] or "processing" in replies[0]["text"]
            release.set()
            await asyncio.wait_for(done.wait(), 5)
            record = (await pipeline.state.recent_ingest_records(42, platform="telegram"))[0]
            assert (record.uploaded, record.errors) == (1, 0)
        finally:
            release.set()
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    assert offsets == [0, 3, 4]
    assert file_ids == ["best"]
    assert image.exists()
    assert all(client.is_closed for client in clients)


@pytest.mark.skipif(__import__("sys").platform == "win32", reason="POSIX container signal handling")
def test_cli_sigterm_waits_for_runtime_cleanup():
    import subprocess
    import sys

    script = """
import asyncio, os, signal
import immich_chat_importer.__main__ as app
from types import SimpleNamespace
app.Settings = lambda: SimpleNamespace(log_level="INFO")
async def run(settings):
    asyncio.get_running_loop().call_later(0.05, os.kill, os.getpid(), signal.SIGTERM)
    try:
        await asyncio.Event().wait()
    finally:
        print("runtime closed")
app.run = run
app.main()
"""
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, timeout=10
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "runtime closed"


@pytest.mark.parametrize(
    "caption,imports",
    [("/help@OtherBot", 1), ("/unknown@OtherBot", 1), ("/help@TestBot", 0), ("/start@TestBot", 0)],
)
async def test_media_caption_command_falls_back_to_import(tmp_path, monkeypatch, caption, imports):
    import asyncio

    from immich_chat_importer.adapters.telegram.bot import run_bot
    from immich_chat_importer.config import Settings
    from immich_chat_importer.runtime import ingestion_runtime

    path = tmp_path / "photo.jpg"
    path.write_bytes(b"photo")
    done = asyncio.Event()
    uploads = []
    first = True

    async def respond(request):
        nonlocal first
        method = request.url.path.rsplit("/", 1)[-1]
        if method == "getMe":
            result = {"username": "TestBot"}
        elif method == "getUpdates":
            if not first:
                await asyncio.Event().wait()
            first = False
            result = [
                {
                    "update_id": 1,
                    "message": {
                        "message_id": 1,
                        "date": 1700000000,
                        "chat": {"id": 42, "type": "private"},
                        "from": {"id": 42, "first_name": "Alice"},
                        "photo": [{"file_id": "f"}],
                        "caption": caption,
                    },
                }
            ]
        elif method == "getFile":
            result = {"file_path": str(path)}
        elif method == "assets":
            uploads.append(await request.aread())
            return httpx.Response(201, json={"id": "asset", "status": "created"})
        elif method == "sendMessage":
            done.set()
            result = {"message_id": 2}
        else:
            raise AssertionError(method)
        return httpx.Response(200, json={"ok": True, "result": result})

    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kw: original(**{**kw, "transport": httpx.MockTransport(respond)}),
    )
    settings = Settings.model_construct(
        immich_url="https://immich.test/api",
        immich_api_key="key",
        telegram_bot_token="TEST",
        telegram_api_base="http://telegram.test",
        telegram_allowed_user_ids=[42],
    )
    async with ingestion_runtime(settings) as pipeline:
        task = asyncio.create_task(run_bot(settings, pipeline))
        try:
            await asyncio.wait_for(done.wait(), 3)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    assert len(uploads) == imports
