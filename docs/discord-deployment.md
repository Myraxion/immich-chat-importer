# Discord and combined deployment / Discord 与双平台部署

## Setup / 配置

1. Create an application in the [Discord Developer Portal](https://discord.com/developers/applications), obtain its bot token, enable user installation and select the `applications.commands` scope for the user install. Install it to your account using the installation link. The application uses Gateway; no public callback or privileged message-content intent is needed. Global commands are registered when the process starts. Distribution and installation settings must be verified for your own application and account.
2. Set `IMMICH_URL` (including `/api`), `IMMICH_API_KEY`, `DISCORD_TOKEN`, and `DISCORD_ALLOWED_USER_IDS` (comma-separated numeric IDs) in `.env`. Enable Discord Developer Mode to copy your user ID. An empty whitelist authorizes nobody. One deployment uses one Immich account.
3. Select a mode below. The application container must be able to reach Immich, e.g. by joining the same Docker network; see the main README. Do not expose tokens or commit `.env`.

1. 在 [Discord 开发者门户](https://discord.com/developers/applications) 创建应用，取得 bot token，启用用户安装并为用户安装选择 `applications.commands` scope，使用安装链接安装到自己的账号。应用通过 Gateway 连接，无需公网回调或特权 Message Content intent；进程启动时注册全局命令。请实际确认自己应用和账号的分发及安装设置。
2. 在 `.env` 填写 `IMMICH_URL`（包含 `/api`）、`IMMICH_API_KEY`、`DISCORD_TOKEN`、`DISCORD_ALLOWED_USER_IDS`（数字 ID，以逗号分隔）。开启 Discord 开发者模式可复制用户 ID。空白名单不允许任何用户操作。每套部署只使用一个 Immich 账号。
3. 选择以下模式，并确保应用容器能访问 Immich（例如加入同一 Docker 网络，参阅主 README）。不要公开 token 或提交 `.env`。

| Mode / 模式 | `ENABLED_PLATFORMS` | Compose command / 命令 |
| --- | --- | --- |
| Telegram only / 仅 Telegram | `telegram` (default) | `docker compose up -d` |
| Discord only / 仅 Discord | `discord` | `docker compose -f docker-compose.discord.yml up -d` |
| Both / 双平台 | `telegram,discord` | `docker compose up -d` |

Download `docker-compose.discord.yml` as well as `.env.example` for Discord-only deployment. The default Compose file retains the local Telegram Bot API service and shared volume. Discord-only uses neither that service nor Telegram credentials. Telegram and combined modes require `TELEGRAM_BOT_TOKEN`, `TELEGRAM_API_ID`, and `TELEGRAM_API_HASH`. Use the same `-f docker-compose.discord.yml` option for Discord-only logs, pull and shutdown. Avoid starting both Compose configurations simultaneously.

仅 Discord 部署需额外下载 `docker-compose.discord.yml`。默认 Compose 保留本地 Telegram Bot API 和共享卷；仅 Discord 不需要该服务或 Telegram 凭证。Telegram 与双平台模式需要 `TELEGRAM_BOT_TOKEN`、`TELEGRAM_API_ID`、`TELEGRAM_API_HASH`。仅 Discord 模式查看日志、更新和停止时也需使用相同的 `-f docker-compose.discord.yml` 参数；不要同时启动两套配置。

Discord options: `DISCORD_ALBUM_NAME` defaults to `Discord Inbox`; `DISCORD_ALBUM_NAME_TEMPLATE` and `DISCORD_FILENAME_TEMPLATE` customize names (default filename `{original_name}`). `DISCORD_MAX_ATTACHMENT_MB` defaults to 2000 MiB per attachment. `MAX_ARCHIVE_FILES` defaults to 1000 media entries per archive; an over-limit archive is rejected before its entries upload. `TZ`, `DEFAULT_LANGUAGE`, `MAX_ARCHIVE_FILES`, and `CLEANUP_LOCAL_FILES` are shared. See `.env.example` for naming variables. Discord accepts supported photo, video and archive attachments; ordinary archive subdirectories are included, while nested archives and non-media entries are skipped. Password-protected or invalid archives fail. These limits do not cap total extracted bytes.

Discord 配置：`DISCORD_ALBUM_NAME` 默认 `Discord Inbox`；`DISCORD_ALBUM_NAME_TEMPLATE` 和 `DISCORD_FILENAME_TEMPLATE` 控制名称（默认文件名 `{original_name}`）。`DISCORD_MAX_ATTACHMENT_MB` 默认每附件 2000 MiB；`MAX_ARCHIVE_FILES` 默认每压缩包 1000 个媒体文件，超限时上传任何条目之前拒绝该压缩包。`TZ`、`DEFAULT_LANGUAGE`、`MAX_ARCHIVE_FILES`、`CLEANUP_LOCAL_FILES` 两平台共享；命名变量见 `.env.example`。Discord 支持照片、视频和压缩包附件，包含压缩包普通子目录中的媒体，跳过嵌套压缩包和非媒体；加密或无效压缩包会失败。限制不约束解压后的总字节数。

## Use and upgrade / 使用与升级

Send attachments to the bot DM, or use Apps → **Save to Immich** on a message. Menu results are private. `/status` shows your five most recent Discord imports, including waiting, running, partial, failed and interrupted results. Long imports continue after an interaction expires; query `/status`. Retry by sending again or invoking the menu again: already saved bytes are reused and a failed album association can be completed. Restart marks unfinished records interrupted; it does not resume them automatically. Telegram and Discord batches run serially, while status queries remain available.

向 bot 私信发送附件，或在消息的 Apps 菜单选择 **保存到 Immich**；菜单回复仅调用者可见。`/status` 显示自己最近五次 Discord 导入，包括等待、运行、部分成功、失败和中断。交互过期后长任务仍继续，可用 `/status` 查询。重新发送或再次选择菜单可手动重试：已保存的相同内容会复用，并可补齐失败的相册关联。重启将未完成记录标记为中断，不自动恢复；两平台批次串行执行，状态查询仍可响应。

For upgrades, back up `./data` and retain it when replacing the image; it contains the SQLite state and existing Telegram identities. Existing Telegram configuration remains the default. Pull the new image and recreate the container with the command for your chosen mode. Exact-content deduplication is shared across platforms; visual similarity is not considered. The app does not monitor arbitrary chats, export to Discord, maintain separate Immich accounts, or automatically replay jobs.

升级前备份并保留 `./data`，其中的 SQLite 状态包含旧 Telegram 身份记录；原 Telegram 配置和默认模式保持兼容。拉取新镜像后按所选模式重建容器。两平台共享精确内容去重，不做视觉相似匹配；不监听任意聊天、不导出到 Discord、不支持多个 Immich 账号或自动重放任务。

## Acceptance evidence / 验收记录

The user confirmed on 2026-10-31 that the real-account acceptance for issue #9 is complete. The earlier progress record includes confirmed personal-channel imports, a server message-menu import, a bot DM archive, and a successful #8 test-image check. The full acceptance matrix has been confirmed complete; per-scenario environment details were not captured in this repository. Automated regression on the implementation commit passed 162 tests. Keep real-account results distinct from simulated integration tests when adding further evidence.

用户于 2026-10-31 确认 #9 要求的真实账号实机验收已完成。此前记录的具体场景包括个人频道导入、服务器消息菜单导入、bot 私信压缩包导入及 #8 测试镜像验证。完整验收矩阵已由用户确认完成；逐场景的环境细节未记录在本仓库。实现提交的自动化回归 162 项通过。后续补充证据时，继续区分真实账号实测与模拟集成测试。
