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
