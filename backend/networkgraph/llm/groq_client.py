"""
llm/groq_client.py — Groq API wrapper for narrative analysis.

Model: llama-3.3-70b-versatile
Mode:  Single-shot structured inference. No agents, no chains.
Output: Six structured fields parsed from LLM response.
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Optional

import httpx

from networkgraph.models.schemas import NarrativeAnalysis

log = logging.getLogger("sntis.groq")

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"
MAX_TOKENS = 1200
TEMPERATURE = 0.3   # Low — we want factual pattern description, not creative output


# ─────────────────────────────────────────────────────────────
# Prompt builder
# ─────────────────────────────────────────────────────────────

def build_prompt(
    title: str,
    domain: str,
    url: str,
    created_datetime: str,
    origin_subreddit: str,
    hours_from_origin: Optional[float],
    # Narrative-level
    total_posts: Optional[int],
    unique_subreddits: Optional[int],
    unique_authors: Optional[int],
    spread_strength: Optional[float],
    topic_label: Optional[str],
    topic_cluster: Optional[str],
    # Transport chain
    chain_steps: list,           # list of dicts: {step, subreddit, author, hours}
    # User context
    communities_active_in: Optional[int],
    unique_narratives_by_user: Optional[int],
    # Amplification
    amplification_events: Optional[int],
    total_relative_amplification: Optional[float],
    # Article text (may be partial or None)
    article_text: Optional[str],
) -> str:

    chain_str = "\n".join([
        f"  Step {s.get('step_number', i+1)}: r/{s.get('subreddit','?')} "
        f"(via u/{s.get('author','?')}, "
        f"{s.get('hours_from_origin', '?')}h from origin)"
        for i, s in enumerate(chain_steps[:20])  # cap at 20 steps
    ]) or "  (chain not available)"

    article_section = ""
    if article_text and len(article_text.strip()) > 100:
        preview = article_text.strip()[:2000]
        article_section = f"""
--- ARTICLE TEXT (first 2000 chars) ---
{preview}
--- END ARTICLE TEXT ---
"""
    else:
        article_section = "  (Article text could not be retrieved. Analyze from metadata only.)"

    prompt = f"""You are a neutral narrative transport analyst.
Your job is to describe factual patterns in how online content spreads.
You do NOT accuse, judge political bias, or label propaganda.
You ONLY describe observable patterns.

=== ARTICLE METADATA ===
Title: {title}
Domain: {domain}
URL: {url}
Published: {created_datetime}
Origin Community: r/{origin_subreddit}
Hours from origin to this post: {hours_from_origin}

=== SPREAD METRICS ===
Total posts across Reddit: {total_posts}
Unique subreddits reached: {unique_subreddits}
Unique authors involved: {unique_authors}
Spread strength score: {spread_strength}
Topic cluster: {topic_cluster} — {topic_label}

=== TRANSPORT CHAIN ===
{chain_str}

=== AMPLIFICATION CONTEXT ===
Amplification events by key user: {amplification_events}
Total relative amplification score: {total_relative_amplification}
Communities active in (by key user): {communities_active_in}
Unique narratives spread by key user: {unique_narratives_by_user}

=== ARTICLE CONTENT ===
{article_section}

=== YOUR TASK ===
Respond in valid JSON only. No markdown. No preamble. Use exactly these keys:

{{
  "article_summary": "2-3 sentence factual summary of what the article covers.",
  "headline_tone": "One sentence describing the tone and framing of the headline (e.g. alarming, neutral, sardonic, urgent).",
  "resonance_factors": "2-3 sentences on structural or content factors that may explain why this article spread across communities. Focus on the content characteristics, not political alignment.",
  "spread_pattern_description": "2-3 sentences describing the observed transport pattern: origin, velocity, number of hops, communities reached.",
  "amplification_characteristics": "1-2 sentences on the amplification pattern: how concentrated or distributed user-level sharing was.",
  "topic_cluster_context": "1-2 sentences placing this narrative within its topic cluster and noting if the cluster is typically high or low velocity."
}}"""

    return prompt


# ─────────────────────────────────────────────────────────────
# API call
# ─────────────────────────────────────────────────────────────

async def call_groq(prompt: str) -> tuple[Optional[NarrativeAnalysis], Optional[str], Optional[str]]:
    """
    Sends the prompt to Groq and returns:
      (NarrativeAnalysis | None, raw_text | None, error | None)
    """
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return None, None, "GROQ_API_KEY environment variable not set."

    payload = {
        "model": GROQ_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": MAX_TOKENS,
        "temperature": TEMPERATURE,
        "response_format": {"type": "json_object"},   # Groq supports forced JSON mode
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                GROQ_API_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        err = f"Groq HTTP error {e.response.status_code}: {e.response.text[:300]}"
        log.error(err)
        return None, None, err
    except Exception as e:
        err = f"Groq connection error: {type(e).__name__}: {e}"
        log.error(err)
        return None, None, err

    try:
        data = resp.json()
        raw_text = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        return None, None, f"Unexpected Groq response shape: {e}"

    # ── Parse structured JSON from LLM ──────────────────────────────────────
    try:
        # Strip any accidental markdown code fences
        clean = re.sub(r"```(?:json)?|```", "", raw_text).strip()
        parsed = json.loads(clean)
        analysis = NarrativeAnalysis(
            article_summary=parsed.get("article_summary", ""),
            headline_tone=parsed.get("headline_tone", ""),
            resonance_factors=parsed.get("resonance_factors", ""),
            spread_pattern_description=parsed.get("spread_pattern_description", ""),
            amplification_characteristics=parsed.get("amplification_characteristics", ""),
            topic_cluster_context=parsed.get("topic_cluster_context", ""),
        )
        return analysis, raw_text, None
    except Exception as e:
        log.warning("Could not parse JSON from LLM response: %s", e)
        return None, raw_text, f"LLM response was not valid JSON: {e}"
