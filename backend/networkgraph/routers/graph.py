"""
routers/graph.py — Layer 1 Macro Network View

Endpoints:
  GET /graph            → full graph (nodes + edges + topic clusters)
  GET /graph/time       → time-filtered edges only
  GET /graph/topics     → available topic clusters
"""
from __future__ import annotations
import hashlib
import logging
from datetime import datetime, timezone
from typing import List, Dict, Optional

import pandas as pd
import numpy as np
from fastapi import APIRouter, Depends, Query, HTTPException

from networkgraph.data.loader import get_store, DataStore
from networkgraph.models.schemas import (
    SubredditNode, UserNode, GraphEdge,
    GraphResponse, TimeFilterResponse
)

router = APIRouter(prefix="/graph", tags=["graph"])
log = logging.getLogger("sntis.graph")


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _edge_id(narrative_id: str, author: str, subreddit: str) -> str:
    raw = f"{narrative_id}::{author}::{subreddit}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def _safe(val, cast=None):
    # Unwrap numpy scalars to Python native types first
    if isinstance(val, np.integer):
        val = int(val)
    elif isinstance(val, np.floating):
        val = float(val)
    elif isinstance(val, np.bool_):
        val = bool(val)
    elif isinstance(val, np.ndarray):
        return None
    # Now safe to check for NaN/None
    try:
        if val is None or pd.isna(val):
            return None
    except (TypeError, ValueError):
        pass
    try:
        return cast(val) if cast else val
    except Exception:
        return None


def _build_subreddit_nodes(store: DataStore) -> List[SubredditNode]:
    nodes = []
    for sub, row in store.subreddit_map.items():
        echo = None
        if store.echo_map and sub in store.echo_map:
            echo = _safe(store.echo_map[sub].get("echo_score"), float)

        nodes.append(SubredditNode(
            id=f"sub::{sub}",
            label=sub,
            total_duplicate_posts=int(row.get("total_duplicate_posts") or 0),
            unique_narratives=int(row.get("unique_narratives") or 0),
            unique_users=int(row.get("unique_users") or 0),
            avg_score=float(row.get("avg_score") or 0.0),
            top_domains=_safe(row.get("top_domains")),
            echo_score=echo,
        ))
    return nodes


def _build_user_nodes(store: DataStore) -> List[UserNode]:
    nodes = []
    for author, row in store.user_map.items():
        amp_row = store.amplification_map.get(author, {})
        nodes.append(UserNode(
            id=f"usr::{author}",
            label=author,
            total_duplicate_posts=int(row.get("total_duplicate_posts") or 0),
            unique_narratives=int(row.get("unique_narratives") or 0),
            communities_active_in=_safe(row.get("communities_active_in"), int),
            first_seen=_safe(row.get("first_seen")),
            most_common_domain=_safe(row.get("most_common_domain")),
            final_influence_score=_safe(row.get("final_influence_score"), float),
            total_relative_amplification=_safe(
                amp_row.get("total_relative_amplification") or
                row.get("total_relative_amplification"), float
            ),
        ))
    return nodes


def _row_to_edge(row: dict) -> GraphEdge:
    narrative_id = str(row.get("narrative_id", ""))
    author = str(row.get("author", ""))
    subreddit = str(row.get("subreddit", ""))
    hours = _safe(row.get("hours_from_origin"), float)

    dt = row.get("created_datetime")
    if hasattr(dt, "isoformat"):
        dt_str = dt.isoformat()
    else:
        dt_str = _safe(dt, str)

    return GraphEdge(
        id=_edge_id(narrative_id, author, subreddit),
        narrative_id=narrative_id,
        source=f"usr::{author}",
        target=f"sub::{subreddit}",
        title=str(row.get("title", "")),
        domain=_safe(row.get("domain")),
        url=_safe(row.get("url")),
        permalink=_safe(row.get("permalink")),
        created_datetime=dt_str,
        score=_safe(row.get("score"), float),
        num_comments=_safe(row.get("num_comments"), int),
        origin_subreddit=_safe(row.get("origin_subreddit")),
        hours_from_origin=hours,
        topic_cluster=str(_safe(row.get("topic_cluster"))) if _safe(row.get("topic_cluster")) is not None else None,
        topic_label=str(_safe(row.get("topic_label"))) if _safe(row.get("topic_label")) is not None else None,
        is_origin=(hours == 0.0 or hours is None),
    )


def _build_edges(df: pd.DataFrame) -> List[GraphEdge]:
    records = df.where(pd.notna(df), None).to_dict(orient="records")
    return [_row_to_edge(r) for r in records]


# ─────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────

@router.get("", response_model=GraphResponse, summary="Full macro network graph")
def get_full_graph(
    limit: Optional[int] = Query(None, description="Max edges to return (default: all)"),
    topic_cluster: Optional[str] = Query(None, description="Filter by topic cluster"),
    store: DataStore = Depends(get_store),
):
    """
    Returns all subreddit nodes, user nodes, edges, and topic cluster legend.
    This is the full dataset for the Layer 1 macro view.
    """
    df = store.edges_df.copy()

    if topic_cluster:
        df = df[df["topic_cluster"] == topic_cluster]

    if limit:
        df = df.head(limit)

    # Build topic cluster legend
    topic_clusters: Dict[str, str] = {}
    if "topic_cluster" in df.columns and "topic_label" in df.columns:
        for _, row in store.topics_df.drop_duplicates("topic_cluster").iterrows():
            c = str(row.get("topic_cluster", ""))
            l = str(row.get("topic_label", ""))
            if c:
                topic_clusters[c] = l

    return GraphResponse(
        subreddit_nodes=_build_subreddit_nodes(store),
        user_nodes=_build_user_nodes(store),
        edges=_build_edges(df),
        topic_clusters=topic_clusters,
    )


@router.get("/time", response_model=TimeFilterResponse, summary="Time-filtered edges")
def get_time_filtered_graph(
    before: str = Query(..., description="ISO8601 datetime — show edges at or before this time"),
    store: DataStore = Depends(get_store),
):
    """
    Layer 4 — Time scrubber.
    Returns only edges where created_datetime <= `before`.
    Frontend hides nodes with no active edges.
    """
    try:
        cutoff = pd.to_datetime(before, utc=True)
    except Exception:
        raise HTTPException(status_code=400, detail=f"Invalid datetime format: '{before}'. Use ISO8601.")

    df = store.edges_df.copy()
    df_filtered = df[df["created_datetime"] <= cutoff]

    edges = _build_edges(df_filtered)
    active_user_ids = list({e.source for e in edges})
    active_subreddit_ids = list({e.target for e in edges})

    return TimeFilterResponse(
        edges=edges,
        active_user_ids=active_user_ids,
        active_subreddit_ids=active_subreddit_ids,
    )


@router.get("/topics", summary="Available topic clusters")
def get_topics(store: DataStore = Depends(get_store)):
    """Returns all unique topic clusters and their labels for the legend."""
    result = {}
    for _, row in store.topics_df.drop_duplicates("topic_cluster").iterrows():
        c = str(row.get("topic_cluster", ""))
        l = str(row.get("topic_label", ""))
        if c:
            result[c] = l
    return {"topic_clusters": result, "count": len(result)}
