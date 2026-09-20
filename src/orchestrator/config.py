from functools import lru_cache
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Agent Orchestrator"
    app_env: str = "development"
    api_prefix: str = "/api/v1"
    database_url: str = "sqlite+aiosqlite:///./orchestrator.db"
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000", "http://localhost:5173"]
    default_provider: str = "mock"
    log_level: str = "INFO"
    secret_encryption_key: str | None = None
    # Authentication is intentionally opt-out only for isolated local tests.
    # A public deployment must never accidentally expose workspace data.
    auth_required: bool = True
    session_days: int = 30
    auth_rate_limit_per_minute: int = 10
    expensive_rate_limit_per_minute: int = 12
    # Daily per-account spend gate. 0 disables a limit; owners are never gated.
    daily_research_limit: int = 10
    daily_message_limit: int = 100
    email_verification_required: bool = True
    email_verification_ttl_minutes: int = 60 * 24
    admin_emails: Annotated[list[str], NoDecode] = []
    sentry_dsn: str | None = None
    public_url: str = "http://127.0.0.1:8000"
    google_auth_client_id: str | None = None
    google_auth_client_secret: str | None = None
    google_auth_callback_url: str | None = None
    google_auth_state_ttl_seconds: int = 600
    twitter_oauth_client_id: str | None = None
    twitter_oauth_client_secret: str | None = None
    twitter_oauth_callback_url: str | None = None
    twitter_oauth_scopes: str = "tweet.read users.read offline.access"
    twitter_oauth_state_ttl_seconds: int = 600
    google_model_oauth_client_id: str | None = None
    google_model_oauth_client_secret: str | None = None
    google_model_oauth_callback_url: str | None = None
    google_model_oauth_scopes: str = "openid email profile https://www.googleapis.com/auth/cloud-platform https://www.googleapis.com/auth/generative-language.retriever"
    google_model_oauth_state_ttl_seconds: int = 600
    context_oauth_state_ttl_seconds: int = 600
    github_oauth_client_id: str | None = None
    github_oauth_client_secret: str | None = None
    github_oauth_callback_url: str | None = None
    github_oauth_scopes: str = "read:user repo"
    github_oauth_state_ttl_seconds: int = 600
    notion_oauth_client_id: str | None = None
    notion_oauth_client_secret: str | None = None
    notion_oauth_callback_url: str | None = None
    notion_webhook_verification_token: str | None = None
    slack_oauth_client_id: str | None = None
    slack_oauth_client_secret: str | None = None
    slack_oauth_callback_url: str | None = None
    slack_oauth_scopes: str = "channels:read,groups:read,channels:history,groups:history,users:read,files:read"
    slack_signing_secret: str | None = None
    google_context_oauth_client_id: str | None = None
    google_context_oauth_client_secret: str | None = None
    google_context_oauth_callback_url: str | None = None
    google_drive_oauth_scopes: str = "openid email profile https://www.googleapis.com/auth/drive.readonly"
    youtube_oauth_scopes: str = "openid email profile https://www.googleapis.com/auth/youtube.readonly"
    context_sync_interval_seconds: int = 900
    # Deep Research credentials belong to the Orbit deployment, never to end users.
    # Every source also has an API-free public-web fallback.
    research_brave_api_key: str | None = None
    research_youtube_api_key: str | None = None
    research_tiktok_access_token: str | None = None
    research_instagram_access_token: str | None = None
    research_instagram_account_id: str | None = None
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from: str = "Orbit <no-reply@localhost>"
    smtp_starttls: bool = True
    max_request_bytes: int = 2_000_000
    max_file_bytes: int = 25_000_000
    file_storage_dir: str = "./data/files"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("admin_emails", mode="before")
    @classmethod
    def split_admin_emails(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip().lower() for item in value.split(",") if item.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
