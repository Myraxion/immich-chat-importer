# Immich Telegram Bot

Telegram bot that ingests forwarded photos, videos, documents, and archives into a self-hosted Immich instance.

## Language

### Ingestion

**IngestItem**:
A single inbound file or media payload designated for upload.
_Avoid_: UploadTask, Job, FileMessage

**IngestBatch**:
A set of ingestion items processed together for one import request, with a combined status outcome. A batch may succeed partially without undoing the assets already imported.
_Avoid_: UploadJob, ImportTransaction

**IngestRecord**:
The queryable status and outcome of one ingestion batch, belonging to the requesting user on its source messaging platform, with Telegram and Discord identities kept separate. Records are available during the current service run and are discarded on restart.
_Avoid_: RecoveryTask, ResumeJob

**IngestionPipeline**:
The pipeline coordinating end-to-end asset ingestion, metadata resolution, deduplication, and album association.
_Avoid_: IngestionService, Uploader, ProcessingManager

**IngestSummary**:
The aggregated status outcome of a processed batch of ingestion items.
_Avoid_: UploadResult, ProcessResponse

**CaptureTime**:
The time used to describe when an imported media file was captured: its EXIF time when available, otherwise the current source message time. It is distinct from the message or forwarded date used for naming; an unavailable EXIF date remains absent.
_Avoid_: MessageDate, UploadTime

**MediaMetadata**:
File-derived information about one media file, shared by naming and ingestion. It distinguishes an available EXIF date from the CaptureTime used when importing the file.
_Avoid_: MessageMetadata (for file-derived information)

**Deduplication**:
The recognition of identical file contents, so repeated imports across messaging platforms share one Immich asset. Files with different contents remain distinct even when they look alike.
_Avoid_: DedupCheck, Filter

### Naming and Organization

**NamingTemplate**:
A parameterized template string resolved against message metadata to generate human-readable file stems or album names.
_Avoid_: FilePattern, NameFormat, Rule

**MessageMetadata**:
The normalized context of a source message (author, chat, origin, timestamp, caption, index) used for dynamic naming and album routing, independent of its messaging platform.
Message and forwarded dates describe the messaging context; the EXIF date describes the file independently and remains absent when unavailable.
_Avoid_: TelegramContext, OriginInfo, MessageData

**AlbumRouting**:
The resolution of target Immich albums for an import, with template-based selection and a static fallback. An existing asset can be associated with a new target album without creating another copy of the asset.
_Avoid_: AlbumMapping, FolderDispatch

### Localization

**LanguagePreference**:
The resolved target language tag ('en', 'zh', 'ja', 'ru') derived from Telegram message sender metadata and default configuration, used to select localized reply messages.
_Avoid_: UserLanguage, LocaleSetting, MessageLanguage
