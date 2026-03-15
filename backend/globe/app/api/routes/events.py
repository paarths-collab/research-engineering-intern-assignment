from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from datetime import date, datetime, timezone
import asyncio
import json
import xml.etree.ElementTree as ET
from urllib.parse import quote_plus
from pathlib import Path
import httpx
import hashlib

from pydantic import BaseModel, Field
from app.config import get_settings
from app.llm.client import request_chat_completion

def load_latest_output():
    """Load latest pipeline output when pipeline deps are available."""
    try:
        from app.pipeline.orchestrator import load_latest_output as _load_latest_output
        return _load_latest_output()
    except Exception:
        return None

from app.pipeline.news_correlator import (
    _search_tavily, _search_newsapi, _search_gnews, _search_newsdata, _is_trusted,
)
from app.database.connection import get_connection
from app.utils.logger import get_logger

router = APIRouter(prefix="/events", tags=["events"])
logger = get_logger(__name__)
settings = get_settings()


class LocationNewsRequest(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    limit: int = Field(default=10, ge=1, le=25)


class HeadlineArticleInput(BaseModel):
    title: str = Field(..., min_length=3)
    link: Optional[str] = None
    description: Optional[str] = None
    source_name: Optional[str] = None
    pub_date: Optional[str] = None


class HeadlineAnalysisRequest(BaseModel):
    headline: str = Field(..., min_length=5)
    location: Optional[str] = None
    scraped_articles: list[HeadlineArticleInput] = Field(default_factory=list)
    scrape_news: bool = True
    max_scraped_articles: int = Field(default=10, ge=1, le=25)


def _dedup_news_records(records: list[dict], limit: int) -> list[dict]:
    dedup: dict[str, dict] = {}
    for item in records:
        url = (item.get("link") or item.get("url") or "").strip()
        title = (item.get("title") or "").strip()
        if not title:
            continue
        key = url or title.lower()
        if key in dedup:
            continue
        dedup[key] = {
            "article_id": hashlib.md5((url or title).encode()).hexdigest()[:16],
            "title": title,
            "description": (item.get("description") or item.get("snippet") or "").strip(),
            "link": url or None,
            "source_name": (item.get("source_name") or item.get("source") or "Unknown").strip(),
            "pub_date": item.get("pub_date") or item.get("published_at") or item.get("published") or None,
        }
        if len(dedup) >= limit:
            break
    return list(dedup.values())

# ── Mock data (used when no pipeline output exists yet) ───────────────────────
_MOCK_EVENTS = [
    {
        "id": "mock-tel-aviv",
        "title": "Tel Aviv, Israel — Escalating",
        "locations": [{"name": "Tel Aviv, Israel", "lat": 32.09, "lon": 34.78, "geo_type": "city", "display_name": ""}],
        "impact_score": 0.72,
        "sentiment": "negative",
        "risk_level": "High",
        "confidence": "Medium",
        "summary": "Regional conflict escalation with cross-border exchange. Diplomatic channels under strain.",
        "strategic_implications": ["Escalation of regional conflict", "Disruption to energy markets", "Civilian displacement risk"],
        "reddit_metrics": {"total_score": 10116, "total_comments": 3419, "post_count": 4, "subreddits": ["worldnews", "news"]},
        "news_sources": [],
        "last_updated": datetime.now(timezone.utc).isoformat(),
    },
    {
        "id": "mock-tehran",
        "title": "Tehran, Iran — Escalating",
        "locations": [{"name": "Tehran, Iran", "lat": 35.69, "lon": 51.39, "geo_type": "city", "display_name": ""}],
        "impact_score": 0.69,
        "sentiment": "neutral",
        "risk_level": "High",
        "confidence": "Medium",
        "summary": "Diplomatic shift following leadership transition. Strategic realignment underway.",
        "strategic_implications": ["Potential US-Iran conflict escalation", "Regional alliance shifts", "Nuclear programme uncertainty"],
        "reddit_metrics": {"total_score": 1627, "total_comments": 236, "post_count": 2, "subreddits": ["worldnews"]},
        "news_sources": [],
        "last_updated": datetime.now(timezone.utc).isoformat(),
    },
    {
        "id": "mock-kyiv",
        "title": "Kyiv, Ukraine — Active",
        "locations": [{"name": "Kyiv, Ukraine", "lat": 50.45, "lon": 30.52, "geo_type": "city", "display_name": ""}],
        "impact_score": 0.81,
        "sentiment": "negative",
        "risk_level": "High",
        "confidence": "High",
        "summary": "Ongoing conflict with sustained infrastructure targeting. Western aid discussions ongoing.",
        "strategic_implications": ["Energy infrastructure at risk", "Western alliance cohesion tested", "Refugee flows increasing"],
        "reddit_metrics": {"total_score": 22000, "total_comments": 7800, "post_count": 9, "subreddits": ["worldnews", "europe", "geopolitics"]},
        "news_sources": [],
        "last_updated": datetime.now(timezone.utc).isoformat(),
    },
    {
        "id": "mock-beijing",
        "title": "Beijing, China — Monitoring",
        "locations": [{"name": "Beijing, China", "lat": 39.91, "lon": 116.39, "geo_type": "city", "display_name": ""}],
        "impact_score": 0.55,
        "sentiment": "neutral",
        "risk_level": "Medium",
        "confidence": "Medium",
        "summary": "Trade tension signals emerging. Policy statements indicate strategic posturing.",
        "strategic_implications": ["Supply chain disruption risk", "Taiwan strait tensions", "Tech sector decoupling"],
        "reddit_metrics": {"total_score": 5400, "total_comments": 1200, "post_count": 3, "subreddits": ["worldnews", "asia"]},
        "news_sources": [],
        "last_updated": datetime.now(timezone.utc).isoformat(),
    },
    {
        "id": "mock-washington",
        "title": "Washington D.C., USA — Active",
        "locations": [{"name": "Washington D.C., USA", "lat": 38.90, "lon": -77.04, "geo_type": "city", "display_name": ""}],
        "impact_score": 0.63,
        "sentiment": "neutral",
        "risk_level": "Medium",
        "confidence": "High",
        "summary": "Policy shifts on foreign aid and military posture generating international attention.",
        "strategic_implications": ["NATO commitment uncertainty", "Foreign aid reallocation", "Diplomatic repositioning"],
        "reddit_metrics": {"total_score": 18000, "total_comments": 5500, "post_count": 7, "subreddits": ["worldnews", "news", "worldpolitics"]},
        "news_sources": [],
        "last_updated": datetime.now(timezone.utc).isoformat(),
    },
    {
        "id": "mock-nairobi",
        "title": "Nairobi, Kenya — Emerging",
        "locations": [{"name": "Nairobi, Kenya", "lat": -1.29, "lon": 36.82, "geo_type": "city", "display_name": ""}],
        "impact_score": 0.38,
        "sentiment": "neutral",
        "risk_level": "Low",
        "confidence": "Low",
        "summary": "Economic instability and social unrest indicators detected. Monitoring escalation potential.",
        "strategic_implications": ["Regional stability risk", "Humanitarian aid access"],
        "reddit_metrics": {"total_score": 840, "total_comments": 102, "post_count": 1, "subreddits": ["worldnews"]},
        "news_sources": [],
        "last_updated": datetime.now(timezone.utc).isoformat(),
    },
]


def _mock_data_payload():
    """Return a mock output payload matching the real pipeline structure."""
    return {
        "run_id": "mock-000",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "event_count": len(_MOCK_EVENTS),
        "events": _MOCK_EVENTS,
        "_is_mock": True,
    }


def _project_root() -> Path:
    # backend/globe/app/api/routes/events.py -> project root at parents[5]
    return Path(__file__).resolve().parents[5]


def _analysis_cache_path() -> Path:
    return _project_root() / "data" / "ai_cache.json"


def _load_analysis_cache() -> dict:
    path = _analysis_cache_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_analysis_cache(cache: dict) -> None:
    path = _analysis_cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")


def _fetch_reddit_context_from_db(event: dict, max_posts: int = 50) -> dict:
    post_ids = list(dict.fromkeys(event.get("reddit_post_ids") or []))
    if not post_ids:
        post_ids = list(dict.fromkeys((event.get("reddit_metrics") or {}).get("post_ids") or []))

    if not post_ids and event.get("id"):
        try:
            conn = get_connection()
            row = conn.execute(
                "SELECT post_ids FROM event_clusters WHERE cluster_id = ? LIMIT 1",
                [event.get("id")],
            ).fetchone()
            if row and row[0]:
                parsed = json.loads(row[0]) if isinstance(row[0], str) else []
                post_ids = list(dict.fromkeys(parsed))
        except Exception:
            post_ids = []

    top_posts = []
    if post_ids:
        conn = get_connection()
        placeholders = ", ".join(["?"] * len(post_ids))
        rows = conn.execute(
            f"""
            SELECT id, title, subreddit, score, num_comments, created_utc, url
            FROM raw_posts
            WHERE id IN ({placeholders})
            ORDER BY score DESC, num_comments DESC
            LIMIT ?
            """,
            [*post_ids, max_posts],
        ).fetchall()
        for r in rows:
            top_posts.append({
                "id": r[0],
                "title": r[1],
                "subreddit": r[2],
                "upvote_score": int(r[3] or 0),
                "comment_count": int(r[4] or 0),
                "timestamp": datetime.fromtimestamp(float(r[5] or 0), tz=timezone.utc).isoformat() if r[5] else None,
                "url": r[6],
            })

    related_subreddits = list(dict.fromkeys((event.get("reddit_metrics") or {}).get("subreddits") or []))
    top_comments = []
    if top_posts:
        top_comments = [
            {
                "post_id": p["id"],
                "summary": f"High discussion volume: {p['comment_count']} comments",
            }
            for p in top_posts[:5]
            if p["comment_count"] > 0
        ]

    return {
        "top_posts": top_posts,
        "top_comments": top_comments,
        "related_subreddits": related_subreddits,
        "reddit_post_ids": [p["id"] for p in top_posts] if top_posts else post_ids,
    }


@router.get("/")
async def get_events(
    risk_level: Optional[str] = Query(None, description="Filter by risk: Low|Medium|High"),
    confidence: Optional[str] = Query(None, description="Filter by confidence: Low|Medium|High"),
    min_impact: float = Query(0.0, ge=0.0, le=1.0),
    limit: int = Query(50, ge=1, le=200),
):
    """Return the latest processed map events."""
    data = load_latest_output() or _mock_data_payload()
    events = data.get("events", [])

    if risk_level:
        events = [e for e in events if e.get("risk_level") == risk_level]
    if confidence:
        events = [e for e in events if e.get("confidence") == confidence]
    if min_impact > 0:
        events = [e for e in events if e.get("impact_score", 0) >= min_impact]

    events.sort(key=lambda e: e.get("impact_score", 0), reverse=True)
    events = events[:limit]

    return {
        "generated_at": data.get("generated_at"),
        "total": len(events),
        "events": events,
    }


@router.get("/summary")
async def get_summary():
    """High-level summary of current global event landscape."""
    data = load_latest_output() or _mock_data_payload()
    events = data.get("events", [])
    risk_dist = {"Low": 0, "Medium": 0, "High": 0}
    sentiment_dist = {}
    for e in events:
        r = e.get("risk_level", "Low")
        risk_dist[r] = risk_dist.get(r, 0) + 1
        s = e.get("sentiment", "neutral")
        sentiment_dist[s] = sentiment_dist.get(s, 0) + 1

    high_impact = [e for e in events if e.get("impact_score", 0) >= 0.5]

    return {
        "run_id": data.get("run_id"),
        "generated_at": data.get("generated_at"),
        "total_events": len(events),
        "risk_distribution": risk_dist,
        "sentiment_distribution": sentiment_dist,
        "high_impact_count": len(high_impact),
        "avg_impact": round(
            sum(e.get("impact_score", 0) for e in events) / len(events), 3
        ) if events else 0,
    }


@router.get("/map")
async def get_map_data():
    """Optimised payload for frontend globe rendering."""
    data = load_latest_output() or _mock_data_payload()
    map_pins = []
    for e in data.get("events", []):
        for loc in e.get("locations", []):
            map_pins.append({
                "id": e["id"],
                "event_id": e.get("event_id") or e["id"],
                "lat": loc.get("lat"),
                "lon": loc.get("lon"),
                "location": loc.get("name"),
                "name": loc.get("name"),
                "title": e.get("title"),
                "timestamp": e.get("timestamp") or e.get("last_updated") or data.get("generated_at"),
                "impact_score": e.get("impact_score"),
                "risk_level": e.get("risk_level"),
                "sentiment": e.get("sentiment"),
                "sentiment_score": e.get("sentiment_score", 0.0),
                "subreddit": e.get("subreddit") or ((e.get("reddit_metrics") or {}).get("subreddits") or [""])[0],
                "reddit_post_ids": e.get("reddit_post_ids") or ((e.get("reddit_metrics") or {}).get("post_ids") or []),
                "confidence": e.get("confidence"),
                "summary": e.get("strategic_implications", [])[:1],
            })

    return {
        "generated_at": data.get("generated_at"),
        "pin_count": len(map_pins),
        "pins": map_pins,
    }


@router.post("/news")
async def get_location_news(payload: LocationNewsRequest):
    """
    Fetch location-aware news based on clicked map coordinates.
    Returns normalized article fields expected by the globe frontend panel.
    """
    async with httpx.AsyncClient(timeout=20.0) as client:
        city = None
        state = None
        country = None
        country_code = None

        try:
            reverse = await client.get(
                "https://nominatim.openstreetmap.org/reverse",
                params={
                    "lat": payload.latitude,
                    "lon": payload.longitude,
                    "format": "jsonv2",
                    "addressdetails": 1,
                },
                headers={"User-Agent": "narrativesignal-globe/1.0"},
            )
            if reverse.status_code == 200:
                rdata = reverse.json() or {}
                addr = rdata.get("address", {}) if isinstance(rdata, dict) else {}
                city = addr.get("city") or addr.get("town") or addr.get("village") or addr.get("hamlet")
                state = addr.get("state")
                country = addr.get("country")
                country_code = (addr.get("country_code") or "").upper() or None
        except Exception as e:
            logger.warning("Reverse geocoding failed for (%.4f, %.4f): %s", payload.latitude, payload.longitude, e)

        place = ", ".join([p for p in [city, state, country] if p]) or f"{payload.latitude:.4f}, {payload.longitude:.4f}"
        queries = []
        if city and country:
            queries.append(f"{city} {country} breaking news")
        if state and country:
            queries.append(f"{state} {country} headlines")
        if country:
            queries.append(f"{country} latest news")
        if not queries:
            queries.append(place)

        raw_articles = []
        try:
            for q in list(dict.fromkeys(queries))[:3]:
                tavily, newsapi, gnews, newsdata = await asyncio.gather(
                    _search_tavily(q, client),
                    _search_newsapi(q, client),
                    _search_gnews(q, client),
                    _search_newsdata(q, client),
                    return_exceptions=True,
                )
                for bucket in (tavily, newsapi, gnews, newsdata):
                    if isinstance(bucket, BaseException) or not isinstance(bucket, list):
                        continue
                    raw_articles.extend(bucket or [])
        except Exception as e:
            logger.warning("Location news search failed for '%s': %s", place, e)

    dedup = {}
    for a in raw_articles:
        url = (a.get("url") or "").strip()
        title = (a.get("title") or "").strip()
        if not url or not title:
            continue
        if url in dedup:
            continue
        dedup[url] = {
            "article_id": hashlib.md5(url.encode()).hexdigest()[:16],
            "title": title,
            "description": (a.get("snippet") or "").strip(),
            "link": url,
            "image_url": a.get("image_url") or None,
            "source_name": (a.get("source") or "Unknown source").strip(),
            "pub_date": a.get("published_at") or a.get("published") or None,
            "category": [],
            "sentiment": None,
        }

    # Fallback to pipeline-attached news when external fetches return empty.
    if not dedup:
        data = load_latest_output() or _mock_data_payload()
        for event in data.get("events", []):
            for ns in (event.get("news_sources") or []):
                url = (ns.get("url") or "").strip()
                title = (ns.get("title") or "").strip()
                if not url or not title or url in dedup:
                    continue
                dedup[url] = {
                    "article_id": hashlib.md5(url.encode()).hexdigest()[:16],
                    "title": title,
                    "description": (ns.get("snippet") or "").strip(),
                    "link": url,
                    "image_url": None,
                    "source_name": (ns.get("source") or "Pipeline").strip(),
                    "pub_date": ns.get("published") or None,
                    "category": [],
                    "sentiment": None,
                }
                if len(dedup) >= payload.limit:
                    break
            if len(dedup) >= payload.limit:
                break

    articles = list(dedup.values())[: payload.limit]
    return {
        "location": {
            "city": city,
            "state": state,
            "country": country,
            "country_code": country_code,
        },
        "articles": articles,
        "total_count": len(articles),
        "search_priority": "location-first",
    }


@router.post("/headline-analysis")
async def headline_analysis_workflow(
    payload: HeadlineAnalysisRequest,
    refresh_cache: bool = Query(False, description="Bypass the cache and force a new analysis"),
):
    """
    In-depth AI pipeline for a specific headline.
    Input can include pre-scraped articles from frontend and optionally triggers
    fresh scraping to enrich context before generating the intelligence report.
    """
    if not settings.GROQ_API_KEY:
        raise HTTPException(status_code=503, detail="GROQ_API_KEY not configured on server.")

    seed_records: list[dict] = [a.model_dump() for a in payload.scraped_articles]

    if payload.scrape_news:
        queries = [payload.headline]
        if payload.location:
            queries.append(f"{payload.location} {payload.headline}")

        scraped_records: list[dict] = []
        try:
            async with httpx.AsyncClient(
                timeout=18.0,
                follow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 (compatible; NarrativeSignal/1.0)"},
            ) as client:
                for q in list(dict.fromkeys(queries))[:2]:
                    tavily, newsapi, gnews, newsdata = await asyncio.gather(
                        _search_tavily(q, client),
                        _search_newsapi(q, client),
                        _search_gnews(q, client),
                        _search_newsdata(q, client),
                        return_exceptions=True,
                    )
                    for bucket in (tavily, newsapi, gnews, newsdata):
                        if isinstance(bucket, BaseException) or not isinstance(bucket, list):
                            continue
                        for row in (bucket or []):
                            scraped_records.append({
                                "title": row.get("title"),
                                "description": row.get("snippet"),
                                "link": row.get("url"),
                                "source_name": row.get("source"),
                                "pub_date": row.get("published_at") or row.get("published"),
                            })
        except Exception as e:
            logger.warning("headline-analysis scraping failed for '%s': %s", payload.headline[:120], e)

        seed_records.extend(scraped_records)

    articles = _dedup_news_records(seed_records, limit=payload.max_scraped_articles)

    cache_key = hashlib.md5(
        json.dumps(
            {
                "headline": payload.headline,
                "location": payload.location,
                "articles": [
                    {"title": a.get("title"), "link": a.get("link")} for a in articles
                ],
            },
            sort_keys=True,
            ensure_ascii=False,
        ).encode()
    ).hexdigest()

    cache = _load_analysis_cache()
    cached = cache.get(f"headline_analysis:{cache_key}")
    if not refresh_cache and cached:
        return {"cached": True, **cached}

    article_titles = [a.get("title") for a in articles[:12] if a.get("title")]
    article_lines = [
        {
            "title": a.get("title"),
            "source": a.get("source_name"),
            "summary": (a.get("description") or "")[:260],
            "published": a.get("pub_date"),
        }
        for a in articles[:12]
    ]

    prompt = f"""You are a senior geopolitical and crisis intelligence analyst.
Create a deep intelligence assessment from the headline and scraped news context, with explicit sentiment and narrative dynamics.

HEADLINE:
{payload.headline}

LOCATION CONTEXT:
{payload.location or 'Unknown / global'}

SCRAPED NEWS TITLES:
{json.dumps(article_titles, ensure_ascii=False)}

SCRAPED NEWS DETAILS:
{json.dumps(article_lines, ensure_ascii=False)}

Return plain text with these exact sections:

**Situation Snapshot**
**Evidence Base (Confirmed vs Unclear)**
**Actor Map and Motivations**
**Sentiment and Narrative Field**
**Timeline and Escalation Pathways**
**Information Integrity, Bias, and Gaps**
**Strategic Implications (24h / 72h / 1 week)**
**Indicators and Tripwires To Monitor Next**

Rules:
- Write in concise but substantive analytical prose (not generic commentary).
- In 'Sentiment and Narrative Field', assess sentiment by stakeholder audience (local public, state actors, international observers, media) and describe whether tone is escalating, stabilizing, or fragmenting.
- In 'Evidence Base (Confirmed vs Unclear)', separate verified claims from ambiguous claims and explain confidence level.
- In 'Indicators and Tripwires To Monitor Next', use bullet points and include concrete signals that would change the assessment.
- If evidence is thin, explicitly mark uncertainty instead of inventing details.
"""

    try:
        report = (
            await request_chat_completion(
                messages=[{"role": "user", "content": prompt}],
                model="llama-3.3-70b-versatile",
                max_tokens=1000,
                temperature=0.2,
            )
        ).strip()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI service unavailable: {e}")

    result = {
        "headline": payload.headline,
        "location": payload.location,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "articles_used": articles,
        "analysis_report": report,
    }

    cache[f"headline_analysis:{cache_key}"] = result
    _save_analysis_cache(cache)

    return {"cached": False, **result}


@router.post("/{event_id}/analyze")
async def event_analysis_workflow(
    event_id: str,
    max_reddit_posts: int = Query(50, ge=1, le=50),
    max_news_sources: int = Query(10, ge=1, le=10),
    refresh_cache: bool = Query(False, description="Bypass the cache and force a new analysis"),
):
    """
    On-demand multi-step analysis workflow.
    Reuses existing event lookup + news analysis pipeline and adds structured
    Reddit context extraction + aggregated AI report.
    """
    data = load_latest_output() or _mock_data_payload()
    event = next((e for e in data.get("events", []) if e.get("id") == event_id), None)
    if not event:
        raise HTTPException(404, f"Event '{event_id}' not found.")

    cache_key = f"event_analysis:{event_id}:{event.get('last_updated') or data.get('generated_at') or ''}"
    cache = _load_analysis_cache()
    if not refresh_cache and cache_key in cache:
        return {"cached": True, **cache[cache_key]}

    reddit_ctx = _fetch_reddit_context_from_db(event, max_posts=max_reddit_posts)

    news_payload = await event_news_analysis(event_id, refresh_cache=refresh_cache)
    articles = (news_payload.get("articles") or [])[:max_news_sources]

    aggregation = {
        "event": {
            "event_id": event_id,
            "title": event.get("title", "Unknown event"),
            "location": (event.get("locations") or [{}])[0].get("name", "Unknown"),
            "timestamp": event.get("timestamp") or event.get("last_updated") or data.get("generated_at"),
            "risk_level": event.get("risk_level", "Unknown"),
            "impact_score": event.get("impact_score", 0.0),
            "sentiment": event.get("sentiment", "neutral"),
            "subreddit": event.get("subreddit") or (reddit_ctx.get("related_subreddits") or [""])[0],
            "reddit_post_ids": reddit_ctx.get("reddit_post_ids") or [],
        },
        "reddit": reddit_ctx,
        "news": {
            "topic_sentences": news_payload.get("topic_sentences") or [],
            "articles": articles,
        },
        "timeline": sorted(
            [p.get("timestamp") for p in reddit_ctx.get("top_posts", []) if p.get("timestamp")]
            + [a.get("published") for a in articles if a.get("published")]
        ),
    }

    if not settings.GROQ_API_KEY:
        raise HTTPException(503, "GROQ_API_KEY not configured on server.")

    prompt = f"""You are a senior event intelligence analyst.
Produce a deep intelligence report for this event using Reddit + news context, with explicit sentiment decomposition.

Event:
{aggregation['event']['title']}

Reddit posts:
{json.dumps([p.get('title') for p in aggregation['reddit']['top_posts'][:12]], ensure_ascii=False)}

News articles:
{json.dumps([a.get('title') for a in aggregation['news']['articles'][:10]], ensure_ascii=False)}

Timeline:
{json.dumps(aggregation['timeline'][:20], ensure_ascii=False)}

Return plain text with these exact sections:

**Event Summary**
**Key Developments**
**Timeline of the Event**
**Sentiment Decomposition (Reddit vs News vs Official Narratives)**
**Source Reliability and Confidence**
**Information Spread Pattern and Amplification Risks**
**Scenario Outlook and Potential Implications**

Rules:
- Use bullet points under Key Developments and Scenario Outlook and Potential Implications.
- In Sentiment Decomposition, compare tone, intensity, and direction (escalatory/de-escalatory) across Reddit and news.
- Explicitly flag where sentiment appears organic vs coordinated or agenda-driven.
- State confidence for major conclusions when evidence is mixed."""

    try:
        report = (
            await request_chat_completion(
                messages=[{"role": "user", "content": prompt}],
                model="llama-3.3-70b-versatile",
                max_tokens=900,
                temperature=0.2,
            )
        ).strip()
    except Exception as e:
        raise HTTPException(502, f"AI service unavailable: {e}")

    payload = {
        "event_id": event_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "limits": {"max_reddit_posts": max_reddit_posts, "max_news_sources": max_news_sources},
        "reddit_context": reddit_ctx,
        "news_context": {"topic_sentences": news_payload.get("topic_sentences") or [], "articles": articles},
        "aggregated_context": aggregation,
        "analysis_report": report,
    }
    cache[cache_key] = payload
    _save_analysis_cache(cache)
    return {"cached": False, **payload}


@router.get("/{event_id}")
async def get_event_detail(event_id: str):
    """Full detail for a single event cluster."""
    data = load_latest_output() or _mock_data_payload()
    for event in data.get("events", []):
        if event.get("id") == event_id:
            return event

    raise HTTPException(status_code=404, detail=f"Event '{event_id}' not found.")


# ── AI-powered analysis endpoints ─────────────────────────────────────────────

@router.post("/ai-analysis")
async def global_ai_analysis():
    """
    Comprehensive Groq-powered intelligence report across all current events.
    Synthesises Reddit signal, news sources, risk levels and impact scores.
    """
    data   = load_latest_output() or _mock_data_payload()
    events = data.get("events", [])

    if not settings.GROQ_API_KEY:
        raise HTTPException(503, "GROQ_API_KEY not configured on server.")

    # Build compact event digest
    digest = []
    for e in events:
        digest.append(
            f"- {e.get('title','?')} | Risk: {e.get('risk_level')} "
            f"| Impact: {e.get('impact_score',0):.2f} | Sentiment: {e.get('sentiment')} "
            f"| Reddit posts: {e.get('reddit_metrics',{}).get('post_count',0)} "
            f"| {(e.get('summary') or '')[:200]}"
        )

    news_lines = []
    for e in events:
        for ns in (e.get("news_sources") or [])[:2]:
            news_lines.append(f"  [{ns.get('source','?')}] {ns.get('title','')[:120]}")

    prompt = f"""You are a senior geopolitical intelligence analyst.
Analyse the following globally-tracked events and produce a structured intelligence report with deeper sentiment assessment.

=== CURRENT EVENTS ({len(events)} tracked) ===
{chr(10).join(digest)}

=== CORROBORATING NEWS HEADLINES ===
{chr(10).join(news_lines) if news_lines else '(No news sources available)'}

=== REPORT FORMAT ===
Write in intelligence-briefing style with these exact sections:

**EXECUTIVE SUMMARY**
(3-4 sentences: the single most important global trend right now)

**HIGH-RISK HOTSPOTS**
(Bullet list with - : 2-3 active high-risk locations with one-line assessment each)

**DOMINANT THEMES**
(Bullet list with - : 3-4 cross-cutting geopolitical themes across all events)

**INFORMATION ENVIRONMENT AND SENTIMENT LANDSCAPE**
(3-4 sentences: how Reddit and news media are covering this — tone, volume, polarity, bias signals, and divergence between platforms)

**STRATEGIC WATCH**
(2-3 sentences: what to monitor in the next 24-72 hours)

**SENTIMENT-DRIVEN ESCALATION RISKS**
(Bullet list with - : 2-3 sentiment shifts or narrative triggers most likely to accelerate instability)

Use plain text. Bold headers with **. Bullet points with -."""

    try:
        raw = (
            await request_chat_completion(
                messages=[{"role": "user", "content": prompt}],
                model="llama-3.3-70b-versatile",
                max_tokens=900,
                temperature=0.25,
            )
        ).strip()
    except Exception as e:
        raise HTTPException(502, f"AI service unavailable: {e}")

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "event_count":  len(events),
        "report":       raw,
    }


