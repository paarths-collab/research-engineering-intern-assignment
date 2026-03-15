"""
routers/intelligence.py — Database-powered Narrative Ecosystem Graph

All narrative and graph intelligence is sourced from data/analysis_v2.db.
No CSV reads are used in this router.
"""
from __future__ import annotations

import ast
import hashlib
import json
import logging
import math
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import duckdb
import httpx
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from networkgraph.models.schemas import AnalyzeNodeRequest, AnalyzeNodeResponse

log = logging.getLogger("sntis.intelligence")
router = APIRouter(prefix="/intelligence", tags=["intelligence"])

# Resolve data directory: try Render persistent disk first, then env var, then relative
# Resolve data directory: try Render persistent disk first, then seed path, then relative
_RENDER_PERSISTENT = Path("/app/data")
_RENDER_SEED = Path("/app/seed_data")
_REL_DATA = Path(__file__).resolve().parents[3] / "data" 

if _RENDER_PERSISTENT.exists():
    DEFAULT_DATA_PATH = _RENDER_PERSISTENT
elif _RENDER_SEED.exists():
    DEFAULT_DATA_PATH = _RENDER_SEED
else:
    DEFAULT_DATA_PATH = _REL_DATA

DB_PATH = Path(os.getenv("DATA_PATH", str(DEFAULT_DATA_PATH))) / "analysis_v2.db"
MAX_DOMAINS_PER_SUB = 10
MAX_AUTHORS_PER_SUB = 15
AMP_THRESHOLD = 0.15

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"

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


_is_db_fixed = False

def _db():
    global _is_db_fixed
    if not DB_PATH.exists():
        raise HTTPException(status_code=500, detail=f"Database not found at {DB_PATH.absolute()}")

    # Recreate the views dynamically on Render to fix the hardcoded local paths
    # from the original database creation.
    if not _is_db_fixed:
        try:
            # Briefly open in write mode to patch views
            patch_con = duckdb.connect(str(DB_PATH), read_only=False)
            data_dir = DEFAULT_DATA_PATH
            csvs = {
                "narratives": "narrative_intelligence_summary.csv",
                "topics": "narrative_topic_mapping.csv",
                "chains": "narrative_spread_chain_table.csv",
                "amplification": "author_amplification_summary.csv",
                "daily_volume": "daily_volume_v2.csv",
                "echo_chambers": "echo_chamber_scores.csv",
                "ideological_matrix": "ideological_distance_matrix.csv"
            }
            for view_name, fname in csvs.items():
                fpath = data_dir / fname
                if fpath.exists():
                    # Use SELECT * to ensure we get all analytical columns required by the app
                    patch_con.execute(f"CREATE OR REPLACE VIEW {view_name} AS SELECT * FROM read_csv_auto('{fpath.resolve().as_posix()}')")
            patch_con.close()
            _is_db_fixed = True
        except Exception as e:
            log.warning(f"Failed to patch DuckDB views: {e}")

    # Return a read-only connection for the request
    return duckdb.connect(str(DB_PATH), read_only=True)


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
            "EXISTS (SELECT 1 FROM posts p WHERE CAST(p.duplicate_cluster_id AS BIGINT)=n.cluster_id "
            "AND p.created_datetime::DATE BETWEEN ?::DATE AND ?::DATE)"
        )
        params.extend([start_date, end_date])

    sql = f"""
        SELECT
            n.narrative_id,
            n.cluster_id,
            n.representative_title,
            COALESCE(n.unique_authors, 0) AS author_count,
            COALESCE(n.unique_subreddits_x, 0) AS subreddit_count,
            COALESCE(n.spread_strength, 0) AS spread_score,
            n.primary_domain,
            n.first_seen_x AS first_seen,
            n.last_seen,
            t.topic_cluster,
            t.topic_label,
            p0.author AS starter_author,
            p0.subreddit AS starter_subreddit,
            p0.created_datetime AS start_timestamp
        FROM narratives n
        LEFT JOIN topics t ON t.narrative_id = n.narrative_id
        LEFT JOIN LATERAL (
            SELECT p.author, p.subreddit, p.created_datetime
            FROM posts p
            WHERE CAST(p.duplicate_cluster_id AS BIGINT) = n.cluster_id
            ORDER BY p.created_datetime ASC
            LIMIT 1
        ) p0 ON TRUE
        WHERE {' AND '.join(where)}
        ORDER BY spread_score DESC
    """
    return con.execute(sql, params).fetchdf()


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


def _edge_width(weight: float) -> float:
    return max(1.0, min(5.0, 1.0 + math.log(float(weight or 0.0) + 1.0)))


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


