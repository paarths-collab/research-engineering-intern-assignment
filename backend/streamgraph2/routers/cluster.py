"""
cluster.py — Cluster-based streamgraph and event intelligence endpoints.

Routes (all under /api prefix from stream_app):
  GET  /clustered-streamgraph            → 5-cluster time-series + spike list
  GET  /timeline-volume                  → per-subreddit daily volume + z-score spikes
  GET  /event-window/{cluster}/{date}    → ±10d post context + topic list
  POST /analyze-event                    → LLM brief (cached by cluster+date+topic)
  GET  /topics                           → headlines in date window (for topic extraction)
  POST /topic-analysis                   → Stage 2 LLM narrative analysis
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from streamgraph2.data import db

router = APIRouter(tags=["Cluster Intelligence"])

# ── Shared cache (ai_cache.json, same file used by hybrid_crew) ──
_CACHE_PATH = Path(__file__).resolve().parents[3] / "data" / "ai_cache.json"


def _load_cache() -> dict:
    if _CACHE_PATH.exists():
        try:
            return json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_cache(cache: dict) -> None:
    _CACHE_PATH.write_text(
        json.dumps(cache, indent=2, default=str, ensure_ascii=False),
        encoding="utf-8",
    )


def _cache_key(cluster: str, event_date: str, topic: str) -> str:
    slug = topic.lower().replace(" ", "_").replace("/", "")[:30]
    return f"cluster_{cluster.lower().replace(' ', '_')}_{event_date}_{slug}"


# ── Endpoints ─────────────────────────────────────────────────

@router.get("/clustered-streamgraph")
async def get_clustered_streamgraph():
    """
    5-cluster streamgraph with pre-detected spike events.

    Returns:
        keys:   ["Geopolitics", "US Politics", "Economy", "Technology", "Culture"]
        data:   [{date, Geopolitics: n, US Politics: n, ...}]
        spikes: [{date, cluster, z_score, post_count}]
    """
    return await db.get_clustered_streamgraph()


@router.get("/event-window/{cluster}/{event_date}")
async def event_window(cluster: str, event_date: str):
    """
    Extract ±10-day post context around a spike.

    Returns:
        cluster, event_date, topics[], total_posts,
        top_subreddits, top_domains, headline_examples
    """
    try:
        date.fromisoformat(event_date)
    except ValueError:
        raise HTTPException(400, "event_date must be YYYY-MM-DD")

    return await db.get_event_window_topics(cluster, event_date)


class EventAnalysisRequest(BaseModel):
    cluster: str
    event_date: str
    topic: str


@router.post("/analyze-event")
async def analyze_event(req: EventAnalysisRequest):
    """
    Build a structured payload from the event window and generate an LLM brief.
    Results are cached by (cluster, date, topic) — no duplicate API calls.

    Returns the full payload + brief + cached flag.
    """
    cache = _load_cache()
    key   = _cache_key(req.cluster, req.event_date, req.topic)

    if key in cache:
        return {**cache[key], "cached": True}

    # Build context from ±10-day post window
    context = await db.get_event_window_topics(req.cluster, req.event_date)

    payload: dict = {
        "event_date":        req.event_date,
        "cluster":           req.cluster,
        "topic":             req.topic,
        "total_posts":       context["total_posts"],
        "top_subreddits":    context["top_subreddits"],
        "top_domains":       context["top_domains"],
        "headline_examples": context["headline_examples"],
    }

    # LLM brief — graceful degradation if API key missing
    from streamgraph2.data.config import GROQ_API_KEY

    brief: str
    if GROQ_API_KEY:
        try:
            from streamgraph2.llm.event_llm import generate_event_brief
            brief = await generate_event_brief(payload)
        except Exception as exc:
            brief = f"[Analysis unavailable: {exc}]"
    else:
        brief = "[GROQ_API_KEY not configured — LLM brief unavailable]"

    result = {**payload, "brief": brief}

    # Persist to cache (without the runtime `cached` flag)
    cache[key] = result
    _save_cache(cache)

    return {**result, "cached": False}


# ── Narrative Timeline ─────────────────────────────────────────

_DATA_CSV = Path(__file__).resolve().parents[3] / "data" / "clean_posts.csv"
_POSTS_DF: pd.DataFrame | None = None


def _get_posts_df() -> pd.DataFrame:
    global _POSTS_DF
    if _POSTS_DF is None:
        df = pd.read_csv(_DATA_CSV, parse_dates=["created_datetime"])
        df["date"] = df["created_datetime"].dt.date
        _POSTS_DF = df
    return _POSTS_DF


@router.get("/timeline-volume")
async def get_timeline_volume():
    """
    Per-subreddit daily post counts + global z-score spike events.

    Returns:
        series: {subreddit: [{date, count}]}
        spikes: [{date, z_score, post_count}]
    """
    df = _get_posts_df()

    grouped = (
        df.groupby(["date", "subreddit"])
          .size()
          .reset_index(name="count")
          .sort_values("date")
    )

    series: dict = {}
    for sub, grp in grouped.groupby("subreddit"):
        points = []
        for _, r in grp.iterrows():
            d_val = r["date"]
            # Find top headline for this subreddit + date
            day_posts = df[(df["date"] == d_val) & (df["subreddit"] == sub)]
            top_head = ""
            if not day_posts.empty:
                top_head = str(day_posts.loc[day_posts["score"].idxmax()]["title"])
            
            points.append({
                "date": str(d_val),
                "count": int(r["count"]),
                "top_headline": top_head
            })
        series[sub] = points

    # Global daily total for spike detection
    daily = df.groupby("date").size().reset_index(name="count").sort_values("date")
    daily["rm"] = daily["count"].rolling(7, min_periods=1).mean()
    daily["rs"] = daily["count"].rolling(7, min_periods=1).std().fillna(0)
    daily["z"]  = ((daily["count"] - daily["rm"]) / daily["rs"].replace(0, 1)).round(3)

    spikes = []
    for _, r in daily[daily["z"] >= 2.0].iterrows():
        d_val = r["date"]
        # Find top global headline for this date
        day_posts = df[df["date"] == d_val]
        top_head = ""
        if not day_posts.empty:
            top_head = str(day_posts.loc[day_posts["score"].idxmax()]["title"])
            
        spikes.append({
            "date": str(d_val),
            "z_score": round(float(r["z"]), 3),
            "post_count": int(r["count"]),
            "top_headline": top_head
        })

    return {"series": series, "spikes": spikes}


@router.get("/topics")
async def get_topics(
    start: str = Query(..., description="YYYY-MM-DD"),
    end:   str = Query(..., description="YYYY-MM-DD"),
):
    """
    Return up to 300 headlines (title + subreddit + domain + date)
    for posts in the [start, end] date window.
    These are sent to the Stage 1 LLM for topic extraction.
    """
    try:
        start_d = date.fromisoformat(start)
        end_d   = date.fromisoformat(end)
    except ValueError:
        raise HTTPException(400, "start and end must be YYYY-MM-DD")

    df   = _get_posts_df()
    mask = (df["date"] >= start_d) & (df["date"] <= end_d)
    sub  = df[mask]
    # Stride-sample to get at most 200 evenly-spread headlines
    if len(sub) > 200:
        step = len(sub) // 200
        sub  = sub.iloc[::step].head(200)

    headlines = [
        {
            "title":     row["title"],
            "subreddit": row["subreddit"],
            "domain":    row.get("domain", ""),
            "date":      str(row["date"]),
        }
        for _, row in sub.iterrows()
    ]

    return {"start": start, "end": end, "count": len(headlines), "headlines": headlines}


class ExtractTopicsRequest(BaseModel):
    start_date: str
    end_date:   str


@router.post("/extract-topics")
async def extract_topics_endpoint(req: ExtractTopicsRequest):
    """
    Stage 1: fetch up to 300 headlines from [start_date, end_date],
    run LLM topic extraction, return [{topic, subreddits, example_headlines}].
    Cached by date range.
    """
    cache = _load_cache()
    key   = f"topics_extract_{req.start_date}_{req.end_date}"
    if key in cache:
        return {**cache[key], "cached": True}

    try:
        start_d = date.fromisoformat(req.start_date)
        end_d   = date.fromisoformat(req.end_date)
    except ValueError:
        raise HTTPException(400, "start_date and end_date must be YYYY-MM-DD")

    df   = _get_posts_df()
    mask = (df["date"] >= start_d) & (df["date"] <= end_d)
    sub  = df[mask]
    # Stride-sample to get at most 200 evenly-spread posts for LLM
    if len(sub) > 200:
        step = len(sub) // 200
        sub  = sub.iloc[::step].head(200)

    if sub.empty:
        return {"start_date": req.start_date, "end_date": req.end_date,
                "topics": [], "headline_count": 0, "cached": False}

    headlines = [
        {"title": row["title"], "subreddit": row["subreddit"],
         "domain": row.get("domain", ""), "date": str(row["date"])}
        for _, row in sub.iterrows()
    ]

    from streamgraph2.data.config import GROQ_API_KEY

    topics: list
    llm_error: str | None = None
    if GROQ_API_KEY:
        try:
            from streamgraph2.llm.event_llm import extract_topics
            topics = await extract_topics(headlines)
        except Exception as exc:
            llm_error = str(exc)
            topics = []
    else:
        llm_error = "GROQ_API_KEY not configured on server."
        topics = []

    result = {
        "start_date":     req.start_date,
        "end_date":       req.end_date,
        "topics":         topics,
        "headline_count": len(headlines),
        "llm_error":      llm_error,
    }
    # Do not cache transient LLM failures as empty topics.
    if llm_error is None:
        cache[key] = result
        _save_cache(cache)
    return {**result, "cached": False}


class TopicAnalysisRequest(BaseModel):
    topic:      str
    start_date: str
    end_date:   str


@router.post("/topic-analysis")
async def topic_analysis(req: TopicAnalysisRequest):
    """
    Stage 2: deep narrative analysis for a user-selected topic.
    Collects posts in [start_date, end_date], enriches with bridge author data,
    and calls the Stage 2 LLM.
    Results are cached by (topic_slug + start + end).
    """
    cache = _load_cache()
    slug  = req.topic.lower().replace(" ", "_")[:40]
    key   = f"topic_analysis_{slug}_{req.start_date}_{req.end_date}"

    if key in cache:
        return {**cache[key], "cached": True}

    try:
        start_d = date.fromisoformat(req.start_date)
        end_d   = date.fromisoformat(req.end_date)
    except ValueError:
        raise HTTPException(400, "start_date and end_date must be YYYY-MM-DD")

    df   = _get_posts_df()
    mask = (df["date"] >= start_d) & (df["date"] <= end_d)
    sub  = df[mask]
    # Stride-sample for diverse temporal coverage, capped at 200 for LLM budget
    if len(sub) > 200:
        step = len(sub) // 200
        sub  = sub.iloc[::step].head(200)

    posts = [
        {
            "title":     row["title"],
            "subreddit": row["subreddit"],
            "domain":    row.get("domain", ""),
            "author":    row.get("author", ""),
            "date":      str(row["date"]),
        }
        for _, row in sub.iterrows()
    ]

    # Bridge authors (cross-community posters)
    bridge_path = Path(__file__).resolve().parents[3] / "data" / "bridge_authors_v2.csv"
    bridge_authors: list[str] = []
    if bridge_path.exists():
        ba = pd.read_csv(bridge_path)
        active = ba[ba["author"].isin([p["author"] for p in posts])]
        bridge_authors = active["author"].unique().tolist()[:10]

    top_subreddits = (
        sub.groupby("subreddit").size()
           .sort_values(ascending=False)
           .head(5)
           .reset_index()
           .rename(columns={0: "count"})
           .apply(lambda r: [r["subreddit"], int(r["count"])], axis=1)
           .tolist()
    )
    top_domains = (
        sub[sub["domain"].notna() & (sub["domain"] != "")]
           .groupby("domain").size()
           .sort_values(ascending=False)
           .head(5)
           .reset_index()
           .rename(columns={0: "count"})
           .apply(lambda r: [r["domain"], int(r["count"])], axis=1)
           .tolist()
    )

    from streamgraph2.data.config import GROQ_API_KEY

    brief: str
    if GROQ_API_KEY:
        try:
            from streamgraph2.llm.event_llm import generate_narrative_analysis
            brief = await generate_narrative_analysis(req.topic, posts)
        except Exception as exc:
            brief = f"[Analysis unavailable: {exc}]"
    else:
        brief = "[GROQ_API_KEY not configured — LLM brief unavailable]"

    result = {
        "topic":          req.topic,
        "start_date":     req.start_date,
        "end_date":       req.end_date,
        "total_posts":    len(posts),
        "top_subreddits": top_subreddits,
        "top_domains":    top_domains,
        "bridge_authors": bridge_authors,
        "brief":          brief,
    }

    cache[key] = result
    _save_cache(cache)

    return {**result, "cached": False}