@router.post("/{event_id}/news-analysis")
async def event_news_analysis(
    event_id: str,
    refresh_cache: bool = Query(False, description="Bypass the cache and force a new analysis")
):
    """
    For a single event:
    1. Groq generates 4 full topic sentences from Reddit discussion context.
    2. All news scrapers run in parallel:
       - Tavily (AI search) → NewsAPI → GNews → NewsData.io  (API scrapers)
       - Google News RSS  (fallback / supplemental)
    3. Results merged, deduplicated, trusted-source flagged.
    Returns: topic_sentences + articles (with source, trusted flag, snippet).
    """
    data  = load_latest_output() or _mock_data_payload()
    event = next((e for e in data.get("events", []) if e.get("id") == event_id), None)
    if not event:
        raise HTTPException(404, f"Event '{event_id}' not found.")

    title        = event.get("title", "Unknown event")
    subreddits   = event.get("reddit_metrics", {}).get("subreddits", [])
    summary      = event.get("summary", "") or ""
    implications = event.get("strategic_implications", []) or []
    location     = (event.get("locations") or [{}])[0].get("name", "the region")
    # Include any news already attached to the event from the pipeline run
    pipeline_news = event.get("news_sources") or []

    groq_available = bool(settings.GROQ_API_KEY)
    topic_sentences: list = []
    search_queries:  list = []

    if groq_available:
        prompt = f"""You are a news intelligence analyst.
Based on this global event being discussed on Reddit, generate exactly 4 distinct topic sentences.

EVENT: {title}
LOCATION: {location}
REDDIT COMMUNITIES: {', '.join(subreddits) if subreddits else 'worldnews'}
SUMMARY: {summary[:300] or 'N/A'}
KEY ASPECTS: {'; '.join(implications[:3]) if implications else 'geopolitical tensions'}

Rules for the 4 sentences:
- Each must be a COMPLETE sentence, NOT a keyword or phrase
- Use journalistic language (active voice, specific actors/places)
- Each describes a DISTINCT angle of the event
- Each reads like a proper news headline sentence

Return ONLY the 4 sentences, one per line, no numbering, no bullets, no extra text."""
        try:
            raw = (
                await request_chat_completion(
                    messages=[{"role": "user", "content": prompt}],
                    model="llama-3.3-70b-versatile",
                    max_tokens=260,
                    temperature=0.3,
                )
            ).strip()
            topic_sentences = [
                ln.strip().lstrip("0123456789.-) ").strip()
                for ln in raw.splitlines() if ln.strip()
            ][:4]
            # Use title + first topic sentence as search queries
            search_queries = list(dict.fromkeys([title] + topic_sentences[:2]))
        except Exception as e:
            logger.warning("Groq topic generation failed: %s", e)

    if not topic_sentences:
        topic_sentences = [
            f"Escalating tensions in {location} have drawn international attention amid ongoing conflict.",
            f"Reddit communities are amplifying coverage of the {title} situation across multiple forums.",
            f"Geopolitical analysts assess the strategic implications of developments in {location}.",
            f"Diplomatic and humanitarian responses are being coordinated following the crisis in {location}.",
        ]
        search_queries = [title]

    # ── Run all scrapers in parallel ────────────────────────────────────────
    raw_articles: list = []

    async def _google_rss(query: str, client: httpx.AsyncClient) -> list:
        """Google News RSS scrape for a single query."""
        results = []
        try:
            url = f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=en-US&gl=US&ceid=US:en"
            r   = await client.get(url)
            if r.status_code == 200:
                root = ET.fromstring(r.content)
                for item in root.findall(".//item")[:6]:
                    t   = item.find("title")
                    lk  = item.find("link")
                    pub = item.find("pubDate")
                    src = item.find("source")
                    link_url = (lk.text or "").strip() if lk is not None else ""
                    if not link_url:
                        guid = item.find("guid")
                        link_url = (guid.text or "").strip() if guid is not None else ""
                    if not link_url:
                        continue
                    title_text = (t.text or "Untitled").strip() if t is not None else "Untitled"
                    results.append({
                        "title":     title_text,
                        "url":       link_url,
                        "source":    (src.text or "Google News").strip() if src is not None else "Google News",
                        "published": pub.text if pub is not None else None,
                        "snippet":   "",
                        "trusted":   _is_trusted(link_url),
                        "via":       "rss",
                    })
        except Exception as e:
            logger.warning("Google RSS failed for '%s': %s", query[:60], e)
        return results

    async with httpx.AsyncClient(
        timeout=15.0,
        follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 (compatible; NarrativeSignal/1.0)"},
    ) as client:
        tasks = []
        # API scrapers — try all in parallel for each query
        for q in search_queries[:2]:
            tasks.append(_search_tavily(q, client))
            tasks.append(_search_newsapi(q, client))
            tasks.append(_search_gnews(q, client))
            tasks.append(_search_newsdata(q, client))
            tasks.append(_google_rss(q, client))

        results = await asyncio.gather(*tasks, return_exceptions=True)

    for bucket in results:
        if isinstance(bucket, BaseException) or not isinstance(bucket, list):
            continue
        for a in (bucket or []):
            url    = a.get("url") or ""
            if not url:
                continue
            raw_articles.append({
                "title":     (a.get("title") or "Untitled").strip(),
                "url":       url,
                "source":    (a.get("source") or "Unknown").strip(),
                "published": a.get("published_at") or a.get("published") or None,
                "snippet":   (a.get("snippet") or "")[:220],
                "trusted":   a.get("trusted") if "trusted" in a else _is_trusted(url),
                "via":       a.get("via", "api"),
            })

    # Add articles already stored from the pipeline run (with snippet/trusted info)
    for ns in pipeline_news:
        ns_url = ns.get("url") or ""
        if not ns_url:
            continue
        raw_articles.append({
            "title":     (ns.get("title") or "Untitled").strip(),
            "url":       ns_url,
            "source":    (ns.get("source") or "Unknown").strip(),
            "published": ns.get("published_at") or None,
            "snippet":   (ns.get("snippet") or "")[:220],
            "trusted":   ns.get("trusted") or ns.get("is_trusted") or _is_trusted(ns_url),
            "via":       "pipeline",
        })

    # Deduplicate by URL, trusted sources first
    seen: set = set()
    unique: list = []
    for a in sorted(raw_articles, key=lambda x: (0 if x["trusted"] else 1)):
        if a["url"] not in seen:
            seen.add(a["url"])
            unique.append(a)

    return {
        "event_id":        event_id,
        "topic_sentences": topic_sentences,
        "sources_used":    ["tavily", "newsapi", "gnews", "newsdata", "google_rss", "pipeline"],
        "articles":        unique[:12],
    }