@router.get("/subreddit/neighbors")
def get_subreddit_neighbors(
    name: str = Query(..., min_length=1),
    min_authors: int = Query(1, ge=0),
    min_subreddits: int = Query(0, ge=0),
    depth: int = Query(1, ge=1, le=2),
):
    con = _db()
    try:
        subreddit = str(name).strip()
        ndf = _get_filtered_narratives(con, min_authors, min_subreddits, None, None)
        if ndf.empty:
            return {"name": subreddit, "nodes": [], "edges": []}

        cluster_ids: list[int] = []
        for raw in ndf["cluster_id"].tolist():
            try:
                cluster_ids.append(int(raw))
            except (TypeError, ValueError):
                continue

        if not cluster_ids:
            return {"name": subreddit, "nodes": [], "edges": []}

        cid_sql = ",".join(str(cid) for cid in sorted(set(cluster_ids)))

        narrative_rows = con.execute(
            f"""
            SELECT DISTINCT n.narrative_id
            FROM narratives n
            JOIN posts p ON CAST(p.duplicate_cluster_id AS BIGINT) = n.cluster_id
            WHERE n.cluster_id IN ({cid_sql})
              AND p.subreddit = ?
            """,
            [subreddit],
        ).fetchall()
        narrative_ids = [_norm_nid(r[0]) for r in narrative_rows if r and r[0] is not None]
        if not narrative_ids:
            return {"name": subreddit, "nodes": [], "edges": []}

        narrative_ids_sql = "', '".join([v.replace("'", "''") for v in set(narrative_ids)])

        nodes = []
        edges = []
        node_ids = set()

        def add_node(node):
            nid = node["id"]
            if nid not in node_ids:
                node_ids.add(nid)
                nodes.append(node)

        # Spread neighbors around clicked subreddit.
        seq_rows = con.execute(
            f"""
            SELECT spread_sequence
            FROM chains
            WHERE narrative_id IN ('{narrative_ids_sql}')
            """
        ).fetchall()
        all_pair_weight = defaultdict(int)
        for (spread_sequence,) in seq_rows:
            seq = _parse_sequence(spread_sequence)
            for i in range(len(seq) - 1):
                src = seq[i].strip()
                tgt = seq[i + 1].strip()
                if src and tgt and src != tgt:
                    all_pair_weight[(src, tgt)] += 1

        first_hop_subs = set()
        for (src, tgt), _weight in all_pair_weight.items():
            if src == subreddit:
                first_hop_subs.add(tgt)
            if tgt == subreddit:
                first_hop_subs.add(src)

        allowed_subs = {subreddit}
        if depth >= 2:
            allowed_subs.update(first_hop_subs)

        pair_weight = defaultdict(int)
        for (src, tgt), weight in all_pair_weight.items():
            if depth == 1:
                if src == subreddit or tgt == subreddit:
                    pair_weight[(src, tgt)] += weight
            else:
                if src in allowed_subs or tgt in allowed_subs:
                    pair_weight[(src, tgt)] += weight

        for (src, tgt), weight in pair_weight.items():
            edges.append(
                {
                    "id": hashlib.md5(f"nei-ss::{src}::{tgt}".encode()).hexdigest()[:12],
                    "from": f"sub::{src}",
                    "to": f"sub::{tgt}",
                    "edge_type": "spread",
                    "color": {"color": EDGE_COLORS["spread"], "opacity": 0.35},
                    "width": _edge_width(weight),
                    "title": f"{src} -> {tgt} ({weight})",
                    "arrows": "to",
                }
            )

        # Source neighbors for selected hop scope.
        scope_subs = sorted(allowed_subs)
        scope_subs_sql = "', '".join([s.replace("'", "''") for s in scope_subs])
        dom_rows = con.execute(
            f"""
            SELECT p.subreddit, p.domain, COUNT(*) AS cnt
            FROM posts p
            JOIN narratives n ON CAST(p.duplicate_cluster_id AS BIGINT) = n.cluster_id
            WHERE n.narrative_id IN ('{narrative_ids_sql}')
              AND p.subreddit IN ('{scope_subs_sql}')
              AND p.domain IS NOT NULL AND p.domain <> ''
            GROUP BY 1, 2
            ORDER BY cnt DESC
            LIMIT 80
            """
        ).fetchall()
        for sub, dom, cnt in dom_rows:
            sub = str(sub)
            dom = str(dom)
            cnt = int(cnt)
            edges.append(
                {
                    "id": hashlib.md5(f"nei-sd::{sub}::{dom}".encode()).hexdigest()[:12],
                    "from": f"sub::{sub}",
                    "to": f"dom::{dom}",
                    "edge_type": "source",
                    "color": {"color": EDGE_COLORS["source"], "opacity": 0.35},
                    "width": _edge_width(cnt),
                    "title": f"{sub} -> {dom} ({cnt})",
                    "arrows": "to",
                }
            )
            add_node(
                {
                    "id": f"dom::{dom}",
                    "label": dom,
                    "type": "domain",
                    "shape": "triangle",
                    "size": max(16, min(42, 16 + int(math.log(cnt + 1) * 6))),
                    "color": NODE_COLORS["domain"],
                    "font": {"color": "#ffffff", "size": 10},
                }
            )

        # Amplifier neighbors for selected hop scope.
        aut_rows = con.execute(
            f"""
            SELECT p.author, p.subreddit, COUNT(*) AS cnt
            FROM posts p
            JOIN narratives n ON CAST(p.duplicate_cluster_id AS BIGINT) = n.cluster_id
            WHERE n.narrative_id IN ('{narrative_ids_sql}')
              AND p.subreddit IN ('{scope_subs_sql}')
              AND p.author IS NOT NULL AND p.author <> ''
            GROUP BY 1, 2
            ORDER BY cnt DESC
            LIMIT 120
            """
        ).fetchall()
        for author, sub, cnt in aut_rows:
            author = str(author)
            sub = str(sub)
            cnt = int(cnt)
            edges.append(
                {
                    "id": hashlib.md5(f"nei-as::{author}::{sub}".encode()).hexdigest()[:12],
                    "from": f"aut::{author}",
                    "to": f"sub::{sub}",
                    "edge_type": "amplifier",
                    "color": {"color": EDGE_COLORS["amplifier"], "opacity": 0.35},
                    "width": _edge_width(cnt),
                    "title": f"{author} -> {sub} ({cnt})",
                    "arrows": "to",
                }
            )
            add_node(
                {
                    "id": f"aut::{author}",
                    "label": author,
                    "type": "author",
                    "shape": "square",
                    "size": max(11, min(30, 11 + int(math.log(cnt + 1) * 5))),
                    "color": NODE_COLORS["author"],
                    "font": {"color": "#ffffff", "size": 10},
                }
            )

        subreddits = {subreddit}
        for src, tgt in pair_weight.keys():
            subreddits.add(str(src))
            subreddits.add(str(tgt))

        for sub in subreddits:
            is_focus = sub == subreddit
            add_node(
                {
                    "id": f"sub::{sub}",
                    "label": sub,
                    "type": "subreddit",
                    "shape": "dot",
                    "size": 34 if is_focus else 22,
                    "color": {
                        "background": "#22C55E" if is_focus else NODE_COLORS["subreddit"]["background"],
                        "border": "#166534" if is_focus else NODE_COLORS["subreddit"]["border"],
                    },
                    "font": {"color": "#ffffff", "size": 13 if is_focus else 12},
                }
            )

        return {"name": subreddit, "depth": depth, "nodes": nodes, "edges": edges}
    finally:
        con.close()


