"""
hybrid/database.py
-------------------
- Loads all 19 CSVs as DuckDB in-memory views on first call (thread-safe singleton).
- Provides semantic_search() via lightweight lexical similarity.
- Falls back to SQL ILIKE keyword search when in-memory ranking is unavailable.
"""

import logging
import re
import threading

import duckdb

from hybrid.constants import DATA_DIR, CSV_TO_VIEW

logger = logging.getLogger(__name__)

# ── DuckDB singleton ───────────────────────────────────────────────────────────
_db_lock = threading.Lock()
_conn: duckdb.DuckDBPyConnection | None = None


def get_db_connection() -> duckdb.DuckDBPyConnection:
    global _conn
    if _conn is not None:
        return _conn
    with _db_lock:
        if _conn is not None:
            return _conn
        logger.info(f"[DB] Connecting | DATA_DIR={DATA_DIR}")
        _conn = duckdb.connect(database=":memory:", read_only=False)
        _load_all_views(_conn)
    return _conn


def _load_all_views(conn: duckdb.DuckDBPyConnection) -> None:
    loaded, skipped = [], []
    for csv_file, view_name in CSV_TO_VIEW.items():
        path = DATA_DIR / csv_file
        if not path.exists():
            logger.warning(f"[DB] Missing -> skipping '{view_name}': {path}")
            skipped.append(view_name)
            continue
        try:
            conn.execute(
                f"CREATE OR REPLACE VIEW {view_name} AS "
                f"SELECT * FROM read_csv_auto('{path.as_posix()}', "
                f"header=True, all_varchar=False)"
            )
            loaded.append(view_name)
        except Exception as exc:
            logger.error(f"[DB] Failed '{view_name}': {exc}")
            skipped.append(view_name)

    logger.info(f"[DB] Loaded {len(loaded)} views. Skipped: {skipped or 'none'}")


def get_loaded_views() -> list[str]:
    try:
        return get_db_connection().execute("SHOW TABLES").fetchdf()["name"].tolist()
    except Exception:
        return []


def _tokenize(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", str(text).lower()) if len(t) > 2}


def _lexical_score(query_tokens: set[str], title: str) -> float:
    if not query_tokens:
        return 0.0
    title_tokens = _tokenize(title)
    if not title_tokens:
        return 0.0
    overlap = len(query_tokens & title_tokens)
    return float(overlap / max(1, len(query_tokens)))


def semantic_search(topic: str, top_k: int = 5) -> list[dict]:
    """
    Returns top_k posts semantically closest to topic.
    Each result: {id, subreddit, title, date, score, similarity?}
    Falls back to SQL ILIKE if in-memory lexical ranking fails.
    """

    try:
        df = get_db_connection().execute(
            "SELECT id, subreddit, title, "
            "CAST(created_datetime AS VARCHAR) AS date, score "
            "FROM posts LIMIT 5000"
        ).fetchdf()
        records = df.to_dict("records")
        query_tokens = _tokenize(topic)
        scored = []
        for rec in records:
            s = _lexical_score(query_tokens, rec.get("title", ""))
            if s > 0:
                scored.append({**rec, "similarity": round(s, 4)})
        scored.sort(key=lambda x: x["similarity"], reverse=True)
        return scored[:top_k]
    except Exception as exc:
        logger.warning(f"[Search] Lexical ranking failed, falling back: {exc}")
        return _keyword_fallback(topic, top_k)


def _keyword_fallback(topic: str, top_k: int) -> list[dict]:
    try:
        safe = topic.replace("'", "''")
        df = get_db_connection().execute(
            f"SELECT id, subreddit, title, "
            f"CAST(created_datetime AS VARCHAR) AS date, score "
            f"FROM posts WHERE title ILIKE '%{safe}%' "
            f"ORDER BY score DESC LIMIT {top_k}"
        ).fetchdf()
        return df.to_dict("records")
    except Exception:
        return []
