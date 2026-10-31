# immich-chat-importer

> 自托管机器人，将 Telegram 和 Discord 中的媒体导入你的 [Immich](https://immich.app) 相册库。

[English](README.md) | 简体中文

支持在同一进程中运行 Telegram、Discord 或两者。Discord 配置及使用方法请参阅 [Discord 与双平台部署指南](docs/discord-deployment.md)。

[![Release](https://img.shields.io/github/v/release/myraxion/immich-chat-importer?display_name=tag&sort=semver)](https://github.com/myraxion/immich-chat-importer/releases)
[![Docker image](https://img.shields.io/badge/ghcr.io-immich--chat--importer-blue?logo=docker)](https://github.com/myraxion/immich-chat-importer/pkgs/container/immich-chat-importer)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-orange.svg)](LICENSE)
[![CI](https://github.com/myraxion/immich-chat-importer/actions/workflows/ci.yml/badge.svg)](https://github.com/myraxion/immich-chat-importer/actions/workflows/ci.yml)

将媒体转发给 Telegram 机器人，向 Discord 机器人私信发送附件，或通过 Discord 消息的 **Apps → 保存到 Immich** 导入。两平台共用一个 Immich 账号、精确内容去重与相册归档能力。

## 特性

- **Telegram**：导入照片、视频、动图、音频、文档、媒体组及支持的压缩包；内置本地 Bot API 服务支持大文件下载。
- **Discord**：通过机器人私信或个人安装的消息命令导入支持的照片、视频和压缩包附件。菜单回复仅调用者可见；`/status` 可查询最近五次导入。
- **压缩包**：在服务端解压 ZIP、RAR、7z 和 tar 系列，包含普通子目录中的媒体，但不递归解压嵌套压缩包。媒体数量超限时，在上传条目前拒绝整个包。
- **共享导入**：跨平台复用完全相同的内容并加入目标相册；单项失败不撤销其他成功结果，相册关联失败可手动重试。
- **命名与日期**：两平台可分别配置文件名与相册；照片优先使用 EXIF 拍摄时间，否则使用来源消息时间。
- **鉴权与语言**：两平台使用独立用户 ID 白名单；支持英语、中文、日语和俄语回复，可配置回退语言。
- **部署**：支持仅 Telegram、仅 Discord 或双平台；镜像支持 `linux/amd64` 和 `linux/arm64`。

## 工作原理

```text
Telegram → 本地 Bot API ─┐
                         ├→ 共享导入流程和 SQLite 状态 → Immich
Discord → Gateway ───────┘
```

启用的平台在同一进程中运行，导入批次串行执行；导入期间仍可查询 Discord 状态。仅 Discord 部署不需要 Telegram Bot API 服务或 Telegram 凭证。

## 选择部署模式

| 模式 | `ENABLED_PLATFORMS` | Compose 命令 |
| --- | --- | --- |
| 仅 Telegram（默认） | `telegram` | `docker compose up -d` |
| 仅 Discord | `discord` | `docker compose -f docker-compose.discord.yml up -d` |
| 双平台 | `telegram,discord` | `docker compose up -d` |

下方快速开始和配置表针对默认的 Telegram 部署。Discord 或双平台部署请参阅[部署指南](docs/discord-deployment.md)，按照其中的步骤安装应用并配置；启动前需下载对应的 Compose 文件和 `.env.example`。

## Telegram 快速开始

你需要一个已正常运行的 Immich 实例并安装好 Docker。

```bash
mkdir immich-chat-importer && cd immich-chat-importer

curl -O https://raw.githubusercontent.com/myraxion/immich-chat-importer/main/docker-compose.yml
curl -o .env https://raw.githubusercontent.com/myraxion/immich-chat-importer/main/.env.example

# 填入 6 项必填配置（详见下文“详细配置步骤”）
${EDITOR:-nano} .env

docker compose up -d
```

大功告成！在 Telegram 中向你的机器人发送 `/start`，然后转发一张照片即可体验。

## Telegram 详细配置步骤

### 1. 创建 Telegram 机器人

1. 打开 [@BotFather](https://t.me/BotFather)，发送 `/newbot`，按提示完成创建。
2. 保存它提供的 **HTTP API token** → 填入 `TELEGRAM_BOT_TOKEN`。
3. （可选但推荐）：发送 `/setprivacy` → 选择 **Disable**。允许机器人在群组中读取转发消息（如果仅私聊机器人则无需配置）。

### 2. 获取 `api_id` / `api_hash`

内置的本地 Bot API 服务端需要 Telegram 应用凭证来与 Telegram 云端通信。这**不是机器人 Token** —— 它们用于标识应用程序，而非机器人本身。

1. 访问 <https://my.telegram.org/apps> 并使用你的手机号登录。
2. 创建一个新应用（标题与短名称随意填写）。
3. 复制 `api_id`（数字）→ 填入 `TELEGRAM_API_ID`。
4. 复制 `api_hash`（一串较长的十六进制字符串）→ 填入 `TELEGRAM_API_HASH`。

### 3. 获取 Immich API Key

1. 在 Immich 中，点击头像 → **Account Settings（账户设置）** → **API Keys** → **New API Key**。
2. 输入名称（例如 `telegram-bot`），复制生成的密钥 → 填入 `IMMICH_API_KEY`。

### 4. 确认 Immich 地址

`IMMICH_URL` 必须以 `/api` 结尾。

- 如果机器人与 Immich 运行在**同一台 Docker 宿主机**且共享网络：`http://immich-server:2283/api`（请将 `immich-server` 替换为你 Immich 容器的名称）。
- 如果你通过反向代理访问 Immich：`https://photos.example.com/api`。

如果你在独立的 Compose 项目中运行机器人，还需要将其加入 Immich 的网络：

```yaml
# 在 docker-compose.yml 的 immich-chat-importer 服务下添加：
networks: [immich, default]
networks:
  immich:
    external: true
    name: immich_default      # 请调整为你 Immich 的实际网络名称
```

### 5. 获取你的 Telegram 用户 ID

给 [@userinfobot](https://t.me/userinfobot) 发送消息，复制它回复的数字 ID → 填入 `TELEGRAM_ALLOWED_USER_IDS`。

需要允许多个用户？用英文逗号分隔：`TELEGRAM_ALLOWED_USER_IDS=11111111,22222222`。

### 6. 启动服务

```bash
docker compose up -d
docker compose logs -f immich-chat-importer
```

正常启动时，日志输出大致如下：

```
INFO immich_tg_bot.bot: Using Immich album 'Telegram Inbox' (id=...)
INFO immich_tg_bot.bot: Bot starting (allowed users: [...], album: Telegram Inbox, immich: ...)
```

在 Telegram 中向你的机器人发送 `/start`。转发一张照片，几秒钟内它就会出现在 Immich 中。

## Telegram 配置项说明

**不兼容变更：** Telegram 专属环境变量现统一使用 `TELEGRAM_` 前缀。升级时请按下表修改现有 `.env`，旧名称不再读取。

`BOT_TOKEN` → `TELEGRAM_BOT_TOKEN`; `ALLOWED_USER_IDS` → `TELEGRAM_ALLOWED_USER_IDS`; `ALBUM_NAME` → `TELEGRAM_ALBUM_NAME`; `ALBUM_NAME_TEMPLATE` → `TELEGRAM_ALBUM_NAME_TEMPLATE`; `MEDIA_NAME_TEMPLATE` → `TELEGRAM_MEDIA_NAME_TEMPLATE`; `DOCUMENT_NAME_TEMPLATE` → `TELEGRAM_DOCUMENT_NAME_TEMPLATE`; `TG_FILES_DIR` → `TELEGRAM_FILES_DIR`; `TG_API_BASE` → `TELEGRAM_API_BASE`.

所有配置均从 `.env` 读取。Telegram 专属必填项仅在启用 Telegram 时适用；Discord 配置请参阅[部署指南](docs/discord-deployment.md)。

| 环境变量 | 必填 | 默认值 | 说明 |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | ✅ | — | 来自 BotFather 的 Telegram 机器人 Token。 |
| `TELEGRAM_API_ID` | ✅ | — | 来自 my.telegram.org 的数字应用 ID。 |
| `TELEGRAM_API_HASH` | ✅ | — | 来自 my.telegram.org 的应用 Hash。 |
| `IMMICH_URL` | ✅ | — | 以 `/api` 结尾的 Immich Base URL。 |
| `IMMICH_API_KEY` | ✅ | — | 在 Immich 账户设置中生成的 API Key。 |
| `TELEGRAM_ALLOWED_USER_IDS` | ✅ | — | 英文逗号分隔的 Telegram 用户 ID 白名单。 |
| `TELEGRAM_ALBUM_NAME` |  | `Telegram Inbox` | 默认回退相册名称。留空表示仅导入图库，不加入相册。 |
| `TZ` |  | `UTC` | 文件名及相册日期的时区（例如 `Asia/Shanghai`）。 |
| `DEFAULT_LANGUAGE` |  | `en` | 默认回退回复语言（`en`、`zh`、`ja`、`ru`）。 |
| `TELEGRAM_MEDIA_NAME_TEMPLATE` |  | `{source}_{message_id}_{index}` | 照片、视频、动图及音频的动态命名模板。 |
| `TELEGRAM_DOCUMENT_NAME_TEMPLATE` |  | `{original_name}` | 文档文件的动态命名模板。 |
| `TELEGRAM_ALBUM_NAME_TEMPLATE` |  | *(留空)* | 动态相册模板（例如 `{source}`）。若未命中则回退至 `TELEGRAM_ALBUM_NAME`。 |
| `MAX_ARCHIVE_MB` |  | `2000` | 允许传入的压缩包大小上限（MB）。 |
| `MAX_ARCHIVE_FILES` |  | `1000` | 单个压缩包的媒体条目数量上限；超限时上传前拒绝整个包。 |
| `LOG_LEVEL` |  | `INFO` | 日志级别：`DEBUG` / `INFO` / `WARNING` / `ERROR`。 |
| `DATA_DIR` |  | `/data` | 容器内部 `state.sqlite` 的存储路径。 |
| `TELEGRAM_FILES_DIR` |  | `/var/lib/telegram-bot-api` | 本地 Bot API 共享卷在容器内的挂载路径。 |
| `TELEGRAM_API_BASE` |  | `http://telegram-bot-api:8081` | 本地 Bot API 服务的访问地址。 |

最后三项通常保持默认即可 —— 它们与默认的 `docker-compose.yml` 保持一致。

## Discord 命名模板

`.env.example` 将 `DISCORD_FILENAME_TEMPLATE` 设置为 `{source}_{sender}_{message_id}_{index}`。如果未设置该变量，程序默认使用 `{original_name}`，保留附件的原始文件名。模板生成不含扩展名的文件名主体，程序会自动追加原扩展名。压缩包中解出的媒体保留各自的条目文件名，不使用此模板。

`DISCORD_ALBUM_NAME_TEMPLATE` 使用相同的变量选择相册。该模板默认为空，使用 `DISCORD_ALBUM_NAME`（默认 `Discord Inbox`）；模板渲染失败或结果为空时，也会回退到该配置。

| 变量 | Discord 中的值 |
|---|---|
| `{original_name}` | 不含扩展名的原附件文件名。 |
| `{sender}` | 原消息作者的显示名称，缺失时依次使用用户名或用户 ID。 |
| `{sender_id}`、`{source_id}` | 原消息作者的用户 ID。 |
| `{source_username}`、`{username}` | 原消息作者的用户名，缺失时使用用户 ID。 |
| `{source}`、`{chat_title}` | 服务器消息为 `服务器名_频道名`；私人会话中为作者显示名称。 |
| `{chat_id}` | 原消息所在频道的 ID。 |
| `{message_id}`、`{msg_id}` | 原消息 ID。 |
| `{index}` | 附件在消息中的序号，从 1 开始。 |
| `{date}`、`{msg_date}` | 原消息时间，使用 `TZ` 配置的时区（默认 `UTC`）。 |
| `{exif_date}` | 附件的 EXIF 时间，使用 `TZ` 时区；无法读取时为空。 |
| `{media_type}` | 按文件名推断的 MIME 类型为视频时是 `video`，否则为 `photo`。 |
| `{file_unique_id}` | Discord 附件 ID。 |
| `{caption}` | 原消息文本。 |

`{forward_date}`、`{media_group_id}`、`{forward_source}`、`{forward_channel}`、`{forward_author}`、`{forward_source_id}` 和 `{forward_msg_id}` 在 Discord 导入中为空。未知变量也会渲染为空。日期变量支持 Python 日期格式，例如：

```env
TZ=Asia/Shanghai
DISCORD_FILENAME_TEMPLATE={sender}_{date:%Y%m%d}_{original_name}
DISCORD_ALBUM_NAME_TEMPLATE={source}_{date:%Y-%m}
```

例如 Alice 在 2026 年 10 月 31 日发送附件 `photo.jpg`，生成的文件名为 `Alice_20261031_photo.jpg`。文件名主体和模板生成的相册名中，`/`、`\`、`:`、`*`、`?`、`"`、`<`、`>`、`|`、换行和制表符会替换为下划线，连续下划线会合并，首尾的空格、下划线和点会被移除，长度最多为 200 个字符。文件名模板渲染失败或结果为空时，先回退到 `{original_name}`，再回退到 `{source}_{message_id}_{index}`（必要时使用 `file_{index}`）。

## Telegram 限制与注意事项

- **单文件大小限制为 2 GB**：受限于 Telegram 本身，即使使用本地 Bot API 服务端也存在此上限。超过该大小的文件需要走 MTProto（userbot 协议），不在本项目的支持范围内。
- **直接以“图片”发送的照片会丢失 EXIF 并被 Telegram 重新压缩**：机器人依然会正常上传，但时间戳将使用 Telegram 消息时间，而非原始拍摄日期。如果需要完整保留元数据，请以**“文件/文档”**（Document/File）形式发送。
- **首次启动 `telegram-bot-api` 时需要初始化机器人专属目录**，耗时约 10–30 秒。在此期间机器人可能会打印几次连接重试日志，之后会自动恢复正常。
- **`tg-files` 数据卷占用可能会持续增长**：本地 Bot API 服务端会保留下载的文件直到调用 `deleteFile`。目前机器人暂不自动删除它们；如果不需保留历史缓存，可以定期执行 `docker compose down -v` 清理。
- **Compose 网络**：默认情况下 `immich-chat-importer` 服务可以访问 `telegram-bot-api`（同一 Compose 网络），但**无法访问你的 Immich 实例**，除非它们加入同一网络。请参考上文第 4 步。

## 更新

从原 `immich-telegram-bot` 部署升级时，先停止旧 Compose 服务，再启动改名后的服务，避免容器冲突。保留并备份 `./data` 以保存导入状态。旧的 `immich-telegram-bot` 命令仍可作为别名使用；新镜像发布后才能拉取。

```bash
docker compose pull
docker compose up -d
```

## 卸载

```bash
docker compose down -v   # 同时会删除 tg-files 数据卷
rm -rf data/
```

Immich 中的照片库不受任何影响 —— 已上传的资源依然保留在 Immich 中。

## 本地开发

```bash
git clone https://github.com/myraxion/immich-chat-importer.git
cd immich-chat-importer

# 使用 uv（推荐）：
uv sync --all-extras --dev

# 或使用标准 venv + pip：
# python -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"

# 构建本地镜像并使用 Compose 运行：
docker build -t local/immich-chat-importer .
# 修改 docker-compose.yml 中的镜像为：image: local/immich-chat-importer
docker compose up
```

每次 PR 时 CI 会自动运行 `ruff` 代码检查/格式化、`pytest` 单元测试以及 Docker 构建冒烟测试。
发布新版本时，推送 `vX.Y.Z` 标签将自动触发多架构镜像构建并发布至 `ghcr.io/myraxion/immich-chat-importer`。

## 开源协议

[AGPL-3.0-only](LICENSE) —— 与 Immich 保持一致的开源协议。如果你将修改后的版本作为网络服务运行，必须以相同协议开源你的修改。