@router.post("/{event_id}/ai-analysis")
async def event_ai_analysis(event_id: str):
    """
    Groq-powered focused intelligence brief for a single event.
    Uses all available event context: location, risk, sentiment, Reddit metrics,
    news sources, summary and strategic implications.
    """
    data  = load_latest_output() or _mock_data_payload()
    event = next((e for e in data.get("events", []) if e.get("id") == event_id), None)
    if not event:
        raise HTTPException(status_code=404, detail=f"Event '{event_id}' not found.")

    title        = event.get("title", "Unknown")
    location     = (event.get("locations") or [{}])[0].get("name", "Unknown")
    risk         = event.get("risk_level", "Unknown")
    impact       = event.get("impact_score") or 0.0
    sentiment    = event.get("sentiment", "neutral")
    summary_text = (event.get("summary") or "")[:400]
    implications = event.get("strategic_implications") or []
    reddit       = event.get("reddit_metrics") or {}
    news_titles  = [ns.get("title", "") for ns in (event.get("news_sources") or [])[:4]]

    if not settings.GROQ_API_KEY:
        raise HTTPException(status_code=503, detail="GROQ_API_KEY not configured on server.")

    prompt = f"""You are a senior geopolitical intelligence analyst.
Write a focused but deep intelligence assessment for this single event, with explicit sentiment dynamics.

EVENT: {title}
LOCATION: {location}
RISK LEVEL: {risk} | IMPACT SCORE: {impact:.2f} | SENTIMENT: {sentiment}
SUMMARY: {summary_text or 'N/A'}
STRATEGIC IMPLICATIONS: {'; '.join(implications[:4]) or 'N/A'}
REDDIT SIGNAL: {reddit.get('post_count', 0)} posts, cumulative score {reddit.get('total_score', 0):,}, communities: {', '.join(reddit.get('subreddits', [])[:5])}
NEWS HEADLINES: {'; '.join(news_titles) if news_titles else 'N/A'}

Write an intelligence brief with these exact sections:

**SITUATION ASSESSMENT**
(2-3 sentences on the current state and near-term trajectory)

**KEY DRIVERS**
(Bullet list with - : 3 root causes or accelerants driving this event)

**SENTIMENT DYNAMICS**
(2-3 sentences separating emotional tone and narrative momentum across Reddit communities, mainstream media, and official actors)

**INFORMATION ENVIRONMENT**
(2-3 sentences on volume, framing, bias signals, and confidence in available reporting)

**WATCH ITEMS AND TRIPWIRES**
(Bullet list with - : 3-4 specific indicators in the next 24-72 hours that would materially shift risk)

Bold section headers using **. Bullet points with -. Plain text only. No numbering.
If evidence is weak or conflicting, explicitly note uncertainty and confidence level."""

    try:
        report = (
            await request_chat_completion(
                messages=[{"role": "user", "content": prompt}],
                model="llama-3.3-70b-versatile",
                max_tokens=520,
                temperature=0.2,
            )
        ).strip()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI service unavailable: {e}")

    return {
        "event_id":     event_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "report":       report,
    }
