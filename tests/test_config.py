import pytest

from immich_tg_bot.config import Settings


@pytest.fixture
def required_settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_API_ID", "1")
    monkeypatch.setenv("TELEGRAM_API_HASH", "hash")
    monkeypatch.setenv("IMMICH_URL", "https://immich.example/api")
    monkeypatch.setenv("IMMICH_API_KEY", "key")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1643423542,6111406923", [1643423542, 6111406923]),
        ("[123,456]", [123, 456]),
    ],
)
def test_allowed_user_ids_accepts_csv_and_json(
    monkeypatch: pytest.MonkeyPatch,
    required_settings_env: None,
    value: str,
    expected: list[int],
) -> None:
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", value)

    settings = Settings(_env_file=None)
    assert settings.telegram_allowed_user_ids == expected


def test_default_naming_and_timezone_settings(
    monkeypatch: pytest.MonkeyPatch, required_settings_env: None
) -> None:
    settings = Settings(_env_file=None)
    assert settings.tz == "UTC"
    assert settings.telegram_media_name_template == "{source}_{message_id}_{index}"
    assert settings.telegram_document_name_template == "{original_name}"
    assert settings.telegram_album_name_template == ""


def test_custom_naming_and_timezone_settings(
    monkeypatch: pytest.MonkeyPatch, required_settings_env: None
) -> None:
    monkeypatch.setenv("TZ", "Asia/Shanghai")
    monkeypatch.setenv("TELEGRAM_MEDIA_NAME_TEMPLATE", "{date:%Y%m%d}_{source}_{index}")
    monkeypatch.setenv("TELEGRAM_DOCUMENT_NAME_TEMPLATE", "{source}_{original_name}")
    monkeypatch.setenv("TELEGRAM_ALBUM_NAME_TEMPLATE", "{source}")

    settings = Settings(_env_file=None)
    assert settings.tz == "Asia/Shanghai"
    assert settings.telegram_media_name_template == "{date:%Y%m%d}_{source}_{index}"
    assert settings.telegram_document_name_template == "{source}_{original_name}"
    assert settings.telegram_album_name_template == "{source}"


def test_invalid_timezone_raises_value_error(
    monkeypatch: pytest.MonkeyPatch, required_settings_env: None
) -> None:
    monkeypatch.setenv("TZ", "Invalid/Timezone_Name")
    with pytest.raises(ValueError, match="Invalid timezone"):
        Settings(_env_file=None)


def test_default_language_setting(
    monkeypatch: pytest.MonkeyPatch, required_settings_env: None
) -> None:
    settings = Settings(_env_file=None)
    assert settings.default_language == "en"


def test_custom_language_setting(
    monkeypatch: pytest.MonkeyPatch, required_settings_env: None
) -> None:
    monkeypatch.setenv("DEFAULT_LANGUAGE", "ZH")
    settings = Settings(_env_file=None)
    assert settings.default_language == "zh"


def test_invalid_language_raises_value_error(
    monkeypatch: pytest.MonkeyPatch, required_settings_env: None
) -> None:
    monkeypatch.setenv("DEFAULT_LANGUAGE", "fr")
    with pytest.raises(ValueError, match="Invalid default_language"):
        Settings(_env_file=None)


def test_cleanup_local_files_setting(
    monkeypatch: pytest.MonkeyPatch, required_settings_env: None
) -> None:
    settings = Settings(_env_file=None)
    assert settings.cleanup_local_files is True

    monkeypatch.setenv("CLEANUP_LOCAL_FILES", "false")
    settings_custom = Settings(_env_file=None)
    assert settings_custom.cleanup_local_files is False


def test_discord_only_requires_no_telegram_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENABLED_PLATFORMS", "discord")
    monkeypatch.setenv("DISCORD_TOKEN", "token")
    monkeypatch.setenv("DISCORD_ALLOWED_USER_IDS", "12,34")
    monkeypatch.setenv("TELEGRAM_API_ID", "")
    monkeypatch.setenv("IMMICH_URL", "https://immich.example/api")
    monkeypatch.setenv("IMMICH_API_KEY", "key")
    settings = Settings(_env_file=None)
    assert settings.discord_allowed_user_ids == [12, 34]
    assert settings.telegram_api_id is None
    assert settings.discord_album_name == "Discord Inbox"
    assert settings.discord_max_attachment_mb == 2000


def test_discord_requires_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENABLED_PLATFORMS", "discord")
    monkeypatch.setenv("IMMICH_URL", "https://immich.example/api")
    monkeypatch.setenv("IMMICH_API_KEY", "key")
    with pytest.raises(ValueError, match="Discord token"):
        Settings(_env_file=None)


def test_telegram_configuration_uses_only_prefixed_environment_names(
    monkeypatch: pytest.MonkeyPatch, required_settings_env: None
) -> None:
    monkeypatch.setenv("ALBUM_NAME", "old")
    monkeypatch.setenv("ALLOWED_USER_IDS", "99")
    monkeypatch.setenv("TELEGRAM_ALBUM_NAME", "new")
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "42")
    settings = Settings(_env_file=None)
    assert settings.telegram_album_name == "new"
    assert settings.telegram_allowed_user_ids == [42]
    monkeypatch.delenv("TELEGRAM_ALBUM_NAME")
    monkeypatch.delenv("TELEGRAM_ALLOWED_USER_IDS")
    settings = Settings(_env_file=None)
    assert settings.telegram_album_name is None
    assert settings.telegram_allowed_user_ids == []