@router.get("/spread-levels")
def get_spread_levels():
    con = _db()
    try:
        return _threshold_counts(
            con,
            table="narratives",
            column="unique_authors",
            base_levels=[1, 2, 3, 4, 5, 6, 10],
        )
    finally:
        con.close()


@router.get("/subreddit-reach")
def get_subreddit_reach():
    con = _db()
    try:
        return _threshold_counts(
            con,
            table="narratives",
            column="unique_subreddits_x",
            base_levels=[1, 2, 3, 4, 5, 6],
        )
    finally:
        con.close()


@router.get("/subreddit/{subreddit}/details")
def get_subreddit_details(
    subreddit: str,
    min_authors: int = Query(1, ge=0),
    min_subreddits: int = Query(0, ge=0),
):
    con = _db()
    try:
        ndf = _get_filtered_narratives(con, min_authors, min_subreddits, None, None)
        if ndf.empty:
            return {
                "subreddit": subreddit,
                "summary": {
                    "total_posts": 0,
                    "distinct_authors": 0,
                    "distinct_domains": 0,
                    "narratives": 0,
                    "first_seen": None,
                    "last_seen": None,
                },
                "top_domains": [],
                "top_authors": [],
                "connected_subreddits": [],
                "top_narratives": [],
            }

        cluster_ids: list[int] = []
        for raw in ndf["cluster_id"].tolist():
            try:
                cluster_ids.append(int(raw))
            except (TypeError, ValueError):
                continue

        if not cluster_ids:
            return {
                "subreddit": subreddit,
                "summary": {
                    "total_posts": 0,
                    "distinct_authors": 0,
                    "distinct_domains": 0,
                    "narratives": 0,
                    "first_seen": None,
                    "last_seen": None,
                },
                "top_domains": [],
                "top_authors": [],
                "connected_subreddits": [],
                "top_narratives": [],
            }

        cid_sql = ",".join(str(cid) for cid in sorted(set(cluster_ids)))

        summary = con.execute(
            f"""
            SELECT
                COUNT(*) AS total_posts,
                COUNT(DISTINCT p.author) AS distinct_authors,
                COUNT(DISTINCT p.domain) AS distinct_domains,
                COUNT(DISTINCT CAST(p.duplicate_cluster_id AS BIGINT)) AS narratives,
                MIN(p.created_datetime) AS first_seen,
                MAX(p.created_datetime) AS last_seen
            FROM posts p
            WHERE CAST(p.duplicate_cluster_id AS BIGINT) IN ({cid_sql})
              AND p.subreddit = ?
            """,
            [subreddit],
        ).fetchone()
        summary = summary or (0, 0, 0, 0, None, None)

        top_domains = con.execute(
            f"""
            SELECT p.domain, COUNT(*) AS cnt
            FROM posts p
            WHERE CAST(p.duplicate_cluster_id AS BIGINT) IN ({cid_sql})
              AND p.subreddit = ?
              AND p.domain IS NOT NULL AND p.domain <> ''
            GROUP BY 1
            ORDER BY cnt DESC
            LIMIT 12
            """,
            [subreddit],
        ).fetchall()

        top_authors = con.execute(
            f"""
            SELECT p.author, COUNT(*) AS cnt
            FROM posts p
            WHERE CAST(p.duplicate_cluster_id AS BIGINT) IN ({cid_sql})
              AND p.subreddit = ?
              AND p.author IS NOT NULL AND p.author <> ''
            GROUP BY 1
            ORDER BY cnt DESC
            LIMIT 12
            """,
            [subreddit],
        ).fetchall()

        connected_subs = con.execute(
            f"""
            SELECT p2.subreddit, COUNT(*) AS cnt
            FROM posts p
            JOIN posts p2
              ON CAST(p.duplicate_cluster_id AS BIGINT) = CAST(p2.duplicate_cluster_id AS BIGINT)
            WHERE CAST(p.duplicate_cluster_id AS BIGINT) IN ({cid_sql})
              AND p.subreddit = ?
              AND p2.subreddit IS NOT NULL
              AND p2.subreddit <> ''
              AND p2.subreddit <> ?
            GROUP BY 1
            ORDER BY cnt DESC
            LIMIT 12
            """,
            [subreddit, subreddit],
        ).fetchall()

        top_narratives = con.execute(
            f"""
            SELECT n.narrative_id, n.representative_title, COUNT(*) AS cnt
            FROM posts p
            JOIN narratives n ON CAST(p.duplicate_cluster_id AS BIGINT) = n.cluster_id
            WHERE CAST(p.duplicate_cluster_id AS BIGINT) IN ({cid_sql})
              AND p.subreddit = ?
            GROUP BY 1, 2
            ORDER BY cnt DESC
            LIMIT 10
            """,
            [subreddit],
        ).fetchall()

        return {
            "subreddit": subreddit,
            "summary": {
                "total_posts": int(summary[0] or 0),
                "distinct_authors": int(summary[1] or 0),
                "distinct_domains": int(summary[2] or 0),
                "narratives": int(summary[3] or 0),
                "first_seen": str(summary[4]) if summary[4] else None,
                "last_seen": str(summary[5]) if summary[5] else None,
            },
            "top_domains": [{"domain": str(d), "count": int(c)} for d, c in top_domains],
            "top_authors": [{"author": str(a), "count": int(c)} for a, c in top_authors],
            "connected_subreddits": [{"subreddit": str(s), "count": int(c)} for s, c in connected_subs],
            "top_narratives": [
                {"narrative_id": str(nid), "title": str(title or ""), "count": int(c)}
                for nid, title, c in top_narratives
            ],
        }
    finally:
        con.close()


