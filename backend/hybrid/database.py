"""
hybrid/database.py
-------------------
- Loads all 19 CSVs as DuckDB in-memory views on first call (thread-safe singleton).
- Provides semantic_search() via sentence-transformers (all-MiniLM-L6-v2).
- Falls back to SQL ILIKE keyword search when embeddings are unavailable.
"""

import logging
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


# ── Embedder singleton ─────────────────────────────────────────────────────────
_emb_lock    = threading.Lock()
_embedder    = None       # SentenceTransformer or "unavailable"
_emb_matrix  = None       # numpy ndarray, pre-normalised
_emb_records: list[dict] = []


def _init_embedder() -> None:
    global _embedder, _emb_matrix, _emb_records
    if _embedder is not None:
        return
    with _emb_lock:
        if _embedder is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer
            logger.info("[Embedder] Loading all-MiniLM-L6-v2...")
            model = SentenceTransformer("all-MiniLM-L6-v2")
            df = get_db_connection().execute(
                "SELECT id, subreddit, title, "
                "CAST(created_datetime AS VARCHAR) AS date, score "
                "FROM posts LIMIT 5000"
            ).fetchdf()
            _emb_records = df.to_dict("records")
            _emb_matrix  = model.encode(
                df["title"].tolist(),
                batch_size=64,
                show_progress_bar=False,
                normalize_embeddings=True,
            )
            _embedder = model
            logger.info(f"[Embedder] Embedded {len(_emb_records)} titles.")
        except ImportError:
            logger.warning("[Embedder] sentence-transformers not installed -> SQL fallback.")
            _embedder = "unavailable"
        except Exception as exc:
            logger.error(f"[Embedder] Init failed: {exc}")
            _embedder = "unavailable"


def semantic_search(topic: str, top_k: int = 5) -> list[dict]:
    """
    Returns top_k posts semantically closest to topic.
    Each result: {id, subreddit, title, date, score, similarity?}
    Falls back to SQL ILIKE if embeddings unavailable.
    """
    _init_embedder()
    if _embedder == "unavailable" or _emb_matrix is None:
        return _keyword_fallback(topic, top_k)
    try:
        q = _embedder.encode([topic], normalize_embeddings=True)
        sims = (_emb_matrix @ q.T).flatten()
        top_idx = sims.argsort()[::-1][:top_k]
        return [
            {**_emb_records[i], "similarity": round(float(sims[i]), 4)}
            for i in top_idx
        ]
    except Exception as exc:
        logger.warning(f"[Embedder] Search error, falling back: {exc}")
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
