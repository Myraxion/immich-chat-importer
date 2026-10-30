# immich-telegram-bot

> Self-hosted Telegram bot that uploads photos, videos and archives forwarded to it straight into your [Immich](https://immich.app) library.

English | [简体中文](README_zh.md)

[![Release](https://img.shields.io/github/v/release/myraxion/immich-telegram-bot?display_name=tag&sort=semver)](https://github.com/myraxion/immich-telegram-bot/releases)
[![Docker image](https://img.shields.io/badge/ghcr.io-immich--telegram--bot-blue?logo=docker)](https://github.com/myraxion/immich-telegram-bot/pkgs/container/immich-telegram-bot)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-orange.svg)](LICENSE)
[![CI](https://github.com/myraxion/immich-telegram-bot/actions/workflows/ci.yml/badge.svg)](https://github.com/myraxion/immich-telegram-bot/actions/workflows/ci.yml)

Someone shares a photo with you over Telegram and you want it in your photo library? Forward it to this bot — it will upload it for you, deduplicate, and (optionally) put it into a dedicated album.

## Features

- 📸 **Photos** (compressed and as documents), 🎥 **videos**, **animations**, **voice / audio / video notes**, and **arbitrary documents**.
- 📦 **Archives**: `zip`, `rar`, `7z`, `tar`, `tar.gz`, `tar.bz2`, `tar.xz` — unpacked server-side, media files extracted recursively.
- 🖼️ **Media groups** (albums up to 10 files) — processed together so they land in Immich as a coherent group.
- 🔁 **Deduplication** via SHA-1: forwarding the same file twice is safe and free.
- 📅 **EXIF-aware timestamps**: original capture date is preserved when present (otherwise falls back to the Telegram message date).
- 🔒 **Whitelist auth**: only allowed Telegram user IDs can talk to the bot.
- 🌐 **Multi-language support**: automatic replies matching sender's Telegram language (English, Chinese, Japanese, Russian) with configurable fallback.
- 📂 **Optional album**: every uploaded asset goes into the album you name.
- 🚀 **Large files up to 2 GB** via a bundled [local Bot API server](https://github.com/tdlib/telegram-bot-api) — the stock cloud API caps downloads at 20 MB.
- 🐳 **Two-container Compose stack**, multi-arch image (`linux/amd64`, `linux/arm64`).

## How it works

```
   Telegram client                Telegram cloud
        │                                │
        │  (forward / send media)        │
        ▼                                │
 ┌────────────────────┐    long-polling  │
 │ local Bot API      │ ◄────────────────┘
 │ (tdlib container)  │  ── writes file to a shared volume
 └─────────┬──────────┘
           │ file appears at /var/lib/telegram-bot-api/...
           ▼
 ┌─────────────────────────────┐   POST /api/assets  ┌──────────────┐
 │ immich-telegram-bot         │ ──────────────────► │ Immich server│
 │   • whitelist auth          │   sha1 dedup        │              │
 │   • exif date extraction    │   optional album    │              │
 │   • archive unpacking       │                     └──────────────┘
 │   • sqlite state            │
 └─────────────────────────────┘
```

## Quick start

You need a working Immich instance and Docker installed.

```bash
mkdir immich-telegram-bot && cd immich-telegram-bot

curl -O https://raw.githubusercontent.com/myraxion/immich-telegram-bot/main/docker-compose.yml
curl -o .env https://raw.githubusercontent.com/myraxion/immich-telegram-bot/main/.env.example

# Fill in the 6 required values (see "Detailed setup" below)
${EDITOR:-nano} .env

docker compose up -d
```

That's it. Send `/start` to your bot in Telegram, then forward a photo.

## Detailed setup

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
# add to docker-compose.yml under immich-telegram-bot:
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
docker compose logs -f immich-telegram-bot
```

On a clean start you should see something like:

```
INFO immich_tg_bot.bot: Using Immich album 'Telegram Inbox' (id=...)
INFO immich_tg_bot.bot: Bot starting (allowed users: [...], album: Telegram Inbox, immich: ...)
```

Send `/start` to your bot. Forward a photo. Watch it appear in Immich within a few seconds.

## Configuration

All settings are read from `.env`.

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
| `MAX_ARCHIVE_FILES` |  | `1000` | Hard limit for files extracted from one archive. |
| `LOG_LEVEL` |  | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR`. |
| `DATA_DIR` |  | `/data` | Inside-container path for `state.sqlite`. |
| `TG_FILES_DIR` |  | `/var/lib/telegram-bot-api` | Inside-container path of the shared local-Bot-API volume. |
| `TG_API_BASE` |  | `http://telegram-bot-api:8081` | URL of the local Bot API server. |


The bottom three rarely need to change — they match the default `docker-compose.yml`.

## Limits & gotchas

- **Telegram caps single files at 2 GB** even with the local Bot API server. Files larger than that need MTProto (userbot) and are out of scope here.
- **Photos sent as Picture lose EXIF and are recompressed by Telegram.** The bot still uploads them, but timestamps will use the message date and not the original capture date. Send as **Document/File** to preserve everything.
- **First start of `telegram-bot-api` initialises a per-bot directory** and takes ~10–30 seconds. The bot may log a few connection retries during that window; it will settle.
- **`tg-files` named volume can grow** since the local Bot API server keeps each downloaded file until you call `deleteFile`. The bot does not currently delete them; safe to `docker compose down -v` periodically if you don't need history.
- **Compose network**: by default the `immich-telegram-bot` service can reach `telegram-bot-api` (same Compose project network) but **not your Immich instance** unless they share a network. See step 4 above.

## Updating

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
git clone https://github.com/myraxion/immich-telegram-bot.git
cd immich-telegram-bot

# Using uv (recommended):
uv sync --all-extras --dev

# Or using standard venv + pip:
# python -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"

# Build a local image and run with compose:
docker build -t local/immich-telegram-bot .
# edit docker-compose.yml: image: local/immich-telegram-bot
docker compose up
```

CI runs `ruff` lint/format, `pytest`, and a Docker build smoke-test on every PR.
Releases are cut by pushing a `vX.Y.Z` tag — that triggers a multi-arch build pushed to `ghcr.io/myraxion/immich-telegram-bot`.

## License

[AGPL-3.0-only](LICENSE) — same family as Immich itself. If you run a modified version as a network service, you must offer your changes back under the same license.
# Discord DM import

To run Discord alone, install the project and set `ENABLED_PLATFORMS=discord`,
`DISCORD_TOKEN`, `DISCORD_ALLOWED_USER_IDS`, `IMMICH_URL` and `IMMICH_API_KEY`.
Set `DISCORD_ALBUM_NAME` to change the default `Discord Inbox` album and
`DISCORD_MAX_ATTACHMENT_MB` to change the per-file limit (default 2000 MiB).
The existing `DEFAULT_LANGUAGE`, `DATA_DIR`, and `CLEANUP_LOCAL_FILES` settings apply.
Telegram credentials and the local Telegram Bot API server are unnecessary in this mode.

Create a Discord bot, install it to an account or server where you can DM it, and
run `immich-telegram-bot`. Send a photo and a video as attachments in a direct
message from a whitelisted account. The reply reports the outcome; check the
Discord Inbox album in Immich for the imported media. Archives, status queries
and combined container deployment are subsequent work.

Set `DISCORD_FILENAME_TEMPLATE` (default `{original_name}`) and
`DISCORD_ALBUM_NAME_TEMPLATE` (default empty, falling back to `DISCORD_ALBUM_NAME`)
to use the same naming variables and `TZ` as Telegram. For a server message,
`{source}` is the server and channel names, each falling back to its ID. In
private conversations it is the original author's display name or username.
`{sender}` is always the original author. Archive entries retain their filenames.

### Personal installation acceptance checklist

These checks require real Discord accounts and have not yet been performed:

1. In the Developer Portal enable user installation and the `applications.commands`
   scope; install the application to a whitelisted account. Start the bot and allow
   global commands to synchronize.
2. In a server the bot has not joined, use Apps → Save to Immich on another
   author's photo/video message. Confirm every supported attachment arrives, the
   source and sender templates identify the original message, and only the caller
   sees the result. Repeat where external apps cannot post public responses.
3. Repeat in the bot DM, another person's DM, and a group DM. Check that the
   private result appears only to the caller, and that saving a bot DM already
   imported automatically does not upload a second copy.
4. Repeat with a non-whitelisted caller, missing server/channel names, Chinese
   locale, and configured filename/album templates. Confirm denial happens before
   download, ID fallbacks work, and the result is localized.

Results after the interaction response window and restart interruption handling
are planned for the long-running task issue.

