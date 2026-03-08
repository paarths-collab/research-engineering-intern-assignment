"""
llm_engine.py — Structured narrative synthesis via Groq API.

The LLM receives ONLY structured JSON metrics.
It does NOT:
  - Fetch external data
  - Guess events
  - Have internet access

It translates structured metrics into a readable intelligence brief.
"""

import json
from typing import Dict, List

from litellm import acompletion

from streamgraph2.data.config import GROQ_API_KEY, LLM_MODEL
from streamgraph2.data import db


async def generate_smart_search_query(representative_posts: list) -> str:
    prompt = f"""
    Read these Reddit posts from a single conversation cluster today:
    {representative_posts}

    Your task is to figure out EXACTLY what real-world news event triggered this discussion.
    Return ONLY a highly specific 4-to-6 word search query that I can plug into a News API to find the source article. 
    (Example: "Trump signs reciprocal tariffs executive order")
    Do not include quotes or extra text.
    """
    response = await acompletion(
        model=LLM_MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=30,
        temperature=0.3,
        api_key=GROQ_API_KEY
    )
    return response.choices[0].message.content.strip().strip('"').strip("'")


def _build_prompt(payload: Dict) -> str:
    acceleration = payload["acceleration"]
    topics       = payload["topics"]
    sentiment    = payload["sentiment"]

    t = topics[0] if topics else {}
    catalysts = t.get("catalysts", [])
    top_cat   = catalysts[0] if catalysts else {}
    matched_news_headline = top_cat.get("headline", "N/A")
    representative_posts = t.get("representative_posts", [])

    delta_neg    = "N/A"
    if len(sentiment) >= 2:
        spike_idx = 1 if len(sentiment) > 1 else 0
        delta_neg    = sentiment[spike_idx].get("delta_negative", "N/A")

    return f"""You are a Lead OSINT Intelligence Analyst.

DATA:
- Real-World Catalyst (News Headline): {matched_news_headline}
- Reddit Community Conversation: {representative_posts}
- Volume Acceleration: {acceleration.get('ratio', 'N/A')}x baseline
- Sentiment Shift: {delta_neg}% more negative today.

Write a forensic Intelligence Brief focusing on the WHAT, HOW, and WHY. Do NOT just list numbers. 

Format your response with these exact headings:
1. THE CATALYST (What happened?): Explain the real-world news event in one sentence.
2. THE REACTION (Why is Reddit mad/happy?): Explain how the Reddit community is reacting to this news. What are their specific grievances or celebrations?
3. THE NARRATIVE FRAMING (How are they twisting it?): How does the Reddit conversation differ from the objective news headline? Are they introducing bias, conspiracy, or partisan framing?
4. DATA EVIDENCE: Briefly state the volume spike and sentiment shift as proof of this intense reaction.
"""


async def generate_brief(
    job_id: str,
    spike_date: str,
    acceleration: Dict,
    topics: List[Dict],
    matches: List[Dict],
    sentiment: List[Dict],
    skip_db_save: bool = False
) -> str:
    """
    Build structured payload, call Groq (llama-3.3-70b-versatile), store result.
    Returns brief text.
    """
    # Attach top catalysts to each topic
    enriched_topics = []
    for t in topics:
        catalysts = [m for m in matches if m.get("topic_id") == t["topic_id"]]
        catalysts.sort(key=lambda x: -x.get("similarity", 0))
        enriched_topics.append({**t, "catalysts": catalysts[:3]})

    payload = {
        "spike_date"  : spike_date,
        "acceleration": acceleration,
        "topics"      : enriched_topics,
        "sentiment"   : sentiment,
    }

    response = await acompletion(
        model=LLM_MODEL,
        messages=[{"role": "user", "content": _build_prompt(payload)}],
        max_tokens=1200,
        api_key=GROQ_API_KEY
    )

    brief_text = response.choices[0].message.content.strip()
    if not skip_db_save:
        await db.save_brief(job_id, brief_text)
    return brief_text
