"""
hybrid/tools_sql.py
--------------------
SQL tools for the SQL Agent.

Fix 3: Hard SQL guardrails enforced at tool level (not prompt level):
  - Mutation keyword rejection (DROP, INSERT, UPDATE, DELETE, CREATE, ALTER)
  - SELECT * rejection on large tables
  - Auto-LIMIT enforcement (caps runaway queries at 500 rows)
  - Subreddit pre-flight (rejects invalid subs before querying)
  - Column guard (warns on internal key column SELECTs)
  - Empty result injection (valid values returned to LLM on 0 rows)
  - Error schema injection (trimmed schema returned on SQL errors)
"""

import re
import os
import time
import logging

from langchain.tools import tool

from hybrid.database import get_db_connection
from hybrid.constants import (
    VALID_SUBREDDITS, INTERNAL_KEY_COLUMNS, VALID_SUBS_STR,
    DATE_START, DATE_END, TABLE_SCHEMA
)

logger = logging.getLogger(__name__)
_SLEEP = float(os.getenv("TOOL_SLEEP_SECONDS", "4"))

# ── Tables where SELECT * without WHERE is dangerous (large row counts) ────────
_LARGE_TABLES = {
    "posts", "posts_with_clusters", "narrative_diffusion",
    "amplification_events", "graph_edges", "narrative_registry"
}

# ── Mutation keywords that must never appear in a query ───────────────────────
_MUTATION_KEYWORDS = {
    "drop", "insert", "update", "delete", "create",
    "alter", "truncate", "replace", "merge", "upsert"
}

_SCHEMA_ERR = "\n".join(
    f"  {tbl}({', '.join(cols)})"
    for tbl, cols in TABLE_SCHEMA.items()
)


# ── Guards ─────────────────────────────────────────────────────────────────────

def _mutation_guard(sql: str) -> str | None:
    """Hard-blocks any mutation keyword regardless of context."""
    tokens = set(re.findall(r"\b\w+\b", sql.lower()))
    found = tokens & _MUTATION_KEYWORDS
    if found:
        return (
            f"BLOCKED: Query contains mutation keywords: {found}. "
            "Only SELECT queries are permitted. Rewrite as a SELECT statement."
        )
    return None


def _select_star_guard(sql: str) -> str | None:
    """Rejects SELECT * on large tables without a WHERE clause."""
    if "select *" not in sql.lower():
        return None
    for tbl in _LARGE_TABLES:
        if tbl in sql.lower() and "where" not in sql.lower():
            return (
                f"BLOCKED: SELECT * on '{tbl}' without a WHERE clause is too expensive. "
                "Select specific columns and add a WHERE or LIMIT clause."
            )
    return None


def _apply_limit(sql: str, cap: int = 500) -> str:
    """Injects LIMIT {cap} if the query has no LIMIT, preventing full-table scans."""
    if re.search(r"\blimit\b", sql, re.IGNORECASE):
        return sql
    return sql.rstrip(";") + f" LIMIT {cap}"


def _quoted_values(sql: str) -> list[str]:
    return re.findall(r"'([^']*)'", sql)


def _subreddit_guard(sql: str) -> str | None:
    if "subreddit" not in sql.lower():
        return None
    invalid = [
        v for v in _quoted_values(sql)
        if v and v not in VALID_SUBREDDITS and len(v) > 2
    ]
    if invalid:
        return (
            f"STOP: Subreddits not in dataset: {invalid}. "
            f"Valid subreddits: {VALID_SUBS_STR}. "
            "Rewrite the query using only valid subreddit names."
        )
    return None


def _column_guard(sql: str) -> str | None:
    flagged = [c for c in INTERNAL_KEY_COLUMNS if c.upper() in sql.upper()]
    if flagged:
        return (
            f"NOTE: {flagged} are opaque internal IDs, NOT human-readable names. "
            "Use representative_title or topic_label for narrative names."
        )
    return None


def _bridge_authors_guard(sql: str) -> str | None:
    """Blocks direct queries to the bridge_authors table."""
    lower_sql = sql.lower()
    if "bridge_authors" in lower_sql and "from" in lower_sql:
        return (
            "ERROR: You must NEVER query the 'bridge_authors' table directly. "
            "For any cross-subreddit author overlap queries, you MUST use the "
            "analyze_bridges tool instead."
        )
    return None


