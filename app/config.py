import json
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    BOT_TOKEN: str = ""
    ADMIN_IDS: list[int] = Field(default_factory=list)

    S3_ENDPOINT: str = ""
    S3_ACCESS_KEY: str = ""
    S3_SECRET_KEY: str = ""
    S3_BUCKET: str = ""
    S3_REGION: str = "auto"
    S3_PUBLIC_BASE_URL: str = ""

    WEB_PASSWORD: str = "change_me"
    WEB_PORT: int = 8000
    WEB_SECRET_KEY: str = "super_secret_session_key"

    DATABASE_PATH: str = "/data/app.db"
    PANEL_BASE_URL: str = "http://localhost:8000"
    FREE_PACK_KEY: str = "free/free_pack.zip"
    WEB_APP_URL: str = ""

    @field_validator("ADMIN_IDS", mode="before")
    @classmethod
    def parse_admin_ids(cls, value):
        if isinstance(value, list):
            return [int(v) for v in value]
        if isinstance(value, str):
            raw = value.strip()
            if not raw:
                return []
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError("ADMIN_IDS must be a JSON array, e.g. [111,222]") from exc
            if not isinstance(parsed, list):
                raise ValueError("ADMIN_IDS must be a JSON array")
            return [int(v) for v in parsed]
        return []


@lru_cache
def get_settings() -> Settings:
    return Settings()
