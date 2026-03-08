from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import List
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
    DUCKDB_PATH: str = "outputs/globe.duckdb"

    # ── Pipeline ─────────────────────────────────────────────
    NEWS_ARTICLE_LIMIT: int = 2
    NEWS_TIME_WINDOW_HOURS: int = 48
    CLUSTER_MIN_SAMPLES: int = 2
    CLUSTER_SIMILARITY_THRESHOLD: float = 0.75

    # ── Paths ────────────────────────────────────────────────
    DATA_DIR: str = "outputs"
    LOG_DIR: str = "logs"

    @property
    def subreddit_list(self) -> List[str]:
        return [s.strip() for s in self.REDDIT_SUBREDDITS.split(",")]

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
