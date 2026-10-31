from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from .config import Settings
from .immich import ImmichClient
from .pipeline import IngestionPipeline
from .state import State


@asynccontextmanager
async def ingestion_runtime(settings: Settings) -> AsyncIterator[IngestionPipeline]:
    state = State(settings.data_dir / "state.sqlite")
    await state.open()
    try:
        await state.interrupt_unfinished_ingest_records()
        immich = ImmichClient(base_url=settings.immich_url, api_key=settings.immich_api_key)
        try:
            yield IngestionPipeline(
                immich=immich,
                state=state,
                max_archive_files=settings.max_archive_files,
                cleanup_local=settings.cleanup_local_files,
            )
        finally:
            await immich.aclose()
    finally:
        await state.close()
