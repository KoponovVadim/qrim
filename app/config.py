from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Telegram
    TG_TOKEN: str
    WEBHOOK_URL: str
    
    # Redis
    REDIS_URL: str = "redis://redis:6379/0"
    REDIS_TTL: int = 3600
    
    # AI
    REPLICATE_API_KEY: str
    AI_MODEL: str = "meta/meta-llama-3-70b-instruct"
    
    # Google Sheets
    GOOGLE_SHEETS_ID: str
    GOOGLE_CREDENTIALS_JSON: str
    
    # App
    DEBUG: bool = False
    TIMEZONE: str = "Europe/Moscow"
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
