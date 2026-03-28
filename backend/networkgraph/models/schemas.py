from __future__ import annotations
from typing import Optional, List, Dict, Any, Union
from pydantic import BaseModel, field_validator
import pandas as pd


class SNTISModel(BaseModel):
    """Base class that automatically converts pandas NaN to None."""

    @field_validator("*", mode="before")
    @classmethod
    def _nan_to_none(cls, v):
        # Fallback for pandas/numpy NaN to None
        # Lists and dicts should be returned as-is
        if isinstance(v, (list, dict)):
            return v
            
        import numpy as np
        # Numpy arrays and pandas Series are list-like; pd.isna on them returns an array
        if isinstance(v, (np.ndarray, pd.Series, pd.Index)):
            return v
            
        try:
            # Only call pd.isna on scalars or single values
            if pd.isna(v):
                return None
        except Exception:
            pass
        return v


# ─────────────────────────────────────────────
# LAYER 1 — GRAPH (Macro View)
# ─────────────────────────────────────────────

class SubredditNode(SNTISModel):
    id: str
    type: str = "subreddit"
    label: str
    total_duplicate_posts: int
    unique_narratives: int
    unique_users: int
    avg_score: float
    top_domains: Optional[str] = None
    echo_score: Optional[float] = None


class UserNode(SNTISModel):
    id: str
    type: str = "user"
    label: str
    total_duplicate_posts: int
    unique_narratives: int
    communities_active_in: Optional[int] = None
    first_seen: Optional[str] = None
    most_common_domain: Optional[str] = None
    final_influence_score: Optional[float] = None
    total_relative_amplification: Optional[float] = None


class GraphEdge(SNTISModel):
    id: str                        # narrative_id + author + subreddit hash
    narrative_id: str
    source: str                    # author (user node id)
    target: str                    # subreddit node id
    title: str
    domain: Optional[str] = None
    url: Optional[str] = None
    permalink: Optional[str] = None
    created_datetime: Optional[str] = None
    score: Optional[float] = None
    num_comments: Optional[int] = None
    origin_subreddit: Optional[str] = None
    hours_from_origin: Optional[float] = None
    topic_cluster: Optional[Union[str, int]] = None
    topic_label: Optional[str] = None
    is_origin: bool

class GraphResponse(SNTISModel):
    subreddit_nodes: List[SubredditNode]
    user_nodes: List[UserNode]
    edges: List[GraphEdge]
    topic_clusters: Dict[str, str]   # cluster_id -> label


# ─────────────────────────────────────────────
# LAYER 2 — TRANSPORT CHAIN (Micro View)
# ─────────────────────────────────────────────

class TransportStep(SNTISModel):
    step_number: int
    subreddit: str
    author: str
    created_datetime: Optional[str] = None
    hours_from_origin: Optional[float] = None
    score: Optional[float] = None
    title: Optional[str] = None
    url: Optional[str] = None


class TransportChainResponse(SNTISModel):
    narrative_id: str
    total_steps: int
    origin_subreddit: Optional[str] = None
    chain: List[TransportStep]


# ─────────────────────────────────────────────
# LAYER 3 — NARRATIVE INTELLIGENCE
# ─────────────────────────────────────────────

class NarrativeDetail(SNTISModel):
    narrative_id: str
    total_posts: Optional[int] = None
    unique_subreddits: Optional[int] = None
    unique_authors: Optional[int] = None
    first_seen: Optional[str] = None
    last_seen: Optional[str] = None
    spread_strength: Optional[float] = None
    topic_cluster: Optional[str] = None
    topic_label: Optional[str] = None
    # Joined from edge table
    sample_title: Optional[str] = None
    sample_url: Optional[str] = None
    primary_domain: Optional[str] = None
    origin_subreddit: Optional[str] = None


# ─────────────────────────────────────────────
# NARRATIVE EXPLORER & OVERLAY
# ─────────────────────────────────────────────

class NarrativeOverlayStep(SNTISModel):
    source: str           # subreddit node id
    target: str           # subreddit node id
    timestamp: Optional[str] = None
    sequence_index: int

class NarrativeOverlayResponse(SNTISModel):
    narrative_id: str
    edges: List[NarrativeOverlayStep]

class NarrativeListEntry(SNTISModel):
    narrative_id: str
    representative_title: str
    author_count: int
    community_count: int
    spread_score: float
    primary_domain: Optional[str] = None
    first_seen: Optional[str] = None

class NarrativeListResponse(SNTISModel):
    # Keys like "3+", "4+", "5+", "6+", "10+"
    tabs: Dict[str, List[NarrativeListEntry]]


# ─────────────────────────────────────────────
# LAYER 4 — USER INTELLIGENCE
# ─────────────────────────────────────────────

class UserDetail(SNTISModel):
    author: str
    total_duplicate_posts: int
    unique_narratives: int
    communities_active_in: Optional[int] = None
    first_seen: Optional[str] = None
    most_common_domain: Optional[str] = None
    final_influence_score: Optional[float] = None
    total_relative_amplification: Optional[float] = None
    amplification_events: Optional[int] = None
    avg_relative_amplification: Optional[float] = None
    max_relative_amplification: Optional[float] = None


# ─────────────────────────────────────────────
# LAYER 5 — AI ANALYSIS
# ─────────────────────────────────────────────

class AnalyzeRequest(SNTISModel):
    narrative_id: str
    url: str


class ArticleScrapeInfo(SNTISModel):
    success: bool
    tier_used: str
    title: Optional[str] = None
    text_preview: Optional[str] = None   # first 1000 chars
    word_count: int
    error: Optional[str] = None


class NarrativeAnalysis(SNTISModel):
    article_summary: str
    headline_tone: str
    resonance_factors: str
    spread_pattern_description: str
    amplification_characteristics: str
    topic_cluster_context: str


class AnalyzeResponse(SNTISModel):
    narrative_id: str
    url: str
    scrape_info: ArticleScrapeInfo
    analysis: Optional[NarrativeAnalysis] = None
    raw_llm_response: Optional[str] = None
    error: Optional[str] = None


# ─────────────────────────────────────────────
# NODE INTELLIGENCE (Intelligence Map)
# ─────────────────────────────────────────────

class AnalyzeNodeRequest(SNTISModel):
    node_type: str
    node_id: str
    context_data: Optional[Dict[str, Any]] = None

class AnalyzeNodeResponse(SNTISModel):
    analysis: str
    risk_level: Optional[str] = None
    key_points: Optional[List[str]] = []


# ─────────────────────────────────────────────
# TIME FILTER
# ─────────────────────────────────────────────

class TimeFilterRequest(SNTISModel):
    before_datetime: str    # ISO8601 string, e.g. "2024-03-15T12:00:00"


class TimeFilterResponse(SNTISModel):
    edges: List[GraphEdge]
    active_user_ids: List[str]
    active_subreddit_ids: List[str]


# ─────────────────────────────────────────────
# HEALTH
# ─────────────────────────────────────────────

class HealthResponse(SNTISModel):
    status: str
    datasets_loaded: Dict[str, int]   # dataset_name -> row count
    version: str = "1.0.0"
