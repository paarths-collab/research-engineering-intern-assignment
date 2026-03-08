from __future__ import annotations
import logging
from fastapi import APIRouter, HTTPException
from litellm import acompletion
from streamgraph2.logic import media_ecosystem as me
from streamgraph2.data.config import GROQ_API_KEY, LLM_MODEL
from streamgraph2.models.schemas import MediaBriefRequest

router = APIRouter(tags=["Media Ecosystem"])

@router.get("/subreddits")
async def list_subreddits():
    """All subreddits in the media ecosystem dataset."""
    return {"subreddits": await me.get_all_subreddits()}

@router.get("/echo-scores")
async def echo_scores():
    """
    Panel 1 — Isolation lift scores per subreddit.
    Sorted descending. High score = concentrated media diet, not extremism.
    """
    return {"scores": await me.get_echo_scores()}

@router.get("/similarity")
async def similarity_matrix():
    """
    Panel 2 — Pairwise cosine similarity on domain link vectors.
    Returns { subreddits: [...], matrix: [[...]] }
    """
    return await me.get_similarity_matrix()

@router.get("/category-breakdown/{subreddit}")
async def category_breakdown(subreddit: str):
    """Panel 3 — Source type composition for one subreddit."""
    breakdown = await me.get_category_breakdown(subreddit)
    if not breakdown:
        raise HTTPException(404, f"No domain data for r/{subreddit}")
    return {"subreddit": subreddit, "breakdown": breakdown}

@router.get("/top-domains/{subreddit}")
async def top_domains(subreddit: str, n: int = 5):
    """Top n distinctive domains by lift."""
    domains = await me.get_top_domains(subreddit, n)
    if not domains:
        raise HTTPException(404, f"No data for r/{subreddit}")
    return {"subreddit": subreddit, "domains": domains}

@router.post("/media-brief")
async def media_brief(req: MediaBriefRequest):
    """
    Panel 4 — LLM intelligence brief for a subreddit's media ecosystem.
    Sends structured metrics only. LLM interprets domain identity from training knowledge.
    """
    payload = await me.build_llm_payload(req.subreddit)
    if not payload["top_domains"]:
        raise HTTPException(404, f"No domain data for r/{req.subreddit}")

    brief = await _call_media_llm(payload)
    return {"subreddit": req.subreddit, "brief": brief, "payload": payload}

async def _call_media_llm(payload: dict) -> str:
    sub     = payload["subreddit"]
    score   = payload["echo_score"]
    domains = payload["top_domains"]
    cats    = payload["category_breakdown"]
    similar = payload["similar_subreddits"]

    domain_lines = "\n".join(
        f"  - {d['domain']}  (lift {d['lift']}×, type: {d['category']})"
        for d in domains
    )
    cat_lines = "\n".join(f"  - {c['cat']}: {c['pct']}%" for c in cats)
    sim_lines = (
        "\n".join(f"  - r/{s['subreddit']} ({int(s['similarity']*100)}% overlap)" for s in similar)
        if similar else "  - No close neighbors (structurally isolated)"
    )

    prompt = f"""You are writing an intelligence brief for a media ecosystem analysis dashboard.
Interpret structural metrics — derive orientation from domain names, not subreddit name.

SUBREDDIT: r/{sub}
ECHO SCORE: {score}× (avg lift of top domains vs global baseline)

TOP DISTINCTIVE DOMAINS:
{domain_lines}

SOURCE TYPE BREAKDOWN:
{cat_lines}

SIMILAR SUBREDDITS (cosine similarity on domain link vectors):
{sim_lines}

Write 4–5 sentences covering:
1. What the top domains represent (organization types, publication character)
2. What the concentration score means in practical terms
3. Source type mix — journalism vs advocacy vs institutional
4. Ecosystem overlap or isolation
5. What this suggests about the community's information environment

Tone: analytical, neutral, intelligence-briefing style. No bullet points. No hedging.
Do not repeat raw numbers — translate them into meaning."""
    msg = await acompletion(
        model=LLM_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        api_key=GROQ_API_KEY
    )
    return msg.choices[0].message.content.strip()
