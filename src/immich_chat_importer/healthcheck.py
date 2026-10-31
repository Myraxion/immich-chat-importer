"""Docker HEALTHCHECK: verifies the bot can reach the Immich API."""

import asyncio
import sys

from .config import Settings
from .immich import ImmichClient


async def _main() -> int:
    try:
        settings = Settings()
    except Exception as e:
        print(f"config error: {e}", file=sys.stderr)
        return 1
    client = ImmichClient(base_url=settings.immich_url, api_key=settings.immich_api_key)
    try:
        return 0 if await client.ping() else 1
    finally:
        await client.aclose()


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
