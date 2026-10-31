import asyncio
import logging

from .adapters.telegram.bot import run_bot
from .config import Settings
from .runtime import ingestion_runtime


async def run(settings: Settings) -> None:
    async with ingestion_runtime(settings) as pipeline:
        if set(settings.enabled_platforms) == {"telegram"}:
            await run_bot(settings, pipeline)
        elif set(settings.enabled_platforms) == {"discord"}:
            from .adapters.discord.bot import run_discord

            await run_discord(settings, pipeline)
        else:
            from .adapters.discord.bot import run_discord

            tasks = [
                asyncio.create_task(run_bot(settings, pipeline)),
                asyncio.create_task(run_discord(settings, pipeline)),
            ]
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
