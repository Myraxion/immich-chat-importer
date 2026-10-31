import asyncio
import logging
import signal
import sys
from importlib import import_module

from .config import Settings
from .runtime import ingestion_runtime

_ADAPTERS = {
    "telegram": (".adapters.telegram.bot", "run_bot"),
    "discord": (".adapters.discord.bot", "run_discord"),
}


async def run(settings: Settings) -> None:
    async with ingestion_runtime(settings) as pipeline:
        runners = []
        for platform in dict.fromkeys(settings.enabled_platforms):
            module, entrypoint = _ADAPTERS[platform]
            runners.append(getattr(import_module(module, package=__package__), entrypoint))
        tasks = [asyncio.create_task(runner(settings, pipeline)) for runner in runners]
        try:
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)


async def _serve(settings: Settings) -> None:
    loop = asyncio.get_running_loop()
    task = asyncio.create_task(run(settings))
    stopping = False

    def stop() -> None:
        nonlocal stopping
        stopping = True
        task.cancel()

    if sys.platform != "win32":
        loop.add_signal_handler(signal.SIGTERM, stop)
    try:
        await task
    except asyncio.CancelledError:
        if not stopping:
            raise
    finally:
        if sys.platform != "win32":
            loop.remove_signal_handler(signal.SIGTERM)


def main() -> None:
    settings = Settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # HTTPX request URLs include the Telegram token in the path.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    asyncio.run(_serve(settings))


if __name__ == "__main__":
    main()
