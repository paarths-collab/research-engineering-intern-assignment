"""
routers/narrative.py — Layer 3 Narrative Intelligence

Endpoints:
  GET /narrative/{narrative_id}   → narrative-level detail
  GET /narrative                  → paginated list of all narratives
"""
from __future__ import annotations

import logging
from typing import List, Optional

import pandas as pd
from fastapi import APIRouter, Depends, Query, HTTPException

from networkgraph.data.loader import get_store, DataStore
from networkgraph.models.schemas import NarrativeDetail

router = APIRouter(prefix="/narrative", tags=["narrative"])
log = logging.getLogger("sntis.narrative")


def _safe(val, cast=None):
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    try:
        return cast(val) if cast else val
    except Exception:
        return None


def _build_narrative_detail(narrative_id: str, store: DataStore) -> NarrativeDetail:
    row = store.narrative_map.get(narrative_id)
    if not row:
        raise HTTPException(
            status_code=404,
            detail=f"Narrative '{narrative_id}' not found in narrative_intelligence_summary."
        )

    topic_info = store.topic_map.get(narrative_id, {})

    # Get a sample post from the edge table for title/url/origin
    edge_df = store.edges_df[
        store.edges_df["narrative_id"].astype(str) == narrative_id
    ]

    sample_title = None
    sample_url = None
    origin_subreddit = None

    if not edge_df.empty:
        # Prefer origin post (hours_from_origin == 0)
        origin_rows = edge_df[edge_df["hours_from_origin"] == 0]
        ref_row = origin_rows.iloc[0] if not origin_rows.empty else edge_df.iloc[0]
        sample_title = _safe(ref_row.get("title"))
        sample_url = _safe(ref_row.get("url"))
        origin_subreddit = _safe(ref_row.get("origin_subreddit") or ref_row.get("subreddit"))

    return NarrativeDetail(
        narrative_id=narrative_id,
        total_posts=_safe(row.get("total_posts"), int),
        unique_subreddits=_safe(row.get("unique_subreddits"), int),
        unique_authors=_safe(row.get("unique_authors"), int),
        first_seen=_safe(row.get("first_seen")),
        last_seen=_safe(row.get("last_seen")),
        spread_strength=_safe(row.get("spread_strength"), float),
        topic_cluster=topic_info.get("topic_cluster") or _safe(row.get("topic_cluster")),
        topic_label=topic_info.get("topic_label") or _safe(row.get("topic_label")),
        sample_title=sample_title,
        sample_url=sample_url,
        origin_subreddit=origin_subreddit,
    )


@router.get(
    "/{narrative_id}",
    response_model=NarrativeDetail,
    summary="Narrative intelligence detail",
)
def get_narrative(narrative_id: str, store: DataStore = Depends(get_store)):
    """
    Returns full intelligence summary for a single narrative_id.
    Powers the side panel when a user clicks an edge in the graph.
    """
    return _build_narrative_detail(narrative_id, store)


@router.get(
    "",
    response_model=List[NarrativeDetail],
    summary="List all narratives",
)
def list_narratives(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    topic_cluster: Optional[str] = Query(None),
    store: DataStore = Depends(get_store),
):
    """
    Paginated list of all narratives.
    Optional filter by topic_cluster.
    """
    df = store.narratives_df.copy()

    if topic_cluster:
        # Try native column first, fallback to topic_map
        if "topic_cluster" in df.columns:
            df = df[df["topic_cluster"].astype(str) == topic_cluster]
        else:
            ids_in_cluster = [
                nid for nid, tinfo in store.topic_map.items()
                if str(tinfo.get("topic_cluster", "")) == topic_cluster
            ]
            df = df[df["narrative_id"].astype(str).isin(ids_in_cluster)]

    narrative_ids = df["narrative_id"].astype(str).tolist()
    page_ids = narrative_ids[offset: offset + limit]

    return [_build_narrative_detail(nid, store) for nid in page_ids]
