# Retry ingestion operations and reconcile uncertain album creation

Accepted on 2026-10-31.

Apply bounded automatic retries to individual transiently failing ingestion operations: source-file retrieval, Immich asset upload, album lookup, and album association. Preserve completed work rather than replaying the enclosing batch or archive; successful recovery is not a final ingestion error. This extends [ADR-0006](0006-delegate-deduplication-to-immich.md): imports remain user-triggered, asset replay relies on Immich content deduplication, and no persistent retry queue or restart recovery is introduced. A batch already executing in the shared ingestion pipeline retains its serial processing position during retry waits, while status queries remain responsive.

Do not automatically resend album-creation requests. If creation has an uncertain outcome, query albums again and continue association when a matching album is found; otherwise report that album creation could not be confirmed, retaining assets already saved. This deliberately favors an actionable partial result over replaying a potentially successful creation request and producing duplicate albums.
