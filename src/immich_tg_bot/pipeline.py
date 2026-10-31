import asyncio
import json
import logging
import tempfile
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image

from .archives import extract, is_archive, walk_media
from .immich import ImmichClient, sha1_file
from .state import State

log = logging.getLogger(__name__)

DEVICE_ID = "immich-telegram-bot"

# EXIF tag IDs
_EXIF_DATETIME_ORIGINAL = 36867
_EXIF_DATETIME = 306


@dataclass(frozen=True)
class IngestItem:
    chat_id: int | str
    message_id: int | str
    local_path: Path
    file_name: str
    created_at: datetime
    target_album: str | None = None
    original_file_name: str | None = None
    platform: str = "telegram"
    attachment_id: str = ""


@dataclass
class IngestSummary:
    uploaded: int = 0
    duplicates: int = 0
    errors: int = 0
    new_asset_ids: list[str] = field(default_factory=list)
    error_messages: list[str] = field(default_factory=list)
    skipped_messages: list[str] = field(default_factory=list)


def _exif_datetime(path: Path) -> datetime | None:
    try:
        with Image.open(path) as img:
            exif = img.getexif()
    except Exception:
        return None
    if not exif:
        return None
    for tag in (_EXIF_DATETIME_ORIGINAL, _EXIF_DATETIME):
        raw = exif.get(tag)
        if not raw:
            continue
        try:
            return datetime.strptime(str(raw), "%Y:%m:%d %H:%M:%S").replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def _safe_unlink(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError as e:
        log.warning("Could not remove local file %s: %s", path, e)


class IngestionPipeline:
    def __init__(
        self,
        immich: ImmichClient,
        state: State,
        album_id: str | None = None,
        default_album_name: str | None = None,
        max_archive_files: int = 1000,
        device_id: str = DEVICE_ID,
        cleanup_local: bool = True,
    ) -> None:
        self._immich = immich
        self._state = state
        self._album_id = album_id
        self._default_album_name = default_album_name
        self._max_archive_files = max_archive_files
        self._device_id = device_id
        self._cleanup_local = cleanup_local
        self._ingest_lock = asyncio.Lock()

    @property
    def state(self) -> State:
        return self._state

    async def ingest(
        self,
        items: Sequence[IngestItem],
        record_id: int | None = None,
        summary: IngestSummary | None = None,
    ) -> IngestSummary:
        async with self._ingest_lock:
            if record_id is not None:
                await self._state.start_ingest_record(record_id)
            return await self._ingest(items, summary)

    async def _ingest(
        self, items: Sequence[IngestItem], summary: IngestSummary | None = None
    ) -> IngestSummary:
        if summary is None:
            summary = IngestSummary()
        if not items:
            return summary

        album_groups: dict[str, dict[str, str]] = defaultdict(dict)
        for item in items:
            await self._ingest_item(item, summary, album_groups)

        for album_key, assets in album_groups.items():
            pending = assets
            stage = "album lookup/create"
            try:
                if self._album_id and album_key == self._album_id:
                    target_id = self._album_id
                else:
                    target_id = await self._immich.get_or_create_album(album_key)
                pending = {
                    asset_id: name
                    for asset_id, name in assets.items()
                    if not await self._state.album_completed(asset_id, target_id)
                }
                if not pending:
                    continue
                stage = "album association"
                failures = await self._immich.add_to_album(target_id, list(pending)) or {}
                for asset_id, name in pending.items():
                    if asset_id in failures:
                        summary.errors += 1
                        summary.error_messages.append(
                            f"{name} ({asset_id}): {stage} {album_key}: {failures[asset_id]}"
                        )
                    else:
                        await self._state.mark_album_completed(asset_id, target_id)
            except Exception as e:
                log.warning(
                    "Failed to add %d asset(s) to album %r: %s",
                    len(pending),
                    album_key,
                    e,
                )
                for asset_id, name in pending.items():
                    summary.errors += 1
                    summary.error_messages.append(f"{name} ({asset_id}): {stage} {album_key}: {e}")

        return summary

    def _maybe_cleanup(self, path: Path) -> None:
        if self._cleanup_local:
            _safe_unlink(path)

    async def _ingest_item(
        self,
        item: IngestItem,
        summary: IngestSummary,
        album_groups: dict[str, dict[str, str]],
    ) -> None:
        # 1. 消息级去重
        legacy = item.platform == "telegram" and not item.attachment_id
        identity = (item.platform, str(item.chat_id), str(item.message_id), item.attachment_id)
        processed = (
            legacy and await self._state.already_processed(item.chat_id, item.message_id)
        ) or (not legacy and await self._state.item_processed(*identity))
        album = item.target_album or self._default_album_name or self._album_id
        if processed:
            assets = await self._state.source_assets(identity)
            if assets or not album:
                summary.duplicates += max(1, len(assets))
                if album:
                    album_groups[album].update(assets)
                self._maybe_cleanup(item.local_path)
                return

        # 2. 单文件 vs 归档展开
        item_errors: list[str] = []
        item_new_ids: list[str] = []

        prefix = (
            f"telegram:{item.chat_id}:{item.message_id}"
            if legacy
            else json.dumps(identity, ensure_ascii=True, separators=(",", ":"))
        )

        if is_archive(item.original_file_name or item.file_name):
            with tempfile.TemporaryDirectory(prefix="tg-archive-") as tmpdir:
                tmp = Path(tmpdir)
                try:
                    await extract(item.local_path, tmp)
                except Exception as e:
                    log.exception("Extraction failed for %s", item.local_path)
                    err = f"{item.original_file_name or item.file_name}: extract: {e}"
                    summary.errors += 1
                    summary.error_messages.append(err)
                    item_errors.append(err)
                    return

                media, skipped = walk_media(tmp)
                archive_name = item.original_file_name or item.file_name
                summary.skipped_messages.extend(
                    f"{archive_name}: {p.relative_to(tmp).as_posix()}" for p in skipped
                )
                if len(media) > self._max_archive_files:
                    summary.errors += 1
                    summary.error_messages.append(
                        f"{archive_name}: archive media count exceeds limit "
                        f"({self._max_archive_files})"
                    )
                    return
                if not media:
                    log.info("Archive %s contained no recognised media", item.local_path)
                    summary.skipped_messages.append(f"{archive_name}: no supported media")
                    if legacy:
                        await self._state.mark_processed(
                            item.chat_id, item.message_id, 0, "done", None
                        )
                    else:
                        await self._state.mark_item_processed(*identity)
                    self._maybe_cleanup(item.local_path)
                    return

                for m in media:
                    await self._dispatch_upload(
                        file_path=m,
                        file_name=m.name,
                        target_album=item.target_album,
                        device_asset_id=prefix,
                        archive_member=True,
                        created_at=item.created_at,
                        summary=summary,
                        item_new_ids=item_new_ids,
                        item_errors=item_errors,
                        album_groups=album_groups,
                        identity=identity,
                        error_name=f"{archive_name}: {m.relative_to(tmp).as_posix()}",
                    )
        else:
            await self._dispatch_upload(
                file_path=item.local_path,
                file_name=item.file_name,
                target_album=item.target_album,
                device_asset_id=prefix,
                created_at=item.created_at,
                summary=summary,
                item_new_ids=item_new_ids,
                item_errors=item_errors,
                album_groups=album_groups,
                identity=identity,
            )

        # 3. 严格成功标记：若无错误，标记消息已完成
        if not item_errors:
            if legacy:
                await self._state.mark_processed(item.chat_id, item.message_id, 0, "done", None)
            else:
                await self._state.mark_item_processed(*identity)
            self._maybe_cleanup(item.local_path)

    async def _dispatch_upload(
        self,
        *,
        file_path: Path,
        file_name: str,
        target_album: str | None,
        device_asset_id: str,
        created_at: datetime,
        summary: IngestSummary,
        item_new_ids: list[str],
        item_errors: list[str],
        album_groups: dict[str, dict[str, str]],
        identity: tuple[str, str, str, str],
        archive_member: bool = False,
        error_name: str | None = None,
    ) -> None:
        try:
            status, asset_id = await self._upload_one(
                file_path=file_path,
                file_name=file_name,
                device_asset_id=device_asset_id,
                fallback_created_at=created_at,
                archive_member=archive_member,
            )
            if status == "created":
                summary.uploaded += 1
                summary.new_asset_ids.append(asset_id)
                item_new_ids.append(asset_id)
            elif status in ("duplicate", "cached"):
                summary.duplicates += 1
            await self._state.save_source_asset(identity, asset_id, file_name)
            effective_album = target_album or self._default_album_name or self._album_id
            if effective_album:
                album_groups[effective_album][asset_id] = file_name
        except Exception as e:
            log.exception("Upload failed for %s", file_path)
            err = f"{error_name or file_name}: upload: {e}"
            summary.errors += 1
            summary.error_messages.append(err)
            item_errors.append(err)

    async def _upload_one(
        self,
        *,
        file_path: Path,
        file_name: str,
        device_asset_id: str,
        fallback_created_at: datetime,
        archive_member: bool = False,
    ) -> tuple[str, str]:
        checksum = await asyncio.to_thread(sha1_file, file_path)
        if archive_member:
            device_asset_id = f"{device_asset_id}:{checksum}"
        cached = await self._state.asset_for_sha1(checksum)
        if cached:
            return "cached", cached

        created_at = _exif_datetime(file_path) or fallback_created_at
        modified_at = datetime.fromtimestamp(file_path.stat().st_mtime, tz=UTC)

        result = await self._immich.upload_asset(
            file_path=file_path,
            file_name=file_name,
            device_asset_id=device_asset_id,
            device_id=self._device_id,
            file_created_at=created_at,
            file_modified_at=modified_at,
            checksum=checksum,
        )
        asset_id = result["id"]
        status = result.get("status", "created")
        await self._state.cache_sha1(checksum, asset_id)
        return status, asset_id
