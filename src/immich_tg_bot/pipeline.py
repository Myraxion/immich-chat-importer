import asyncio
import json
import logging
import tempfile
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timezone, tzinfo
from pathlib import Path

from PIL import Image

from .archives import extract, is_archive, walk_media
from .errors import failure_kind
from .immich import ImmichClient, sha1_file
from .retry import report_stage
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
    error_details: list[tuple[str, str, str]] = field(default_factory=list)
    skipped_messages: list[str] = field(default_factory=list)


def _exif_datetime(path: Path, target_tz: tzinfo = UTC) -> datetime | None:
    try:
        with Image.open(path) as img:
            exif = img.getexif()
            original = exif.get_ifd(34665)
    except Exception:
        return None
    if not exif:
        return None
    for tag, offset_tag in ((_EXIF_DATETIME_ORIGINAL, 36881), (_EXIF_DATETIME, 36880)):
        raw = original.get(tag) or exif.get(tag)
        if not raw:
            continue
        try:
            value = datetime.strptime(str(raw), "%Y:%m:%d %H:%M:%S")
            offset = original.get(offset_tag) or exif.get(offset_tag)
            zone = target_tz
            if offset:
                parsed = datetime.strptime(str(offset), "%z").utcoffset()
                if parsed is not None:
                    zone = timezone(parsed)
            return value.replace(tzinfo=zone)
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
        target_tz: tzinfo = UTC,
    ) -> None:
        self._immich = immich
        self._state = state
        self._album_id = album_id
        self._default_album_name = default_album_name
        self._max_archive_files = max_archive_files
        self._device_id = device_id
        self._cleanup_local = cleanup_local
        self._target_tz = target_tz
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
            name = item.original_file_name or item.file_name
            stage = "extract" if is_archive(name) else "upload"
            await report_stage(f"{stage}: {name}")
            await self._ingest_item(item, summary, album_groups)

        for album_key, assets in album_groups.items():
            stage = "album lookup/create"
            try:
                if self._album_id and album_key == self._album_id:
                    target_id = self._album_id
                else:
                    target_id = await self._immich.get_or_create_album(album_key)
                stage = "album association"
                failures = await self._immich.add_to_album(target_id, list(assets)) or {}
                for asset_id, name in assets.items():
                    if asset_id in failures:
                        summary.errors += 1
                        summary.error_messages.append(
                            f"{name} ({asset_id}): {stage} {album_key}: {failures[asset_id]}"
                        )
                        summary.error_details.append((name, stage, "failure_unknown"))
            except Exception as e:
                log.warning(
                    "Failed to add %d asset(s) to album %r: %s",
                    len(assets),
                    album_key,
                    e,
                )
                for asset_id, name in assets.items():
                    summary.errors += 1
                    summary.error_messages.append(f"{name} ({asset_id}): {stage} {album_key}: {e}")
                    summary.error_details.append((name, stage, failure_kind(e, stage)))

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
        legacy = item.platform == "telegram" and not item.attachment_id
        identity = (item.platform, str(item.chat_id), str(item.message_id), item.attachment_id)
        item_errors: list[str] = []

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
                    summary.error_details.append(
                        (
                            item.original_file_name or item.file_name,
                            "extract",
                            failure_kind(e, "extract"),
                        )
                    )
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
                    summary.error_details.append((archive_name, "extract", "failure_archive_limit"))
                    return
                if not media:
                    log.info("Archive %s contained no recognised media", item.local_path)
                    summary.skipped_messages.append(f"{archive_name}: no supported media")
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
                        item_errors=item_errors,
                        album_groups=album_groups,
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
                item_errors=item_errors,
                album_groups=album_groups,
            )

        if not item_errors:
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
        item_errors: list[str],
        album_groups: dict[str, dict[str, str]],
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
            elif status == "duplicate":
                summary.duplicates += 1
            effective_album = target_album or self._default_album_name or self._album_id
            if effective_album:
                album_groups[effective_album][asset_id] = file_name
        except Exception as e:
            log.exception("Upload failed for %s", file_path)
            err = f"{error_name or file_name}: upload: {e}"
            summary.errors += 1
            summary.error_messages.append(err)
            summary.error_details.append((error_name or file_name, "upload", failure_kind(e)))
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
        created_at = _exif_datetime(file_path, self._target_tz) or fallback_created_at
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
        return status, asset_id
