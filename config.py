"""
config.py — Application settings loaded from environment variables.
All secrets must be set via .env or hosting platform env vars.
Never hardcode credentials here.
"""

from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── Twilio ───────────────────────────────────────────────────────────────
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_whatsapp_number: str = "whatsapp:+14155238886"  # Sandbox default

    # ── Encryption ───────────────────────────────────────────────────────────
    # Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    fernet_key: str = ""

    # ── Database ─────────────────────────────────────────────────────────────
    database_url: str = "sqlite+aiosqlite:///./expenses.db"
    db_file_path: str = "./expenses.db"

    # ── App ──────────────────────────────────────────────────────────────────
    app_env: str = "development"  # "production" | "development"
    log_level: str = "INFO"

    # ── Spending Alerts ───────────────────────────────────────────────────────
    default_daily_alert_threshold: float = 100.0   # USD equivalent
    default_weekly_alert_threshold: float = 500.0

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
