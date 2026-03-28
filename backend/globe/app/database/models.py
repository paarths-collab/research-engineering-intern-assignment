from __future__ import annotations
from pydantic import BaseModel, Field
from typing import List, Optional, Any
from datetime import datetime


# ── Ingestion Layer ──────────────────────────────────────────
class RawPost(BaseModel):
    id: str
    title: str
    subreddit: str
    score: int = 0
    num_comments: int = 0
    created_utc: float = 0.0
    author: str = "[unknown]"
    url: str = ""
    engagement_score: float = 0.0
    velocity_score: float = 0.0


# ── Geo Filter Layer ─────────────────────────────────────────
class GeoCandidate(BaseModel):
    post_id: str
    title: str
    detected_geo_terms: List[str] = []
    subreddit: str = ""


# ── Geo Resolution Layer ─────────────────────────────────────
class ResolvedLocation(BaseModel):
    name: str
    lat: float
    lon: float
    geo_type: str = "unknown"
    display_name: str = ""


# ── Event Structuring Layer ──────────────────────────────────
class StructuredEvent(BaseModel):
    id: str
    post_id: str
    event_type: str = "unknown"
    primary_location: str
    secondary_locations: List[str] = []
    key_entities: List[str] = []
    search_queries: List[str] = []


# ── News Correlation Layer ───────────────────────────────────
class NewsArticle(BaseModel):
    id: str
    event_id: str
    title: str
    snippet: str = ""
    url: str
    source: str = ""
    published_at: str = ""
    is_trusted: bool = False


class NewsBundle(BaseModel):
    event_id: str
    articles: List[NewsArticle] = []
    news_count: int = 0
    trusted_source_count: int = 0


# ── Intelligence Layer ───────────────────────────────────────
class NarrativeIntel(BaseModel):
    event_id: str
    summary: str = ""
    sentiment_label: str = "neutral"
    sentiment_confidence: float = 0.5
    risk_level: str = "Low"
    strategic_implications: List[str] = []


# ── Impact Scoring Layer ─────────────────────────────────────
class ImpactScore(BaseModel):
    event_id: str
    impact_value: float = Field(ge=0.0, le=1.0)
    confidence_level: str = "Low"


# ── Cluster Layer ────────────────────────────────────────────
class EventCluster(BaseModel):
    cluster_id: str
    post_ids: List[str] = []
    primary_location: str
    lat: float
    lon: float
    average_impact: float = 0.0
    dominant_sentiment: str = "neutral"
    risk_level: str = "Low"
    escalation_level: str = "Emerging"
    summary: str = ""
    strategic_implications: List[str] = []
    news_count: int = 0
    confidence: str = "Low"
    run_date: str = ""


# ── Final Map Output Layer ───────────────────────────────────
class MapEvent(BaseModel):
    id: str
    title: str
    event_id: str = ""
    locations: List[ResolvedLocation] = []
    timestamp: str = ""
    impact_score: float = 0.0
    sentiment: str = "neutral"
    sentiment_score: float = 0.5
    risk_level: str = "Low"
    subreddit: str = ""
    reddit_post_ids: List[str] = []
    reddit_metrics: dict = {}
    news_sources: List[dict] = []
    confidence: str = "Low"
    summary: str = ""
    strategic_implications: List[str] = []
    last_updated: str = ""


# ── Pipeline Run State ───────────────────────────────────────
class PipelineStatus(BaseModel):
    run_id: str
    status: str = "pending"       # pending | running | complete | failed
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    posts_ingested: int = 0
    geo_candidates: int = 0
    events_structured: int = 0
    news_fetched: int = 0
    clusters_built: int = 0
    error: Optional[str] = None
