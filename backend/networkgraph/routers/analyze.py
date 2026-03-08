"""
routers/analyze.py — Layer 5: AI Narrative Analysis

Endpoint:
  POST /analyze   → scrape article + gather all metrics + call Groq LLM

Pipeline:
  1. Validate narrative_id exists
  2. Pull metadata from 5 data sources
  3. Scrape article (3-tier pipeline, async via threadpool)
  4. Assemble structured prompt
  5. Call Groq (llama-3.3-70b-versatile)
  6. Return structured analysis
"""
from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException

from networkgraph.data.loader import get_store, DataStore
from llm.groq_client import build_prompt, call_groq
from networkgraph.models.schemas import AnalyzeRequest, AnalyzeResponse, ArticleScrapeInfo, NarrativeAnalysis
from networkgraph.scraper.pipeline import scrape

router = APIRouter(prefix="/analyze", tags=["analyze"])
log = logging.getLogger("sntis.analyze")

# Thread pool for running the sync scraper without blocking the event loop
_SCRAPER_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="scraper")


def _safe(val, cast=None):
    if pd.isna(val):
        return None
    try:
        return cast(val) if cast else val
    except Exception:
        return None


async def _async_scrape(url: str):
    """Run the synchronous scraper in a thread so we don't block FastAPI's event loop."""
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(_SCRAPER_POOL, scrape, url)
    return result


def _collect_metadata(narrative_id: str, url: str, store: DataStore) -> dict:
    """
    Gather all structured data for a narrative from all relevant datasets.
    Returns a single dict for prompt assembly.
    """
    # ── narrative_intelligence_summary ──────────────────────────────────────
    narr = store.narrative_map.get(narrative_id, {})
    topic_info = store.topic_map.get(narrative_id, {})

    # ── graph_edge_intelligence_table ───────────────────────────────────────
    edge_df = store.edges_df[
        store.edges_df["narrative_id"].astype(str) == narrative_id
    ]

    # Find the specific post matching the URL (or fall back to origin post)
    matching = edge_df[edge_df["url"].astype(str) == url] if not edge_df.empty else edge_df
    if matching.empty and not edge_df.empty:
        origin_rows = edge_df[edge_df.get("hours_from_origin", pd.Series()).fillna(1) == 0]
        ref_row = origin_rows.iloc[0].to_dict() if not origin_rows.empty else edge_df.iloc[0].to_dict()
    elif not matching.empty:
        ref_row = matching.iloc[0].to_dict()
    else:
        ref_row = {}

    # ── narrative_spread_chain_table ────────────────────────────────────────
    chain_df = store.chains_df[
        store.chains_df["narrative_id"].astype(str) == narrative_id
    ]
    if "step_number" in chain_df.columns:
        chain_df = chain_df.sort_values("step_number", ascending=True)
    chain_steps = chain_df.where(pd.notna(chain_df), None).to_dict(orient="records")

    # ── user_intelligence_summary ───────────────────────────────────────────
    author = str(ref_row.get("author", ""))
    user_row = store.user_map.get(author, {})

    # ── author_amplification_summary ────────────────────────────────────────
    amp_row = store.amplification_map.get(author, {})

    # ── Datetime formatting ─────────────────────────────────────────────────
    dt = ref_row.get("created_datetime")
    if hasattr(dt, "isoformat"):
        dt_str = dt.isoformat()
    else:
        dt_str = str(dt) if dt else "unknown"

    return {
        # Article metadata
        "title": _safe(ref_row.get("title")) or "Unknown",
        "domain": _safe(ref_row.get("domain")) or "Unknown",
        "url": url,
        "created_datetime": dt_str,
        "origin_subreddit": _safe(ref_row.get("origin_subreddit")) or "Unknown",
        "hours_from_origin": _safe(ref_row.get("hours_from_origin"), float),
        # Narrative metrics
        "total_posts": _safe(narr.get("total_posts"), int),
        "unique_subreddits": _safe(narr.get("unique_subreddits"), int),
        "unique_authors": _safe(narr.get("unique_authors"), int),
        "spread_strength": _safe(narr.get("spread_strength"), float),
        "topic_label": topic_info.get("topic_label") or _safe(narr.get("topic_label")),
        "topic_cluster": topic_info.get("topic_cluster") or _safe(narr.get("topic_cluster")),
        # Chain
        "chain_steps": chain_steps,
        # User
        "communities_active_in": _safe(user_row.get("communities_active_in"), int),
        "unique_narratives_by_user": _safe(user_row.get("unique_narratives"), int),
        # Amplification
        "amplification_events": _safe(amp_row.get("amplification_events"), int),
        "total_relative_amplification": _safe(amp_row.get("total_relative_amplification"), float),
    }


