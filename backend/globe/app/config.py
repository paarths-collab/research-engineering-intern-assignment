from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import List
from pydantic import field_validator
from pathlib import Path
import os


class Settings(BaseSettings):
    # ── App ──────────────────────────────────────────────────
    APP_NAME: str = "SimPPL Globe Backend"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # ── Reddit ───────────────────────────────────────────────
    REDDIT_CLIENT_ID: str = ""
    REDDIT_CLIENT_SECRET: str = ""
    REDDIT_USER_AGENT: str = "simppl-globe/1.0"
    REDDIT_SUBREDDITS: str = "worldnews,news,geopolitics,europe,asia,MiddleEast,worldpolitics"
    REDDIT_POST_LIMIT: int = 30
    REDDIT_TIME_WINDOW_HOURS: int = 24
    MIN_ENGAGEMENT_SCORE: int = 200

    # ── LLM ──────────────────────────────────────────────────
    GROQ_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    PRIMARY_MODEL: str = "llama-3.3-70b-versatile"
    FAST_MODEL: str = "llama-3.1-8b-instant"

    # ── News APIs ────────────────────────────────────────────
    NEWSAPI_KEY: str = ""
    NEWSDATA_KEY: str = ""
    GNEWS_KEY: str = ""
    TAVILY_API_KEY: str = ""
    CURRENTS_API_KEY: str = ""

    # ── Database ─────────────────────────────────────────────
    # Priorities: 1. ENV['DATA_PATH'], 2. /app/data (Production), 3. Local backend/data
    DATA_PATH: str = os.getenv("DATA_PATH", "/app/data" if Path("/app/data").exists() else str(Path(__file__).resolve().parents[2] / "data"))
    DUCKDB_PATH: str = ""

    # ── Pipeline ─────────────────────────────────────────────
    NEWS_ARTICLE_LIMIT: int = 2
    NEWS_TIME_WINDOW_HOURS: int = 48
    CLUSTER_MIN_SAMPLES: int = 2
    CLUSTER_SIMILARITY_THRESHOLD: float = 0.75

    # ── Paths ────────────────────────────────────────────────
    @property
    def DATA_DIR(self) -> str:
        return self.DATA_PATH

    LOG_DIR: str = str(Path(__file__).resolve().parents[2] / "logs")

    @property
    def subreddit_list(self) -> List[str]:
        return [s.strip() for s in self.REDDIT_SUBREDDITS.split(",")]

    class Config:
        env_file = ".env"
        extra = "ignore"

    @field_validator("DEBUG", mode="before")
    @classmethod
    def parse_debug(cls, value):
        if value is None:
            return False
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            normalized = value.strip().strip('"').strip("'").lower()
            if normalized in {"1", "true", "yes", "y", "on"}:
                return True
            if normalized in {"0", "false", "no", "n", "off", ""}:
                return False
        # Safe fallback: never break startup on malformed DEBUG values.
        return False

    @field_validator("DUCKDB_PATH", mode="before")
    @classmethod
    def parse_duckdb_path(cls, value):
        if value is None:
            return ""
        return str(value).strip()


@lru_cache()
def get_settings() -> Settings:
    settings = Settings()
    if not settings.DUCKDB_PATH:
        settings.DUCKDB_PATH = str(Path(settings.DATA_PATH) / "globe.duckdb")
    return settings