@router.get("/subreddit/{subreddit}/ecosystem")
def get_subreddit_ecosystem(
    subreddit: str,
    min_authors: int = Query(1, ge=0),
    min_subreddits: int = Query(0, ge=0),
):
    con = _db()
    try:
        ndf = _get_filtered_narratives(con, min_authors, min_subreddits, None, None)
        if ndf.empty:
            return {"subreddit": subreddit, "nodes": [], "edges": []}

        cluster_ids: list[int] = []
        for raw in ndf["cluster_id"].tolist():
            try:
                cluster_ids.append(int(raw))
            except (TypeError, ValueError):
                continue

        if not cluster_ids:
            return {"subreddit": subreddit, "nodes": [], "edges": []}

        cid_sql = ",".join(str(cid) for cid in sorted(set(cluster_ids)))

        narrative_rows = con.execute(
            f"""
            SELECT DISTINCT n.narrative_id
            FROM narratives n
            JOIN posts p ON CAST(p.duplicate_cluster_id AS BIGINT) = n.cluster_id
            WHERE n.cluster_id IN ({cid_sql})
              AND p.subreddit = ?
            """,
            [subreddit],
        ).fetchall()

        narrative_ids = [_norm_nid(r[0]) for r in narrative_rows if r and r[0] is not None]
        if not narrative_ids:
            return {"subreddit": subreddit, "nodes": [], "edges": []}

        narrative_ids_sql = "', '".join([v.replace("'", "''") for v in set(narrative_ids)])

        nodes = []
        edges = []
        node_ids = set()

        def add_node(node):
            nid = node["id"]
            if nid not in node_ids:
                node_ids.add(nid)
                nodes.append(node)

        # Spread edges within narratives containing the selected subreddit
        seq_rows = con.execute(
            f"""
            SELECT spread_sequence
            FROM chains
            WHERE narrative_id IN ('{narrative_ids_sql}')
            """
        ).fetchall()

        pair_weight = defaultdict(int)
        for (spread_sequence,) in seq_rows:
            seq = _parse_sequence(spread_sequence)
            for i in range(len(seq) - 1):
                src = seq[i].strip()
                tgt = seq[i + 1].strip()
                if src and tgt and src != tgt:
                    pair_weight[(src, tgt)] += 1

        for (src, tgt), weight in pair_weight.items():
            edges.append(
                {
                    "id": hashlib.md5(f"eco-ss::{src}::{tgt}".encode()).hexdigest()[:12],
                    "from": f"sub::{src}",
                    "to": f"sub::{tgt}",
                    "edge_type": "spread",
                    "color": {"color": "#F43F5E", "opacity": 0.45},
                    "width": max(1.2, min(6.0, float(weight) ** 0.45)),
                    "title": f"{src} -> {tgt} ({weight})",
                    "arrows": "to",
                }
            )

        # Source edges and domain nodes
        src_rows = con.execute(
            f"""
            SELECT p.subreddit, p.domain, COUNT(*) AS cnt
            FROM posts p
            JOIN narratives n ON CAST(p.duplicate_cluster_id AS BIGINT) = n.cluster_id
            WHERE n.narrative_id IN ('{narrative_ids_sql}')
              AND p.subreddit IS NOT NULL AND p.subreddit <> ''
              AND p.domain IS NOT NULL AND p.domain <> ''
            GROUP BY 1, 2
            ORDER BY cnt DESC
            """
        ).fetchall()

        per_sub_domains = defaultdict(list)
        for sub, dom, cnt in src_rows:
            per_sub_domains[str(sub)].append((str(dom), int(cnt)))

        for sub, pairs in per_sub_domains.items():
            for dom, cnt in sorted(pairs, key=lambda x: x[1], reverse=True)[:MAX_DOMAINS_PER_SUB]:
                edges.append(
                    {
                        "id": hashlib.md5(f"eco-sd::{sub}::{dom}".encode()).hexdigest()[:12],
                        "from": f"sub::{sub}",
                        "to": f"dom::{dom}",
                        "edge_type": "source",
                        "color": {"color": "#38BDF8", "opacity": 0.45},
                        "width": max(1.0, min(5.0, float(cnt) ** 0.35)),
                        "title": f"{sub} -> {dom} ({cnt})",
                        "arrows": "to",
                    }
                )
                add_node(
                    {
                        "id": f"dom::{dom}",
                        "label": dom,
                        "type": "domain",
                        "shape": "triangle",
                        "size": max(16, min(42, 16 + int(cnt ** 0.35))),
                        "color": {"background": "#3B0A45", "border": "#E879F9"},
                        "font": {"color": "#ffffff", "size": 10},
                    }
                )

        # Amplifier edges and author nodes
        amp_rows = con.execute(
            f"""
            SELECT p.author, p.subreddit, COUNT(*) AS cnt
            FROM posts p
            JOIN narratives n ON CAST(p.duplicate_cluster_id AS BIGINT) = n.cluster_id
            WHERE n.narrative_id IN ('{narrative_ids_sql}')
              AND p.author IS NOT NULL AND p.author <> ''
              AND p.subreddit IS NOT NULL AND p.subreddit <> ''
            GROUP BY 1, 2
            ORDER BY cnt DESC
            """
        ).fetchall()

        per_sub_authors = defaultdict(list)
        for author, sub, cnt in amp_rows:
            per_sub_authors[str(sub)].append((str(author), int(cnt)))

        for sub, pairs in per_sub_authors.items():
            for author, cnt in sorted(pairs, key=lambda x: x[1], reverse=True)[:MAX_AUTHORS_PER_SUB]:
                edges.append(
                    {
                        "id": hashlib.md5(f"eco-as::{author}::{sub}".encode()).hexdigest()[:12],
                        "from": f"aut::{author}",
                        "to": f"sub::{sub}",
                        "edge_type": "amplifier",
                        "color": {"color": "#F59E0B", "opacity": 0.45},
                        "width": max(1.0, min(5.0, float(cnt) ** 0.35)),
                        "title": f"{author} -> {sub} ({cnt})",
                        "arrows": "to",
                    }
                )
                add_node(
                    {
                        "id": f"aut::{author}",
                        "label": author,
                        "type": "author",
                        "shape": "square",
                        "size": max(11, min(30, 11 + int(cnt ** 0.35))),
                        "color": {"background": "#3A2306", "border": "#FB923C"},
                        "font": {"color": "#ffffff", "size": 10},
                    }
                )

        # Subreddit nodes from all ecosystem edges
        subreddits = set()
        for e in edges:
            if str(e.get("from", "")).startswith("sub::"):
                subreddits.add(str(e["from"]).split("sub::", 1)[1])
            if str(e.get("to", "")).startswith("sub::"):
                subreddits.add(str(e["to"]).split("sub::", 1)[1])

        if subreddit:
            subreddits.add(subreddit)

        for sub in subreddits:
            is_focus = sub == subreddit
            add_node(
                {
                    "id": f"sub::{sub}",
                    "label": sub,
                    "type": "subreddit",
                    "shape": "dot",
                    "size": 34 if is_focus else 22,
                    "color": {
                        "background": "#0B2B3A" if not is_focus else "#1F2937",
                        "border": "#22D3EE" if not is_focus else "#FDE047",
                    },
                    "font": {"color": "#ffffff", "size": 12 if not is_focus else 13},
                }
            )

        return {"subreddit": subreddit, "nodes": nodes, "edges": edges}
    finally:
        con.close()