@router.post(
    "",
    response_model=AnalyzeResponse,
    summary="AI narrative analysis: scrape + metrics + LLM",
)
async def analyze_narrative(
    request: AnalyzeRequest,
    store: DataStore = Depends(get_store),
):
    """
    Layer 5 full pipeline:
      1. Validate narrative exists
      2. Collect metadata from all 5 data sources
      3. Scrape article with 3-tier pipeline
      4. Build structured prompt
      5. Call Groq llama-3.3-70b-versatile
      6. Return structured analysis

    All data-driven. No autonomous agents. Single inference call.
    """
    narrative_id = request.narrative_id
    url = request.url

    # ── 1. Validate narrative exists ────────────────────────────────────────
    if narrative_id not in store.narrative_map:
        raise HTTPException(
            status_code=404,
            detail=f"narrative_id '{narrative_id}' not found."
        )

    # ── 2. Collect all structured metadata ──────────────────────────────────
    log.info("Collecting metadata for narrative_id=%s", narrative_id)
    metadata = _collect_metadata(narrative_id, url, store)

    # ── 3. Scrape article (async, non-blocking) ──────────────────────────────
    log.info("Scraping URL: %s", url)
    scrape_result = await _async_scrape(url)

    scrape_info = ArticleScrapeInfo(
        success=scrape_result.success,
        tier_used=scrape_result.tier_used,
        title=scrape_result.title,
        text_preview=scrape_result.text[:1000] if scrape_result.text else None,
        word_count=scrape_result.word_count,
        error=scrape_result.error,
    )

    article_text = scrape_result.text

    # ── 4. Build prompt ──────────────────────────────────────────────────────
    log.info("Building LLM prompt.")
    prompt = build_prompt(
        title=metadata["title"],
        domain=metadata["domain"],
        url=url,
        created_datetime=metadata["created_datetime"],
        origin_subreddit=metadata["origin_subreddit"],
        hours_from_origin=metadata["hours_from_origin"],
        total_posts=metadata["total_posts"],
        unique_subreddits=metadata["unique_subreddits"],
        unique_authors=metadata["unique_authors"],
        spread_strength=metadata["spread_strength"],
        topic_label=metadata["topic_label"],
        topic_cluster=metadata["topic_cluster"],
        chain_steps=metadata["chain_steps"],
        communities_active_in=metadata["communities_active_in"],
        unique_narratives_by_user=metadata["unique_narratives_by_user"],
        amplification_events=metadata["amplification_events"],
        total_relative_amplification=metadata["total_relative_amplification"],
        article_text=article_text,
    )

    # ── 5. Call Groq ─────────────────────────────────────────────────────────
    log.info("Calling Groq API (model=%s)", "llama-3.3-70b-versatile")
    analysis, raw_response, llm_error = await call_groq(prompt)

    # ── 6. Return ─────────────────────────────────────────────────────────────
    return AnalyzeResponse(
        narrative_id=narrative_id,
        url=url,
        scrape_info=scrape_info,
        analysis=analysis,
        raw_llm_response=raw_response,
        error=llm_error,
    )
