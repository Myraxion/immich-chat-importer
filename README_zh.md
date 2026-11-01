# immich-chat-importer

> 自托管机器人，将 Telegram 和 Discord 中的媒体导入你的 [Immich](https://immich.app) 相册库。

[English](README.md) | 简体中文

将媒体转发给 Telegram 机器人，向 Discord 机器人私信发送附件或通过 Discord 消息的 **Apps → 保存到 Immich** 导入。两平台共用一个 Immich 账号、精确内容去重与相册归档能力。

[![Release](https://img.shields.io/github/v/release/myraxion/immich-chat-importer?display_name=tag&sort=semver)](https://github.com/myraxion/immich-chat-importer/releases)
[![Docker image](https://img.shields.io/badge/ghcr.io-immich--chat--importer-blue?logo=docker)](https://github.com/myraxion/immich-chat-importer/pkgs/container/immich-chat-importer)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-orange.svg)](LICENSE)

## 特性

- **Telegram**：导入照片、视频、动图、音频、文档、媒体组及支持的压缩包；内置本地 Bot API 服务支持大文件下载。
- **Discord**：通过机器人私信或个人安装的消息命令导入支持的照片、视频和压缩包附件。菜单回复仅调用者可见；`/status` 可查询本次启动后的最近五次导入。
- **压缩包**：在服务端解压 ZIP、RAR、7z 和 tar 系列，包含普通子目录中的媒体，但不递归解压嵌套压缩包。媒体数量超限时，在上传条目前拒绝整个包。
- **命名与日期**：两平台可分别配置文件名与相册；照片优先使用 EXIF 拍摄时间，否则使用来源消息时间。
- **鉴权**：两平台使用独立用户 ID 白名单。
- **语言**：支持英语、中文、日语和俄语回复
- **部署**：支持仅 Telegram、仅 Discord 或双平台；镜像支持 `linux/amd64` 和 `linux/arm64`。

## 工作原理

```text
Telegram → 本地 Bot API ─┐
                         ├→ 共享导入流程 → Immich
Discord → Gateway ───────┘
```

## 选择部署模式

| 模式 | `ENABLED_PLATFORMS` | 说明 |
| --- | --- | --- |
| 仅 Telegram（默认） | `telegram` | 仅启用 Telegram 导入机器人 |
| 仅 Discord | `discord` | 仅启用 Discord 导入机器人 |
| 双平台 | `telegram,discord` | 同时启用两平台机器人 |

本项目统一使用同一个 `docker-compose.yml` 部署，只需在 `.env` 中通过 `ENABLED_PLATFORMS` 配置启用的平台，并填写对应平台的必填环境变量即可。

## 快速开始

你需要一个已正常运行的 Immich 实例并安装好 Docker。

```bash
mkdir immich-chat-importer && cd immich-chat-importer

curl -O https://raw.githubusercontent.com/myraxion/immich-chat-importer/main/docker-compose.yml
curl -o .env https://raw.githubusercontent.com/myraxion/immich-chat-importer/main/.env.example

# 在 .env 中填入对应模式的配置（详见下文“详细配置步骤”）
${EDITOR:-nano} .env

docker compose up -d
```

启动完成后：

- **Telegram**：向机器人发送 `/start`，然后转发一张照片或文件即可体验。
- **Discord**：向机器人私信发送附件，或右键消息点击 **Apps → 保存到 Immich** 即可导入。

## 详细配置步骤

### 1. 通用配置（所有模式必填）

#### 获取 Immich API Key

1. 在 Immich 中，点击头像 → **Account Settings（账户设置）** → **API Keys** → **New API Key**。
2. 输入名称（例如 `chat-importer`），复制生成的密钥 → 填入 `IMMICH_API_KEY`。

#### 确认 Immich 地址与网络

`IMMICH_URL` 必须以 `/api` 结尾。

- 如果机器人与 Immich 运行在**同一台 Docker 宿主机**且共享网络：`http://immich-server:2283/api`（请将 `immich-server` 替换为你 Immich 容器的名称）。
- 如果你通过反向代理访问 Immich：`https://photos.example.com/api`。

如果机器人在独立的 Compose 项目中运行，还需要将其加入 Immich 的网络：

```yaml
# 在 docker-compose.yml 的 immich-chat-importer 服务下添加：
networks: [immich, default]
networks:
  immich:
    external: true
    name: immich_default      # 请调整为你 Immich 的实际网络名称
```

### 2. Telegram 配置（启用 Telegram 时）

#### 创建 Telegram 机器人

1. 打开 [@BotFather](https://t.me/BotFather)，发送 `/newbot`，按提示完成创建。
2. 保存它提供的 **HTTP API token** → 填入 `TELEGRAM_BOT_TOKEN`。
3. （可选但推荐）：发送 `/setprivacy` → 选择 **Disable**。允许机器人在群组中读取转发消息（如果仅私聊机器人则无需配置）。

#### 获取 `api_id` / `api_hash`

内置的本地 Bot API 服务端需要 Telegram 应用凭证来与 Telegram 云端通信。这**不是机器人 Token** —— 它们用于标识应用程序，而非机器人本身。

1. 访问 <https://my.telegram.org/apps> 并使用你的手机号登录。
2. 创建一个新应用（标题与短名称随意填写）。
3. 复制 `api_id`（数字）→ 填入 `TELEGRAM_API_ID`。
4. 复制 `api_hash`（一串较长的十六进制字符串）→ 填入 `TELEGRAM_API_HASH`。

#### 获取你的 Telegram 用户 ID

给 [@userinfobot](https://t.me/userinfobot) 发送消息，复制它回复的数字 ID → 填入 `TELEGRAM_ALLOWED_USER_IDS`。

需要允许多个用户？用英文逗号分隔：`TELEGRAM_ALLOWED_USER_IDS=11111111,22222222`。

### 3. Discord 配置（启用 Discord 时）

#### 创建 Discord 机器人应用

1. 打开 [Discord Developer Portal](https://discord.com/developers/applications)，点击 **New Application** 创建新应用。
2. 进入左侧 **Bot** 页面，点击 **Reset Token** 生成并复制 Token → 填入 `DISCORD_TOKEN`。
   > [!NOTE]
   > 应用通过 Discord Gateway 长连接工作，无需公网回调域名，也无需勾选特权的 Message Content Intent。机器人进程启动时会自动向 Discord 注册全局斜杠命令与上下文菜单。

#### 配置用户安装（User Install）并添加到账号

1. 进入左侧 **Installation** 页面：
   - 在 **Installation Contexts** 中勾选 **User Install**（支持在任何你有权限查看消息的地方使用上下文菜单导入）。
   - 在 **Default Install Settings** 的 **Scopes** 中添加 `applications.commands`（用于注册斜杠命令与消息上下文菜单）。
2. 使用页面生成的 **Install Link**（或进入 **OAuth2** → **URL Generator** 勾选 `applications.commands` 和 `bot`，选择 User Install）打开链接，将机器人应用安装到你的 Discord 个人账号。

#### 获取你的 Discord 用户 ID

1. 在 Discord 客户端中，打开 **设置** → **高级** → 开启 **开发者模式**。
2. 右键点击自己的头像或个人资料，选择 **复制用户 ID** → 填入 `DISCORD_ALLOWED_USER_IDS`。
3. 允许多个用户时使用英文逗号分隔：`DISCORD_ALLOWED_USER_IDS=111111111111111111,222222222222222222`。空白名单将不允许任何人操作。

### 4. 启动服务

```bash
docker compose up -d
docker compose logs -f immich-chat-importer
```

正常启动时，日志输出大致如下：

```log
INFO immich_chat_importer.adapters.telegram.bot: Using Immich album 'Telegram Inbox' (id=...)
INFO immich_chat_importer.adapters.telegram.bot: Bot starting (allowed users: [...], album: Telegram Inbox, immich: ...)
# 若启用了 Discord:
INFO immich_chat_importer.adapters.discord.bot: Discord bot starting (allowed users: [...], album: Discord Inbox, immich: ...)
```

### 5. 使用说明

- **Telegram**：
  - 向机器人发送 `/start`。
  - 直接转发照片、视频、动图、音频或文件给机器人，几秒钟内即可导入 Immich。
  - 私聊机器人发送 `/status` 可查询本次启动以来的最近 5 次导入状态。
- **Discord**：
  - **私信发送**：向机器人私聊发送照片、视频或压缩包附件。
  - **消息菜单导入**：在任意频道或私信中，右键（手机长按）包含媒体的消息 → **Apps** → 点击 **保存到 Immich**。导入结果仅调用者本人可见。
  - **状态查询**：在私信或频道中发送 `/status` 斜杠命令，查询本次启动以来本人最近 5 次导入的状态。
  - **重试机制**：遇到网络抖动等情况导致相册关联失败时，重新发送或再次点击菜单即可；Immich 会自动复用已有媒体文件，并补齐相册关联。

## 配置项说明

所有配置均从 `.env` 读取。特定平台的必填项仅在该平台启用时生效。

| 环境变量 | 必填 | 默认值 | 说明 |
|---|---|---|---|
| `IMMICH_URL` | ✅ | — | 以 `/api` 结尾的 Immich Base URL。 |
| `IMMICH_API_KEY` | ✅ | — | 在 Immich 账户设置中生成的 API Key。 |
| `ENABLED_PLATFORMS` |  | `telegram` | 启用的平台：`telegram`、`discord` 或 `telegram,discord`。 |
| **Telegram 配置** |  |  | *(仅在启用 Telegram 时生效)* |
| `TELEGRAM_BOT_TOKEN` | ✅* | — | 来自 BotFather 的 Telegram 机器人 Token。 |
| `TELEGRAM_API_ID` | ✅* | — | 来自 my.telegram.org 的数字应用 ID。 |
| `TELEGRAM_API_HASH` | ✅* | — | 来自 my.telegram.org 的应用 Hash。 |
| `TELEGRAM_ALLOWED_USER_IDS` | ✅* | — | 英文逗号分隔的 Telegram 用户 ID 白名单。 |
| `TELEGRAM_ALBUM_NAME` |  | `Telegram Inbox` | Telegram 默认回退相册名称。留空表示仅导入图库，不加入相册。 |
| `TELEGRAM_MEDIA_NAME_TEMPLATE` |  | `{source}_{message_id}_{index}` | 照片、视频、动图及音频的动态命名模板。 |
| `TELEGRAM_DOCUMENT_NAME_TEMPLATE` |  | `{original_name}` | 文档文件的动态命名模板。 |
| `TELEGRAM_ALBUM_NAME_TEMPLATE` |  | *(留空)* | 动态相册模板（例如 `{source}`）。若未命中则回退至 `TELEGRAM_ALBUM_NAME`。 |
| **Discord 配置** |  |  | *(仅在启用 Discord 时生效)* |
| `DISCORD_TOKEN` | ✅* | — | 来自 Discord Developer Portal 的机器人 Token。 |
| `DISCORD_ALLOWED_USER_IDS` | ✅* | — | 英文逗号分隔的 Discord 数字用户 ID 白名单。 |
| `DISCORD_ALBUM_NAME` |  | `Discord Inbox` | Discord 默认回退相册名称。留空表示仅导入图库，不加入相册。 |
| `DISCORD_FILENAME_TEMPLATE` |  | `{original_name}` | Discord 附件动态命名模板（`.env.example` 建议 `{source}_{sender}_{message_id}_{index}`）。 |
| `DISCORD_ALBUM_NAME_TEMPLATE` |  | *(留空)* | Discord 动态相册模板。若未命中则回退至 `DISCORD_ALBUM_NAME`。 |
| `DISCORD_MAX_ATTACHMENT_MB` |  | `2000` | 单个 Discord 附件大小上限（MiB）。 |
| **通用与高级配置** |  |  | |
| `TZ` |  | `UTC` | 文件名、相册日期及 `/status` 时间的时区（例如 `Asia/Shanghai`）。 |
| `DEFAULT_LANGUAGE` |  | `en` | 默认回退回复语言（`en`、`zh`、`ja`、`ru`）。 |
| `MAX_ARCHIVE_MB` |  | `2000` | 允许传入的压缩包大小上限（MB）。 |
| `MAX_ARCHIVE_FILES` |  | `1000` | 单个压缩包的媒体条目数量上限；超限时上传前拒绝整个包。 |
| `CLEANUP_LOCAL_FILES` |  | `true` | 导入成功或去重后是否自动清理临时下载文件。 |
| `LOG_LEVEL` |  | `INFO` | 日志级别：`DEBUG` / `INFO` / `WARNING` / `ERROR`。 |
| `DATA_DIR` |  | `/data` | 容器内部临时下载与解压目录。 |
| `TELEGRAM_FILES_DIR` |  | `/var/lib/telegram-bot-api` | 本地 Bot API 共享卷在容器内的挂载路径。 |
| `TELEGRAM_API_BASE` |  | `http://telegram-bot-api:8081` | 本地 Bot API 服务的访问地址。 |

*\*注：标记为 ✅\* 的变量仅在对应平台启用时必填。*

## Telegram 命名模板

Telegram 提供了针对不同媒体类型的独立命名与相册模板配置：

- `TELEGRAM_MEDIA_NAME_TEMPLATE`：用于照片、视频、动图及音频等常规媒体，默认 `{source}_{message_id}_{index}`。
- `TELEGRAM_DOCUMENT_NAME_TEMPLATE`：用于以文件/文档（Document）形式发送的文件，默认 `{original_name}`（保留原文件名）。
- `TELEGRAM_ALBUM_NAME_TEMPLATE`：动态相册模板，默认为空；未设置或解析为空时回退至 `TELEGRAM_ALBUM_NAME`（默认 `Telegram Inbox`）。

模板生成不含扩展名的文件名主体，程序会自动追加原扩展名。压缩包中解出的媒体保留各自的条目文件名，不使用此模板。

| 变量 | Telegram 中的值与说明 |
|---|---|
| `{original_name}` | 文档的原文件名（不含扩展名），普通照片/视频无文件名时为空。 |
| `{source}` | 来源名称：转发时为转发来源频道标题、群组名或作者名；非转发时为当前对话标题、发送者名称或 `telegram`。 |
| `{source_id}` | 来源 ID：转发来源 ID、当前对话 ID 或发送者 ID。 |
| `{source_username}`、`{username}` | 来源用户名：转发来源用户名、当前对话用户名或发送者用户名。 |
| `{sender}` | 原消息发送者的全名（缺失时使用用户名）。 |
| `{sender_id}` | 原消息发送者的 Telegram 数字 ID。 |
| `{chat_title}` | 当前对话的标题或全名。 |
| `{chat_id}` | 当前对话的数字 ID。 |
| `{message_id}` | 消息 ID：频道转发时为原频道消息 ID；普通消息为当前消息 ID。 |
| `{msg_id}` | 当前消息的 Telegram 消息 ID（不受转发影响）。 |
| `{index}` | 附件在媒体组（相册）或消息中的序号，从 1 开始。 |
| `{date}` | 智能时间：转发时优先使用原消息的转发时间；非转发时使用当前消息发送时间，使用 `TZ` 时区。 |
| `{msg_date}` | 当前消息的实际发送时间（即使是转发也采用当前时间），使用 `TZ` 时区。 |
| `{forward_date}` | 转发消息的原始发布时间，非转发消息时为空，使用 `TZ` 时区。 |
| `{exif_date}` | 照片 EXIF 中记录的拍摄时间，使用 `TZ` 时区；无 EXIF 或非照片时为空。 |
| `{media_type}` | 媒体类型：`photo`、`video`、`animation`、`audio`、`voice` 或 `document`。 |
| `{file_unique_id}` | Telegram 为该文件分配的唯一标识符（全局唯一）。 |
| `{media_group_id}` | 媒体组 ID（多图发送时所属相册组的 ID），单张发送时为空。 |
| `{caption}` | 消息的文字说明（换行与制表符会转为下划线，最多截取前 50 个字符）。 |
| `{forward_source}` | 转发来源名称（频道标题、群名或用户名），非转发为空。 |
| `{forward_channel}` | 转发来源频道的标题，非频道转发为空。 |
| `{forward_author}` | 转发来源的作者签名或用户名称，无签名或非转发为空。 |
| `{forward_source_id}` | 转发来源的数字 ID，非转发为空。 |
| `{forward_msg_id}` | 原频道消息 ID，非频道转发为空。 |

日期变量支持 Python 日期格式，例如：

```env
TZ=Asia/Shanghai
TELEGRAM_MEDIA_NAME_TEMPLATE={source}_{date:%Y%m%d}_{message_id}_{index}
TELEGRAM_DOCUMENT_NAME_TEMPLATE={source}_{original_name}
TELEGRAM_ALBUM_NAME_TEMPLATE={source}_{date:%Y-%m}
```

例如将频道转发的照片保存时，若频道名为 `Nature`、消息 ID 为 `108`、序号为 `1`，生成的文件名为 `Nature_20261031_108_1.jpg`。文件名主体和模板生成的相册名中，`/`、`\`、`:`、`*`、`?`、`"`、`<`、`>`、`|`、换行和制表符会替换为下划线，连续下划线会合并，首尾的空格、下划线和点会被移除，长度最多为 200 个字符。文件名模板渲染失败或结果为空时，常规媒体回退到 `{source}_{message_id}_{index}`（必要时使用 `file_{index}`），文档回退到 `{original_name}`。

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

## 限制与注意事项

### Telegram

- **单文件大小限制为 2 GB**：受限于 Telegram 本身，即使使用本地 Bot API 服务端也存在此上限。超过该大小的文件需要走 MTProto（userbot 协议），不在本项目的支持范围内。
- **直接以“图片”发送的照片会丢失 EXIF 并被 Telegram 重新压缩**：机器人依然会正常上传，但时间戳将使用 Telegram 消息时间，而非原始拍摄日期。如果需要完整保留元数据，请以**“文件/文档”**（Document/File）形式发送。
- **首次启动 `telegram-bot-api` 时需要初始化机器人专属目录**，耗时约 10–30 秒。在此期间机器人可能会打印几次连接重试日志，之后会自动恢复正常。
- **`tg-files` 数据卷占用可能会持续增长**：本地 Bot API 服务端会保留下载的文件直到调用 `deleteFile`。目前机器人暂不自动删除它们；如果不需保留历史缓存，可以定期执行 `docker compose down -v` 清理。
- **Compose 网络**：默认情况下 `immich-chat-importer` 服务可以访问 `telegram-bot-api`（同一 Compose 网络），但**无法访问你的 Immich 实例**，除非它们加入同一网络。请参考上文通用配置。

### Discord

- **转发消息**：支持在机器人私信和消息菜单中导入 Discord 原生转发消息快照内的附件。`{source}` 优先使用原频道名称，机器人无权查询时回退为原频道 ID。发送者和消息时间仍取自转发这条消息。
- **附件类型与压缩包限制**：支持照片、视频和压缩包（ZIP、RAR、7z、tar 系列，包含普通子目录），跳过嵌套压缩包和非媒体内容；不支持加密或无效的压缩包。单个附件大小上限由 `DISCORD_MAX_ATTACHMENT_MB` 控制。
- **隐私与权限**：机器人不监听任意群聊消息，仅接收直接私信与手动通过消息菜单触发的导入。菜单回复仅调用者本人可见。
- **状态记录**：`/status` 查询的导入记录仅保存在内存中，重启后清空，不会自动恢复未完成的任务。

### 跨平台与共享特性

- **图片拍摄日期**：Pillow 可读取的图片会随上传附带含拍摄日期及 `TZ` 偏移的 XMP sidecar，原图字节不变。无时区 EXIF 按 `TZ` 解释，有明确偏移时保留实际时间点，无 EXIF 日期时使用消息时间。视频及其他格式仍由 Immich 提取元数据；已有重复资产不会自动更新日期。
- **精准内容去重**：两平台共享 Immich 的精确内容去重（基于 SHA-1 哈希），不进行视觉相似度匹配。重复上传不会产生多份资产，但会加入指定相册。
- **单一账户**：每套部署对应一个 Immich 账号。

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
推送 `vX.Y.Z` 标签后，CI 通过才会构建 `linux/amd64` 和 `linux/arm64` 镜像，并发布至 `ghcr.io/myraxion/immich-chat-importer` 和 `docker.io/myraxion/immich-chat-importer`。Compose 默认使用 GHCR。稳定版会更新 `latest` 和版本别名；`vX.Y.Z-rc.1` 等预发布版本不会更新 `latest`。手动运行发布工作流时必须选择版本标签。发布旧稳定版也会更新版本别名和 `latest`。

发布工作流需要名为 `DOCKERHUB_TOKEN` 的 GitHub Actions secret，其权限须允许推送到 Docker Hub 的 `myraxion/immich-chat-importer`。如果任一仓库推送失败，重新运行前请检查两个仓库的镜像状态。

### 运行时内存测量

Telegram 使用精简 HTTPX Bot API 适配器。可在 Linux 镜像中运行
`scripts/measure_telegram_memory.py`，使用模拟接口验证正式 Telegram 适配器和导入流水线，
不会连接你的账号。详见[测量方法与结果](docs/research/http-telegram-memory.md)。

## 开源协议

[AGPL-3.0-only](LICENSE) —— 与 Immich 保持一致的开源协议。如果你将修改后的版本作为网络服务运行，必须以相同协议开源你的修改。
