import asyncio
import logging

from .bot import run_bot
from .config import Settings
from .runtime import ingestion_runtime


async def run(settings: Settings) -> None:
    async with ingestion_runtime(settings) as pipeline:
        if settings.enabled_platforms == ["telegram"]:
            await run_bot(settings, pipeline)
        elif settings.enabled_platforms == ["discord"]:
            from .discord_bot import run_discord

            await run_discord(settings, pipeline)
        else:
            raise ValueError("Combined platform deployment is not yet supported")


def main() -> None:
    settings = Settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(run(settings))


if __name__ == "__main__":
    main()
