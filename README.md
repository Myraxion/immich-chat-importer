# immich-chat-importer

> Self-hosted bot that imports media from Telegram and Discord into your [Immich](https://immich.app) library.

English | [简体中文](README_zh.md)

Run Telegram, Discord, or both in one process. See the [Discord and combined deployment guide](docs/discord-deployment.md) for Discord setup and operation.

[![Release](https://img.shields.io/github/v/release/myraxion/immich-chat-importer?display_name=tag&sort=semver)](https://github.com/myraxion/immich-chat-importer/releases)
[![Docker image](https://img.shields.io/badge/ghcr.io-immich--chat--importer-blue?logo=docker)](https://github.com/myraxion/immich-chat-importer/pkgs/container/immich-chat-importer)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-orange.svg)](LICENSE)
[![CI](https://github.com/myraxion/immich-chat-importer/actions/workflows/ci.yml/badge.svg)](https://github.com/myraxion/immich-chat-importer/actions/workflows/ci.yml)

Forward media to the Telegram bot, send attachments to the Discord bot in a DM, or use Discord’s **Apps → Save to Immich** message command. Imports share one Immich account, exact-content deduplication, and album routing.

## Features

- **Telegram**: import photos, videos, animations, audio, documents, media groups, and supported archives. The bundled local Bot API server supports large downloads.
- **Discord**: import supported photo, video, and archive attachments from bot DMs or a user-installed message command. Menu replies are private; `/status` shows your five latest imports since startup.
- **Archives**: ZIP, RAR, 7z, and tar variants are unpacked server-side. Media in ordinary subdirectories is included; nested archives are not expanded. Archives exceeding the configured media count are rejected before their entries are uploaded.
- **Shared ingestion**: reuse identical content across platforms, add assets to the target album, and retain successful imports when another item fails. Failed album associations can be retried.
- **Naming and dates**: configure filenames and albums separately for each platform; photo timestamps use EXIF when available and otherwise the source message time.
- **Access and language**: separate platform user-ID whitelists and replies in English, Chinese, Japanese, or Russian, with a configurable fallback.
- **Deployment**: Telegram only, Discord only, or both; multi-architecture images support `linux/amd64` and `linux/arm64`.

## How it works

```text
Telegram → local Bot API ─┐
                          ├→ shared ingestion → Immich
Discord → Gateway ────────┘
```

Enabled adapters run in one process and serialize imports. On either platform, `/status` shows the caller's five latest imports on that platform and remains responsive during an import. In Telegram, query it in a private chat with the bot. Status history is kept in memory and cleared on restart. Temporary network and selected service failures are retried up to three attempts; other failures include guidance. Imports and manual retries process each file again, and Immich reuses assets with identical contents. Discord-only deployments do not need the Telegram Bot API service or Telegram credentials.

## Choose a deployment

| Mode | `ENABLED_PLATFORMS` | Compose command |
| --- | --- | --- |
| Telegram only (default) | `telegram` | `docker compose up -d` |
| Discord only | `discord` | `docker compose -f docker-compose.discord.yml up -d` |
| Both | `telegram,discord` | `docker compose up -d` |

The quick start and configuration table below describe the default Telegram deployment. For Discord or both platforms, use the [deployment guide](docs/discord-deployment.md), including its application installation and configuration steps. Download the appropriate Compose file and `.env.example` before starting.

## Telegram quick start

You need a working Immich instance and Docker installed.

```bash
mkdir immich-chat-importer && cd immich-chat-importer

curl -O https://raw.githubusercontent.com/myraxion/immich-chat-importer/main/docker-compose.yml
curl -o .env https://raw.githubusercontent.com/myraxion/immich-chat-importer/main/.env.example

# Fill in the 6 required values (see "Detailed setup" below)
${EDITOR:-nano} .env

docker compose up -d
```

That's it. Send `/start` to your bot in Telegram, then forward a photo.

## Telegram detailed setup

### 1. Create a Telegram bot

1. Open [@BotFather](https://t.me/BotFather), send `/newbot`, follow prompts.
2. Save the **HTTP API token** it gives you → goes into `TELEGRAM_BOT_TOKEN`.
3. Optional but recommended: `/setprivacy` → **Disable**. Lets the bot read forwarded messages in groups (irrelevant if you only DM the bot).

### 2. Get `api_id` / `api_hash`

The bundled local Bot API server needs Telegram application credentials to authenticate with the Telegram cloud. They are **not the bot token** — they identify the app, not the bot.

1. Go to <https://my.telegram.org/apps> and log in with your phone number.
2. Create a new application (any title / short name).
3. Copy `api_id` (a number) → `TELEGRAM_API_ID`.
4. Copy `api_hash` (a long hex string) → `TELEGRAM_API_HASH`.

### 3. Get an Immich API key

1. In Immich, click your avatar → **Account Settings** → **API Keys** → **New API Key**.
2. Give it a name like `telegram-bot`, copy the value → `IMMICH_API_KEY`.

### 4. Find your Immich URL

`IMMICH_URL` must end in `/api`.

- If you run the bot on the **same Docker host** as Immich and they share a network: `http://immich-server:2283/api` (replace `immich-server` with your Immich container name).
- If you reach Immich via a reverse proxy: `https://photos.example.com/api`.

If you run the bot in a separate Compose project, also attach it to Immich's network:

```yaml
# add to docker-compose.yml under immich-chat-importer:
networks: [immich, default]
networks:
  immich:
    external: true
    name: immich_default      # adjust to your Immich network name
```

### 5. Find your Telegram user ID

Message [@userinfobot](https://t.me/userinfobot) and copy the number it replies with → `TELEGRAM_ALLOWED_USER_IDS`.

Multiple users? Comma-separated: `TELEGRAM_ALLOWED_USER_IDS=11111111,22222222`.

### 6. Start

```bash
docker compose up -d
docker compose logs -f immich-chat-importer
```

On a clean start you should see something like:

```
INFO immich_tg_bot.bot: Using Immich album 'Telegram Inbox' (id=...)
INFO immich_tg_bot.bot: Bot starting (allowed users: [...], album: Telegram Inbox, immich: ...)
```

Send `/start` to your bot. Forward a photo. Watch it appear in Immich within a few seconds.

## Telegram configuration

**Breaking change:** Telegram-specific environment variables now use the `TELEGRAM_` prefix. Rename the old variables in existing `.env` files using the names in the table below; old names are not read.

`BOT_TOKEN` → `TELEGRAM_BOT_TOKEN`; `ALLOWED_USER_IDS` → `TELEGRAM_ALLOWED_USER_IDS`; `ALBUM_NAME` → `TELEGRAM_ALBUM_NAME`; `ALBUM_NAME_TEMPLATE` → `TELEGRAM_ALBUM_NAME_TEMPLATE`; `MEDIA_NAME_TEMPLATE` → `TELEGRAM_MEDIA_NAME_TEMPLATE`; `DOCUMENT_NAME_TEMPLATE` → `TELEGRAM_DOCUMENT_NAME_TEMPLATE`; `TG_FILES_DIR` → `TELEGRAM_FILES_DIR`; `TG_API_BASE` → `TELEGRAM_API_BASE`.

All settings are read from `.env`. Telegram-specific required values apply only when Telegram is enabled; see the [deployment guide](docs/discord-deployment.md) for Discord settings.

| Variable | Required | Default | Description |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | ✅ | — | Telegram bot token from BotFather. |
| `TELEGRAM_API_ID` | ✅ | — | Numeric app id from my.telegram.org. |
| `TELEGRAM_API_HASH` | ✅ | — | App hash from my.telegram.org. |
| `IMMICH_URL` | ✅ | — | Immich base URL ending in `/api`. |
| `IMMICH_API_KEY` | ✅ | — | API key from Immich account settings. |
| `TELEGRAM_ALLOWED_USER_IDS` | ✅ | — | Comma-separated whitelist of Telegram user IDs. |
| `TELEGRAM_ALBUM_NAME` |  | `Telegram Inbox` | Default fallback album. Empty = library only. |
| `TZ` |  | `UTC` | Timezone for filename and album dates (e.g. `Asia/Shanghai`). |
| `DEFAULT_LANGUAGE` |  | `en` | Default fallback reply language (`en`, `zh`, `ja`, `ru`). |
| `TELEGRAM_MEDIA_NAME_TEMPLATE` |  | `{source}_{message_id}_{index}` | Dynamic naming template for photos, videos, animations, and audio. |
| `TELEGRAM_DOCUMENT_NAME_TEMPLATE` |  | `{original_name}` | Dynamic naming template for document files. |
| `TELEGRAM_ALBUM_NAME_TEMPLATE` |  | *(empty)* | Dynamic album template (e.g. `{source}`). Falls back to `TELEGRAM_ALBUM_NAME`. |
| `MAX_ARCHIVE_MB` |  | `2000` | Hard limit for incoming archive size (MB). |
| `MAX_ARCHIVE_FILES` |  | `1000` | Maximum media entries per archive; archives exceeding it are rejected before upload. |
| `LOG_LEVEL` |  | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR`. |
| `DATA_DIR` |  | `/data` | Inside-container directory for temporary Discord downloads. |
| `TELEGRAM_FILES_DIR` |  | `/var/lib/telegram-bot-api` | Inside-container path of the shared local-Bot-API volume. |
| `TELEGRAM_API_BASE` |  | `http://telegram-bot-api:8081` | URL of the local Bot API server. |


The bottom three rarely need to change — they match the default `docker-compose.yml`.

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

## Telegram limits & gotchas

- **Telegram caps single files at 2 GB** even with the local Bot API server. Files larger than that need MTProto (userbot) and are out of scope here.
- **Photos sent as Picture lose EXIF and are recompressed by Telegram.** The bot still uploads them, but timestamps will use the message date and not the original capture date. Send as **Document/File** to preserve everything.
- **First start of `telegram-bot-api` initialises a per-bot directory** and takes ~10–30 seconds. The bot may log a few connection retries during that window; it will settle.
- **`tg-files` named volume can grow** since the local Bot API server keeps each downloaded file until you call `deleteFile`. The bot does not currently delete them; safe to `docker compose down -v` periodically if you don't need history.
- **Compose network**: by default the `immich-chat-importer` service can reach `telegram-bot-api` (same Compose project network) but **not your Immich instance** unless they share a network. See step 4 above.

## Updating

For an existing `immich-telegram-bot` deployment, stop the old Compose stack before starting the renamed service to avoid container conflicts. The old `state.sqlite` is no longer read or modified; existing status history is unavailable after upgrading. The `immich-telegram-bot` CLI remains available as an alias. The new image must be published before pulling it.

```bash
docker compose pull
docker compose up -d
```

## Uninstalling

```bash
docker compose down -v   # also drops the tg-files volume
rm -rf data/
```

The Immich library is untouched — uploaded assets stay there.

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
