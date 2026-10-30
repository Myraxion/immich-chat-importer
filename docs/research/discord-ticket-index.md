# Discord ingestion implementation tickets

Parent specification: [#1](https://github.com/Myraxion/immich-telegram-bot/issues/1).

Published on 2026-10-30 after approval of the eight-ticket breakdown. All tickets are labeled ready-for-agent and use native GitHub parent/sub-issue and blocking relationships. The parent specification body, title, state, and labels were preserved.

| Slice | Issue | Blocked by |
| --- | --- | --- |
| 1 | [#2 前置重构：保持 Telegram 兼容的共享摄取边界](https://github.com/Myraxion/immich-telegram-bot/issues/2) | None |
| 2 | [#3 重复资产加入目标相册，并支持失败补齐](https://github.com/Myraxion/immich-telegram-bot/issues/3) | [#2](https://github.com/Myraxion/immich-telegram-bot/issues/2) |
| 3 | [#4 Discord 私信导入照片和视频](https://github.com/Myraxion/immich-telegram-bot/issues/4) | [#2](https://github.com/Myraxion/immich-telegram-bot/issues/2) |
| 4 | [#5 个人安装的消息菜单与模板归档](https://github.com/Myraxion/immich-telegram-bot/issues/5) | [#4](https://github.com/Myraxion/immich-telegram-bot/issues/4) |
| 5 | [#6 Discord 压缩包导入与严格限额](https://github.com/Myraxion/immich-telegram-bot/issues/6) | [#4](https://github.com/Myraxion/immich-telegram-bot/issues/4) |
| 6 | [#7 持久化 IngestRecord 与 /status 查询](https://github.com/Myraxion/immich-telegram-bot/issues/7) | [#4](https://github.com/Myraxion/immich-telegram-bot/issues/4) |
| 7 | [#8 长任务反馈与重启中断处理](https://github.com/Myraxion/immich-telegram-bot/issues/8) | [#5](https://github.com/Myraxion/immich-telegram-bot/issues/5), [#7](https://github.com/Myraxion/immich-telegram-bot/issues/7) |
| 8 | [#9 双平台部署与完整验收](https://github.com/Myraxion/immich-telegram-bot/issues/9) | [#3](https://github.com/Myraxion/immich-telegram-bot/issues/3), [#6](https://github.com/Myraxion/immich-telegram-bot/issues/6), [#8](https://github.com/Myraxion/immich-telegram-bot/issues/8) |

The initial frontier is [#2](https://github.com/Myraxion/immich-telegram-bot/issues/2). After it completes, slices 2 and 3 can proceed independently; all further work follows the native blocking graph.

Ticket-specific acceptance tests belong in every slice. The final ticket verifies the combined deployment and real-account matrix; it does not replace tests in earlier tickets.
