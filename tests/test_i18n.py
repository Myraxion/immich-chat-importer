from typing import Any

import pytest

from immich_chat_importer.i18n import SUPPORTED_LANGUAGES, resolve_language, t


@pytest.mark.parametrize(
    ("lang_code", "default_lang", "expected"),
    [
        (None, "en", "en"),
        ("", "en", "en"),
        ("en", "en", "en"),
        ("EN", "en", "en"),
        ("en-US", "en", "en"),
        ("en_GB", "en", "en"),
        ("zh", "en", "zh"),
        ("zh-CN", "en", "zh"),
        ("zh-hans", "en", "zh"),
        ("zh_Hant_HK", "en", "zh"),
        ("ja", "en", "ja"),
        ("ja-JP", "en", "ja"),
        ("ru", "en", "ru"),
        ("ru-RU", "en", "ru"),
        ("fr", "en", "en"),
        ("de-DE", "ru", "ru"),
        (None, "zh", "zh"),
    ],
)
def test_resolve_language(lang_code: str | None, default_lang: str, expected: str) -> None:
    assert resolve_language(lang_code, default_lang=default_lang) == expected


def test_supported_languages_contains_four_targets() -> None:
    assert set(SUPPORTED_LANGUAGES) == {"en", "zh", "ja", "ru"}


ALL_KEYS = [
    "start",
    "help",
    "error_file_fetch",
    "status_errors_only",
    "status_mixed",
    "status_duplicates_only",
    "status_uploaded_duplicates",
    "status_uploaded_only",
    "status_no_media",
]


@pytest.mark.parametrize("lang", ["en", "zh", "ja", "ru"])
@pytest.mark.parametrize("key", ALL_KEYS)
def test_all_keys_translated_in_all_languages(key: str, lang: str) -> None:
    params: dict[str, Any] = {
        "error": "Boom",
        "errors": 2,
        "uploaded": 5,
        "duplicates": 3,
    }
    rendered = t(key, lang_code=lang, **params)
    assert isinstance(rendered, str)
    assert len(rendered) > 0
    # Ensure no unformatted placeholders remaining
    assert "{" not in rendered and "}" not in rendered


def test_t_uses_language_resolution() -> None:
    zh_result = t("status_uploaded_only", lang_code="zh-CN", uploaded=3)
    assert "已上传：3" in zh_result

    en_result = t("status_uploaded_only", lang_code="en-US", uploaded=3)
    assert "Uploaded: 3" in en_result

    ja_result = t("status_uploaded_only", lang_code="ja", uploaded=3)
    assert "アップロード済み: 3" in ja_result

    ru_result = t("status_uploaded_only", lang_code="ru", uploaded=3)
    assert "Загружено: 3" in ru_result

    fallback_result = t("status_uploaded_only", lang_code="fr", default_lang="ru", uploaded=3)
    assert "Загружено: 3" in fallback_result
