from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    mongodb_uri: str = "mongodb://127.0.0.1:27017"
    mongodb_database: str = "dml_v4_survey"
    mongodb_server_selection_timeout_ms: int = Field(default=3_000, ge=500, le=30_000)
    admin_username: str = "admin"
    admin_password_hash: str = ""
    admin_session_secret: str = ""
    admin_secure_cookie: bool = False
    admin_session_hours: int = Field(default=8, ge=1, le=24)
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
