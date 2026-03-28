"""
Layer 5 — News Correlation
Grounds Reddit claims in real journalism.
Primary: Tavily (AI-optimised search)
Fallbacks: NewsAPI → GNews → NewsData.io
Deduplicates by URL, filters to last 48h.
"""
import hashlib
import asyncio
from datetime import datetime, timedelta, timezone
from typing import List, Optional
import httpx

from app.config import get_settings
from app.database.models import StructuredEvent, NewsArticle, NewsBundle
from app.database.connection import get_connection
from app.utils.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()

TRUSTED_DOMAINS = {
    "reuters.com", "apnews.com", "bbc.com", "bbc.co.uk", "aljazeera.com",
    "theguardian.com", "nytimes.com", "washingtonpost.com", "ft.com",
    "bloomberg.com", "economist.com", "foreignpolicy.com", "cfr.org",
    "politico.com", "axios.com", "npr.org", "dw.com", "france24.com",
    "rfi.fr", "abc.net.au", "cbc.ca", "theatlantic.com",
}


def _is_trusted(url: str) -> bool:
    return any(domain in url for domain in TRUSTED_DOMAINS)


def _article_id(url: str, event_id: str) -> str:
    return hashlib.md5(f"{event_id}:{url}".encode()).hexdigest()[:16]


def _cutoff_iso() -> str:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=settings.NEWS_TIME_WINDOW_HOURS)
    return cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")


# ── Tavily ───────────────────────────────────────────────────
async def _search_tavily(query: str, client: httpx.AsyncClient) -> List[dict]:
    if not settings.TAVILY_API_KEY:
        return []
    try:
        resp = await client.post(
            "https://api.tavily.com/search",
            json={
                "api_key": settings.TAVILY_API_KEY,
                "query": query,
                "search_depth": "basic",
                "max_results": 5,
                "include_answer": False,
            },
            timeout=15,
        )
        data = resp.json()
        return [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "snippet": r.get("content", "")[:300],
                "source": r.get("url", "").split("/")[2] if "/" in r.get("url","") else "",
                "published_at": r.get("published_date", ""),
            }
            for r in data.get("results", [])
        ]
    except Exception as e:
        logger.debug(f"Tavily error: {e}")
        return []


# ── NewsAPI ──────────────────────────────────────────────────
async def _search_newsapi(query: str, client: httpx.AsyncClient) -> List[dict]:
    if not settings.NEWSAPI_KEY:
        return []
    try:
        resp = await client.get(
            "https://newsapi.org/v2/everything",
            params={
                "q": query,
                "from": _cutoff_iso(),
                "sortBy": "publishedAt",
                "pageSize": 7,
                "apiKey": settings.NEWSAPI_KEY,
            },
            timeout=15,
        )
        data = resp.json()
        return [
            {
                "title": a.get("title", ""),
                "url": a.get("url", ""),
                "snippet": a.get("description", "")[:300],
                "source": a.get("source", {}).get("name", ""),
                "published_at": a.get("publishedAt", ""),
            }
            for a in data.get("articles", [])
            if a.get("url") and a.get("title")
        ]
    except Exception as e:
        logger.debug(f"NewsAPI error: {e}")
        return []


# ── GNews ────────────────────────────────────────────────────
async def _search_gnews(query: str, client: httpx.AsyncClient) -> List[dict]:
    if not settings.GNEWS_KEY:
        return []
    try:
        resp = await client.get(
            "https://gnews.io/api/v4/search",
            params={
                "q": query,
                "lang": "en",
                "max": 5,
                "apikey": settings.GNEWS_KEY,
            },
            timeout=15,
        )
        data = resp.json()
        return [
            {
                "title": a.get("title", ""),
                "url": a.get("url", ""),
                "snippet": a.get("description", "")[:300],
                "source": a.get("source", {}).get("name", ""),
                "published_at": a.get("publishedAt", ""),
            }
            for a in data.get("articles", [])
        ]
    except Exception as e:
        logger.debug(f"GNews error: {e}")
        return []


# ── NewsData.io ──────────────────────────────────────────────
async def _search_newsdata(query: str, client: httpx.AsyncClient) -> List[dict]:
    if not settings.NEWSDATA_KEY:
        return []
    try:
        resp = await client.get(
            "https://newsdata.io/api/1/news",
            params={
                "q": query,
                "language": "en",
                "apikey": settings.NEWSDATA_KEY,
            },
            timeout=15,
        )
        data = resp.json()
        return [
            {
                "title": a.get("title", ""),
                "url": a.get("link", ""),
                "snippet": (a.get("description") or "")[:300],
                "source": a.get("source_id", ""),
                "published_at": a.get("pubDate", ""),
            }
            for a in data.get("results", [])
            if a.get("link")
        ]
    except Exception as e:
        logger.debug(f"NewsData error: {e}")
        return []


# ── Main correlator ──────────────────────────────────────────
async def correlate_news_for_event(
    event: StructuredEvent,
    client: httpx.AsyncClient,
) -> NewsBundle:
    """Run all search queries, aggregate + deduplicate articles."""
    seen_urls: set = set()
    all_articles: List[NewsArticle] = []

    for query in event.search_queries:
        # Try sources in priority order
        raw_articles = await _search_tavily(query, client)
        if not raw_articles:
            raw_articles = await _search_newsapi(query, client)
        if not raw_articles:
            raw_articles = await _search_gnews(query, client)
        if not raw_articles:
            raw_articles = await _search_newsdata(query, client)

        for a in raw_articles:
            url = a.get("url", "")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)

            article = NewsArticle(
                id=_article_id(url, event.id),
                event_id=event.id,
                title=a.get("title", ""),
                snippet=a.get("snippet", ""),
                url=url,
                source=a.get("source", ""),
                published_at=a.get("published_at", ""),
                is_trusted=_is_trusted(url),
            )
            all_articles.append(article)

            if len(all_articles) >= settings.NEWS_ARTICLE_LIMIT:
                break

        if len(all_articles) >= settings.NEWS_ARTICLE_LIMIT:
            break

    bundle = NewsBundle(
        event_id=event.id,
        articles=all_articles,
        news_count=len(all_articles),
        trusted_source_count=sum(1 for a in all_articles if a.is_trusted),
    )

    logger.debug(
        f"NEWS [{event.primary_location}]: {bundle.news_count} articles "
        f"({bundle.trusted_source_count} trusted)"
    )
    return bundle


async def correlate_all_events(events: List[StructuredEvent]) -> List[NewsBundle]:
    async with httpx.AsyncClient() as client:
        semaphore = asyncio.Semaphore(3)

        async def _bounded(e: StructuredEvent):
            async with semaphore:
                return await correlate_news_for_event(e, client)

        tasks = [_bounded(e) for e in events]
        bundles = await asyncio.gather(*tasks, return_exceptions=True)

    results = []
    for b in bundles:
        if isinstance(b, Exception):
            logger.warning(f"News correlation task failed: {b}")
            continue
        results.append(b)

    _persist_articles(results)
    logger.info(f"News correlation complete — {len(results)} bundles")
    return results


def _persist_articles(bundles: List[NewsBundle]) -> None:
    conn = get_connection()
    for bundle in bundles:
        for a in bundle.articles:
            conn.execute("""
                INSERT OR REPLACE INTO news_articles
                (id, event_id, title, snippet, url, source, published_at, is_trusted)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, [a.id, a.event_id, a.title, a.snippet,
                  a.url, a.source, a.published_at, a.is_trusted])
