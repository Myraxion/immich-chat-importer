# Delegate deduplication to Immich and keep transient ingestion records

Accepted on 2026-10-31.

Remove SQLite and its source-completion, source-to-asset, content-to-asset, and album-completion caches, letting Immich own asset deduplication and album membership for the configured account. Each user-triggered import processes the input again, including archive extraction and file SHA-1 calculation, and uses the existing upload API with `x-immich-checksum` to obtain either a new or an existing asset ID before ensuring the current target album association. We accept repeated processing and API requests to reduce local state and branching; retries preserve successful assets, create no additional copies of identical content, and report upload and album failures separately.

Keep caller-owned Discord `/status` records in memory, showing each caller's five most recent imports during the current process lifetime and remaining responsive while imports wait or run. Ingestion can continue beyond the original interaction reply window and its result stays queryable while the process lives; restart clears all records, including unfinished imports, without retaining interrupted history or automatically replaying work. No replacement persistent store is introduced.

This supersedes the local deduplication/persistence parts of [ADR-0001](0001-consolidate-ingestion-pipeline.md), the cached completion and retry-without-reupload parts of [ADR-0004](0004-cross-platform-ingestion-identity-and-completion.md), and the persistent history/restart interruption parts of [ADR-0005](0005-shared-runtime-and-queryable-ingestion-records.md). The shared pipeline, one-process runtime, serial ingestion, partial-success semantics, and user-triggered retries remain.

The protocol basis is Immich's [checksum upload precheck and duplicate response containing the existing asset ID](https://github.com/immich-app/immich/blob/main/server/src/middleware/asset-upload.interceptor.ts), already supported by the bot's upload client.
