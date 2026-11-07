from pathlib import Path

import pytest
from pydantic import ValidationError

from context_lens.settings import DatabaseSettings, Settings

DEFAULT_DATABASE_URL = (
    "postgresql+psycopg://context_lens:context_lens@localhost:5432/context_lens"
)
OTHER_DATABASE_URL = "postgresql+psycopg://someone:hunter2@db.example:6543/other"


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
    assert settings.gemini_embedding_model == "gemini-embedding-2"
    assert settings.gemini_timeout_seconds == 60.0
    assert settings.max_upload_bytes == 1_000_000
    assert settings.max_documents_per_dataset == 100
    assert settings.chunks_per_question == 8


def test_environment_overrides_the_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_MODEL", "another-model")
    monkeypatch.setenv("GEMINI_EMBEDDING_MODEL", "another-embedding-model")
    monkeypatch.setenv("GEMINI_TIMEOUT_SECONDS", "5.5")
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "10")
    monkeypatch.setenv("MAX_DOCUMENTS_PER_DATASET", "3")
    monkeypatch.setenv("CHUNKS_PER_QUESTION", "4")

    settings = Settings(_env_file=None)

    assert settings.gemini_model == "another-model"
    assert settings.gemini_embedding_model == "another-embedding-model"
    assert settings.gemini_timeout_seconds == 5.5
    assert settings.max_upload_bytes == 10
    assert settings.max_documents_per_dataset == 3
    assert settings.chunks_per_question == 4


def write_env_file(path: Path, *entries: str) -> Path:
    path.write_text("".join(f"{entry}\n" for entry in entries))
    return path


def test_database_url_has_a_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    for settings in (DatabaseSettings(_env_file=None), Settings(_env_file=None)):
        assert settings.database_url.get_secret_value() == DEFAULT_DATABASE_URL


def test_environment_overrides_the_database_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", OTHER_DATABASE_URL)

    for settings in (DatabaseSettings(_env_file=None), Settings(_env_file=None)):
        assert settings.database_url.get_secret_value() == OTHER_DATABASE_URL


def test_empty_database_url_means_the_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "")

    settings = DatabaseSettings(_env_file=None)

    assert settings.database_url.get_secret_value() == DEFAULT_DATABASE_URL


@pytest.mark.parametrize("settings_class", [DatabaseSettings, Settings])
def test_database_password_is_hidden_when_printed(
    monkeypatch: pytest.MonkeyPatch,
    settings_class: type[DatabaseSettings],
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert "context_lens" not in repr(settings_class(_env_file=None))

    monkeypatch.setenv("DATABASE_URL", OTHER_DATABASE_URL)
    assert "hunter2" not in repr(settings_class(_env_file=None))


def test_database_settings_need_no_gemini_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    settings = DatabaseSettings(_env_file=None)

    assert settings.database_url.get_secret_value() == DEFAULT_DATABASE_URL


def test_database_settings_ignore_other_entries_in_the_env_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    env_file = write_env_file(
        tmp_path / ".env",
        "GEMINI_API_KEY=file-key",
        "SOMETHING_ELSE=1",
        f"DATABASE_URL={OTHER_DATABASE_URL}",
    )

    settings = DatabaseSettings(_env_file=env_file)

    assert settings.database_url.get_secret_value() == OTHER_DATABASE_URL


def test_both_settings_read_dotenv_from_the_working_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    # conftest made tmp_path the working directory.
    write_env_file(
        tmp_path / ".env",
        "GEMINI_API_KEY=file-key",
        f"DATABASE_URL={OTHER_DATABASE_URL}",
    )

    for settings in (DatabaseSettings(), Settings()):
        assert settings.database_url.get_secret_value() == OTHER_DATABASE_URL


def test_env_file_with_only_the_key_still_works(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    env_file = write_env_file(tmp_path / ".env", "GEMINI_API_KEY=file-key")

    settings = Settings(_env_file=env_file)

    assert settings.gemini_api_key.get_secret_value() == "file-key"
    assert settings.database_url.get_secret_value() == DEFAULT_DATABASE_URL


def test_settings_reject_an_unknown_entry_in_the_env_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    env_file = write_env_file(
        tmp_path / ".env", "GEMINI_API_KEY=file-key", "SOMETHING_ELSE=1"
    )

    with pytest.raises(ValidationError, match="something_else"):
        Settings(_env_file=env_file)


def test_settings_require_the_key_even_with_a_database_url(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    env_file = write_env_file(tmp_path / ".env", f"DATABASE_URL={OTHER_DATABASE_URL}")

    with pytest.raises(ValidationError, match="gemini_api_key"):
        Settings(_env_file=env_file)
