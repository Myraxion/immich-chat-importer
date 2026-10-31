from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from zoneinfo import ZoneInfo

from .config import Settings
from .immich import ImmichClient
from .pipeline import IngestionPipeline
from .state import State


@asynccontextmanager
async def ingestion_runtime(settings: Settings) -> AsyncIterator[IngestionPipeline]:
    state = State()
    immich = ImmichClient(
        base_url=settings.immich_url, api_key=settings.immich_api_key, tz=settings.tz
    )
    try:
        yield IngestionPipeline(
            immich=immich,
            state=state,
            max_archive_files=settings.max_archive_files,
            cleanup_local=settings.cleanup_local_files,
            target_tz=ZoneInfo(settings.tz),
        )
    finally:
        await immich.aclose()
