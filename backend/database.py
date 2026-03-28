import duckdb
import numpy as np
import pandas as pd
from pathlib import Path
import os
import logging
import re

logger = logging.getLogger(__name__)

# === PATHS ===
BASE_DIR = Path(__file__).parent.parent
DATA_PATH = Path(os.getenv("DATA_PATH", str(BASE_DIR / "data")))
DB_PATH   = DATA_PATH / "analysis_v2.db"
CSV_PATH  = DATA_PATH / "clean_with_clusters_v2.csv"

# === GLOBAL SINGLETONS ===
CONN       = None
POSTS_DF   = None


def get_db_connection():
    """Lazy singleton DuckDB connection, mounts new CSV datasets."""
    global CONN
    if CONN is None:
        print(f"🦆 Connecting to DuckDB at {DB_PATH}...")
        CONN = duckdb.connect(str(DB_PATH), read_only=False) # Changed to False to create views
        # Mount new CSVs as views
        data_dir = DATA_PATH
        csv_mappings = {
            "narratives": "narrative_intelligence_summary.csv",
            "topics": "narrative_topic_mapping.csv",
            "chains": "narrative_spread_chain_table.csv",
            "amplification": "author_amplification_summary.csv",
            "daily_volume": "daily_volume_v2.csv",
            "echo_chambers": "echo_chamber_scores.csv",
            "ideological_matrix": "ideological_distance_matrix.csv"
        }
        for view_name, file_name in csv_mappings.items():
            file_path = data_dir / file_name
            if file_path.exists():
                if view_name == "narratives":
                    CONN.execute(f"CREATE OR REPLACE VIEW narratives AS SELECT narrative_id AS internal_system_id, title AS narrative_theme, domains, top_subreddits, top_authors FROM read_csv_auto('{file_path}')")
                elif view_name == "topics":
                    CONN.execute(f"CREATE OR REPLACE VIEW topics AS SELECT narrative_id AS internal_system_id, topic_cluster, topic_label FROM read_csv_auto('{file_path}')")
                elif view_name == "chains":
                    CONN.execute(f"CREATE OR REPLACE VIEW chains AS SELECT narrative_id AS internal_system_id, step_number, from_subreddit, to_subreddit, minutes_to_jump FROM read_csv_auto('{file_path}')")
                else:
                    CONN.execute(f"CREATE OR REPLACE VIEW {view_name} AS SELECT * FROM read_csv_auto('{file_path}')")
                
    return CONN


def get_vector_store():
    """Lazy-load posts dataframe used for lightweight lexical search."""
    global POSTS_DF
    if POSTS_DF is None:
        print(f"📄 Loading posts CSV from {CSV_PATH}...")
        POSTS_DF = pd.read_csv(str(CSV_PATH))

    return POSTS_DF


