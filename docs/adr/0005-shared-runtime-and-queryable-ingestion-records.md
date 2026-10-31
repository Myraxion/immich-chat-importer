# Shared runtime and queryable ingestion records

The persistent history and restart interruption decisions are superseded by [ADR-0006](0006-delegate-deduplication-to-immich.md). The shared runtime, serial ingestion, responsive status queries, and manual retriggering remain in effect.

Run the enabled Telegram and Discord adapters in one application process, sharing the ingestion core and state, with Discord receiving direct messages and interactions through Gateway rather than a public HTTP callback. Process ingestion batches serially while keeping status queries responsive: this favors simple content deduplication and resource ownership over parallel throughput and independent platform restarts.

Persist caller-owned ingestion records for Discord `/status`, including results that outlive an interaction's reply window, but do not build an automatically replayed task queue. On restart, mark unfinished records interrupted and let the user trigger another import; this retains useful history while avoiding durable execution and recovery machinery.
