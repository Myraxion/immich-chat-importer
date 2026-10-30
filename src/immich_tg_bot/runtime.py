import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from .config import Settings
from .immich import ImmichClient
from .pipeline import IngestionPipeline
from .state import State

log = logging.getLogger(__name__)


@asynccontextmanager
async def ingestion_runtime(settings: Settings) -> AsyncIterator[IngestionPipeline]:
    state = State(settings.data_dir / "state.sqlite")
    await state.open()
    try:
        immich = ImmichClient(base_url=settings.immich_url, api_key=settings.immich_api_key)
        try:
            album_id = None
            if settings.album_name:
                try:
                    album_id = await immich.get_or_create_album(settings.album_name)
                    log.info("Using Immich album %r (id=%s)", settings.album_name, album_id)
                except Exception as e:
                    log.warning(
                        "Could not resolve album %r (%s) — uploads will go to library only",
                        settings.album_name,
                        e,
                    )
            yield IngestionPipeline(
                immich=immich,
                state=state,
                album_id=album_id,
                default_album_name=settings.album_name,
                max_archive_files=settings.max_archive_files,
                cleanup_local=settings.cleanup_local_files,
            )
        finally:
            await immich.aclose()
    finally:
        await state.close()
