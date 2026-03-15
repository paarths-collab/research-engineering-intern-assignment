"""
config.py — Centralised settings loaded from environment.
All secrets live in backend/.env — never hardcoded.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Point to backend/.env so streamgraph2 shares the single env file
_env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(_env_path)


def _require(key: str) -> str:
    val = os.getenv(key)
    if not val:
        raise EnvironmentError(f"Missing required env var: {key}")
    return val


# ── Database ──────────────────────────────────────────────────
DATABASE_URL: str = os.getenv("DATABASE_URL", "")   # Optional — CSV fallback active when empty
DUCKDB_PATH: Path = Path(
    os.getenv(
        "STREAMGRAPH2_DUCKDB_PATH",
        str(Path(__file__).resolve().parents[2] / "data" / "streamgraph2.duckdb"),
    )
)

# ── Groq ──────────────────────────────────────────────────────
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")   # Optional — LLM brief skipped when empty
_raw_llm_model = os.getenv("LLM_MODEL", "groq/llama-3.3-70b-versatile")
# LiteLLM requires provider-qualified model names (e.g. groq/llama-3.3-70b-versatile).
LLM_MODEL: str = _raw_llm_model if "/" in _raw_llm_model else f"groq/{_raw_llm_model}"
# Used only by lightweight topic clustering post-processing (hybrid mode).
TOPIC_REFINER_MODEL: str = os.getenv("TOPIC_REFINER_MODEL", "gemma-3-27b-it")

# ── Reddit ────────────────────────────────────────────────────
REDDIT_CLIENT_ID: str     = os.getenv("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET: str = os.getenv("REDDIT_CLIENT_SECRET", "")
REDDIT_USER_AGENT: str    = os.getenv("REDDIT_USER_AGENT", "catalyst-engine/1.0")

# ── News APIs ─────────────────────────────────────────────────
NEWSAPI_KEY: str     = os.getenv("NEWSAPI_KEY", "")
NEWSDATA_KEY: str    = os.getenv("NEWSDATA_KEY", "")
CURRENTS_KEY: str    = os.getenv("CURRENTS_KEY", "")
GNEWS_KEY: str       = os.getenv("GNEWS_KEY", "")
APITUBE_KEY: str     = os.getenv("APITUBE_KEY", "")
TAVILY_KEY: str      = os.getenv("TAVILY_KEY", "")

# ── Embedding model ───────────────────────────────────────────
EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "hash-lexical-v1")
EMBEDDING_DIM: int   = 384

# ── Pipeline tuning ───────────────────────────────────────────
SPIKE_Z_THRESHOLD: float   = float(os.getenv("SPIKE_Z_THRESHOLD", "2.0"))
BERTOPIC_MIN_TOPIC: int    = int(os.getenv("BERTOPIC_MIN_TOPIC", "5"))
NEWS_FETCH_LIMIT: int      = int(os.getenv("NEWS_FETCH_LIMIT", "50"))
SIMILARITY_TOP_K: int      = int(os.getenv("SIMILARITY_TOP_K", "3"))
REDDIT_COMMENTS_LIMIT: int = int(os.getenv("REDDIT_COMMENTS_LIMIT", "20"))

# ── Agent thresholds ──────────────────────────────────────────
AGENT_MIN_SIMILARITY: float = float(os.getenv("AGENT_MIN_SIMILARITY", "0.40"))
AGENT_WARN_SIMILARITY: float = float(os.getenv("AGENT_WARN_SIMILARITY", "0.60"))
AGENT_MAX_DOMINANT_TOPIC: float = float(os.getenv("AGENT_MAX_DOMINANT_TOPIC", "80.0"))
AGENT_MIN_NEWS_COUNT: int   = int(os.getenv("AGENT_MIN_NEWS_COUNT", "5"))
