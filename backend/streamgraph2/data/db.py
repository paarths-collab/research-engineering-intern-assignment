"""
db.py — Async database layer with local DuckDB fallback.

If DATABASE_URL is available, streamgraph2 uses asyncpg as before.
If DATABASE_URL is missing/unreachable, streamgraph2 initialises local DuckDB
at backend/data/streamgraph2.duckdb so background jobs and persistence still work.
"""

import json
import re
import uuid
import threading
import pandas as pd
import duckdb
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, List, Optional
from datetime import date, datetime

try:
    import asyncpg
except Exception:  # pragma: no cover
    asyncpg = None

try:
    from streamgraph2.data.config import DATABASE_URL, DUCKDB_PATH
except Exception:
    DATABASE_URL = None
    DUCKDB_PATH = Path(__file__).resolve().parents[2] / "data" / "streamgraph2.duckdb"

# ── Path to the shared CSV data directory ─────────────────────
# db.py lives at: backend/streamgraph2/data/db.py
# parents[3] = project root  →  project_root/data/
_DATA_DIR = Path(__file__).resolve().parents[3] / "data"

# ── Connections (initialised at startup) ──────────────────────
_pool: Optional[Any] = None
_duck_conn: Optional[duckdb.DuckDBPyConnection] = None
_duck_lock = threading.Lock()
_backend_mode: str = "none"