@router.get("/timeline")
def get_timeline(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
):
    con = _db()
    try:
        where = []
        params = []
        if start_date:
            where.append("p.created_datetime::DATE >= ?::DATE")
            params.append(start_date)
        if end_date:
            where.append("p.created_datetime::DATE <= ?::DATE")
            params.append(end_date)
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""

        rows = con.execute(
            f"""
            SELECT
                p.created_datetime::DATE AS date,
                n.narrative_id,
                COUNT(*) AS post_count
            FROM posts p
            JOIN narratives n ON CAST(p.duplicate_cluster_id AS BIGINT) = n.cluster_id
            {where_sql}
            GROUP BY 1, 2
            ORDER BY 1, 2
            """,
            params,
        ).fetchall()

        date_rows = con.execute(
            f"""
            SELECT p.created_datetime::DATE AS date, COUNT(*) AS total_posts
            FROM posts p
            {where_sql}
            GROUP BY 1
            ORDER BY 1
            """,
            params,
        ).fetchall()

        return {
            "timeline": [
                {"date": str(r[0]), "narrative_id": str(r[1]), "post_count": int(r[2])}
                for r in rows
            ],
            "date_totals": [{"date": str(r[0]), "post_count": int(r[1])} for r in date_rows],
        }
    finally:
        con.close()


@router.get("/leaderboard")
def get_leaderboard(
    limit: int = Query(30, ge=1, le=200),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
):
    con = _db()
    try:
        where = ["p.author IS NOT NULL", "p.author <> ''"]
        params: list = []
        if start_date:
            where.append("p.created_datetime::DATE >= ?::DATE")
            params.append(start_date)
        if end_date:
            where.append("p.created_datetime::DATE <= ?::DATE")
            params.append(end_date)

        where_sql = f"WHERE {' AND '.join(where)}"
        rows = con.execute(
            f"""
            SELECT
                p.author,
                COUNT(*) AS post_count,
                COUNT(DISTINCT p.subreddit) AS community_count,
                COALESCE(a.amplification_events, 0) AS amplification_score
            FROM posts p
            LEFT JOIN amplification a ON a.author = p.author
            {where_sql}
            GROUP BY p.author, a.amplification_events
            ORDER BY post_count DESC, amplification_score DESC
            LIMIT ?
            """,
            [*params, limit],
        ).fetchall()

        return {
            "items": [
                {
                    "author": str(r[0]),
                    "post_count": int(r[1] or 0),
                    "community_count": int(r[2] or 0),
                    "amplification_score": float(r[3] or 0.0),
                }
                for r in rows
            ],
            "total": len(rows),
        }
    finally:
        con.close()


