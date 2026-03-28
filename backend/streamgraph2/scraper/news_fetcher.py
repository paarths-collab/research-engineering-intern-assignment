"""
news_fetcher.py — Fetch, deduplicate, embed, and store news headlines.

Sources (all run concurrently):
  1. NewsAPI       (newsapi.org)
  2. NewsData.io
  3. Currents API
  4. GNews         (gnews.io)
  5. ApiTube       (apitube.io)
  6. Tavily        (app.tavily.com)
  7. Wikipedia current events (no API key — always-on fallback)

Deduplication: lowercase headline set.
Embeddings stored in news_cache table (date-keyed).
"""

import asyncio
from datetime import date
from typing import List, Dict

import httpx

from streamgraph2.data import db
from streamgraph2.data.config import (
    NEWSAPI_KEY, NEWSDATA_KEY, CURRENTS_KEY,
    GNEWS_KEY, APITUBE_KEY, TAVILY_KEY,
    NEWS_FETCH_LIMIT,
)
from streamgraph2.models.embedder import embed


# ── Source fetchers ───────────────────────────────────────────

async def _fetch_newsapi(client: httpx.AsyncClient, target_date: date, query: str = None) -> List[Dict]:
    if not NEWSAPI_KEY:
        return []
    try:
        resp = await client.get(
            "https://newsapi.org/v2/everything",
            params={
                "apiKey":   NEWSAPI_KEY,
                "from":     str(target_date),
                "to":       str(target_date),
                "language": "en",
                "pageSize": 100,
                "sortBy":   "popularity",
                "q": query if query else "politics OR government OR election OR policy",
            },
            timeout=10,
        )
        articles = resp.json().get("articles", [])
        return [
            {
                "headline": a.get("title", ""),
                "source":   a.get("source", {}).get("name", "NewsAPI"),
                "url":      a.get("url", ""),
            }
            for a in articles if a.get("title")
        ]
    except Exception as e:
        print(f"  [News] NewsAPI error: {e}")
        return []


async def _fetch_newsdata(client: httpx.AsyncClient, target_date: date, query: str = None) -> List[Dict]:
    if not NEWSDATA_KEY:
        return []
    try:
        params_dict = {
            "apikey":    NEWSDATA_KEY,
            "language":  "en",
            "from_date": str(target_date),
            "to_date":   str(target_date),
            "category":  "politics,world",
        }
        if query:
            params_dict["q"] = query

        resp = await client.get(
            "https://newsdata.io/api/1/news",
            params=params_dict,
            timeout=10,
        )
        if resp.status_code != 200:
            print(f"  [News] NewsData returned {resp.status_code}: {resp.text}")
            return []
            
        data = resp.json()
        results = data.get("results", []) if isinstance(data, dict) else []
        return [
            {
                "headline": a.get("title", ""),
                "source":   a.get("source_id", "NewsData"),
                "url":      a.get("link", ""),
            }
            for a in results if a.get("title")
        ]
    except Exception as e:
        print(f"  [News] NewsData error: {e}")
        return []


async def _fetch_currents(client: httpx.AsyncClient, target_date: date, query: str = None) -> List[Dict]:
    if not CURRENTS_KEY:
        return []
    try:
        params_dict = {
            "apiKey":     CURRENTS_KEY,
            "language":   "en",
            "start_date": f"{target_date}T00:00:00+00:00",
            "end_date":   f"{target_date}T23:59:59+00:00",
        }
        if query:
            params_dict["keywords"] = query
            
        resp = await client.get(
            "https://api.currentsapi.services/v1/search",
            params=params_dict,
            timeout=10,
        )
        if resp.status_code != 200:
            print(f"  [News] Currents returned {resp.status_code}: {resp.text}")
            return []
            
        data = resp.json()
        news = data.get("news", []) if isinstance(data, dict) else []
        return [
            {
                "headline": a.get("title", ""),
                "source":   "Currents",
                "url":      a.get("url", ""),
            }
            for a in news if a.get("title")
        ]
    except Exception as e:
        print(f"  [News] Currents error: {e}")
        return []


async def _fetch_gnews(client: httpx.AsyncClient, target_date: date, query: str = None) -> List[Dict]:
    """GNews API — gnews.io — up to 10 free articles per call."""
    if not GNEWS_KEY:
        return []
    try:
        resp = await client.get(
            "https://gnews.io/api/v4/search",
            params={
                "token":   GNEWS_KEY,
                "q":       query if query else "politics government election",
                "lang":    "en",
                "from":    f"{target_date}T00:00:00Z",
                "to":      f"{target_date}T23:59:59Z",
                "max":     10,
                "sortby":  "publishedAt",
            },
            timeout=10,
        )
        articles = resp.json().get("articles", [])
        return [
            {
                "headline": a.get("title", ""),
                "source":   a.get("source", {}).get("name", "GNews"),
                "url":      a.get("url", ""),
            }
            for a in articles if a.get("title")
        ]
    except Exception as e:
        print(f"  [News] GNews error: {e}")
        return []


