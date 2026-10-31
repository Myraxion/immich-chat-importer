import asyncio
import logging
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


def main() -> None:
    settings = Settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(run(settings))


if __name__ == "__main__":
    main()
