"""
routers/user.py — Layer 4 User Intelligence

Endpoints:
  GET /user/{author}     → full user profile + amplification metrics
  GET /user              → paginated user list
"""
from __future__ import annotations

import logging
from typing import List, Optional

import pandas as pd
from fastapi import APIRouter, Depends, Query, HTTPException

from networkgraph.data.loader import get_store, DataStore
from networkgraph.models.schemas import UserDetail

router = APIRouter(prefix="/user", tags=["user"])
log = logging.getLogger("sntis.user")


def _safe(val, cast=None):
    if pd.isna(val):
        return None
    try:
        return cast(val) if cast else val
    except Exception:
        return None


def _build_user_detail(author: str, store: DataStore) -> UserDetail:
    row = store.user_map.get(author)
    if not row:
        raise HTTPException(
            status_code=404,
            detail=f"User '{author}' not found in user_intelligence_summary."
        )

    amp = store.amplification_map.get(author, {})

    return UserDetail(
        author=author,
        total_duplicate_posts=int(row.get("total_duplicate_posts") or 0),
        unique_narratives=int(row.get("unique_narratives") or 0),
        communities_active_in=_safe(row.get("communities_active_in"), int),
        first_seen=_safe(row.get("first_seen")),
        most_common_domain=_safe(row.get("most_common_domain")),
        final_influence_score=_safe(row.get("final_influence_score"), float),
        total_relative_amplification=_safe(
            amp.get("total_relative_amplification") or
            row.get("total_relative_amplification"), float
        ),
        amplification_events=_safe(amp.get("amplification_events"), int),
        avg_relative_amplification=_safe(amp.get("avg_relative_amplification"), float),
        max_relative_amplification=_safe(amp.get("max_relative_amplification"), float),
    )


@router.get(
    "/{author}",
    response_model=UserDetail,
    summary="User behavioral profile",
)
def get_user(author: str, store: DataStore = Depends(get_store)):
    """
    Returns the full behavioral + amplification profile for a given Reddit author.
    Powers the user hover card in the macro graph.
    """
    return _build_user_detail(author, store)


@router.get(
    "",
    response_model=List[UserDetail],
    summary="List all users (paginated)",
)
def list_users(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    min_influence: Optional[float] = Query(None, description="Filter by minimum final_influence_score"),
    store: DataStore = Depends(get_store),
):
    """Paginated list of all tracked users, optionally filtered by influence threshold."""
    authors = list(store.user_map.keys())

    if min_influence is not None:
        authors = [
            a for a in authors
            if _safe(store.user_map[a].get("final_influence_score"), float) is not None
            and float(store.user_map[a].get("final_influence_score", 0) or 0) >= min_influence
        ]

    page = authors[offset: offset + limit]
    return [_build_user_detail(a, store) for a in page]