# ── Tools ──────────────────────────────────────────────────────────────────────

@tool
def execute_sql(sql_query: str) -> str:
    """
    Execute a DuckDB SELECT query against the Reddit political dataset.

    Rules:
    - Only SELECT queries. Mutations (DROP, INSERT, UPDATE, DELETE etc.) are blocked.
    - No SELECT * on large tables without WHERE.
    - Queries without LIMIT are capped at 500 rows automatically.
    - Narrative names: use representative_title or topic_label.
      NEVER use narrative_id, cluster_id, or internal_system_id as names.
    - Valid subreddits: politics, Conservative, Anarchism, Liberal, Republican,
      PoliticalDiscussion, socialism, worldpolitics, democrats, neoliberal
    - Date range: 2024-07-23 to 2025-02-18
    - Date filtering: CAST(created_datetime AS DATE)

    Input: a raw DuckDB SELECT statement.
    """
    time.sleep(_SLEEP)
    conn = get_db_connection()

    try:
        clean = sql_query.replace("```sql", "").replace("```", "").strip().rstrip(";")

        # Guard 1: mutation hard-block
        mut = _mutation_guard(clean)
        if mut:
            return mut

        # Guard 2: must start with SELECT
        if not clean.lower().lstrip().startswith("select"):
            return "Error: Only SELECT queries are allowed. Rewrite as a SELECT statement."

        # Guard 3: SELECT * on large table without WHERE
        star = _select_star_guard(clean)
        if star:
            return star

        # Guard 4: invalid subreddits
        sub_warn = _subreddit_guard(clean)
        if sub_warn:
            return sub_warn

        # Guard 5: internal key column warning
        col_warn = _column_guard(clean)

        # Guard 6: block direct queries to bridge_authors
        bridge_warn = _bridge_authors_guard(clean)
        if bridge_warn:
            return bridge_warn

        # Auto-inject LIMIT if missing
        safe_sql = _apply_limit(clean)

        df = conn.execute(safe_sql).fetchdf()

        if df.empty:
            msg = (
                "Query returned 0 results. "
                f"Valid subreddits: {VALID_SUBS_STR}. "
                f"Date range: {DATE_START} to {DATE_END}. "
                "Do NOT invent values."
            )
            return (col_warn + "\n" + msg) if col_warn else msg

        result = df.to_string(index=False)
        if col_warn:
            result = col_warn + "\n\nRESULTS:\n" + result

        logger.info(f"[execute_sql] {len(df)} rows returned.")
        return result

    except Exception as exc:
        return (
            f"SQL Error: {exc}. "
            f"Valid tables and columns:\n{_SCHEMA_ERR}\n"
            f"Valid subreddits: {VALID_SUBS_STR}. "
            "Use CAST(created_datetime AS DATE) for date filtering."
        )


@tool
def analyze_bridges(input_str: str) -> str:
    """
    Find authors who posted in BOTH of two subreddits (bridge/cross-community accounts).

    Input: two subreddit names separated by a comma.
    Example: "politics,Conservative"

    Returns top 10 bridge authors by post volume.
    """
    time.sleep(_SLEEP)
    parts = [p.strip() for p in input_str.split(",")]

    if len(parts) < 2:
        return (
            "Input error: provide two subreddits separated by comma. "
            f"Example: 'politics,Conservative'. Valid: {VALID_SUBS_STR}"
        )

    sub_a, sub_b = parts[0], parts[1]
    invalid = [s for s in [sub_a, sub_b] if s not in VALID_SUBREDDITS]
    if invalid:
        return f"Invalid subreddits: {invalid}. Valid: {VALID_SUBS_STR}"

    conn = get_db_connection()
    try:
        df = conn.execute(f"""
            SELECT author,
                   COUNT(*) AS total_posts,
                   COUNT(DISTINCT subreddit) AS active_in
            FROM posts
            WHERE subreddit IN ('{sub_a}', '{sub_b}')
            GROUP BY author
            HAVING COUNT(DISTINCT subreddit) > 1
            ORDER BY total_posts DESC
            LIMIT 10
        """).fetchdf()

        if df.empty:
            return f"No bridge authors found between r/{sub_a} and r/{sub_b}."
        return (
            f"Bridge authors between r/{sub_a} and r/{sub_b}:\n"
            f"{df.to_string(index=False)}"
        )
    except Exception as exc:
        return f"Bridge query error: {exc}"
