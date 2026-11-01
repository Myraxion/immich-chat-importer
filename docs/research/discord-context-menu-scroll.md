# Discord 消息菜单保存媒体：通知与滚动位置

调研日期：2026-11-01。范围为官方 API 文档、Discord 官方仓库中的第一手报告及本地入口代码；调研阶段未修改运行代码，未进行真实账号客户端联调。

后续确认（2026-11-01）：采用文字链接「返回原消息」。右键保存的处理提示、最终结果及每条分段回复均附链接，成功和失败结果都保留；链接指向被右键点击的消息，包括转发消息本身。处理提示使用即时私密回复，再编辑为结果；私信导入和 `/status` 不增加链接。该选择便于撤销，不新增 ADR 或领域术语。下文的本地行为描述为调研时的实现。

## 结论

当前入口已经使用私密回复；`ephemeral` 只限定可见范围，不能保证保留阅读位置。`silent` 只抑制推送和桌面通知，也没有控制滚动位置的保证。公开 API 未提供消息菜单直接「执行成功、完全无 UI」的 ACK。应将通知和跳转分开验证，不能把加一个 flag 当作确定修复。[Message flags](https://docs.discord.com/developers/resources/message#message-flags)、[Interaction callbacks](https://docs.discord.com/developers/interactions/receiving-and-responding#interaction-response-object)

## 本地行为

`src/immich_chat_importer/adapters/discord/bot.py` 的 `handle_menu` 先调用 `defer(ephemeral=True, thinking=True)`，执行导入，再 `edit_original_response`；超过单条长度的结果通过额外私密 followup 发出。因此用户看见的提示不等于向全频道公开发消息。`/status` 可查询当前调用者的 IngestRecord，可在机器人私聊等其他上下文查询。记录只保留在当前进程内，重启丢弃；以 `CONTEXT.md` 和 ADR-0006 为准，不沿用早期规格的持久化描述。

## 官方明确规定

- 初始响应须在 3 秒内发送，interaction token 有效期 15 分钟。消息菜单是 application command；type 5 defer 会显示加载状态，且此时只允许 `EPHEMERAL` flag。删掉 `thinking=True` 不会把消息菜单变成无提示 ACK。[响应时限与回调类型](https://docs.discord.com/developers/interactions/receiving-and-responding)
- type 6 `DEFERRED_UPDATE_MESSAGE` 可无加载提示地确认组件或 modal submit，不能直接用于消息菜单。type 9 可弹出 modal；type 12 启动 Activity 需要应用启用 Activities。[回调类型](https://docs.discord.com/developers/interactions/receiving-and-responding#interaction-response-object)
- 原回复可编辑、删除；删除不等于撤回已经发生的客户端滚动，也没有恢复原阅读位置的承诺。defer 时确定的私密属性不能在后续编辑时改成公开。[原回复和 followup API](https://docs.discord.com/developers/interactions/receiving-and-responding#followup-messages)
- `SUPPRESS_NOTIFICATIONS`（4096）禁推送/桌面通知；mention 仍可能留下角标。`allowed_mentions` 控制内容里的提及，两者都不定义聊天窗口如何滚动。[消息标志与提及规则](https://docs.discord.com/developers/resources/message#allowed-mentions-object)

## 第一手报告及其证据边界

- Discord 官方仓库 [#4675](https://github.com/discord/discord-api-docs/issues/4675) 记录了历史消息与最新消息之间存在未加载内容时，触发 ephemeral 后滚动/显示异常；2022-11-05 评论明确报告 Message Commands 也受影响。2023 年用户提到 popup modal workaround。**2026-05-28 contributor 已称 Canary 修复并关闭为 completed**，不能据此断言这个旧 bug 仍未修复，也不能认定它就是本次跳转的同一个问题。
- [2026-07-07 官方补丁说明](https://discord.com/blog/discord-patch-notes-july-7-2026) 称修复 Desktop 上命令的 ephemeral 回复在点击 Jump to Present 或跨过重新拉取消息后消失的问题。该修复说明涉及「回复消失」，没有承诺触发菜单时保持阅读位置。
- [2024-03-10 Discord 支持社区第一手反馈](https://support.discord.com/hc/en-us/community/posts/21955968857879-Scrolling-to-bottom-bug) 描述跨大量历史消息跳到底部后 ephemeral 不显示。它是用户报告，不是当前版本的官方行为保证。

## 可选方案与建议

| 方案 | 能确定的收益 | 限制与判断 |
| --- | --- | --- |
| 立即 `send_message(ephemeral=True, silent=True)`，后台导入后编辑原回复 | 避免 type 5 加载阶段；支持抑制推送/桌面通知 | 仍创建私密消息；是否减少跳转只是待验证假设。适合作为最小实验，不应承诺解决阅读位置问题。 |
| 继续 defer 后编辑同一条，缩短结果；详情去 `/status` | 减少额外 followup 和频道内的结果显示 | 初始 defer 仍存在，无法保证不跳。当前实现已采用主体流程。 |
| 结果附原消息 `jump_url` 或链接按钮 | 用户可点击回到目标消息 | 这是返回消息的补救，不恢复原来的精确滚动偏移，也不阻止跳转。 |
| 私密回复后尽快删除，结果只通过 `/status` 查询 | 减少提示残留 | 提示可能已触发滚动；自动删除还会失去成功/失败反馈，不是确定的滚动修复。 |
| 菜单先弹 modal，提交后 type 6 ACK，再后台导入和 `/status` 查询 | 将初始 UI 从聊天消息变成独立弹窗；提交可无加载消息确认 | 增加一步操作；客户端是否保留位置仍需实测。符合「优先保持历史阅读位置」时的实验方向。 |
| 启动 Activity | 使用独立应用 UI | 需配置及实现 Activity，明显超过单次保存媒体所需复杂度，不建议。 |

立即回复的 `silent` 和后续编辑由 [discord.py 官方 API](https://discordpy.readthedocs.io/en/stable/interactions/api.html#discord.InteractionResponse.send_message) 支持。Modal 提交走 type 6 的依据除了官方回调表，还有 [discord.py `InteractionResponse.defer` 源码](https://github.com/Rapptz/discord.py/blob/master/discord/interactions.py)：`modal_submit` 且 `thinking=False` 时选择 type 6，不要求先有频道消息。这不改变「原消息菜单不能直接 type 6 ACK」的限制。

当前 [Component Reference](https://docs.discord.com/developers/components/reference#text-display) 允许 Modal 使用 Text Display，不必用可编辑的预填文本框假装只读提示。但仅含静态文本的无输入弹窗及其关闭/提交体验，仍应通过实际客户端验证，不能把合法组件组合等同于已验证产品方案。

最简单的补救是把结果限制为摘要加「返回原消息」链接，避免自动拆分 followup，详细结果由用户在机器人私聊调用 `/status` 查看。[discord.py `Message.jump_url`](https://discordpy.readthedocs.io/en/stable/api.html#discord.Message.jump_url) 返回指向消息的 URL；链接按钮属于普通导航，不发送新的 interaction。[按钮规则](https://docs.discord.com/developers/components/reference#button)

建议先在最新 Desktop/Web 上对同一条较旧消息复现，记录跳转发生在菜单点击、defer、最终编辑还是 followup。关闭桌面通知可先试立即私密 silent 回复；保留阅读位置则需比较该方案与 modal，并以实际滚动位置验收，不能仅测试保存成功。本次调研不改变导入、鉴权及重启语义。
