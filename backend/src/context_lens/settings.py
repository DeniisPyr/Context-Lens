from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    # Alembic uses this one, so migrations run without a Gemini key, whatever else
    # is in .env.
    model_config = SettingsConfigDict(
        env_file=".env", env_ignore_empty=True, extra="ignore"
    )

    database_url: SecretStr = SecretStr(
        "postgresql+psycopg://context_lens:context_lens@localhost:5432/context_lens"
    )


class Settings(DatabaseSettings):
    # A typo in .env should stop the app, not be ignored.
    model_config = SettingsConfigDict(extra="forbid")

    gemini_api_key: SecretStr
    gemini_model: str = "gemini-3.8-flash"
    gemini_embedding_model: str = "gemini-embedding-2"
    gemini_timeout_seconds: float = 60.0
    max_upload_bytes: int = 1_000_000
