# Cross-platform ingestion identity and completion

The local source/content caching and retry-without-reupload decisions are superseded by [ADR-0006](0006-delegate-deduplication-to-immich.md). Reusing assets, completing the current album association, and preserving partial success remain required.

Telegram and Discord imports target one configured Immich account and share content deduplication, while source identity distinguishes the messaging platform and individual inbound file: one Discord message can contain several attachments. Keeping content identity separate from source identity lets repeated imports reuse one Immich asset across platforms without skipping other attachments in the same message.

Reusing an asset still requires associating it with the current target album; uploading or finding the asset alone does not complete an import that targets an album. Preserve successful uploads when another step fails, report the failure, and allow a manually triggered retry to finish the missing work without uploading successful files again. This extends [ADR-0001](0001-consolidate-ingestion-pipeline.md) and [ADR-0002](0002-dynamic-naming-and-album-routing.md); it deliberately changes the existing behavior that ignores album association for duplicate assets and only logs album failures.
