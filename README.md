# immich-chat-importer

> Self-hosted bot that imports media from Telegram and Discord into your [Immich](https://immich.app) library.

English | [简体中文](README_zh.md)

Forward media to the Telegram bot, send attachments to the Discord bot in a DM, or use Discord’s **Apps → Save to Immich** message command. Both platforms share one Immich account, exact-content deduplication, and album routing.

[![Release](https://img.shields.io/github/v/release/myraxion/immich-chat-importer?display_name=tag&sort=semver)](https://github.com/myraxion/immich-chat-importer/releases)
[![Docker image](https://img.shields.io/badge/ghcr.io-immich--chat--importer-blue?logo=docker)](https://github.com/myraxion/immich-chat-importer/pkgs/container/immich-chat-importer)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-orange.svg)](LICENSE)

## Features

- **Telegram**: import photos, videos, animations, audio, documents, media groups, and supported archives. The bundled local Bot API server supports large downloads.
- **Discord**: import supported photo, video, and archive attachments from bot DMs or a user-installed message command. Menu replies are private; `/status` shows your five latest imports since startup.
- **Archives**: ZIP, RAR, 7z, and tar variants are unpacked server-side, including media in ordinary subdirectories, but nested archives are not expanded. Archives exceeding the configured media count are rejected before any entries are uploaded.
- **Naming and dates**: configure filenames and albums separately for each platform; photo timestamps prioritize EXIF capture time, falling back to message time.
- **Access**: separate user ID whitelists for each platform.
- **Language**: replies in English, Chinese, Japanese, or Russian.
- **Deployment**: Telegram only, Discord only, or both; multi-architecture images support `linux/amd64` and `linux/arm64`.

## How it works

```text
Telegram → local Bot API ─┐
                          ├→ shared ingestion → Immich
Discord → Gateway ────────┘
```

## Choose a deployment

| Mode | `ENABLED_PLATFORMS` | Description |
| --- | --- | --- |
| Telegram only (default) | `telegram` | Run the Telegram import bot only |
| Discord only | `discord` | Run the Discord import bot only |
| Both | `telegram,discord` | Run both bots concurrently |

All modes use the same `docker-compose.yml` deployment (started with `docker compose up -d`). There is no need to maintain separate Compose files; simply set `ENABLED_PLATFORMS` in `.env` and fill in the required environment variables for the enabled platforms.

## Quick start

You need a working Immich instance and Docker installed.

```bash
mkdir immich-chat-importer && cd immich-chat-importer

curl -O https://raw.githubusercontent.com/myraxion/immich-chat-importer/main/docker-compose.yml
curl -o .env https://raw.githubusercontent.com/myraxion/immich-chat-importer/main/.env.example

# Fill in the settings in .env for your chosen mode (see "Detailed setup" below)
${EDITOR:-nano} .env

docker compose up -d
```

Once running:

- **Telegram**: Send `/start` to your bot, then forward a photo or file.
- **Discord**: Send attachments to your bot in a DM, or right-click a message and choose **Apps → Save to Immich**.

## Detailed setup

### 1. Common configuration (required for all modes)

#### Get an Immich API key

1. In Immich, click your avatar → **Account Settings** → **API Keys** → **New API Key**.
2. Give it a name like `chat-importer`, copy the generated key → `IMMICH_API_KEY`.

#### Find your Immich URL & network

`IMMICH_URL` must end in `/api`.

- If you run the bot on the **same Docker host** as Immich and they share a network: `http://immich-server:2283/api` (replace `immich-server` with your Immich container name).
- If you reach Immich via a reverse proxy: `https://photos.example.com/api`.

If you run the bot in a separate Compose project, attach it to Immich's network:

```yaml
# Add under immich-chat-importer in docker-compose.yml:
networks: [immich, default]
networks:
  immich:
    external: true
    name: immich_default      # adjust to your Immich network name
```

### 2. Telegram configuration (when Telegram is enabled)

#### Create a Telegram bot

1. Open [@BotFather](https://t.me/BotFather), send `/newbot`, follow prompts.
2. Save the **HTTP API token** it gives you → `TELEGRAM_BOT_TOKEN`.
3. Optional but recommended: send `/setprivacy` → **Disable**. Lets the bot read forwarded messages in groups (not needed if you only DM the bot).

#### Get `api_id` / `api_hash`

The bundled local Bot API server needs Telegram application credentials to authenticate with the Telegram cloud. They are **not the bot token** — they identify the app, not the bot.

1. Go to <https://my.telegram.org/apps> and log in with your phone number.
2. Create a new application (any title / short name).
3. Copy `api_id` (a number) → `TELEGRAM_API_ID`.
4. Copy `api_hash` (a long hex string) → `TELEGRAM_API_HASH`.

#### Find your Telegram user ID

Message [@userinfobot](https://t.me/userinfobot) and copy the numeric ID it replies with → `TELEGRAM_ALLOWED_USER_IDS`.

Multiple users? Comma-separated: `TELEGRAM_ALLOWED_USER_IDS=11111111,22222222`.

### 3. Discord configuration (when Discord is enabled)

#### Create a Discord application

1. Open the [Discord Developer Portal](https://discord.com/developers/applications) and click **New Application**.
2. Go to the **Bot** page on the left, click **Reset Token**, generate and copy the token → `DISCORD_TOKEN`.
   > [!NOTE]
   > The app connects via Discord Gateway long-lived connections. No public callback URL or privileged Message Content Intent is required. Global slash commands and context menus are registered automatically when the process starts.

#### Configure user install and add to your account

1. Go to the **Installation** page on the left:
   - Under **Installation Contexts**, check **User Install** (allows invoking the context menu anywhere you can view messages).
   - Under **Default Install Settings** → **Scopes**, add `applications.commands` (for slash commands and context menus).
2. Open the generated **Install Link** (or use **OAuth2** → **URL Generator** with `applications.commands` and `bot` selected under User Install) to install the app to your personal Discord account.

#### Find your Discord user ID

1. In your Discord client, open **User Settings** → **Advanced** → enable **Developer Mode**.
2. Right-click your avatar or profile, choose **Copy User ID** → `DISCORD_ALLOWED_USER_IDS`.
3. Multiple users? Comma-separated: `DISCORD_ALLOWED_USER_IDS=111111111111111111,222222222222222222`. An empty whitelist authorizes nobody.

### 4. Start the service

```bash
docker compose up -d
docker compose logs -f immich-chat-importer
```

On a clean start you should see something like:

```log
INFO immich_chat_importer.adapters.telegram.bot: Using Immich album 'Telegram Inbox' (id=...)
INFO immich_chat_importer.adapters.telegram.bot: Bot starting (allowed users: [...], album: Telegram Inbox, immich: ...)
# If Discord is enabled:
INFO immich_chat_importer.adapters.discord.bot: Discord bot starting (allowed users: [...], album: Discord Inbox, immich: ...)
```

### 5. How to use

- **Telegram**:
  - Send `/start` to the bot to activate.
  - Forward photos, videos, animations, audio, or files to the bot; they will appear in Immich within seconds.
  - Query `/status` in a private chat with the bot to see your five most recent imports since startup.
- **Discord**:
  - **DM attachments**: Send supported photos, videos, or archives directly to the bot in a DM.
  - **Message menu import**: Right-click (or tap and hold on mobile) any message with attachments → **Apps** → **Save to Immich**. The response is visible only to you.
  - **Status query**: Send `/status` in a DM or channel to view your five latest imports since startup.
  - **Retry**: If a network failure interrupts an album association, resend or invoke the menu again; Immich reuses existing assets and completes the album routing.

## Configuration reference

**Breaking change:** Telegram-specific environment variables now use the `TELEGRAM_` prefix. Rename old variables in existing `.env` files using the names in the table below; old names are not read.

`BOT_TOKEN` → `TELEGRAM_BOT_TOKEN`; `ALLOWED_USER_IDS` → `TELEGRAM_ALLOWED_USER_IDS`; `ALBUM_NAME` → `TELEGRAM_ALBUM_NAME`; `ALBUM_NAME_TEMPLATE` → `TELEGRAM_ALBUM_NAME_TEMPLATE`; `MEDIA_NAME_TEMPLATE` → `TELEGRAM_MEDIA_NAME_TEMPLATE`; `DOCUMENT_NAME_TEMPLATE` → `TELEGRAM_DOCUMENT_NAME_TEMPLATE`; `TG_FILES_DIR` → `TELEGRAM_FILES_DIR`; `TG_API_BASE` → `TELEGRAM_API_BASE`.

All settings are read from `.env`. Platform-specific required values apply only when that platform is enabled.

| Variable | Required | Default | Description |
|---|---|---|---|
| `IMMICH_URL` | ✅ | — | Immich base URL ending in `/api`. |
| `IMMICH_API_KEY` | ✅ | — | API key generated in Immich account settings. |
| `ENABLED_PLATFORMS` |  | `telegram` | Enabled platforms: `telegram`, `discord`, or `telegram,discord`. |
| **Telegram configuration** |  |  | *(effective only when Telegram is enabled)* |
| `TELEGRAM_BOT_TOKEN` | ✅* | — | Telegram bot token from BotFather. |
| `TELEGRAM_API_ID` | ✅* | — | Numeric app ID from my.telegram.org. |
| `TELEGRAM_API_HASH` | ✅* | — | App hash from my.telegram.org. |
| `TELEGRAM_ALLOWED_USER_IDS` | ✅* | — | Comma-separated whitelist of Telegram user IDs. |
| `TELEGRAM_ALBUM_NAME` |  | `Telegram Inbox` | Fallback album. Leave empty to upload to library only. |
| `TELEGRAM_MEDIA_NAME_TEMPLATE` |  | `{source}_{message_id}_{index}` | Dynamic naming template for photos, videos, animations, and audio. |
| `TELEGRAM_DOCUMENT_NAME_TEMPLATE` |  | `{original_name}` | Dynamic naming template for document files. |
| `TELEGRAM_ALBUM_NAME_TEMPLATE` |  | *(empty)* | Dynamic album template (e.g. `{source}`). Falls back to `TELEGRAM_ALBUM_NAME`. |
| **Discord configuration** |  |  | *(effective only when Discord is enabled)* |
| `DISCORD_TOKEN` | ✅* | — | Bot token from Discord Developer Portal. |
| `DISCORD_ALLOWED_USER_IDS` | ✅* | — | Comma-separated whitelist of numeric Discord user IDs. |
| `DISCORD_ALBUM_NAME` |  | `Discord Inbox` | Fallback album. Leave empty to upload to library only. |
| `DISCORD_FILENAME_TEMPLATE` |  | `{original_name}` | Attachment naming template (`.env.example` suggests `{source}_{sender}_{message_id}_{index}`). |
| `DISCORD_ALBUM_NAME_TEMPLATE` |  | *(empty)* | Dynamic album template. Falls back to `DISCORD_ALBUM_NAME`. |
| `DISCORD_MAX_ATTACHMENT_MB` |  | `2000` | Input limit per Discord attachment in MiB. |
| **Common and advanced settings** |  |  | |
| `TZ` |  | `UTC` | Timezone for filename and album dates and `/status` timestamps (e.g. `Asia/Shanghai`). |
| `DEFAULT_LANGUAGE` |  | `en` | Default fallback reply language (`en`, `zh`, `ja`, `ru`). |
| `MAX_ARCHIVE_MB` |  | `2000` | Upper limit for incoming archives in MB. |
| `MAX_ARCHIVE_FILES` |  | `1000` | Maximum media entries per archive; over-limit archives are rejected before upload. |
| `CLEANUP_LOCAL_FILES` |  | `true` | Automatically delete local downloaded files after ingestion or duplicate detection. |
| `LOG_LEVEL` |  | `INFO` | Log level: `DEBUG` / `INFO` / `WARNING` / `ERROR`. |
| `DATA_DIR` |  | `/data` | Inside-container directory for temporary downloads and extractions. |
| `TELEGRAM_FILES_DIR` |  | `/var/lib/telegram-bot-api` | Inside-container mount path for the shared local Bot API volume. |
| `TELEGRAM_API_BASE` |  | `http://telegram-bot-api:8081` | Address of the local Bot API server. |

*\*Note: Variables marked with ✅\* are required only when their corresponding platform is enabled.*

## Telegram naming templates

Telegram provides separate naming and album templates for different media types:

- `TELEGRAM_MEDIA_NAME_TEMPLATE`: Used for photos, videos, animations, and audio (default: `{source}_{message_id}_{index}`).
- `TELEGRAM_DOCUMENT_NAME_TEMPLATE`: Used for files sent as Documents (default: `{original_name}`, preserving the original filename).
- `TELEGRAM_ALBUM_NAME_TEMPLATE`: Dynamic album template, defaulting to empty; falls back to `TELEGRAM_ALBUM_NAME` (default: `Telegram Inbox`) if unset or rendered empty.

Templates produce the stem without an extension; the original extension is appended automatically. Media extracted from an archive retains its entry filename and does not use this template.

| Variable | Telegram value & description |
|---|---|
| `{original_name}` | Document filename without extension; empty for regular photos/videos without a filename. |
| `{source}` | Source name: channel title, group title, or author name for forwards; chat title, sender name, or `telegram` for direct messages. |
| `{source_id}` | Source ID: forwarded origin ID, chat ID, or sender ID. |
| `{source_username}`, `{username}` | Source username: forwarded username, chat username, or sender username. |
| `{sender}` | Full name of the user who sent the message to the bot (falls back to username). |
| `{sender_id}` | Numeric Telegram ID of the user who sent the message. |
| `{chat_title}` | Title or full name of the current chat. |
| `{chat_id}` | Numeric ID of the current chat. |
| `{message_id}` | Message ID: original channel message ID for channel forwards; current message ID for regular messages. |
| `{msg_id}` | Current Telegram message ID (unaffected by forwarding). |
| `{index}` | Position in the media group (album) or message, starting at 1. |
| `{date}` | Smart date: forward date for forwards; current message date for direct messages, evaluated in `TZ`. |
| `{msg_date}` | Current message date (always uses the current message date even for forwards), in `TZ`. |
| `{forward_date}` | Original publication date for forwards; empty for non-forwarded messages, in `TZ`. |
| `{exif_date}` | Capture date extracted from EXIF metadata in `TZ`; empty if unavailable or not a photo. |
| `{media_type}` | Media type: `photo`, `video`, `animation`, `audio`, `voice`, or `document`. |
| `{file_unique_id}` | Globally unique file identifier assigned by Telegram. |
| `{media_group_id}` | Media group ID (when sending multiple items together as an album); empty for single items. |
| `{caption}` | Text caption of the message (whitespace replaced with underscores, trimmed to first 50 chars). |
| `{forward_source}` | Forward source name (channel title, group name, or username); empty for non-forwards. |
| `{forward_channel}` | Forwarded channel title; empty for non-channel forwards. |
| `{forward_author}` | Author signature or user name of the forwarded message; empty if unsigned or non-forward. |
| `{forward_source_id}` | Numeric ID of the forward source; empty for non-forwards. |
| `{forward_msg_id}` | Original channel message ID; empty for non-channel forwards. |

Date variables support Python date formatting, for example:

```env
TZ=Asia/Shanghai
TELEGRAM_MEDIA_NAME_TEMPLATE={source}_{date:%Y%m%d}_{message_id}_{index}
TELEGRAM_DOCUMENT_NAME_TEMPLATE={source}_{original_name}
TELEGRAM_ALBUM_NAME_TEMPLATE={source}_{date:%Y-%m}
```

For example, when saving a forwarded photo from a channel named `Nature` with message ID `108` and index `1`, the filename would be `Nature_20261031_108_1.jpg`. Filename stems and generated album names replace `/`, `\`, `:`, `*`, `?`, `"`, `<`, `>`, `|`, and control whitespace with underscores, collapse consecutive underscores, trim leading and trailing spaces, underscores and dots, and are limited to 200 characters. If a template fails or renders empty, regular media falls back to `{source}_{message_id}_{index}` (or `file_{index}` if needed), and documents fall back to `{original_name}`.

## Discord naming templates

`.env.example` sets `DISCORD_FILENAME_TEMPLATE` to `{source}_{sender}_{message_id}_{index}`. If the setting is omitted, the application defaults to `{original_name}`, preserving the attachment's original name. The template produces the name without its extension; the original extension is appended automatically. Media extracted from an archive keeps its entry filename instead of using this template.

`DISCORD_ALBUM_NAME_TEMPLATE` uses the same variables to choose an album. It defaults to empty, which uses `DISCORD_ALBUM_NAME` (default: `Discord Inbox`); an empty or invalid rendered album name also falls back to that setting.

| Variable | Discord value |
|---|---|
| `{original_name}` | Original attachment filename without its extension. |
| `{sender}` | Original message author's display name, falling back to their username or ID. |
| `{sender_id}`, `{source_id}` | Original message author's user ID. |
| `{source_username}`, `{username}` | Original message author's username, falling back to their ID. |
| `{source}`, `{chat_title}` | `server_channel` in a server; the author's display name in a private conversation. |
| `{chat_id}` | Channel ID of the original message. |
| `{message_id}`, `{msg_id}` | Original message ID. |
| `{index}` | Attachment position in the message, starting at 1. |
| `{date}`, `{msg_date}` | Original message time, in the timezone configured by `TZ` (default `UTC`). |
| `{exif_date}` | Attachment EXIF time in `TZ`, or empty if unavailable. |
| `{media_type}` | `video` when the filename's MIME type is video; otherwise `photo`. |
| `{file_unique_id}` | Discord attachment ID. |
| `{caption}` | Original message text. |

`{forward_date}`, `{media_group_id}`, `{forward_source}`, `{forward_channel}`, `{forward_author}`, `{forward_source_id}`, and `{forward_msg_id}` are empty for Discord imports. Unknown variables also render as empty. Date variables support Python date formatting, for example:

```env
TZ=Asia/Shanghai
DISCORD_FILENAME_TEMPLATE={sender}_{date:%Y%m%d}_{original_name}
DISCORD_ALBUM_NAME_TEMPLATE={source}_{date:%Y-%m}
```

For an attachment `photo.jpg` sent by Alice on 2026-10-31, the filename would be `Alice_20261031_photo.jpg`. Filename and generated album name stems replace `/`, `\`, `:`, `*`, `?`, `"`, `<`, `>`, `|`, and control whitespace with underscores, collapse consecutive underscores, trim leading and trailing spaces, underscores and dots, and are limited to 200 characters. If a filename template fails or renders empty, the bot falls back to `{original_name}`, then to `{source}_{message_id}_{index}` (or `file_{index}` if needed).

## Limits & gotchas

### Telegram

- **Telegram caps single files at 2 GB** even with the local Bot API server. Files larger than that need MTProto (userbot) and are out of scope here.
- **Photos sent as Picture lose EXIF and are recompressed by Telegram.** The bot still uploads them, but timestamps will use the message date and not the original capture date. Send as **Document/File** to preserve everything.
- **First start of `telegram-bot-api` initialises a per-bot directory** and takes ~10–30 seconds. The bot may log a few connection retries during that window; it will settle.
- **`tg-files` named volume can grow** since the local Bot API server keeps each downloaded file until you call `deleteFile`. The bot does not currently delete them; safe to `docker compose down -v` periodically if you don't need history.
- **Compose network**: by default the `immich-chat-importer` service can reach `telegram-bot-api` (same Compose project network) but **not your Immich instance** unless they share a network. See common configuration above.

### Discord

- **Forwarded messages**: Attachments in native Discord forwarded-message snapshots are supported in bot DMs and message menu imports. `{source}` uses the original channel name when accessible to the bot, otherwise its channel ID. The sender and message time come from the forwarding message.
- **Attachment & archive limitations**: Supported formats include photos, videos, and archives (ZIP, RAR, 7z, tar variants, including ordinary subdirectories). Nested archives and non-media entries are skipped; password-protected or invalid archives fail. Individual attachment size is capped by `DISCORD_MAX_ATTACHMENT_MB`.
- **Privacy & permissions**: The bot does not monitor arbitrary chats; it only handles direct DMs and explicitly triggered message menu imports. Menu replies are ephemeral (visible only to the caller).
- **Status history**: Import history queried via `/status` is kept in memory and cleared upon restart. It will not resume unfinished jobs automatically.

### Cross-platform & shared behavior

- **Image capture dates**: For images readable by Pillow, uploads include an XMP sidecar with the capture date and the configured `TZ` offset, without modifying image bytes. EXIF dates without an offset use `TZ`; otherwise the existing capture instant is preserved. Images without EXIF dates use the message time. Videos and other formats retain Immich's native metadata extraction. Existing duplicate assets are not automatically updated.
- **Exact-content deduplication**: Both platforms share Immich's exact-content deduplication (based on SHA-1 hash), without visual similarity matching. Uploading existing assets reuses them while ensuring they are linked to the target album.
- **Single account**: Each deployment corresponds to a single Immich account.

## Development

```bash
git clone https://github.com/myraxion/immich-chat-importer.git
cd immich-chat-importer

# Using uv (recommended):
uv sync --all-extras --dev

# Or using standard venv + pip:
# python -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"

# Build a local image and run with compose:
docker build -t local/immich-chat-importer .
# edit docker-compose.yml: image: local/immich-chat-importer
docker compose up
```

CI runs `ruff` lint/format, `pytest`, and a Docker build smoke-test on every PR.
Releases are cut by pushing a `vX.Y.Z` tag — that triggers a multi-arch build pushed to `ghcr.io/myraxion/immich-chat-importer`.

## License

[AGPL-3.0-only](LICENSE) — same family as Immich itself. If you run a modified version as a network service, you must offer your changes back under the same license.