@router.get("/narratives")
def get_narratives(
    min_authors: int = Query(1, ge=0),
    min_subreddits: int = Query(0, ge=0),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=1000),
):
    con = _db()
    try:
        df = _get_filtered_narratives(con, min_authors, min_subreddits, start_date, end_date)
        df = df.head(limit)

        items = []
        for _, row in df.iterrows():
            items.append(
                {
                    "narrative_id": _norm_nid(row["narrative_id"]),
                    "title": row.get("representative_title") or "Untitled Narrative",
                    "representative_title": row.get("representative_title") or "Untitled Narrative",
                    "author_count": int(row.get("author_count") or 0),
                    "community_count": int(row.get("subreddit_count") or 0),
                    "subreddit_count": int(row.get("subreddit_count") or 0),
                    "spread_score": float(row.get("spread_score") or 0.0),
                    "primary_domain": row.get("primary_domain"),
                    "first_seen": str(row.get("first_seen")) if row.get("first_seen") else None,
                    "start_timestamp": str(row.get("start_timestamp")) if row.get("start_timestamp") else None,
                    "starter_author": row.get("starter_author"),
                    "starter_subreddit": row.get("starter_subreddit"),
                    "topic_cluster": str(row.get("topic_cluster")) if row.get("topic_cluster") is not None else None,
                    "topic_label": row.get("topic_label"),
                }
            )

        # Keep tabs for backward compatibility with current UI shape.
        thresholds = {"3+": 3, "4+": 4, "5+": 5, "6+": 6, "10+": 10}
        tabs = {k: [it for it in items if it["author_count"] >= v] for k, v in thresholds.items()}

        return {"items": items, "tabs": tabs, "total": len(items)}
    finally:
        con.close()


