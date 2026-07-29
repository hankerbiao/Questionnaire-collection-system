from functools import lru_cache
from urllib.parse import quote_plus

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    mongodb_uri: str = ""
    mongodb_hosts: str = "127.0.0.1:27017"
    mongodb_username: str = ""
    mongodb_password: str = ""
    mongodb_database: str = "dml_v4_survey"
    mongodb_auth_source: str = ""
    mongodb_replica_set: str = ""
    mongodb_write_concern: int = Field(default=1, ge=1, le=3)
    mongodb_server_selection_timeout_ms: int = Field(default=3_000, ge=500, le=30_000)
    admin_username: str = "admin"
    admin_password_hash: str = ""
    admin_session_secret: str = ""
    admin_secure_cookie: bool = False
    admin_session_hours: int = Field(default=8, ge=1, le=24)
    external_sso_shared_secret: str = ""
    external_sso_issuer: str = "dml-demo-external"
    external_sso_audience: str = "dml-survey"
    external_portal_url: str = "http://127.0.0.1:9000"
    survey_callback_url: str = "http://127.0.0.1:5173/api/v1/auth/external/callback"
    survey_login_start_url: str = "http://127.0.0.1:5173/api/v1/auth/external/start"
    external_ticket_max_seconds: int = Field(default=60, ge=30, le=300)
    user_session_secret: str = ""
    user_secure_cookie: bool = False
    user_session_hours: int = Field(default=8, ge=1, le=24)
    log_level: str = "INFO"

    @model_validator(mode="after")
    def populate_mongodb_uri(self) -> "Settings":
        if self.mongodb_uri:
            return self

        if bool(self.mongodb_username) != bool(self.mongodb_password):
            raise ValueError("MONGODB_USERNAME and MONGODB_PASSWORD must be configured together")

        hosts = ",".join(host.strip() for host in self.mongodb_hosts.split(",") if host.strip())
        if not hosts:
            hosts = "127.0.0.1:27017"

        credentials = ""
        auth_source = self.mongodb_auth_source
        if self.mongodb_username and self.mongodb_password:
            credentials = (
                f"{quote_plus(self.mongodb_username)}:{quote_plus(self.mongodb_password)}@"
            )
            auth_source = auth_source or self.mongodb_database

        query_parts: list[str] = []
        if auth_source:
            query_parts.append(f"authSource={quote_plus(auth_source)}")
        if self.mongodb_replica_set:
            query_parts.append(f"replicaSet={quote_plus(self.mongodb_replica_set)}")
        query_parts.append(f"w={self.mongodb_write_concern}")

        query = f"?{'&'.join(query_parts)}" if query_parts else ""
        self.mongodb_uri = f"mongodb://{credentials}{hosts}/{self.mongodb_database}{query}"
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
