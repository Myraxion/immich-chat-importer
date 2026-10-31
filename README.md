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
- **Discord**: import supported photo, video, and archive attachments from bot DMs or a user-installed message command. Menu replies are private; `/status` shows your five latest imports.
- **Archives**: ZIP, RAR, 7z, and tar variants are unpacked server-side. Media in ordinary subdirectories is included; nested archives are not expanded. Archives exceeding the configured media count are rejected before their entries are uploaded.
- **Shared ingestion**: reuse identical content across platforms, add assets to the target album, and retain successful imports when another item fails. Failed album associations can be retried.
- **Naming and dates**: configure filenames and albums separately for each platform; photo timestamps use EXIF when available and otherwise the source message time.
- **Access and language**: separate platform user-ID whitelists and replies in English, Chinese, Japanese, or Russian, with a configurable fallback.
- **Deployment**: Telegram only, Discord only, or both; multi-architecture images support `linux/amd64` and `linux/arm64`.

## How it works

```text
Telegram → local Bot API ─┐
                          ├→ shared ingestion + SQLite state → Immich
Discord → Gateway ────────┘
```

Enabled adapters run in one process and serialize imports. Discord status queries remain responsive during an import. Discord-only deployments do not need the Telegram Bot API service or Telegram credentials.

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
2. Save the **HTTP API token** it gives you → goes into `BOT_TOKEN`.
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

Message [@userinfobot](https://t.me/userinfobot) and copy the number it replies with → `ALLOWED_USER_IDS`.

Multiple users? Comma-separated: `ALLOWED_USER_IDS=11111111,22222222`.

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

All settings are read from `.env`. Telegram-specific required values apply only when Telegram is enabled; see the [deployment guide](docs/discord-deployment.md) for Discord settings.

| Variable | Required | Default | Description |
|---|---|---|---|
| `BOT_TOKEN` | ✅ | — | Telegram bot token from BotFather. |
| `TELEGRAM_API_ID` | ✅ | — | Numeric app id from my.telegram.org. |
| `TELEGRAM_API_HASH` | ✅ | — | App hash from my.telegram.org. |
| `IMMICH_URL` | ✅ | — | Immich base URL ending in `/api`. |
| `IMMICH_API_KEY` | ✅ | — | API key from Immich account settings. |
| `ALLOWED_USER_IDS` | ✅ | — | Comma-separated whitelist of Telegram user IDs. |
| `ALBUM_NAME` |  | `Telegram Inbox` | Default fallback album. Empty = library only. |
| `TZ` |  | `UTC` | Timezone for filename and album dates (e.g. `Asia/Shanghai`). |
| `DEFAULT_LANGUAGE` |  | `en` | Default fallback reply language (`en`, `zh`, `ja`, `ru`). |
| `MEDIA_NAME_TEMPLATE` |  | `{source}_{message_id}_{index}` | Dynamic naming template for photos, videos, animations, and audio. |
| `DOCUMENT_NAME_TEMPLATE` |  | `{original_name}` | Dynamic naming template for document files. |
| `ALBUM_NAME_TEMPLATE` |  | *(empty)* | Dynamic album template (e.g. `{source}`). Falls back to `ALBUM_NAME`. |
| `MAX_ARCHIVE_MB` |  | `2000` | Hard limit for incoming archive size (MB). |
| `MAX_ARCHIVE_FILES` |  | `1000` | Maximum media entries per archive; archives exceeding it are rejected before upload. |
| `LOG_LEVEL` |  | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR`. |
| `DATA_DIR` |  | `/data` | Inside-container path for `state.sqlite`. |
| `TG_FILES_DIR` |  | `/var/lib/telegram-bot-api` | Inside-container path of the shared local-Bot-API volume. |
| `TG_API_BASE` |  | `http://telegram-bot-api:8081` | URL of the local Bot API server. |


The bottom three rarely need to change — they match the default `docker-compose.yml`.

## Telegram limits & gotchas

- **Telegram caps single files at 2 GB** even with the local Bot API server. Files larger than that need MTProto (userbot) and are out of scope here.
- **Photos sent as Picture lose EXIF and are recompressed by Telegram.** The bot still uploads them, but timestamps will use the message date and not the original capture date. Send as **Document/File** to preserve everything.
- **First start of `telegram-bot-api` initialises a per-bot directory** and takes ~10–30 seconds. The bot may log a few connection retries during that window; it will settle.
- **`tg-files` named volume can grow** since the local Bot API server keeps each downloaded file until you call `deleteFile`. The bot does not currently delete them; safe to `docker compose down -v` periodically if you don't need history.
- **Compose network**: by default the `immich-chat-importer` service can reach `telegram-bot-api` (same Compose project network) but **not your Immich instance** unless they share a network. See step 4 above.

## Updating

For an existing `immich-telegram-bot` deployment, stop the old Compose stack before starting the renamed service to avoid container conflicts. Keep and back up `./data` to preserve ingestion state. The `immich-telegram-bot` CLI remains available as an alias. The new image must be published before pulling it.

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
