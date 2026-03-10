"""
ai_brief.py — Calls Groq via LiteLLM to generate an intelligence brief.

Takes a structured payload (from polarize_1.compute.get_subreddit_summary_payload)
and returns a clean, analytical paragraph. No raw data passed — only
structured metrics so the LLM interprets, not restates.
"""

import os
from litellm import acompletion

MODEL = os.getenv("HIGH_MODEL", "groq/llama-3.3-70b-versatile")
MAX_TOKENS = 500


def _build_prompt(payload: dict) -> str:
    sub = payload["subreddit"]
    score = payload["echo_score"]
    domains = payload["top_domains"]
    cats = payload["category_breakdown"]
    similar = payload["similar_subreddits"]

    domain_lines = "\n".join(
        f"  - {d['domain']}  (subreddit share: {round(d['p_sub']*100, 1)}%, global share: {round(d['p_global']*100, 2)}%, count: {d['count']}, type: {d['category']})"
        for d in domains
    )
    cat_lines = "\n".join(
        f"  - {c['cat']}: {c['pct']}%"
        for c in cats
    )
    sim_lines = (
        "\n".join(f"  - r/{s['subreddit']} ({s['overlap']} shared domains)" for s in similar)
        if similar else "  - No close neighbors (highly isolated)"
    )

    return f"""You are writing an intelligence brief for a media ecosystem analysis dashboard.
Your job is to explain what the top news sources this subreddit references reveal about how this community consumes information.
Focus on: what publications/outlets they trust, what narratives those sources promote, and what this says about the community's information diet.

─── STRUCTURED METRICS ───────────────────────────────────────────────────────

SUBREDDIT: r/{sub}

MEDIA DIVERSITY SCORE: {score}
  (Based on number of unique domains referenced. Higher = more diverse sourcing.)

TOP REFERENCED NEWS SOURCES (by share of links in this subreddit):
{domain_lines}

SOURCE TYPE BREAKDOWN:
{cat_lines}

MOST OVERLAPPING COMMUNITIES (shared news sources):
{sim_lines}

─── INSTRUCTIONS ─────────────────────────────────────────────────────────────

Write 4–5 sentences. Structure your brief as follows:
1. Name the top 2-3 news sources and describe what kind of publications they are (e.g. mainstream, partisan, investigative, institutional).
2. Explain what these sources collectively suggest about the community's preferred news framing or political orientation.
3. Comment on the source type mix — what percentage comes from traditional news vs advocacy vs research.
4. Note which other communities share overlapping media diets and what that means.
5. End with one sentence summarizing the overall information environment of this subreddit.

Tone: analytical, neutral, professional. No bullet points. No hedging phrases like "it appears" or
"it seems". State observations directly. Do not repeat the raw numbers — translate them into meaning.
Do not mention the word "echo chamber". Do not make political value judgments."""


async def generate_brief(payload: dict, api_key: str) -> str:
    """
    Async call to Groq via LiteLLM. Returns the brief as a plain string.
    """
    response = await acompletion(
        model=MODEL,
        messages=[{"role": "user", "content": _build_prompt(payload)}],
        max_tokens=MAX_TOKENS,
        api_key=api_key
    )

    return response.choices[0].message.content.strip()
