"""Application configuration.

Values are read from environment variables (optionally from a .env file).
Sensible local-dev defaults keep the app runnable without external services.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

# Lightweight .env loader (avoids a hard dependency on python-dotenv).
_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"


def _load_dotenv() -> None:
    if not _ENV_PATH.exists():
        return
    for raw in _ENV_PATH.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        # Do not override already-exported environment variables.
        os.environ.setdefault(key, value)


_load_dotenv()


class Settings:
    """Central settings object."""

    APP_NAME: str = "Learn++"
    API_PREFIX: str = "/api"

    # ---- Security ----
    SECRET_KEY: str = os.environ.get(
        "SECRET_KEY", "dev-insecure-change-me-in-production"
    )
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(
        os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "720")
    )

    # ---- Database ----
    # This build uses sqlite3 (standard library) for a zero-dependency,
    # fully-runnable local/VM deployment. DB_PATH is the SQLite file.
    #
    # MIGRATION NOTE: the PRD specifies MySQL for production. The data-access
    # layer (app/db/database.py) isolates all SQL so it can be swapped to a
    # MySQL driver (e.g. PyMySQL) on the Ubuntu VM. See docs/MIGRATION.md.
    DB_PATH: str = os.environ.get(
        "DB_PATH", str(Path(__file__).resolve().parents[2] / "learnpp.db")
    )

    # ---- Gemini ----
    GEMINI_API_KEY: str = os.environ.get("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.environ.get("GEMINI_MODEL", "gemini-1.5-flash")
    # Automatic fallback models when the primary is overloaded (503) or
    # rate-limited (429). Lighter models generally have more free-tier headroom.
    GEMINI_FALLBACKS: str = os.environ.get(
        "GEMINI_FALLBACKS", "gemini-1.5-flash-8b,gemini-1.5-flash"
    )

    # ---- Lesson engine (ported from the JS lesson engine) ----
    # Warm, lively temperature for the conversational Coach turns. The
    # structured JSON decompose path stays precise (low temp) elsewhere.
    TUTOR_TEMPERATURE: float = float(os.environ.get("TUTOR_TEMPERATURE", "0.9"))

    # Gamification XP per completed stage (env-overridable to retune).
    XP_INTRO: int = int(os.environ.get("XP_INTRO", "5"))
    XP_VIDEO: int = int(os.environ.get("XP_VIDEO", "10"))
    XP_READING: int = int(os.environ.get("XP_READING", "10"))
    XP_CHALLENGE: int = int(os.environ.get("XP_CHALLENGE", "15"))
    XP_DRAFT: int = int(os.environ.get("XP_DRAFT", "25"))
    XP_COMPLETE: int = int(os.environ.get("XP_COMPLETE", "20"))
    DAILY_XP_GOAL: int = int(os.environ.get("DAILY_XP_GOAL", "50"))

    # Planner (anti-procrastination): schedule backward from the due date,
    # reserve a submission buffer, cap daily load.
    DAILY_CAP_MIN: int = int(os.environ.get("DAILY_CAP_MIN", "15"))
    SUBMISSION_BUFFER_DAYS: int = int(os.environ.get("SUBMISSION_BUFFER_DAYS", "1"))

    # YouTube Data API key (optional). Without it, video blocks fall back to a
    # keyless search-page link, exactly like the JS engine.
    YOUTUBE_API_KEY: str = os.environ.get("YOUTUBE_API_KEY", "")

    # ---- Integrations ----
    # When true, Canvas/OSU/Gemini integrations use offline mock data so the
    # app runs fully without external network access. Auto-enabled when no
    # Gemini key is present.
    USE_MOCK_INTEGRATIONS: bool = (
        os.environ.get("USE_MOCK_INTEGRATIONS", "").lower() in {"1", "true", "yes"}
        or not os.environ.get("GEMINI_API_KEY", "")
    )

    # ---- Organization ----
    ORG_NAME: str = "The Ohio State University"
    ORG_EMAIL_DOMAIN: str = "osu.edu"

    # ---- Server ----
    HOST: str = os.environ.get("HOST", "127.0.0.1")
    PORT: int = int(os.environ.get("PORT", "8000"))


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
