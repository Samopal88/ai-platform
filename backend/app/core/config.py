from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


DEFAULT_PROJECT_ROOT = str(Path(__file__).resolve().parents[3])


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    PROJECT_NAME: str = "AI Workspace Platform"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api"

    ALLOWED_ORIGINS: list[str] = ["*"]

    DATABASE_URL: str = "sqlite:///./ai_workspace.db"
    REDIS_URL: str = "redis://localhost:6379/0"
    ENVIRONMENT: str = "development"
    AUTO_CREATE_DB_TABLES: bool = True
    BACKEND_HOST: str = "0.0.0.0"
    BACKEND_PORT: int = 8000
    AUTH_TOKEN_SECRET: str = ""
    SECRET_KEY: str = ""
    AUTH_TOKEN_TTL_SECONDS: int = 60 * 60 * 24 * 30
    PUBLIC_BASE_URL: str = "http://127.0.0.1:8000"
    PROJECT_ROOT: str = DEFAULT_PROJECT_ROOT
    SYSTEMD_UNIT_NAME: str = "ai-platform.service"
    RUAPI_API_KEY: str = ""
    RUAPI_BASE_URL: str = ""
    ROUTERAI_API_KEY: str = ""
    ROUTERAI_BASE_URL: str = ""
    CLAUDEHUB_API_KEY: str = ""
    CLAUDEHUB_BASE_URL: str = ""
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = ""
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_AUTH_TOKEN: str = ""
    ANTHROPIC_BASE_URL: str = ""
    GOOGLE_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    YOOKASSA_SHOP_ID: str = ""
    YOOKASSA_SECRET_KEY: str = ""
    YOOKASSA_RETURN_URL: str = ""
    YOOKASSA_WEBHOOK_SECRET: str = ""
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = ""
    SMTP_FROM_NAME: str = "AI Platform"
    SMTP_USE_TLS: bool = True


settings = Settings()
