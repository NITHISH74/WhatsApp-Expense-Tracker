"""
config.py — Application settings loaded from environment variables.
"""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ── Twilio ───────────────────────────────────────────────────────────────
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_whatsapp_number: str = "whatsapp:+14155238886"

    # ── Encryption ───────────────────────────────────────────────────────────
    fernet_key: str = ""

    # ── Database ─────────────────────────────────────────────────────────────
    database_url: str = "sqlite+aiosqlite:///./expenses.db"
    db_file_path: str = "./expenses.db"

    # ── App ──────────────────────────────────────────────────────────────────
    app_env: str = "development"
    log_level: str = "INFO"

    # ── Spending Alerts ───────────────────────────────────────────────────────
    default_daily_alert_threshold: float = 100.0
    default_weekly_alert_threshold: float = 500.0

    # ── Google Sheets ─────────────────────────────────────────────────────────
    google_service_account_json: str = ""
    google_sheet_id: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
