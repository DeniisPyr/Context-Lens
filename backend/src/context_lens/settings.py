from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True)

    gemini_api_key: SecretStr
    gemini_model: str = "gemini-3.8-flash"
    gemini_timeout_seconds: float = 60.0
    max_upload_bytes: int = 1_000_000
