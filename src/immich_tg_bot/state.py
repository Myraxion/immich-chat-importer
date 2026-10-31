from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from zoneinfo import ZoneInfo


def _timestamp() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")


@dataclass
class IngestRecord:
    id: int
    source_id: str
    message_id: str
    status: str
    created_at: str
    updated_at: str
    uploaded: int = 0
    duplicates: int = 0
    skipped: int = 0
    errors: int = 0
    details: str = ""
    progress: str = ""

    def format_created_at(self, tz: str) -> str:
        created_at = datetime.fromisoformat(self.created_at).replace(tzinfo=UTC)
        return f"{created_at.astimezone(ZoneInfo(tz)):%Y-%m-%d %H:%M:%S} {tz}"


class State:
    def __init__(self) -> None:
        self._next_id = 1
        self._records: dict[int, IngestRecord] = {}
        self._recent: dict[tuple[str, int], deque[int]] = {}

    async def create_ingest_record(
        self, operator_id: int, source_id: str, message_id: str, *, platform: str = "discord"
    ) -> int:
        record_id = self._next_id
        self._next_id += 1
        now = _timestamp()
        self._records[record_id] = IngestRecord(
            record_id, source_id, message_id, "waiting", now, now
        )
        recent = self._recent.setdefault((platform, operator_id), deque())
        recent.appendleft(record_id)
        if len(recent) > 5:
            old_id = recent.pop()
            if self._records[old_id].status not in ("waiting", "processing"):
                del self._records[old_id]
        return record_id

    async def wait_ingest_record(self, record_id: int) -> None:
        self._records[record_id].progress = ""
        self._set_status(record_id, "waiting")

    async def start_ingest_record(self, record_id: int) -> None:
        self._set_status(record_id, "processing")

    async def set_ingest_progress(self, record_id: int, progress: str) -> None:
        self._records[record_id].progress = progress

    def _set_status(self, record_id: int, status: str) -> None:
        record = self._records[record_id]
        record.status = status
        record.updated_at = _timestamp()

    async def finish_ingest_record(
        self,
        record_id: int,
        status: str,
        uploaded: int,
        duplicates: int,
        skipped: int,
        errors: int,
        details: str,
    ) -> None:
        record = self._records[record_id]
        record.uploaded = uploaded
        record.duplicates = duplicates
        record.skipped = skipped
        record.errors = errors
        record.details = details
        record.progress = ""
        self._set_status(record_id, status)
        if not any(record_id in recent for recent in self._recent.values()):
            del self._records[record_id]

    async def recent_ingest_records(
        self, operator_id: int, *, platform: str = "discord"
    ) -> list[IngestRecord]:
        return [
            self._records[record_id] for record_id in self._recent.get((platform, operator_id), ())
        ]
