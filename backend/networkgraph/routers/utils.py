import ast
import math
import logging
from typing import Optional
from fastapi import HTTPException

log = logging.getLogger("sntis.utils")

# Constants
MAX_DOMAINS_PER_SUB = 12
MAX_AUTHORS_PER_SUB = 15
AMP_THRESHOLD = 0.05

NODE_COLORS = {
    "subreddit": {"background": "#3B82F6", "border": "#1E40AF"},
    "author": {"background": "#F59E0B", "border": "#B45309"},
    "domain": {"background": "#8B5CF6", "border": "#5B21B6"},
    "author_cluster": {"background": "#F59E0B", "border": "#B45309"},
}

EDGE_COLORS = {
    "spread": "#EF4444",
    "source": "#06B6D4",
    "amplifier": "#EAB308",
}

def _norm_nid(narrative_id: str) -> str:
    return str(narrative_id or "").replace(".0_", "_")

def _parse_sequence(raw: str) -> list[str]:
    if raw is None:
        return []
    txt = str(raw).strip()
    if not txt:
        return []
    try:
        val = ast.literal_eval(txt)
        if isinstance(val, list):
            return [str(v).strip() for v in val if str(v).strip()]
    except Exception:
        pass
    return [p.strip() for p in txt.split(",") if p.strip()]

def _edge_width(weight: float) -> float:
    return max(1.0, min(5.0, 1.0 + math.log(float(weight or 0.0) + 1.0)))

def _get_filtered_narratives(
    con,
    min_authors: int,
    min_subreddits: int,
    start_date: Optional[str],
    end_date: Optional[str],
):
    where = [
        "COALESCE(n.unique_authors, 0) >= ?",
        "COALESCE(n.unique_subreddits_x, 0) >= ?",
    ]
    params: list = [min_authors, min_subreddits]

    if start_date and end_date:
        where.append(
            "n.first_seen_x::DATE BETWEEN ?::DATE AND ?::DATE"
        )
        params.extend([start_date, end_date])

    sql = f"""
        SELECT
            n.narrative_id,
            n.cluster_id,
            n.representative_title,
            COALESCE(n.unique_authors, 0)      AS author_count,
            COALESCE(n.unique_subreddits_x, 0) AS subreddit_count,
            COALESCE(n.spread_strength, 0)     AS spread_score,
            n.primary_domain,
            n.first_seen_x                    AS first_seen,
            n.last_seen,
            t.topic_cluster,
            t.topic_label,
            (
                SELECT p.author
                FROM subreddit_edges p
                WHERE p.narrative_id = n.narrative_id
                  AND p.author IS NOT NULL AND p.author <> ''
                ORDER BY p.created_datetime ASC
                LIMIT 1
            )                                 AS starter_author,
            (
                SELECT p.subreddit
                FROM subreddit_edges p
                WHERE p.narrative_id = n.narrative_id
                  AND p.subreddit IS NOT NULL AND p.subreddit <> ''
                ORDER BY p.created_datetime ASC
                LIMIT 1
            )                                 AS starter_subreddit,
            n.first_seen_x                    AS start_timestamp
        FROM narratives n
        LEFT JOIN topics t ON t.narrative_id = n.narrative_id
        WHERE {' AND '.join(where)}
        ORDER BY spread_score DESC
    """
    try:
        return con.execute(sql, params).fetchdf()
    except Exception as e:
        log.error(f"SQL execution failed: {e}")
        raise HTTPException(status_code=500, detail=f"Database query error: {str(e)}")

def _threshold_counts(con, table: str, column: str, base_levels: list[int]) -> dict[str, int]:
    max_row = con.execute(
        f"SELECT COALESCE(MAX(COALESCE({column}, 0)), 0) FROM {table}"
    ).fetchone()
    max_val = int(max_row[0] or 0) if max_row else 0
    levels = sorted(set(base_levels + list(range(1, max_val + 1))))
    if not levels:
        return {}

    exprs = ", ".join(
        [f"SUM(CASE WHEN COALESCE({column}, 0) >= {lvl} THEN 1 ELSE 0 END)" for lvl in levels]
    )
    row = con.execute(f"SELECT {exprs} FROM {table}").fetchone()
    if row is None:
        return {f"{lvl}+": 0 for lvl in levels}

    return {f"{lvl}+": int(row[idx] or 0) for idx, lvl in enumerate(levels)}

def _merge_unique_graph(base_nodes, base_edges, new_nodes, new_edges):
    node_ids = {str(n.get("id")) for n in base_nodes}
    edge_ids = {str(e.get("id")) for e in base_edges}

    nodes = list(base_nodes)
    edges = list(base_edges)

    for n in new_nodes:
        nid = str(n.get("id"))
        if nid and nid not in node_ids:
            node_ids.add(nid)
            nodes.append(n)

    for e in new_edges:
        eid = str(e.get("id"))
        if eid and eid not in edge_ids:
            edge_ids.add(eid)
            edges.append(e)

    return nodes, edges