@router.get("/graph")
def get_intelligence_graph(
    mode: str = Query("spread", pattern="^(spread|sources|amplifiers)$"),
    min_authors: int = Query(1, ge=0),
    min_subreddits: int = Query(0, ge=0),
    progressive: bool = Query(False),
    top_n: int = Query(14, ge=5, le=80),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
):
    con = _db()
    try:
        ndf = _get_filtered_narratives(con, min_authors, min_subreddits, start_date, end_date)
        if ndf.empty:
            return {"nodes": [], "edges": []}

        narrative_ids = {_norm_nid(v) for v in ndf["narrative_id"].astype(str).tolist()}
        narrative_ids_sql = "', '".join([v.replace("'", "''") for v in narrative_ids])

        nodes = []
        edges = []
        node_ids = set()

        def add_node(node):
            nid = node["id"]
            if nid not in node_ids:
                node_ids.add(nid)
                nodes.append(node)

        if mode == "spread":
            seq_rows = con.execute(
                f"""
                SELECT narrative_id, spread_sequence
                FROM chains
                WHERE narrative_id IN ('{narrative_ids_sql}')
                """
            ).fetchall()

            pair_weight = defaultdict(int)
            for nid, spread_sequence in seq_rows:
                seq = _parse_sequence(spread_sequence)
                for i in range(len(seq) - 1):
                    src = seq[i].strip()
                    tgt = seq[i + 1].strip()
                    if src and tgt and src != tgt:
                        pair_weight[(src, tgt)] += 1

            out_degree = defaultdict(int)
            in_degree = defaultdict(int)
            for (src, tgt), weight in pair_weight.items():
                eid = hashlib.md5(f"ss::{src}::{tgt}".encode()).hexdigest()[:12]
                edges.append(
                    {
                        "id": eid,
                        "from": f"sub::{src}",
                        "to": f"sub::{tgt}",
                        "edge_type": "spread",
                        "color": {"color": EDGE_COLORS["spread"], "opacity": 0.35},
                        "width": _edge_width(weight),
                        "title": f"{src} -> {tgt} ({weight})",
                        "arrows": "to",
                    }
                )
                out_degree[src] += 1
                in_degree[tgt] += 1

            subreddits = set([k[0] for k in pair_weight.keys()] + [k[1] for k in pair_weight.keys()])

            if progressive and subreddits:
                ranked = sorted(
                    list(subreddits),
                    key=lambda s: (out_degree.get(s, 0) + in_degree.get(s, 0), out_degree.get(s, 0)),
                    reverse=True,
                )
                keep = set(ranked[:top_n])
                edges = [
                    e
                    for e in edges
                    if str(e.get("from", "")).replace("sub::", "") in keep
                    and str(e.get("to", "")).replace("sub::", "") in keep
                ]
                subreddits = keep

            for sub in subreddits:
                size = max(18, min(56, 20 + out_degree[sub] * 3))
                add_node(
                    {
                        "id": f"sub::{sub}",
                        "label": sub,
                        "type": "subreddit",
                        "shape": "dot",
                        "size": size,
                        "color": NODE_COLORS["subreddit"],
                        "font": {"color": "#ffffff", "size": 12},
                    }
                )

        elif mode == "sources":
            rows = con.execute(
                f"""
                SELECT p.subreddit, p.domain, COUNT(*) AS cnt
                FROM posts p
                JOIN narratives n ON CAST(p.duplicate_cluster_id AS BIGINT)=n.cluster_id
                WHERE n.narrative_id IN ('{narrative_ids_sql}')
                  AND p.subreddit IS NOT NULL
                  AND p.domain IS NOT NULL
                  AND p.domain <> ''
                GROUP BY 1, 2
                ORDER BY cnt DESC
                """
            ).fetchall()

            per_sub = defaultdict(list)
            for sub, dom, cnt in rows:
                per_sub[str(sub)].append((str(dom), int(cnt)))

            dom_freq = defaultdict(int)
            for sub, pairs in per_sub.items():
                for dom, cnt in sorted(pairs, key=lambda x: x[1], reverse=True)[:MAX_DOMAINS_PER_SUB]:
                    eid = hashlib.md5(f"sd::{sub}::{dom}".encode()).hexdigest()[:12]
                    edges.append(
                        {
                            "id": eid,
                            "from": f"sub::{sub}",
                            "to": f"dom::{dom}",
                            "edge_type": "source",
                            "color": {"color": EDGE_COLORS["source"], "opacity": 0.35},
                            "width": _edge_width(cnt),
                            "title": f"{sub} -> {dom} ({cnt})",
                            "arrows": "to",
                        }
                    )
                    dom_freq[dom] += cnt
                    add_node(
                        {
                            "id": f"sub::{sub}",
                            "label": sub,
                            "type": "subreddit",
                            "shape": "dot",
                            "size": 22,
                            "color": NODE_COLORS["subreddit"],
                            "font": {"color": "#ffffff", "size": 12},
                        }
                    )

            for dom, freq in dom_freq.items():
                size = max(18, min(48, 18 + int(freq ** 0.4)))
                add_node(
                    {
                        "id": f"dom::{dom}",
                        "label": dom,
                        "type": "domain",
                        "shape": "triangle",
                        "size": size,
                        "color": NODE_COLORS["domain"],
                        "font": {"color": "#ffffff", "size": 10},
                    }
                )

        else:  # amplifiers
            amp_rows = con.execute("SELECT author, amplification_events FROM amplification").fetchall()
            amp_map = {str(a): float(s or 0.0) for a, s in amp_rows}

            rows = con.execute(
                f"""
                SELECT p.author, p.subreddit, COUNT(*) AS cnt
                FROM posts p
                JOIN narratives n ON CAST(p.duplicate_cluster_id AS BIGINT)=n.cluster_id
                WHERE n.narrative_id IN ('{narrative_ids_sql}')
                  AND p.author IS NOT NULL AND p.author <> ''
                  AND p.subreddit IS NOT NULL AND p.subreddit <> ''
                GROUP BY 1, 2
                ORDER BY cnt DESC
                """
            ).fetchall()

            per_sub = defaultdict(list)
            for author, sub, cnt in rows:
                per_sub[str(sub)].append((str(author), int(cnt)))

            for sub, pairs in per_sub.items():
                top_pairs = sorted(pairs, key=lambda x: x[1], reverse=True)[:MAX_AUTHORS_PER_SUB]
                low_cluster = []
                for author, cnt in top_pairs:
                    amp_score = float(amp_map.get(author, 0.0))
                    if amp_score < AMP_THRESHOLD:
                        low_cluster.append(author)
                        continue

                    eid = hashlib.md5(f"as::{author}::{sub}".encode()).hexdigest()[:12]
                    edges.append(
                        {
                            "id": eid,
                            "from": f"aut::{author}",
                            "to": f"sub::{sub}",
                            "edge_type": "amplifier",
                            "color": {"color": EDGE_COLORS["amplifier"], "opacity": 0.35},
                            "width": _edge_width(cnt),
                            "title": f"{author} -> {sub} ({cnt})",
                            "arrows": "to",
                        }
                    )

                    author_size = max(11, min(36, 12 + abs(amp_score) * 5))
                    add_node(
                        {
                            "id": f"aut::{author}",
                            "label": author,
                            "type": "author",
                            "shape": "square",
                            "size": author_size,
                            "color": NODE_COLORS["author"],
                            "font": {"color": "#ffffff", "size": 10},
                        }
                    )

                add_node(
                    {
                        "id": f"sub::{sub}",
                        "label": sub,
                        "type": "subreddit",
                        "shape": "dot",
                        "size": 22,
                        "color": NODE_COLORS["subreddit"],
                        "font": {"color": "#ffffff", "size": 12},
                    }
                )

                if low_cluster:
                    cid = f"cls::{sub}"
                    add_node(
                        {
                            "id": cid,
                            "label": "Other Authors",
                            "type": "author_cluster",
                            "shape": "square",
                            "size": 12,
                            "color": NODE_COLORS["author_cluster"],
                            "title": f"Low-influence amplifiers in r/{sub}",
                        }
                    )
                    edges.append(
                        {
                            "id": hashlib.md5(f"cluster::{sub}".encode()).hexdigest()[:12],
                            "from": cid,
                            "to": f"sub::{sub}",
                            "edge_type": "amplifier",
                            "color": {"color": EDGE_COLORS["amplifier"], "opacity": 0.35},
                            "width": 1,
                            "title": f"Other Authors -> {sub}",
                            "arrows": "to",
                        }
                    )

        return {"nodes": nodes, "edges": edges}
    finally:
        con.close()


@router.get("/narrative/{narrative_id}/overlay")
def get_narrative_overlay(narrative_id: str):
    con = _db()
    try:
        nid = _norm_nid(narrative_id)
        row = con.execute("SELECT spread_sequence FROM chains WHERE narrative_id = ? LIMIT 1", [nid]).fetchone()
        if not row:
            return {"narrative_id": narrative_id, "edges": []}

        seq = _parse_sequence(row[0])
        if len(seq) < 2:
            return {"narrative_id": narrative_id, "edges": []}

        edges = []
        for idx in range(len(seq) - 1):
            src = seq[idx]
            tgt = seq[idx + 1]
            if src == tgt:
                continue
            edges.append(
                {
                    "source": f"sub::{src}",
                    "target": f"sub::{tgt}",
                    "sequence_index": idx + 1,
                    "timestamp": None,
                }
            )

        return {"narrative_id": narrative_id, "edges": edges}
    finally:
        con.close()