_DUCKDB_TABLES = [
    """
    CREATE TABLE IF NOT EXISTS posts (
        id TEXT,
        subreddit TEXT NOT NULL,
        title TEXT NOT NULL,
        author TEXT,
        score INTEGER DEFAULT 0,
        num_comments INTEGER DEFAULT 0,
        created_utc TIMESTAMP NOT NULL,
        source TEXT DEFAULT 'historical',
        url TEXT,
        embedding TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (id, subreddit)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS comments (
        id TEXT PRIMARY KEY,
        post_id TEXT,
        author TEXT,
        body TEXT,
        score INTEGER DEFAULT 0,
        created_utc TIMESTAMP,
        embedding TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS daily_volume (
        date DATE PRIMARY KEY,
        post_count INTEGER,
        rolling_mean DOUBLE,
        rolling_std DOUBLE,
        z_score DOUBLE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS echo_chamber_scores (
        subreddit TEXT PRIMARY KEY,
        echo_score DOUBLE,
        polarization_score DOUBLE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS subreddit_domain_flow (
        subreddit TEXT,
        domain TEXT,
        post_count INTEGER,
        PRIMARY KEY (subreddit, domain)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS top_distinctive_domains (
        subreddit TEXT,
        domain TEXT,
        count INTEGER,
        category TEXT,
        lift DOUBLE,
        p_domain_given_sub DOUBLE,
        p_domain_global DOUBLE,
        PRIMARY KEY (subreddit, domain)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS bridge_authors (
        author TEXT,
        subreddit_1 TEXT,
        subreddit_2 TEXT,
        bridge_score DOUBLE,
        PRIMARY KEY (author, subreddit_1, subreddit_2)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS spike_jobs (
        job_id TEXT PRIMARY KEY,
        spike_date DATE NOT NULL,
        status TEXT DEFAULT 'processing',
        error_msg TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        completed_at TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS topic_results (
        job_id TEXT,
        topic_id INTEGER,
        size INTEGER,
        size_percent DOUBLE,
        keywords TEXT,
        centroid TEXT,
        PRIMARY KEY (job_id, topic_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS news_cache (
        date DATE,
        headline TEXT,
        source TEXT,
        url TEXT,
        embedding TEXT,
        PRIMARY KEY (date, headline)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS news_matches (
        job_id TEXT,
        topic_id INTEGER,
        headline TEXT,
        source TEXT,
        url TEXT,
        similarity DOUBLE,
        PRIMARY KEY (job_id, topic_id, headline)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sentiment_daily (
        job_id TEXT,
        date DATE,
        negative_percent DOUBLE,
        neutral_percent DOUBLE,
        positive_percent DOUBLE,
        sample_count INTEGER,
        PRIMARY KEY (job_id, date)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS spike_metrics (
        job_id TEXT PRIMARY KEY,
        baseline_count INTEGER,
        spike_count INTEGER,
        acceleration_ratio DOUBLE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS catalyst_briefs (
        job_id TEXT PRIMARY KEY,
        brief_text TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS agent_diagnostics (
        id TEXT PRIMARY KEY,
        job_id TEXT,
        agent_name TEXT NOT NULL,
        status TEXT,
        findings TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
]


class _DuckConnAdapter:
    """Async-like adapter exposing asyncpg-style methods over DuckDB."""

    def __init__(self, connection: duckdb.DuckDBPyConnection):
        self._conn = connection

    async def execute(self, sql: str, *params):
        _duck_execute(self._conn, sql, params, mode="execute")

    async def executemany(self, sql: str, args_list: list):
        if not args_list:
            return
        translated_sql, _ = _translate_sql(sql, ())
        with _duck_lock:
            self._conn.executemany(
                translated_sql,
                [tuple(_normalize_param(v) for v in row) for row in args_list],
            )

    async def fetch(self, sql: str, *params):
        return _duck_execute(self._conn, sql, params, mode="fetch")

    async def fetchrow(self, sql: str, *params):
        return _duck_execute(self._conn, sql, params, mode="fetchrow")


def _normalize_param(value):
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return value


def _translate_sql(sql: str, params: tuple[Any, ...]) -> tuple[str, list[Any]]:
    placeholders = re.findall(r"\$(\d+)", sql)
    if placeholders:
        ordered_params = []
        for p in placeholders:
            idx = int(p) - 1
            ordered_params.append(params[idx] if idx < len(params) else None)
        sql = re.sub(r"\$\d+", "?", sql)
        params_out = [_normalize_param(v) for v in ordered_params]
    else:
        params_out = [_normalize_param(v) for v in params]

    # Strip postgres casts like ::vector, ::text, ::jsonb
    sql = re.sub(r"::[A-Za-z_][A-Za-z0-9_]*(?:\([^)]+\))?", "", sql)
    sql = sql.replace("NOW()", "CURRENT_TIMESTAMP")
    return sql, params_out


def _duck_execute(connection: duckdb.DuckDBPyConnection, sql: str, params: tuple[Any, ...], mode: str):
    translated_sql, translated_params = _translate_sql(sql, params)
    with _duck_lock:
        cur = connection.execute(translated_sql, translated_params)
        if mode == "execute":
            return None
        rows = cur.fetchall()
        cols = [c[0] for c in (cur.description or [])]
        out = [dict(zip(cols, row)) for row in rows]
        if mode == "fetchrow":
            return out[0] if out else None
        return out


async def init_db():
    global _duck_conn
    if _duck_conn is None:
        DUCKDB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _duck_conn = duckdb.connect(str(DUCKDB_PATH))
    for stmt in _DUCKDB_TABLES:
        _duck_conn.execute(stmt)


async def init_pool():
    global _pool, _backend_mode
    if DATABASE_URL and asyncpg is not None:
        try:
            _pool = await asyncpg.create_pool(
                DATABASE_URL,
                min_size=2,
                max_size=10,
                command_timeout=60,
            )
            async with _pool.acquire() as c:
                await c.execute("SET search_path TO public")
            _backend_mode = "postgres"
            print("[ok] streamgraph2 Postgres pool ready")
            return
        except Exception as e:
            print(f"[warn] streamgraph2: Postgres pool failed ({e}) - switching to DuckDB")
            _pool = None

    await init_db()
    _backend_mode = "duckdb"
    print(f"[ok] streamgraph2 DuckDB ready ({DUCKDB_PATH})")


async def close_pool():
    global _duck_conn, _backend_mode
    if _pool:
        await _pool.close()
    if _duck_conn:
        _duck_conn.close()
        _duck_conn = None
    _backend_mode = "none"


@asynccontextmanager
async def conn():
    if _pool is not None:
        async with _pool.acquire() as c:
            yield c
        return
    if _duck_conn is not None:
        yield _DuckConnAdapter(_duck_conn)
        return
    raise RuntimeError("DB backend is not initialised")


# ── Vector helpers ────────────────────────────────────────────

def vec_to_pg(v: List[float]) -> str:
    """Convert Python list to pgvector literal string."""
    return "[" + ",".join(str(x) for x in v) + "]"


def pg_to_vec(s: str) -> List[float]:
    """Convert pgvector string back to Python list."""
    if not s:
        return []
    try:
        return [float(x) for x in str(s).strip("[]").split(",") if str(x).strip()]
    except Exception:
        return []


_POSTS_EMB_DF: Optional[pd.DataFrame] = None


def _load_posts_with_embeddings() -> pd.DataFrame:
    global _POSTS_EMB_DF
    if _POSTS_EMB_DF is not None:
        return _POSTS_EMB_DF

    posts_path = _DATA_DIR / "clean_posts.csv"
    emb_path = _DATA_DIR / "title_embeddings_v2.npy"
    if not posts_path.exists():
        _POSTS_EMB_DF = pd.DataFrame(columns=["id", "title", "created_datetime", "embedding"])
        return _POSTS_EMB_DF

    df = pd.read_csv(posts_path, usecols=["id", "title", "created_datetime"], parse_dates=["created_datetime"])
    if emb_path.exists():
        import numpy as np
        emb = np.load(emb_path)
        n = min(len(df), len(emb))
        df = df.iloc[:n].copy()
        df["embedding"] = ["[" + ",".join(str(float(v)) for v in row) + "]" for row in emb[:n]]
    else:
        df["embedding"] = None

    _POSTS_EMB_DF = df
    return _POSTS_EMB_DF


# ── Posts ─────────────────────────────────────────────────────

async def upsert_post(
    id: str, subreddit: str, title: str, author: str,
    score: int, num_comments: int, created_utc: datetime,
    source: str, embedding: Optional[List[float]] = None,
    url: str = None
):
    emb = vec_to_pg(embedding) if embedding else None
    async with conn() as c:
        await c.execute("""
            INSERT INTO posts (id, subreddit, title, author, score, num_comments,
                               created_utc, source, url, embedding)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10::vector)
            ON CONFLICT (id, subreddit) DO NOTHING
        """, id, subreddit, title, author, score, num_comments, created_utc, source, url, emb)

async def upsert_posts_bulk(args_list: list):
    async with conn() as c:
        await c.executemany("""
            INSERT INTO posts (id, subreddit, title, author, score, num_comments,
                               created_utc, source, url, embedding)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10::vector)
            ON CONFLICT (id, subreddit) DO NOTHING
        """, args_list)



async def get_posts_for_date(target_date: date) -> List[dict]:
    async with conn() as c:
        rows = await c.fetch("""
            SELECT id, title, embedding::text
            FROM posts
            WHERE DATE(created_utc) = $1
        """, target_date)
        if rows:
            return rows

    # Fallback for local mode when posts table is empty.
    df = _load_posts_with_embeddings()
    if df.empty:
        return []
    sub = df[df["created_datetime"].dt.date == target_date]
    if sub.empty:
        return []
    return sub[["id", "title", "embedding"]].to_dict("records")


async def count_posts_for_date(target_date: date) -> int:
    async with conn() as c:
        row = await c.fetchrow("SELECT COUNT(*) FROM posts WHERE DATE(created_utc) = $1", target_date)
        if row:
            if "count_star()" in row:
                return int(row["count_star()"] or 0)
            if "count" in row:
                return int(row["count"] or 0)
            if "COUNT(*)" in row:
                return int(row["COUNT(*)"] or 0)
            return int(next(iter(row.values())) or 0)

    df = _load_posts_with_embeddings()
    if df.empty:
        return 0
    return int((df["created_datetime"].dt.date == target_date).sum())


# ── Comments ──────────────────────────────────────────────────

async def upsert_comment(
    id: str, post_id: str, author: str, body: str,
    score: int, created_utc: datetime,
    embedding: Optional[List[float]] = None
):
    emb = vec_to_pg(embedding) if embedding else None
    async with conn() as c:
        await c.execute("""
            INSERT INTO comments (id, post_id, author, body, score, created_utc, embedding)
            VALUES ($1,$2,$3,$4,$5,$6,$7::vector)
            ON CONFLICT (id) DO NOTHING
        """, id, post_id, author, body, score, created_utc, emb)


async def get_texts_for_date(target_date: date) -> List[str]:
    """Return all post titles + comment bodies for a date (for sentiment)."""
    async with conn() as c:
        rows = await c.fetch("""
            SELECT p.title AS text FROM posts p WHERE DATE(p.created_utc) = $1
            UNION ALL
            SELECT c.body AS text FROM comments c WHERE DATE(c.created_utc) = $1
        """, target_date)
        if rows:
            return [r["text"] for r in rows if r["text"]]

    df = _load_posts_with_embeddings()
    if df.empty:
        return []
    sub = df[df["created_datetime"].dt.date == target_date]
    return [str(v) for v in sub["title"].dropna().tolist()]


# ── Daily Volume ──────────────────────────────────────────────

async def upsert_volume(
    date_val: date, post_count: int,
    rolling_mean: float, rolling_std: float, z_score: float
):
    async with conn() as c:
        await c.execute("""
            INSERT INTO daily_volume (date, post_count, rolling_mean, rolling_std, z_score)
            VALUES ($1,$2,$3,$4,$5)
            ON CONFLICT (date) DO UPDATE
            SET post_count=$2, rolling_mean=$3, rolling_std=$4, z_score=$5
        """, date_val, post_count, rolling_mean, rolling_std, z_score)


async def get_volume_series() -> List[dict]:
    """Daily volume with z-scores. Reads from CSV if DB unavailable."""
    if _backend_mode in {"postgres", "duckdb"}:
        try:
            async with conn() as c:
                rows = await c.fetch("SELECT * FROM daily_volume ORDER BY date")
                if rows:
                    return [dict(r) for r in rows]
        except Exception:
            pass

    # ── CSV fallback ──────────────────────────────────────────
    csv_path = _DATA_DIR / "daily_volume_v2.csv"
    if not csv_path.exists():
        return []

    df = pd.read_csv(csv_path, parse_dates=["created_datetime"])
    df = df.rename(columns={"created_datetime": "date"})
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df = df.sort_values("date").reset_index(drop=True)
    df["rolling_mean"] = df["post_count"].rolling(7, min_periods=1).mean().round(2)
    df["rolling_std"]  = df["post_count"].rolling(7, min_periods=1).std().fillna(0).round(2)
    df["z_score"]      = (
        (df["post_count"] - df["rolling_mean"]) / df["rolling_std"].replace(0, 1)
    ).round(3)

    return df[["date", "post_count", "rolling_mean", "rolling_std", "z_score"]].to_dict("records")


async def get_streamgraph_series() -> List[dict]:
    """Post counts by date × subreddit. Reads from CSV if DB unavailable."""
    if _backend_mode in {"postgres", "duckdb"}:
        try:
            async with conn() as c:
                rows = await c.fetch("""
                    SELECT DATE(created_utc) as date, subreddit, COUNT(*) as count
                    FROM posts
                    GROUP BY DATE(created_utc), subreddit
                    ORDER BY date, subreddit
                """)
                if rows:
                    return [dict(r) for r in rows]
        except Exception:
            pass

    # ── CSV fallback ──────────────────────────────────────────
    csv_path = _DATA_DIR / "clean_posts.csv"
    if not csv_path.exists():
        return []

    df = pd.read_csv(csv_path, parse_dates=["created_datetime"],
                     usecols=["created_datetime", "subreddit"])
    df["date"]      = df["created_datetime"].dt.date
    df["subreddit"] = df["subreddit"].fillna("unknown").astype(str)
    agg = (
        df.groupby(["date", "subreddit"])
          .size()
          .reset_index(name="count")
          .sort_values(["date", "subreddit"])
    )
    return agg.to_dict("records")


# ── Spike Jobs ────────────────────────────────────────────────

async def create_spike_job(spike_date: date) -> str:
    job_id = str(uuid.uuid4())
    async with conn() as c:
        row = await c.fetchrow("""
            INSERT INTO spike_jobs (job_id, spike_date) VALUES ($1, $2) RETURNING job_id
        """, job_id, spike_date)
        return str(row["job_id"]) if row and "job_id" in row else job_id


async def update_job_status(job_id: str, status: str, error_msg: str = None):
    from datetime import datetime as dt
    completed = dt.utcnow() if status in ("done", "failed") else None
    async with conn() as c:
        await c.execute("""
            UPDATE spike_jobs SET status=$2, error_msg=$3, completed_at=$4 WHERE job_id=$1
        """, job_id, status, error_msg, completed)


async def get_job(job_id: str) -> Optional[dict]:
    async with conn() as c:
        return await c.fetchrow("SELECT * FROM spike_jobs WHERE job_id=$1", job_id)


async def get_full_job_result(job_id: str) -> dict:
    """Assemble complete result for a finished job."""
    async with conn() as c:
        job     = await c.fetchrow("SELECT * FROM spike_jobs WHERE job_id=$1", job_id)
        topics  = await c.fetch("SELECT * FROM topic_results WHERE job_id=$1 ORDER BY topic_id", job_id)
        matches = await c.fetch("SELECT * FROM news_matches WHERE job_id=$1 ORDER BY topic_id, similarity DESC", job_id)
        sents   = await c.fetch("SELECT * FROM sentiment_daily WHERE job_id=$1 ORDER BY date", job_id)
        metrics = await c.fetchrow("SELECT * FROM spike_metrics WHERE job_id=$1", job_id)
        brief   = await c.fetchrow("SELECT brief_text FROM catalyst_briefs WHERE job_id=$1", job_id)
        diags   = await c.fetch("SELECT * FROM agent_diagnostics WHERE job_id=$1 ORDER BY created_at", job_id)

    if not job:
        return {"job_id": job_id, "status": "missing"}

    return {
        "job_id": job_id,
        "spike_date": str(job["spike_date"]),
        "status": job["status"],
        "metrics": dict(metrics) if metrics else {},
        "topics": [dict(t) for t in topics],
        "news_matches": [dict(m) for m in matches],
        "sentiment": [dict(s) for s in sents],
        "brief": brief["brief_text"] if brief else None,
        "agent_diagnostics": [dict(d) for d in diags],
    }


# ── Topic Results ─────────────────────────────────────────────

async def save_topic(
    job_id: str, topic_id: int, size: int,
    size_percent: float, keywords: list, centroid: List[float]
):
    async with conn() as c:
        await c.execute("""
            INSERT INTO topic_results (job_id, topic_id, size, size_percent, keywords, centroid)
            VALUES ($1,$2,$3,$4,$5,$6::vector)
            ON CONFLICT (job_id, topic_id) DO NOTHING
        """, job_id, topic_id, size, size_percent, json.dumps(keywords), vec_to_pg(centroid))


async def get_topic_centroids(job_id: str) -> List[dict]:
    async with conn() as c:
        rows = await c.fetch("""
            SELECT topic_id, keywords, centroid::text FROM topic_results WHERE job_id=$1
        """, job_id)
        return [
            {
                "topic_id": r["topic_id"],
                "keywords": json.loads(r["keywords"]) if isinstance(r.get("keywords"), str) else r.get("keywords", []),
                "centroid": pg_to_vec(r["centroid"]),
            }
            for r in rows
        ]


# ── News Cache ────────────────────────────────────────────────

async def save_news_item(
    date_val: date, headline: str, source: str,
    url: str, embedding: List[float]
):
    async with conn() as c:
        await c.execute("""
            INSERT INTO news_cache (date, headline, source, url, embedding)
            VALUES ($1,$2,$3,$4,$5::vector)
            ON CONFLICT (date, headline) DO NOTHING
        """, date_val, headline, source, url, vec_to_pg(embedding))


async def get_news_for_date(date_val: date) -> List[dict]:
    async with conn() as c:
        rows = await c.fetch("""
            SELECT headline, source, url, embedding::text FROM news_cache WHERE date=$1
        """, date_val)
        return [
            {
                "headline": r["headline"],
                "source": r["source"],
                "url": r["url"],
                "embedding": pg_to_vec(r["embedding"]) if r.get("embedding") else [],
            }
            for r in rows
        ]


# ── News Matches ──────────────────────────────────────────────

async def save_news_match(
    job_id: str, topic_id: int, headline: str,
    source: str, url: str, similarity: float
):
    async with conn() as c:
        await c.execute("""
            INSERT INTO news_matches (job_id, topic_id, headline, source, url, similarity)
            VALUES ($1,$2,$3,$4,$5,$6)
            ON CONFLICT (job_id, topic_id, headline) DO NOTHING
        """, job_id, topic_id, headline, source, url, similarity)


# ── Sentiment ─────────────────────────────────────────────────

async def save_sentiment(
    job_id: str, date_val: date,
    neg: float, neu: float, pos: float, sample_count: int
):
    async with conn() as c:
        await c.execute("""
            INSERT INTO sentiment_daily
                (job_id, date, negative_percent, neutral_percent, positive_percent, sample_count)
            VALUES ($1,$2,$3,$4,$5,$6)
            ON CONFLICT (job_id, date) DO UPDATE
            SET negative_percent=$3, neutral_percent=$4, positive_percent=$5, sample_count=$6
        """, job_id, date_val, neg, neu, pos, sample_count)


# ── Spike Metrics ─────────────────────────────────────────────

async def save_spike_metrics(
    job_id: str, baseline: int, spike: int, ratio: float
):
    async with conn() as c:
        await c.execute("""
            INSERT INTO spike_metrics (job_id, baseline_count, spike_count, acceleration_ratio)
            VALUES ($1,$2,$3,$4)
            ON CONFLICT (job_id) DO UPDATE
            SET baseline_count=$2, spike_count=$3, acceleration_ratio=$4
        """, job_id, baseline, spike, ratio)


# ── Catalyst Brief ────────────────────────────────────────────

async def save_brief(job_id: str, brief_text: str):
    async with conn() as c:
        await c.execute("""
            INSERT INTO catalyst_briefs (job_id, brief_text)
            VALUES ($1,$2)
            ON CONFLICT (job_id) DO UPDATE SET brief_text=$2
        """, job_id, brief_text)


# ── Agent Diagnostics ─────────────────────────────────────────

async def save_diagnostic(
    job_id: str, agent_name: str, status: str, findings: dict
):
    diag_id = str(uuid.uuid4())
    async with conn() as c:
        await c.execute("""
            INSERT INTO agent_diagnostics (id, job_id, agent_name, status, findings)
            VALUES ($1,$2,$3,$4,$5)
        """, diag_id, job_id, agent_name, status, json.dumps(findings))


def get_backend_mode() -> str:
    """Return active backend mode: postgres | duckdb | none."""
    return _backend_mode


# ═══════════════════════════════════════════════════════════════
# ── Cluster-based Streamgraph (new 5-cluster pipeline) ────────
# ═══════════════════════════════════════════════════════════════

async def get_clustered_streamgraph() -> dict:
    """
    Return daily post counts for each of the 5 narrative clusters,
    plus per-cluster spike events (z_score >= 2.0).

    Shape:
        {
          "keys": ["Geopolitics", "US Politics", ...],
          "data": [{"date": "YYYY-MM-DD", "Geopolitics": 12, ...}],
          "spikes": [{"date": ..., "cluster": ..., "z_score": ..., "post_count": ...}]
        }
    """
    from streamgraph2.data.cluster_pipeline import get_clustered_df, ORDERED_CLUSTERS

    df = get_clustered_df()
    df["date"] = pd.to_datetime(df["date"]).dt.date

    agg = (
        df.groupby(["date", "cluster_label"])
          .size()
          .reset_index(name="count")
          .sort_values("date")
    )

    # Pivot → wide format (one column per cluster)
    pivot = (
        agg.pivot(index="date", columns="cluster_label", values="count")
           .fillna(0)
           .reset_index()
    )

    data = []
    for _, row in pivot.iterrows():
        item = {"date": str(row["date"])}
        for label in ORDERED_CLUSTERS:
            item[label] = int(row.get(label, 0))
        data.append(item)

    # Per-cluster z-score spike detection
    spikes = []
    for label in ORDERED_CLUSTERS:
        series = agg[agg["cluster_label"] == label].sort_values("date").copy()
        series = series.reset_index(drop=True)
        series["rolling_mean"] = series["count"].rolling(7, min_periods=1).mean()
        series["rolling_std"]  = series["count"].rolling(7, min_periods=1).std().fillna(0)
        series["z_score"] = (
            (series["count"] - series["rolling_mean"])
            / series["rolling_std"].replace(0, 1)
        ).round(3)

        for _, sr in series[series["z_score"] >= 2.0].iterrows():
            spike_date = sr["date"]
            # Find top headline for this cluster + date
            day_hits = df[(df["date"] == spike_date) & (df["cluster_label"] == label)]
            top_headline = ""
            if not day_hits.empty:
                # Use score if available, otherwise just first title
                if "score" in day_hits.columns:
                    top_row = day_hits.loc[day_hits["score"].idxmax()]
                    top_headline = str(top_row["title"])
                else:
                    top_headline = str(day_hits.iloc[0]["title"])

            spikes.append({
                "date":         str(spike_date),
                "cluster":      label,
                "z_score":      round(float(sr["z_score"]), 3),
                "post_count":   int(sr["count"]),
                "top_headline": top_headline,
            })

    spikes.sort(key=lambda x: x["date"])
    return {"keys": ORDERED_CLUSTERS, "data": data, "spikes": spikes}


async def get_event_window_topics(
    cluster: str,
    event_date_str: str,
    window: int = 10,
) -> dict:
    """
    Extract the ±window-day post context for a spike event.

    Returns:
        cluster, event_date, topics (top 5 TF-IDF phrases),
        total_posts, top_subreddits, top_domains, headline_examples
    """
    from datetime import timedelta, date as date_t
    from streamgraph2.data.cluster_pipeline import get_clustered_df

    df = get_clustered_df()
    df["date"] = pd.to_datetime(df["date"]).dt.date

    event_date = date_t.fromisoformat(event_date_str)
    date_lo    = event_date - timedelta(days=window)
    date_hi    = event_date + timedelta(days=window)

    mask = (
        (df["cluster_label"] == cluster)
        & (df["date"] >= date_lo)
        & (df["date"] <= date_hi)
    )
    window_df = df[mask].copy()

    if window_df.empty:
        return {
            "cluster":           cluster,
            "event_date":        event_date_str,
            "topics":            [],
            "total_posts":       0,
            "top_subreddits":    [],
            "top_domains":       [],
            "headline_examples": [],
        }

    titles = window_df["title"].dropna().astype(str).tolist()

    # Lightweight phrase extraction (no external ML runtime dependencies).
    import re
    from collections import Counter

    _stop = {
        "that", "this", "with", "from", "they", "have", "been", "more", "will", "just",
        "your", "about", "after", "there", "their", "would", "could", "should", "into", "over",
        "under", "between", "against", "while", "where", "which", "because", "across", "among",
    }

    tokenized = [re.findall(r"\b[a-zA-Z]{4,}\b", t.lower()) for t in titles]
    unigram = Counter()
    bigram = Counter()
    trigram = Counter()

    for toks in tokenized:
        filt = [w for w in toks if w not in _stop]
        unigram.update(filt)
        bigram.update(" ".join(filt[i:i + 2]) for i in range(len(filt) - 1))
        trigram.update(" ".join(filt[i:i + 3]) for i in range(len(filt) - 2))

    candidates = []
    candidates.extend((phrase, count) for phrase, count in trigram.items() if count >= 2)
    candidates.extend((phrase, count) for phrase, count in bigram.items() if count >= 2)
    candidates.extend((phrase, count) for phrase, count in unigram.items())

    seen = set()
    topics: list[str] = []
    for phrase, _ in sorted(candidates, key=lambda x: x[1], reverse=True):
        norm = phrase.strip().lower()
        if not norm or norm in seen:
            continue
        seen.add(norm)
        topics.append(norm.title())
        if len(topics) == 5:
            break

    top_subreddits = [
        [k, int(v)]
        for k, v in window_df["subreddit"].value_counts().head(5).items()
    ]
    top_domains = [
        [k, int(v)]
        for k, v in window_df["domain"].dropna().value_counts().head(5).items()
    ]
    headline_examples = titles[:5]

    return {
        "cluster":           cluster,
        "event_date":        event_date_str,
        "topics":            topics,
        "total_posts":       len(window_df),
        "top_subreddits":    top_subreddits,
        "top_domains":       top_domains,
        "headline_examples": headline_examples,
    }


if __name__ == "__main__":
    import asyncio
    from datetime import date as _date

    async def _smoke_test():
        print("Running streamgraph2 DuckDB smoke test...")
        await init_pool()
        print(f"Backend mode: {get_backend_mode()}")

        today = _date.today()
        job_id = await create_spike_job(today)
        await save_spike_metrics(job_id, baseline=10, spike=25, ratio=2.5)
        await save_sentiment(job_id, today, neg=20.0, neu=50.0, pos=30.0, sample_count=100)
        await save_brief(job_id, "DuckDB smoke-test brief.")
        await save_diagnostic(
            job_id=job_id,
            agent_name="smoke_test",
            status="pass",
            findings={"message": "local duckdb write ok"},
        )
        await update_job_status(job_id, "done")

        result = await get_full_job_result(job_id)
        print(
            "Smoke test complete:",
            {
                "job_id": result.get("job_id"),
                "status": result.get("status"),
                "metrics": result.get("metrics"),
                "sentiment_rows": len(result.get("sentiment", [])),
                "diagnostics_rows": len(result.get("agent_diagnostics", [])),
            },
        )
        print(f"DuckDB path: {DUCKDB_PATH}")
        await close_pool()

    asyncio.run(_smoke_test())