async def _fetch_apitube(client: httpx.AsyncClient, target_date: date, query: str = None) -> List[Dict]:
    """ApiTube — apitube.io — news aggregator."""
    if not APITUBE_KEY:
        return []
    try:
        params_dict = {
            "api_key":             APITUBE_KEY,
            "language":            "en",
            "published_at.start":  f"{target_date}T00:00:00Z",
            "published_at.end":    f"{target_date}T23:59:59Z",
            "per_page":            50,
        }
        if query:
            params_dict["q"] = query
            
        resp = await client.get(
            "https://api.apitube.io/v1/news/everything",
            params=params_dict,
            timeout=10,
        )
        results = resp.json().get("results", [])
        return [
            {
                "headline": a.get("title", ""),
                "source":   a.get("source", {}).get("name", "ApiTube"),
                "url":      a.get("url", ""),
            }
            for a in results if a.get("title")
        ]
    except Exception as e:
        print(f"  [News] ApiTube error: {e}")
        return []


async def _fetch_tavily(client: httpx.AsyncClient, target_date: date, query: str = None) -> List[Dict]:
    """Tavily search API — app.tavily.com — best for event-driven news retrieval."""
    if not TAVILY_KEY:
        return []
    try:
        resp = await client.post(
            "https://api.tavily.com/search",
            json={
                "api_key":        TAVILY_KEY,
                "query":          f"{query} news {target_date}" if query else f"major news events {target_date}",
                "search_depth":   "basic",
                "include_answer": False,
                "max_results":    20,
            },
            timeout=15,
        )
        results = resp.json().get("results", [])
        return [
            {
                "headline": a.get("title", ""),
                "source":   "Tavily",
                "url":      a.get("url", ""),
            }
            for a in results if a.get("title")
        ]
    except Exception as e:
        print(f"  [News] Tavily error: {e}")
        return []


async def _fetch_wikipedia(client: httpx.AsyncClient, target_date: date) -> List[Dict]:
    """Wikipedia current events portal — always-on, zero-key fallback."""
    year  = target_date.year
    month = target_date.strftime("%B")
    url   = f"https://en.wikipedia.org/wiki/Portal:Current_events/{year}_{month}_{target_date.day}"
    try:
        resp = await client.get(url, timeout=10, follow_redirects=True)
        if resp.status_code != 200:
            return []
        lines, results = resp.text.split("\n"), []
        for line in lines:
            line = line.strip()
            if len(line) > 40 and ("[[" in line or "]]" in line):
                clean = line.replace("[[", "").replace("]]", "").replace("*", "").strip()
                if len(clean) > 20:
                    results.append({"headline": clean[:200], "source": "Wikipedia", "url": url})
            if len(results) >= 30:
                break
        return results
    except Exception as e:
        print(f"  [News] Wikipedia error: {e}")
        return []


# ── Main fetcher ──────────────────────────────────────────────

async def fetch_and_store_news(target_date: date, query: str = None) -> List[Dict]:
    """
    Fetch from all 7 sources concurrently, deduplicate, embed, store in news_cache.
    Returns list of stored items (with embeddings).
    """
    # Check cache first — skip re-fetch if already loaded (unless query is provided)
    if not query:
        cached = await db.get_news_for_date(target_date)
        if len(cached) >= 5:
            print(f"  [News] Using {len(cached)} cached items for {target_date}")
            return cached

    print(f"  [News] Fetching from 7 sources for {target_date} | query='{query}'")
    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(
            _fetch_newsapi(client, target_date, query),    # [0]
            _fetch_newsdata(client, target_date, query),   # [1]
            _fetch_currents(client, target_date, query),   # [2]
            _fetch_gnews(client, target_date, query),      # [3]
            _fetch_apitube(client, target_date, query),    # [4]
            _fetch_tavily(client, target_date, query),     # [5]
            _fetch_wikipedia(client, target_date),         # [6]
        )

    # Flatten and deduplicate
    seen, unique = set(), []
    for item in (item for source in results for item in source):
        key = item["headline"].lower().strip()[:120]
        if key and key not in seen:
            seen.add(key)
            unique.append(item)
        if len(unique) >= NEWS_FETCH_LIMIT:
            break

    source_labels = ["NewsAPI", "NewsData", "Currents", "GNews", "ApiTube", "Tavily", "Wikipedia"]
    counts = " | ".join(f"{lbl}={len(r)}" for lbl, r in zip(source_labels, results))
    print(f"  [News] Source counts: {counts}")
    print(f"  [News] {len(unique)} unique headlines after dedup")

    if not unique:
        print(f"  [News] No headlines fetched for {target_date}")
        return []

    # Embed and store
    print(f"  [News] Embedding {len(unique)} headlines")
    embeddings = embed([item["headline"] for item in unique])

    stored = []
    for item, emb in zip(unique, embeddings):
        await db.save_news_item(
            date_val  = target_date,
            headline  = item["headline"],
            source    = item["source"],
            url       = item["url"],
            embedding = emb,
        )
        stored.append({**item, "embedding": emb})

    print(f"  [News] {len(stored)} items stored for {target_date}")
    return stored
