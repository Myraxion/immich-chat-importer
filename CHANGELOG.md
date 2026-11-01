# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.2] - 2026-11-01

### Changed
- 发布镜像同时推送到 Docker Hub 和 GHCR，Compose 默认继续使用 GHCR。
- 发布前运行 CI；预发布版本不更新 `latest`，手动发布必须选择版本标签。

## [0.2.1] - 2026-11-01

### ⚡ Performance & Memory Optimization
- **Telegram 适配层轻量化（移除 aiogram 依赖）**：
  - 彻底移除庞大的 `aiogram` 框架依赖，直接基于 `httpx` 实现与 Telegram Bot API 的原生轻量 HTTP 长轮询与调用（`getMe`, `getUpdates`, `getFile`, `sendMessage` 等）。
  - **内存占用减少约 66%**：根据实测，运行时常驻内存（RSS）从约 180 MiB 降至约 60 MiB，显著降低低配 VPS/NAS 部署环境的系统资源消耗。
  - 保留所有既有功能、批处理导入管道、相册命名模板及本地 Bot API 大文件支持。
- **Discord 内部消息缓存禁用**：
  - 设置 `max_messages=None`，停用 `discord.py` 内部的消息历史环形缓存，防止长周期运行下的内存累积。
- **Docker HEALTHCHECK 标准库轻量化**：
  - 重写容器健康检查入口，完全采用 Python 标准库（`urllib.request`）进行端点探测，支持 `/server/ping` 及兼容回退 `/server-info/ping`。
  - 消除每次定时健康检查冷启动加载 `pydantic`、`httpx` 与 `asyncio` 带来的额外 CPU 与内存开销。

### ✨ User Experience
- **Discord 消息菜单直达「返回原消息」链接**：
  - 在右键消息 **Apps → 保存到 Immich** (Save to Immich) 的即时提示、分段回复与导入结果中，全量附带原消息直达文字链接（如 `[返回原消息](jump_url)` / `[Return to original message](jump_url)`）。
  - 解决在长历史记录中右键保存媒体时客户端视图跳转到底部、打断浏览上下文的问题，点击链接即可一键跳回刚刚浏览的位置。
  - 支持多语言客户端原生自动匹配（中文、英语、日语、俄语），并使用静默私密回复减少通知干扰。

### 🧪 Tests & Tooling
- 新增 `tests/test_telegram_http.py`，完整覆盖原生 Telegram HTTP 适配器的轮询、请求解析与网络容错。
- 新增 `tests/test_healthcheck.py`，覆盖无外部依赖纯净度与各异常网络场景。
- 新增 `scripts/measure_telegram_memory.py`，提供标准化的运行时内存基准测量工具。

### 🚀 Breaking Changes & Migration
- **Telegram 配置变量统一加前缀**：为支持多平台并存，所有 Telegram 专属环境变量添加 `TELEGRAM_` 前缀（`ALLOWED_USER_IDS` → `TELEGRAM_ALLOWED_USER_IDS`、`ALBUM_NAME` → `TELEGRAM_ALBUM_NAME`、`ALBUM_NAME_TEMPLATE` → `TELEGRAM_ALBUM_NAME_TEMPLATE`、`MEDIA_NAME_TEMPLATE` → `TELEGRAM_MEDIA_NAME_TEMPLATE`、`DOCUMENT_NAME_TEMPLATE` → `TELEGRAM_DOCUMENT_NAME_TEMPLATE`）。已有部署升级时必须更新 `.env`。
- **新增部署模式配置 (`ENABLED_PLATFORMS`)**：支持 `telegram`、`discord` 或 `telegram,discord`（双平台联合部署），默认值为 `telegram`。
- **移除本地 SQLite 状态库**：去重逻辑全面委托给 Immich 服务端校验（`x-immich-checksum`），废弃本地 `bot_state.db`，服务完全实现轻量无状态化。
- **项目与镜像更名**：项目正式重命名为 `immich-chat-importer`（原 `immich-telegram-bot`），镜像名迁移至 `ghcr.io/myraxion/immich-chat-importer`。

### Added
- **Discord 平台全面支持**：
  - 支持向机器人私信（DM）直接发送图片、视频和压缩包进行导入。
  - 支持右键消息 **Apps → 保存到 Immich** (Save to Immich) 快捷导入消息附件。
  - 支持通过 `/status` 查询当前进程生命周期内的最近 5 次导入状态与摘要。
  - 支持 Discord 专属动态命名模板 (`DISCORD_FILENAME_TEMPLATE`) 与相册模板 (`DISCORD_ALBUM_NAME_TEMPLATE`)。
  - 支持独立用户白名单配置 (`DISCORD_ALLOWED_USER_IDS`) 与单附件大小上限 (`DISCORD_MAX_ATTACHMENT_MB`)。
- **共享导入核心 (Shared Ingestion Pipeline)**：
  - 抽象通用的 `IngestionPipeline`、`IngestBatch` 与 `IngestRecord` 领域模型，跨平台解耦消息协议与导入管线。
  - 支持单进程同时挂载运行 Telegram 与 Discord 机器人，共享导入资源与 Immich 会话。
- **服务端去重与相册关联对齐 (ADR 0006)**：
  - 依赖 Immich 服务端校验识别重复资产，跨平台导入完全去重且不占额外存储。
  - 重复资产导入时自动对齐并关联到当前指定的目标相册。
- **动态命名与时区支持**：
  - 全面支持 `{source}`, `{source_id}`, `{sender}`, `{date}`, `{exif_date}` 等动态模板变量。
  - 引入 `TZ` 环境变量（默认 `UTC`），所有日期命名与 `/status` 查询均以本地时区呈现。
  - 模板解析容错：未知变量时输出告警并优雅回退到默认命名。
- **压缩包安全限制与配额**：
  - 新增 `MAX_ARCHIVE_MB`（最大解压体积，默认 2000MB）与 `MAX_ARCHIVE_FILES`（最大媒体文件数，默认 1000）。
  - 支持检测加密压缩包并返回友好错误提示。
- **网络抖动重试与相册幂等 (ADR 0007)**：
  - 对来源拉取、Immich 上传、相册查找与关联增加有界自动重试。
  - 相册创建超时时通过二次查找进行结果对齐，避免重复创建同名相册。

### Fixed
- 图片上传附带包含拍摄日期和 `TZ` 时区偏移的 XMP sidecar，原图字节保持不变；无时区 EXIF 使用 `TZ`，已有偏移保留实际时间点。
- Discord 转发图片的 `{source}` 使用原频道名称，无权限查询时使用频道 ID。
- Telegram 和 Discord 的 `/status` 按 `TZ` 配置显示时间和时区，修复始终显示 UTC 的问题。
- Discord 私信和消息菜单支持导入原生转发消息快照中的附件，修复转发图片时结果全部为 0 的问题。
- 修复因文件系统遍历顺序不同导致归档测试与文件导入顺序不稳定的问题。
- 修复超长错误信息回复被平台拦截截断的问题。
- 修复重建相册时的资产归属异常。

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
