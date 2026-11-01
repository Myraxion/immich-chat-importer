from typing import Any

SUPPORTED_LANGUAGES: tuple[str, ...] = ("en", "zh", "ja", "ru")

_MESSAGES: dict[str, dict[str, str]] = {
    "record_waiting": {"en": "waiting", "zh": "等待中", "ja": "待機中", "ru": "ожидание"},
    "record_processing": {"en": "processing", "zh": "处理中", "ja": "処理中", "ru": "обработка"},
    "record_completed": {"en": "completed", "zh": "已完成", "ja": "完了", "ru": "завершено"},
    "record_partial": {"en": "partial", "zh": "部分成功", "ja": "一部成功", "ru": "частично"},
    "record_failed": {"en": "failed", "zh": "失败", "ja": "失敗", "ru": "ошибка"},
    "status_attempt": {
        "en": "{stage}: attempt {attempt}/3",
        "zh": "{stage}：第 {attempt}/3 次尝试",
        "ja": "{stage}: {attempt}/3 回目",
        "ru": "{stage}: попытка {attempt}/3",
    },
    "status_retry_wait": {
        "en": "{stage}: attempt {attempt}/3 in {delay}s",
        "zh": "{stage}：{delay} 秒后进行第 {attempt}/3 次尝试",
        "ja": "{stage}: {delay} 秒後に {attempt}/3 回目",
        "ru": "{stage}: попытка {attempt}/3 через {delay} с",
    },
    "failure_archive_limit": {
        "en": "Archive contains too many media files. Split it or check the configured limit.",
        "zh": "压缩包中的媒体文件过多，请拆分压缩包或检查配置的数量限制。",
        "ja": "アーカイブ内のファイルが多すぎます。分割するか上限を確認してください。",
        "ru": "В архиве слишком много файлов. Разделите архив или проверьте лимит.",
    },
    "stage_extract": {"en": "extract", "zh": "解压", "ja": "解凍", "ru": "распаковка"},
    "failure_network": {
        "en": "Network or service unavailable. Check the connection and try again later.",
        "zh": "网络或服务暂时不可用，请检查连接后稍后重试。",
        "ja": "ネットワークまたはサービスを確認し、後でもう一度お試しください。",
        "ru": "Проверьте сеть и доступность сервиса, затем повторите попытку.",
    },
    "failure_access": {
        "en": "Access denied. Ask the administrator to check credentials and permissions.",
        "zh": "访问被拒绝，请联系管理员检查凭证和权限。",
        "ja": "アクセスが拒否されました。管理者に認証情報と権限の確認を依頼してください。",
        "ru": "Доступ запрещён. Попросите администратора проверить учётные данные и права.",
    },
    "failure_size": {
        "en": "File is too large. Reduce its size or check the configured limit.",
        "zh": "文件过大，请缩小文件或检查配置的大小限制。",
        "ja": "ファイルが大きすぎます。サイズまたは設定された上限を確認してください。",
        "ru": "Файл слишком велик. Уменьшите его или проверьте настроенный лимит.",
    },
    "failure_archive": {
        "en": "Archive could not be extracted. Check for damage or a password and repack it.",
        "zh": "无法解压，请检查压缩包是否损坏或加密，并重新打包。",
        "ja": "解凍できません。破損やパスワードを確認し、再圧縮してください。",
        "ru": "Не удалось распаковать архив. Проверьте его целостность и пароль.",
    },
    "failure_unknown": {
        "en": "Operation failed. Check the server logs or contact the administrator.",
        "zh": "操作失败，请检查服务日志或联系管理员。",
        "ja": "処理に失敗しました。ログを確認するか管理者に連絡してください。",
        "ru": "Операция не выполнена. Проверьте журнал или обратитесь к администратору.",
    },
    "failure_album_uncertain": {
        "en": "Album creation could not be confirmed; assets were saved. Try again later.",
        "zh": "无法确认相册是否创建；资产已保存，请稍后重新发送。",
        "ja": "アルバムの作成を確認できません。保存済みのデータは保持されます。",
        "ru": "Создание альбома не подтверждено; файлы сохранены. Повторите позже.",
    },
    "status_private_only": {
        "en": "Please query /status in a private chat with the bot.",
        "zh": "请在与机器人的私聊中查询 /status。",
        "ja": "ボットとのプライベートチャットで /status を確認してください。",
        "ru": "Проверьте /status в личном чате с ботом.",
    },
    "status_empty": {
        "en": "No import records yet.",
        "zh": "暂无导入记录。",
        "ja": "インポート履歴はありません。",
        "ru": "История импорта пуста.",
    },
    "discord_too_large": {
        "en": "exceeds {limit} MiB",
        "zh": "超过 {limit} MiB",
        "ja": "{limit} MiB を超過",
        "ru": "превышает {limit} МиБ",
    },
    "discord_download": {"en": "download", "zh": "下载", "ja": "ダウンロード", "ru": "скачивание"},
    "discord_network_error": {
        "en": "network error",
        "zh": "网络错误",
        "ja": "ネットワークエラー",
        "ru": "ошибка сети",
    },
    "discord_return_to_message": {
        "en": "Return to original message",
        "zh": "返回原消息",
        "ja": "元のメッセージに戻る",
        "ru": "Вернуться к исходному сообщению",
    },
    "discord_unauthorized": {
        "en": "You are not authorized to import media.",
        "zh": "你无权导入媒体。",
        "ja": "インポートする権限がありません。",
        "ru": "У вас нет доступа к импорту.",
    },
    "discord_counts": {
        "en": (
            "Uploaded: {uploaded}, duplicates: {duplicates}, skipped: {skipped}, errors: {errors}"
        ),
        "zh": "已上传：{uploaded}，重复项：{duplicates}，跳过：{skipped}，失败：{errors}",
        "ja": "アップロード: {uploaded}、重複: {duplicates}、スキップ: {skipped}、エラー: {errors}",
        "ru": (
            "Загружено: {uploaded}, дубликатов: {duplicates}, "
            "пропущено: {skipped}, ошибок: {errors}"
        ),
    },
    "discord_skipped": {
        "en": "unsupported",
        "zh": "不支持",
        "ja": "未対応",
        "ru": "не поддерживается",
    },
    "stage_upload": {"en": "upload", "zh": "上传", "ja": "アップロード", "ru": "загрузка"},
    "stage_album_lookup": {
        "en": "album lookup/create",
        "zh": "查找或创建相册",
        "ja": "アルバムの検索・作成",
        "ru": "поиск или создание альбома",
    },
    "stage_album_association": {
        "en": "album association",
        "zh": "关联相册",
        "ja": "アルバムへの追加",
        "ru": "добавление в альбом",
    },
    "start": {
        "en": (
            "👋 Hello! Forward photos, videos, files, and archives to me — "
            "and I'll upload them to your Immich.\n\n"
            "It is best to send photos <b>as a file / Document</b> to preserve "
            "EXIF data and original quality."
        ),
        "zh": (
            "👋 你好！将照片、视频、文件和压缩包转发给我，我会将它们上传到你的 Immich。\n\n"
            "照片建议<b>以文件 / Document 形式</b>发送，以保留 EXIF 元数据和原始画质。"
        ),
        "ja": (
            "👋 こんにちは！写真、動画、ファイル、アーカイブを転送していただければ、"
            "Immich にアップロードします。\n\n"
            "EXIF や元の画質を保持するために、写真は<b>ファイル / Document として</b>"
            "送信することをおすすめします。"
        ),
        "ru": (
            "👋 Привет! Пересылай мне фото, видео, файлы и архивы — "
            "и я залью их в твой Immich.\n\n"
            "Фото лучше отправлять <b>как файл / Document</b>, "
            "чтобы сохранить EXIF и оригинальное качество."
        ),
    },
    "help": {
        "en": (
            "What I can do:\n"
            "• photo / video / animation / voice / audio / video_note\n"
            "• document (photos, videos, any file)\n"
            "• archives (zip / rar / 7z / tar) — extracted and media uploaded\n"
            "• media groups (albums up to 10 files) — processed together\n\n"
            "Duplicates are detected via SHA-1 — resending is safe."
        ),
        "zh": (
            "功能介绍：\n"
            "• 照片 / 视频 / 动图 / 语音 / 音频 / 视频消息\n"
            "• 文档 (照片、视频或任意文件)\n"
            "• 压缩包 zip / rar / 7z / tar —— 自动解压并上传媒体文件\n"
            "• 媒体组 (最多 10 个文件的相册) —— 合并处理\n\n"
            "基于 SHA-1 自动识别重复项 —— 重复发送是安全的。"
        ),
        "ja": (
            "機能一覧：\n"
            "• 写真 / 動画 / アニメーション / ボイス / 音声 / ビデオノート\n"
            "• ドキュメント (写真、動画、任意のファイル)\n"
            "• アーカイブ (zip / rar / 7z / tar) — 解凍してメディアをアップロード\n"
            "• メディアグループ (最大10個のアルバム) — まとめて処理\n\n"
            "SHA-1 による重複検出を行うため、再送信しても安全です。"
        ),
        "ru": (
            "Что я умею:\n"
            "• photo / video / animation / voice / audio / video_note\n"
            "• document (фото, видео, любой файл)\n"
            "• архивы zip / rar / 7z / tar — распаковываю и заливаю медиа\n"
            "• media group (альбомы до 10 файлов) — обрабатываю вместе\n\n"
            "Дубликаты определяются по SHA1 — повторная отправка безопасна."
        ),
    },
    "error_file_fetch": {
        "en": "⚠️ Failed to get file: {error}",
        "zh": "⚠️ 获取文件失败：{error}",
        "ja": "⚠️ ファイルを取得できませんでした: {error}",
        "ru": "⚠️ Не удалось получить файл: {error}",
    },
    "status_errors_only": {
        "en": "⚠️ Errors: {errors}",
        "zh": "⚠️ 失败：{errors}",
        "ja": "⚠️ エラー: {errors}",
        "ru": "⚠️ Ошибок: {errors}",
    },
    "status_mixed": {
        "en": "⚠️ Uploaded: {uploaded}, duplicates: {duplicates}, errors: {errors}",
        "zh": "⚠️ 已上传：{uploaded}，重复项：{duplicates}，失败：{errors}",
        "ja": "⚠️ アップロード済み: {uploaded}、重複: {duplicates}、エラー: {errors}",
        "ru": "⚠️ Загружено: {uploaded}, дубликатов: {duplicates}, ошибок: {errors}",
    },
    "status_duplicates_only": {
        "en": "♻️ Already in Immich (duplicates: {duplicates})",
        "zh": "♻️ 已存在于 Immich（重复项：{duplicates}）",
        "ja": "♻️ 既に Immich に存在します (重複: {duplicates})",
        "ru": "♻️ Уже в Immich (дубликатов: {duplicates})",
    },
    "status_uploaded_duplicates": {
        "en": "✅ Uploaded: {uploaded}, duplicates: {duplicates}",
        "zh": "✅ 已上传：{uploaded}，重复项：{duplicates}",
        "ja": "✅ アップロード済み: {uploaded}、重複: {duplicates}",
        "ru": "✅ Загружено: {uploaded}, дубликатов: {duplicates}",
    },
    "status_uploaded_only": {
        "en": "✅ Uploaded: {uploaded}",
        "zh": "✅ 已上传：{uploaded}",
        "ja": "✅ アップロード済み: {uploaded}",
        "ru": "✅ Загружено: {uploaded}",
    },
    "status_no_media": {
        "en": "ℹ️ No media found in this message to upload.",
        "zh": "ℹ️ 此消息中未找到可供上传的媒体文件。",
        "ja": "ℹ️ このメッセージにはアップロード対象のメディアが見つかりませんでした。",
        "ru": "ℹ️ В этом сообщении не нашлось медиа для загрузки.",
    },
}


def resolve_language(lang_code: str | None, default_lang: str = "en") -> str:
    """Normalize and match a language tag to one of SUPPORTED_LANGUAGES."""
    fallback = default_lang.strip().lower() if default_lang else "en"
    if fallback not in SUPPORTED_LANGUAGES:
        fallback = "en"

    if not lang_code:
        return fallback

    normalized = lang_code.strip().lower().replace("_", "-")
    primary = normalized.split("-")[0]
    if primary in SUPPORTED_LANGUAGES:
        return primary
    return fallback


def t(
    key: str,
    lang_code: str | None = None,
    default_lang: str = "en",
    **kwargs: Any,
) -> str:
    """Look up and format a localized message string."""
    lang = resolve_language(lang_code, default_lang=default_lang)
    translations = _MESSAGES.get(key)
    if not translations:
        return key

    template = translations.get(lang) or translations.get(default_lang) or translations.get("en")
    if not template:
        return key

    try:
        return template.format(**kwargs)
    except Exception:
        return template
