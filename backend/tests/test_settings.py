import pytest
from pydantic import ValidationError

from context_lens.settings import Settings


def test_api_key_is_read_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    settings = Settings(_env_file=None)

    assert settings.gemini_api_key.get_secret_value() == "test-key"


def test_missing_api_key_is_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_empty_api_key_is_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_api_key_is_hidden_when_printed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    settings = Settings(_env_file=None)

    assert "test-key" not in repr(settings)


def test_optional_settings_have_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    settings = Settings(_env_file=None)

    assert settings.gemini_model == "gemini-3.8-flash"
    assert settings.gemini_timeout_seconds == 60.0
    assert settings.max_upload_bytes == 1_000_000


def test_environment_overrides_the_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_MODEL", "another-model")
    monkeypatch.setenv("GEMINI_TIMEOUT_SECONDS", "5.5")
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "10")

    settings = Settings(_env_file=None)

    assert settings.gemini_model == "another-model"
    assert settings.gemini_timeout_seconds == 5.5
    assert settings.max_upload_bytes == 10
