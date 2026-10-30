from typing import Any

SUPPORTED_LANGUAGES: tuple[str, ...] = ("en", "zh", "ja", "ru")

_MESSAGES: dict[str, dict[str, str]] = {
    "stage_upload": {"en": "upload", "zh": "上传", "ja": "アップロード", "ru": "загрузка"},
    "stage_album_lookup": {
        "en": "album lookup/create", "zh": "查找或创建相册",
        "ja": "アルバムの検索・作成", "ru": "поиск или создание альбома",
    },
    "stage_album_association": {
        "en": "album association", "zh": "关联相册",
        "ja": "アルバムへの追加", "ru": "добавление в альбом",
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
