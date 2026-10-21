# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.5] - 2026-10-21

### 🛠️ 修复媒体上传失败

- 修复 Telegram 缓存文件没有扩展名时，上传至 Immich 返回 `400 Bad Request / Unsupported file type` 的问题。
- 上传文件名优先保留原始扩展名，其次使用缓存扩展名；缺失时根据 MIME 类型补齐，视频便笺默认使用 `.mp4`。

### 🐳 修复大文件下载配置

- 将 Compose 中的 `command: --local` 替换为 `TELEGRAM_LOCAL: "1"`，确保 `aiogram/telegram-bot-api` 实际启用本地模式，解决因模式未启用导致的 `file is too big` 错误。
- **升级提示**：已有部署需要同步修改 Compose 配置，并重新创建 `telegram-bot-api` 容器，仅更新机器人镜像无法修复此问题。

[完整变更](https://github.com/Myraxion/immich-telegram-bot/compare/v0.1.4...v0.1.5)

## [0.1.4] - 2026-09-25

### Added
- **Automatic Local File Cleanup**: Ingested files downloaded by the local Telegram Bot API server are automatically deleted upon successful upload to Immich or duplicate detection, preventing disk accumulation in `/var/lib/telegram-bot-api`.
- **Configurable Cleanup Switch (`CLEANUP_LOCAL_FILES`)**: Added `CLEANUP_LOCAL_FILES` environment variable (default: `true`). Can be set to `false` if users need to retain downloaded local files for debugging.
- **Fault-Tolerant File Lifecycle**: Ingestion failures (such as archive extraction errors or network issues during upload) retain local files for investigation without deleting them prematurely; filesystem unlinks catch `OSError` to avoid interrupting processing.

### Changed
- **Compose Mount Mode**: Updated `docker-compose.yml` to mount the shared `tg-files` volume into `immich-telegram-bot` in read-write mode (removed `:ro`) to enable file deletion.

## [0.1.3] - 2026-09-25

### Added
- **Native Telegram Localization**: Automatic multi-language reply matching sender's Telegram client language preference with support for English (`en`), Chinese (`zh`), Japanese (`ja`), and Russian (`ru`).
- **Configurable Fallback Language**: Added `DEFAULT_LANGUAGE` environment variable (default: `en`, options: `en`, `zh`, `ja`, `ru`) for unconfigured or unsupported sender locales.
- **Media Group Language Consistency**: Multi-asset media groups consistently resolve localization against the leading message sender preference.
- **Domain Modeling & ADR 0003**: Recorded architecture decision in `docs/adr/0003-telegram-native-localization.md` and added `LanguagePreference` domain definition to `CONTEXT.md`.

## [0.1.2] - 2026-09-24

### Added
- **Dynamic File Naming**: Configurable file naming rules via `MEDIA_NAME_TEMPLATE` (default: `{source}_{message_id}_{index}`) for photos/videos and `DOCUMENT_NAME_TEMPLATE` (default: `{original_name}`) for documents.
- **Dynamic Album Routing**: Configurable target album resolution via `ALBUM_NAME_TEMPLATE`, automatically routing media into dynamically named Immich albums with fallback to `ALBUM_NAME`.
- **Rich Metadata Variables**:
  - Smart fallback variables: `{source}`, `{source_id}`, `{source_username}` / `{username}`, `{message_id}`, `{date}`.
  - Explicit variables: `{msg_date}`, `{forward_date}`, `{exif_date}`, `{sender}`, `{media_type}`, `{file_unique_id}`, `{media_group_id}`, `{caption}`, `{index}`, etc.
- **Timezone Awareness (`TZ`)**: Integrated `TZ` environment configuration (default `UTC`, e.g. `Asia/Shanghai`) converting all date/timestamp metadata to local timezone.
- **Fault-Tolerant Formatting**: Three-level error fallback ensuring unknown variables and malformed templates safely degrade to defaults without interrupting ingestion.
- **Batch Collision Disambiguation**: Deterministic collision avoidance algorithm preventing duplicate filenames in media groups or batch transfers.
- **Immich Album Caching**: Added in-memory album cache in `ImmichClient` to reduce redundant album lookup and creation requests.
- **Domain Modeling & ADR 0002**: Recorded architectural decisions in `docs/adr/0002-dynamic-naming-and-album-routing.md` and expanded `CONTEXT.md`.

## [0.1.1] - 2026-09-24


### Added
- **`IngestionPipeline` Deep Module**: Consolidated deduplication, archive handling, EXIF metadata extraction, Immich asset creation, and album grouping behind a single batch interface.
- **End-to-End Pipeline Tests**: Added comprehensive test suite in `tests/test_pipeline.py` covering deduplication, archive extraction, partial error isolation, and idempotent retry semantics.
- **Domain Modeling & ADR**: Added `CONTEXT.md` domain language glossary and `docs/adr/0001-consolidate-ingestion-pipeline.md`.
- **Type Checking Support**: Added `[tool.mypy]` configuration with `pydantic.mypy` plugin in `pyproject.toml`.

### Changed
- **Thin Adapter Architecture**: Refactored `bot.py` into a thin transport adapter, removing scattered state management and album API calls.
- **Strict Idempotency**: Messages are only marked as processed when all media items succeed; partial failures can be safely retried without re-uploading cached files.
- **Album Soft Degradation**: Failures in adding assets to an album now emit a warning without failing already uploaded library assets.

### Fixed
- **Windows Path Compatibility**: Fixed invalid colon in mock tokens in `tests/test_bot.py`.
- **Empty Archive Handling**: Archives with no recognized media are now correctly marked as processed.

## [0.1.0] - 2026-09-24

### Added
- Initial scaffold for Immich Telegram bot.
- Support for uploading photos, videos, audio, voice, video notes, and documents.
- Automatic archive extraction (zip, rar, 7z, tar) using `bsdtar`.
- Media group (album) debounce aggregation.
- SHA-1 content deduplication and SQLite state persistence.
- Local Telegram Bot API support for up to 2 GB files.
