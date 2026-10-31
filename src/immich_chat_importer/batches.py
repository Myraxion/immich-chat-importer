from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field, replace

from .errors import failure_kind, format_failure, format_progress
from .pipeline import IngestionPipeline, IngestItem, IngestSummary
from .retry import retry_notice
from .state import IngestRecord


@dataclass(frozen=True)
class IngestRequest:
    platform: str
    operator_id: int
    source_id: str
    message_id: str
    language: str | None = None
    default_language: str = "en"


@dataclass
class Preparation:
    items: list[IngestItem] = field(default_factory=list)
    errors: list[str | None] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    stage: str = "preparation"


@dataclass
class BatchResult:
    record: IngestRecord
    summary: IngestSummary
    preparation_errors: int
    errors: list[str]
    skipped: list[str]
    fatal_detail: str | None = None


class IngestBatches:
    """Own record lifecycle while adapters own source files and reply delivery."""

    def __init__(self, pipeline: IngestionPipeline) -> None:
        self._pipeline = pipeline
        self._state = pipeline.state

    async def recent(self, platform: str, operator_id: int) -> list[IngestRecord]:
        return await self._state.recent_ingest_records(operator_id, platform=platform)

    async def run(
        self,
        request: IngestRequest,
        prepare: Callable[[Preparation], AbstractAsyncContextManager[None]],
    ) -> BatchResult:
        state = self._state
        record_id = await state.create_ingest_record(
            request.operator_id, request.source_id, request.message_id, platform=request.platform
        )
        # Retain the result even if five newer requests evict this active record.
        record = (await self.recent(request.platform, request.operator_id))[0]
        await state.start_ingest_record(record_id)

        async def notice(stage: str, attempt: int, delay: float) -> None:
            await state.set_ingest_progress(
                record_id,
                format_progress(stage, attempt, delay, request.language, request.default_language),
            )

        def failure(name: str, stage: str, kind: str) -> str:
            return format_failure(name, stage, kind, request.language, request.default_language)

        token = retry_notice.set(notice)
        batch = Preparation()
        summary = IngestSummary()
        fatal = None
        try:
            try:
                async with prepare(batch):
                    if batch.items:
                        batch.stage = "ingestion"
                        await state.wait_ingest_record(record_id)
                        summary = await self._pipeline.ingest(
                            batch.items, record_id=record_id, summary=summary
                        )
            except Exception as exc:
                fatal = failure(request.message_id, batch.stage, failure_kind(exc))
            details = [failure(*detail) for detail in summary.error_details]
            if len(details) != len(summary.error_messages):
                details = list(summary.error_messages)
            errors = [e for e in batch.errors if e is not None] + details
            if fatal:
                errors.append(fatal)
            skipped = batch.skipped + summary.skipped_messages
            error_count = summary.errors + len(batch.errors) + int(fatal is not None)
            status = (
                "partial"
                if error_count and (summary.uploaded or summary.duplicates)
                else ("failed" if error_count else "completed")
            )
            record_details = [*(f"{name}: skipped" for name in skipped), *errors]
            await state.finish_ingest_record(
                record_id,
                status,
                summary.uploaded,
                summary.duplicates,
                len(skipped),
                error_count,
                "\n".join(record_details),
            )
            return BatchResult(replace(record), summary, len(batch.errors), errors, skipped, fatal)
        finally:
            retry_notice.reset(token)
