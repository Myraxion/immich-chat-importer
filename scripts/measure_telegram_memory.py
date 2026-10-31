"""Isolated formal-adapter RSS probe: mocked API endpoints, real run_bot and pipeline."""

import asyncio
import importlib
import json
import tempfile
import time
from pathlib import Path

started = time.perf_counter()


def report(stage):
    rss = next(
        line
        for line in Path("/proc/self/status").read_text().splitlines()
        if line.startswith("VmRSS:")
    )
    print(
        json.dumps(
            {
                "stage": stage,
                "rss_mib": round(int(rss.split()[1]) / 1024, 2),
                "seconds": round(time.perf_counter() - started, 3),
            }
        ),
        flush=True,
    )


report("python_baseline")


async def main():
    import httpx
    from PIL import Image

    from immich_chat_importer.adapters.telegram.bot import run_bot

    importlib.import_module("immich_chat_importer.adapters.discord.bot")
    from immich_chat_importer.config import Settings
    from immich_chat_importer.runtime import ingestion_runtime

    report("startup_imports")
    ready, release, replied = (asyncio.Event() for _ in range(3))
    with tempfile.TemporaryDirectory() as folder:
        photo = Path(folder) / "photo.jpg"
        with Image.new("RGB", (200, 200), "red") as image:
            image.save(photo)
        payload = photo.read_bytes()
        polls = 0
        methods = []

        async def respond(request):
            nonlocal polls
            method = request.url.path.rsplit("/", 1)[-1]
            methods.append(method)
            if method == "getMe":
                result = {"username": "TestBot"}
            elif method == "getUpdates":
                polls += 1
                if polls > 1:
                    await asyncio.Event().wait()
                ready.set()
                await release.wait()
                result = [
                    {
                        "update_id": 1,
                        "message": {
                            "message_id": 1,
                            "date": 1700000000,
                            "chat": {"id": 42, "type": "private"},
                            "from": {"id": 42, "first_name": "Alice"},
                            "photo": [{"file_id": "f", "file_unique_id": "u"}],
                        },
                    }
                ]
            elif method == "getFile":
                result = {"file_path": str(photo)}
            elif method == "assets":
                assert payload in await request.aread()
                return httpx.Response(201, json={"id": "asset", "status": "created"})
            elif method == "sendMessage":
                assert "Uploaded: 1" in json.loads(request.content)["text"]
                replied.set()
                result = {"message_id": 2}
            else:
                raise AssertionError(method)
            return httpx.Response(200, json={"ok": True, "result": result})

        original = httpx.AsyncClient
        httpx.AsyncClient = lambda **kw: original(
            **{**kw, "transport": httpx.MockTransport(respond)}
        )
        settings = Settings.model_construct(
            immich_url="https://immich.test/api",
            immich_api_key="test",
            telegram_bot_token="TEST",
            telegram_api_base="http://telegram.test",
            telegram_allowed_user_ids=[42],
        )
        async with ingestion_runtime(settings) as pipeline:
            task = asyncio.create_task(run_bot(settings, pipeline))
            try:
                await asyncio.wait_for(ready.wait(), 5)
                await asyncio.sleep(1)
                report("idle")
                release.set()
                await asyncio.wait_for(replied.wait(), 5)
                await asyncio.sleep(1)
                report("after_import")
                record = (await pipeline.state.recent_ingest_records(42, platform="telegram"))[0]
                assert record.uploaded == 1 and record.errors == 0
                print(json.dumps({"verified": methods, "image_bytes": len(payload)}), flush=True)
            finally:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)


asyncio.run(main())
