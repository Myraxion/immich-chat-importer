# Consolidate Ingestion Pipeline into Deep Module

The local deduplication and persistence decisions are superseded by [ADR-0006](0006-delegate-deduplication-to-immich.md); the shared `IngestionPipeline` boundary remains in effect.

We consolidate inbound message deduplication, archive extraction, content SHA-1 hashing, EXIF timestamp parsing, Immich asset uploading, album grouping, and state persistence behind a single deep module `IngestionPipeline`.

Previously, message deduplication and album assignment leaked into `bot.py` while hash caching and archive handling resided in `pipeline.py`, creating a shallow 7-parameter function interface that could not be tested without spinning up Telegram message infrastructure.

By accepting a sequence of normalized `IngestItem` data structures and returning a structured `IngestSummary`, `bot.py` functions solely as a thin Telegram transport adapter, while `IngestionPipeline` guarantees two-phase deduplication locality and end-to-end testability across a single clean seam.