def _tokenize(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", str(text).lower()) if len(t) > 2}


def _lexical_score(query_tokens: set[str], title: str) -> float:
    if not query_tokens:
        return 0.0
    title_tokens = _tokenize(title)
    if not title_tokens:
        return 0.0
    overlap = len(query_tokens & title_tokens)
    base = overlap / max(1, len(query_tokens))
    return float(base)


def semantic_search(query: str, top_k: int = 5):
    """Find posts using lightweight lexical similarity over titles."""
    posts_df = get_vector_store()
    if posts_df is None:
        raise RuntimeError("Vector store is not initialized")

    query_tokens = _tokenize(query)
    if not query_tokens:
        return []

    titles = posts_df["title"].fillna("").astype(str).tolist() if "title" in posts_df else []
    if not titles:
        return []

    scores = np.asarray([_lexical_score(query_tokens, title) for title in titles], dtype="float32")
    top_indices = scores.argsort()[-top_k:][::-1]

    results = []
    for idx in top_indices:
        row = posts_df.iloc[idx]
        results.append({
            "title":     str(row.get("title", "")),
            "subreddit": str(row.get("subreddit", "")),
            "date":      str(row.get("created_datetime", "")),
            "score":     round(float(scores[idx]), 4),
        })

    return results


# ── Sankey helpers (used by main.py /api/sankey + /api/analyze-domain) ────────

# Per-call connection for short-lived sankey queries (separate from singleton)
def get_conn():
    """Per-call DuckDB connection for sankey endpoints, mounts new CSVs."""
    conn = duckdb.connect(str(DB_PATH), read_only=False)
    data_dir = DATA_PATH
    csv_mappings = {
        "narratives": "narrative_intelligence_summary.csv",
        "topics": "narrative_topic_mapping.csv",
        "chains": "narrative_spread_chain_table.csv",
        "amplification": "author_amplification_summary.csv",
        "daily_volume": "daily_volume_v2.csv",
        "echo_chambers": "echo_chamber_scores.csv",
        "ideological_matrix": "ideological_distance_matrix.csv"
    }
    for view_name, file_name in csv_mappings.items():
        file_path = data_dir / file_name
        if file_path.exists():
            if view_name == "narratives":
                conn.execute(f"CREATE OR REPLACE VIEW narratives AS SELECT narrative_id AS internal_system_id, title AS narrative_theme, domains, top_subreddits, top_authors FROM read_csv_auto('{file_path}')")
            elif view_name == "topics":
                conn.execute(f"CREATE OR REPLACE VIEW topics AS SELECT narrative_id AS internal_system_id, topic_cluster, topic_label FROM read_csv_auto('{file_path}')")
            elif view_name == "chains":
                conn.execute(f"CREATE OR REPLACE VIEW chains AS SELECT narrative_id AS internal_system_id, step_number, from_subreddit, to_subreddit, minutes_to_jump FROM read_csv_auto('{file_path}')")
            else:
                conn.execute(f"CREATE OR REPLACE VIEW {view_name} AS SELECT * FROM read_csv_auto('{file_path}')")
    return conn


VALID_SUBREDDITS = [
    "politics", "Conservative", "Anarchism", "Liberal", "Republican",
    "PoliticalDiscussion", "socialism", "worldpolitics", "democrats", "neoliberal"
]


def get_sankey_data(start_date: str, end_date: str, threshold: int = 5) -> dict:
    """
    Returns Sankey diagram data: subreddits → domains.
    threshold = minimum number of posts a domain must have to appear.
    """
    subs = ", ".join(f"'{s}'" for s in VALID_SUBREDDITS)
    sql = f"""
        SELECT
            subreddit,
            url,
            COUNT(*) as post_count
        FROM posts
        WHERE
            subreddit IN ({subs})
            AND url IS NOT NULL
            AND url NOT LIKE '%reddit.com%'
            AND url NOT LIKE '%redd.it%'
            AND CAST(created_datetime AS DATE) BETWEEN '{start_date}' AND '{end_date}'
        GROUP BY subreddit, url
        HAVING COUNT(*) >= 1
    """

    try:
        conn = get_conn()
        df = conn.execute(sql).df()
        conn.close()
    except Exception as e:
        logger.error(f"Sankey query failed: {e}")
        return {"nodes": [], "links": []}

    def extract_domain(url: str) -> str:
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            domain = parsed.netloc.replace("www.", "")
            return domain if domain else "unknown"
        except:
            return "unknown"

    if df.empty:
        return {"nodes": [], "links": []}

    df["domain"] = df["url"].apply(extract_domain)

    agg = df.groupby(["subreddit", "domain"])["post_count"].sum().reset_index()

    domain_totals = agg.groupby("domain")["post_count"].sum()
    valid_domains = domain_totals[domain_totals >= threshold].index
    agg = agg[agg["domain"].isin(valid_domains)]

    if agg.empty:
        return {"nodes": [], "links": []}

    subreddits = sorted(agg["subreddit"].unique().tolist())
    domains = sorted(agg["domain"].unique().tolist())

    nodes = [{"id": s, "type": "subreddit"} for s in subreddits] + \
            [{"id": d, "type": "domain"} for d in domains]

    node_index = {n["id"]: i for i, n in enumerate(nodes)}

    links = []
    for _, row in agg.iterrows():
        src = node_index.get(row["subreddit"])
        tgt = node_index.get(row["domain"])
        if src is not None and tgt is not None:
            links.append({
                "source": src,
                "target": tgt,
                "value": int(row["post_count"])
            })

    return {"nodes": nodes, "links": links}


def get_domain_urls(domain: str, start_date: str, end_date: str, limit: int = 10) -> list[str]:
    """Fetches top URLs posted on Reddit for a given domain in the date range."""
    subs = ", ".join(f"'{s}'" for s in VALID_SUBREDDITS)
    sql = f"""
        SELECT url, COUNT(*) as cnt
        FROM posts
        WHERE
            subreddit IN ({subs})
            AND url LIKE '%{domain}%'
            AND CAST(created_datetime AS DATE) BETWEEN '{start_date}' AND '{end_date}'
        GROUP BY url
        ORDER BY cnt DESC
        LIMIT {limit}
    """
    try:
        conn = get_conn()
        df = conn.execute(sql).df()
        conn.close()
        return df["url"].tolist()
    except Exception as e:
        logger.error(f"Domain URL query failed: {e}")
        return []


def run_sql(query: str) -> str:
    """Generic SQL runner used by the forensic agent tool."""
    try:
        conn = get_conn()
        df = conn.execute(query).df()
        conn.close()
        return df.to_string(index=True, max_rows=30)
    except Exception as e:
        return f"SQL Error: {e}.\nCheck that you used CAST(created_datetime AS DATE) for date filtering and only valid column names."


def get_bridge_users(subreddit_a: str, subreddit_b: str) -> str:
    """Find users who posted in both subreddits."""
    sql = f"""
        SELECT author, COUNT(DISTINCT subreddit) as sub_count,
               STRING_AGG(DISTINCT subreddit, ', ') as subreddits
        FROM posts
        WHERE subreddit IN ('{subreddit_a}', '{subreddit_b}')
          AND author != '[deleted]'
        GROUP BY author
        HAVING COUNT(DISTINCT subreddit) > 1
        ORDER BY sub_count DESC
        LIMIT 20
    """
    return run_sql(sql)