@router.post("/narrative/{narrative_id}/analyze")
async def analyze_narrative(narrative_id: str):
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="GROQ_API_KEY not configured.")

    con = _db()
    try:
        nid = _norm_nid(narrative_id)
        narr = con.execute(
            """
            SELECT narrative_id, cluster_id, representative_title, primary_domain,
                   unique_authors, unique_subreddits_x, spread_strength, first_seen_x, last_seen
            FROM narratives
            WHERE narrative_id = ?
            LIMIT 1
            """,
            [nid],
        ).fetchone()
        if not narr:
            raise HTTPException(status_code=404, detail=f"Narrative '{narrative_id}' not found.")

        cluster_id = narr[1]
        top_posts = con.execute(
            """
            SELECT title, subreddit, author, domain, score, num_comments, created_datetime, url
            FROM posts
            WHERE CAST(duplicate_cluster_id AS BIGINT)=?
            ORDER BY score DESC, num_comments DESC
            LIMIT 12
            """,
            [cluster_id],
        ).fetchall()

        subreddits = [r[0] for r in con.execute(
            "SELECT subreddit FROM posts WHERE CAST(duplicate_cluster_id AS BIGINT)=? GROUP BY subreddit ORDER BY COUNT(*) DESC LIMIT 12",
            [cluster_id],
        ).fetchall()]
        authors = [r[0] for r in con.execute(
            "SELECT author FROM posts WHERE CAST(duplicate_cluster_id AS BIGINT)=? GROUP BY author ORDER BY COUNT(*) DESC LIMIT 12",
            [cluster_id],
        ).fetchall()]
        domains = [r[0] for r in con.execute(
            "SELECT domain FROM posts WHERE CAST(duplicate_cluster_id AS BIGINT)=? AND domain IS NOT NULL AND domain<>'' GROUP BY domain ORDER BY COUNT(*) DESC LIMIT 10",
            [cluster_id],
        ).fetchall()]
        timeline = con.execute(
            """
            SELECT created_datetime::DATE AS date, COUNT(*) AS post_count
            FROM posts
            WHERE CAST(duplicate_cluster_id AS BIGINT)=?
            GROUP BY 1
            ORDER BY 1
            """,
            [cluster_id],
        ).fetchall()
        chain_row = con.execute("SELECT spread_sequence FROM chains WHERE narrative_id=? LIMIT 1", [nid]).fetchone()
        spread_path = _parse_sequence(chain_row[0]) if chain_row else []

        prompt = f"""You are a senior narrative intelligence analyst.
Analyze this narrative context from database records and provide a detailed investigation brief.

Return plain text with these exact sections:
Narrative Summary
Propagation Pattern
Amplification Actors
Source Influence
Timeline of Events
Potential Impact

Context:
- Narrative ID: {nid}
- Title: {narr[2]}
- Primary domain: {narr[3]}
- Unique authors: {narr[4]}
- Unique subreddits: {narr[5]}
- Spread score: {narr[6]}
- First seen: {narr[7]}
- Last seen: {narr[8]}

Top Reddit Posts:
{json.dumps([{"title": p[0], "subreddit": p[1], "author": p[2], "domain": p[3], "score": p[4], "comments": p[5], "created": str(p[6]), "url": p[7]} for p in top_posts], ensure_ascii=False)}

Subreddits involved:
{json.dumps(subreddits, ensure_ascii=False)}

Authors involved:
{json.dumps(authors, ensure_ascii=False)}

Domains used:
{json.dumps(domains, ensure_ascii=False)}

Spread path:
{json.dumps(spread_path, ensure_ascii=False)}

Timeline:
{json.dumps([{"date": str(t[0]), "post_count": int(t[1])} for t in timeline], ensure_ascii=False)}
"""

        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(
                GROQ_API_URL,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": GROQ_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 900,
                    "temperature": 0.2,
                },
            )
            resp.raise_for_status()
            report = resp.json()["choices"][0]["message"]["content"].strip()

        return {
            "narrative_id": nid,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "report": report,
            "context": {
                "subreddits": subreddits,
                "authors": authors,
                "domains": domains,
                "spread_path": spread_path,
                "timeline": [{"date": str(t[0]), "post_count": int(t[1])} for t in timeline],
            },
        }
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"Groq API error: {e.response.status_code}")
    except HTTPException:
        raise
    except Exception as e:
        log.exception("narrative analyze failed")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        con.close()


def _build_node_prompt(node_type: str, node_id: str, ctx: Optional[dict]) -> str:
    if not isinstance(ctx, dict):
        ctx = {}
    if node_type == "subreddit":
        return f"Analyze r/{node_id}. Domains: {ctx.get('top_domains')}. Neighbors: {ctx.get('neighbor_subreddits')}. Task: community intelligence brief (4-6 sentences). End with Propagation Role."
    if node_type == "domain":
        return f"Analyze domain {node_id}. Usage: {ctx.get('subreddits_using')}. Task: source intelligence brief. End with Source Role."
    if node_type in ["author", "author_cluster"]:
        return f"Analyze u/{node_id}. Activity: {ctx.get('subreddits')}. Task: amplifier intelligence brief. End with Amplifier Role."
    return f"Analyze {node_id}"


@router.post("/analyze", response_model=AnalyzeNodeResponse, summary="AI node intelligence brief")
async def analyze_node(req: AnalyzeNodeRequest):
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise HTTPException(503, "GROQ_API_KEY not configured.")
    prompt = _build_node_prompt(req.node_type, req.node_id, req.context_data)
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(
                GROQ_API_URL,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": GROQ_MODEL, "messages": [{"role": "user", "content": prompt}]},
            )
            resp.raise_for_status()
            raw = resp.json()["choices"][0]["message"]["content"].strip()
            return AnalyzeNodeResponse(analysis=raw, risk_level="Analyzed", key_points=[])
    except Exception as e:
        log.error("AI Error: %s", e)
        raise HTTPException(502, f"AI Error: {e}")
