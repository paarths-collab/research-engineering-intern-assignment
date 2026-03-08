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
        f"  - {d['domain']}  (lift: {d['lift']}×, type: {d['category']}, count: {d['count']})"
        for d in domains
    )
    cat_lines = "\n".join(
        f"  - {c['cat']}: {c['pct']}%"
        for c in cats
    )
    sim_lines = (
        "\n".join(f"  - r/{s['subreddit']} ({int(s['similarity']*100)}% overlap)" for s in similar)
        if similar else "  - No close neighbors (highly isolated)"
    )

    return f"""You are writing an intelligence brief for a media ecosystem analysis dashboard.
Your job is to interpret structural metrics and explain what they reveal about how a Reddit community 
consumes information. Derive orientation from domain names and organization types — do not assume ideology 
from the subreddit name alone.

─── STRUCTURED METRICS ───────────────────────────────────────────────────────

SUBREDDIT: r/{sub}

ECHO SCORE: {score}
  (Avg lift of top distinctive domains vs global baseline.
   High score = concentrated media diet. Not a measure of extremism.)

TOP DISTINCTIVE DOMAINS (by lift):
{domain_lines}

SOURCE TYPE BREAKDOWN:
{cat_lines}

MOST SIMILAR SUBREDDITS (cosine similarity on domain link vectors):
{sim_lines}

─── INSTRUCTIONS ─────────────────────────────────────────────────────────────

Write 4–5 sentences. Structure your brief as follows:
1. Identify what the top domains represent (what kind of organizations/publications are they?).
2. Interpret the echo score — what does this concentration level mean in practical terms?
3. Comment on the source type mix — journalism vs advocacy vs institutional vs video.
4. Comment on ecosystem isolation or overlap with other communities.
5. End with one sentence on what this suggests about the community's information environment.

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
