"""
routers/narratives.py — Alias endpoints for narrative ecosystem filters.

Provides /narratives/* routes that proxy to the DB-backed intelligence
implementation so clients can use cleaner endpoint paths.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query

from networkgraph.routers import intelligence as intel

router = APIRouter(prefix="/narratives", tags=["narratives"])


@router.get("/spread-levels")
def spread_levels():
    return intel.get_spread_levels()


@router.get("/subreddit-reach")
def subreddit_reach():
    return intel.get_subreddit_reach()


@router.get("/timeline")
def timeline(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
):
    return intel.get_timeline(start_date=start_date, end_date=end_date)


@router.get("")
def narratives(
    min_authors: int = Query(1, ge=0),
    min_subreddits: int = Query(0, ge=0),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=1000),
):
    return intel.get_narratives(
        min_authors=min_authors,
        min_subreddits=min_subreddits,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )
