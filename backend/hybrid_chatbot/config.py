"""
hybrid_chatbot/config.py
------------------------
Centralized configuration for the deployable hybrid chatbot.
"""

from __future__ import annotations

import os
from pathlib import Path
from llm_models import groq_model

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BACKEND_DIR.parent.parent

# Load backend/.env so chatbot works even when launched standalone
try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_DIR / "backend" / ".env")
except Exception:
    pass


def _resolve_path(value: str | Path) -> Path:
    p = Path(value)
    if p.is_absolute():
        return p
    return (PROJECT_DIR / p).resolve()


_data_dir_env = (
    os.getenv("HYBRID_DATA_DIR")
    or os.getenv("DATA_PATH")
    or os.getenv("DATA_DIR")
)
DATA_DIR = _resolve_path(_data_dir_env) if _data_dir_env else (PROJECT_DIR / "data").resolve()

# The SQL DB path (HYBRID_SQL_DB / HYBRID_SQL_DB_PATH) is resolved at call time by resolve_db_path().
VECTOR_INDEX_PATH = Path(os.getenv("HYBRID_VECTOR_INDEX", DATA_DIR / "hybrid_vector.index"))
VECTOR_META_PATH = Path(os.getenv("HYBRID_VECTOR_META", DATA_DIR / "hybrid_vector_meta.jsonl"))

EMBED_MODEL_NAME = os.getenv("HYBRID_EMBED_MODEL", "disabled")

LLM_BASE_URL = os.getenv("HYBRID_LLM_BASE_URL", "https://api.groq.com/openai/v1")
LLM_API_KEY = os.getenv("HYBRID_LLM_API_KEY", os.getenv("GROQ_API_KEY", ""))
LLM_MODEL = groq_model("HYBRID_LLM_MODEL", "LITE_MODEL", "LLM_MODEL")

# ── Dataset mapping (CSV -> SQL table) ───────────────────────────────────────
CSV_TABLES: dict[str, str] = {
    "narrative_diffusion_table.csv": "narrative_diffusion_table",
    "subreddit_domain_flow_v2.csv": "subreddit_domain_flow_v2",
    "daily_volume_v2.csv": "daily_volume_v2",
    "narrative_registry.csv": "narrative_registry",
    "author_influence_profile.csv": "author_influence_profile",
    "echo_chamber_scores.csv": "echo_chamber_scores",
    "narrative_intelligence_summary.csv": "narrative_intelligence_summary",
    "narrative_topic_mapping.csv": "narrative_topic_mapping",
    "graph_edge_intelligence_table.csv": "graph_edge_intelligence_table",
    "clean_posts.csv": "clean_posts",
    "clean_with_clusters_v2.csv": "clean_with_clusters_v2",
    "subreddit_intelligence_summary.csv": "subreddit_intelligence_summary",
}

# Serverless platforms expose a read-only (or ephemeral) filesystem; the prebuilt
# DB is served as-is and anything else is built into a transient location.
SERVERLESS_ENV_VARS = ("VERCEL", "AWS_LAMBDA_FUNCTION_NAME")

# Below this total CSV size a transient (non-writable destination) build lives in
# an in-memory DuckDB; above it a file under tempfile.gettempdir() is used.
TRANSIENT_MEMORY_MAX_BYTES = 128 * 1024 * 1024

# Columns used to compute the dataset's date range (table -> date-like columns).
DATE_COLUMNS: dict[str, list[str]] = {
    "daily_volume_v2": ["created_datetime"],
    "clean_posts": ["created_datetime"],
    "clean_with_clusters_v2": ["created_datetime"],
    "graph_edge_intelligence_table": ["created_datetime"],
    "narrative_registry": ["first_seen"],
    "narrative_intelligence_summary": ["first_seen_x", "last_seen"],
}


def resolve_db_path() -> Path:
    """DB path resolved from the environment at call time (tests / deployments)."""
    value = os.getenv("HYBRID_SQL_DB") or os.getenv("HYBRID_SQL_DB_PATH")
    return Path(value) if value else resolve_data_dir() / "hybrid_chatbot.duckdb"


def resolve_data_dir() -> Path:
    """CSV directory resolved from the environment at call time."""
    value = os.getenv("HYBRID_DATA_DIR") or os.getenv("DATA_PATH") or os.getenv("DATA_DIR")
    return _resolve_path(value) if value else DATA_DIR


def is_serverless() -> bool:
    return any(os.getenv(name) for name in SERVERLESS_ENV_VARS)


# ── Query routing keywords ────────────────────────────────────────────────────
SQL_KEYWORDS = [
    "how many", "count", "number of", "top", "highest", "lowest", "most", "least",
    "average", "avg", "trend", "over time", "rank", "ranking", "frequently", "dominant", "main"
]
EMBED_KEYWORDS = [
    "explain", "why", "describe", "what is", "what narrative", "how does",
    "context", "meaning", "summary", "narrative about"
]
HYBRID_KEYWORDS = [
    "spike", "spiked", "surge", "drop", "decline", "increase", "decrease",
    "what caused", "cause", "driver", "drivers", "why did"
]

# ── Chunking ─────────────────────────────────────────────────────────────────
CHUNK_MIN_TOKENS = int(os.getenv("HYBRID_CHUNK_MIN_TOKENS", "400"))
CHUNK_MAX_TOKENS = int(os.getenv("HYBRID_CHUNK_MAX_TOKENS", "600"))

# ── Retrieval ────────────────────────────────────────────────────────────────
DEFAULT_TOP_K = int(os.getenv("HYBRID_TOP_K", "6"))

# ── Build behavior ───────────────────────────────────────────────────────────
AUTO_BUILD_INDEX = os.getenv("HYBRID_AUTO_BUILD_INDEX", "0") == "1"
REBUILD_SQL = os.getenv("HYBRID_REBUILD_SQL", "0") == "1"
