"""
ai_brief.py — Calls Groq via LiteLLM to generate an intelligence brief.

Takes a structured payload (from polarize_1.compute.get_subreddit_summary_payload)
and returns a clean, analytical paragraph. No raw data passed — only
structured metrics so the LLM interprets, not restates.
"""

import os
from litellm import acompletion

MODEL = os.getenv("HIGH_MODEL", "groq/llama-3.3-70b-versatile")
MAX_TOKENS = 2500


def _build_prompt(payload: dict) -> str:
    sub = payload["subreddit"]
    domains = payload["top_domains"]
    cats = payload["category_breakdown"]
    similar = payload["similar_subreddits"]

    domain_lines = []
    for d in domains:
        line = f"  - {d['domain']}  (subreddit share: {round(d['p_sub']*100, 1)}%, category: {d['category']})"
        titles = d.get('recent_titles', [])
        if titles:
            title_strs = []
            for t in titles:
                if isinstance(t, dict) and "url" in t:
                    title_strs.append(f"[{t['title'].replace('[', '').replace(']', '')}]({t['url']})")
                else:
                    title_strs.append(str(t))
            line += f"\n    Recent Shared Articles: {', '.join(title_strs)}"
        domain_lines.append(line)
        
    domain_lines_str = "\n".join(domain_lines)
    
    cat_lines = "\n".join(
        f"  - {c['cat']}: {c['pct']}%"
        for c in cats
    )
    
    sim_lines = (
        "\n".join(f"  - r/{s['subreddit']} ({s['overlap']} shared domains)" for s in similar)
        if similar else "  - No close neighbors (highly isolated)"
    )

    return f"""You are writing an intelligence brief for a media ecosystem analysis dashboard.
Your job is to provide a structured analytical perspective on how this community consumes information, based strictly on their Top 20 most referenced news sources, their shared article headlines, and source overlaps.

─── STRUCTURED METRICS ───────────────────────────────────────────────────────

SUBREDDIT: r/{sub}

TOP 20 REFERENCED NEWS SOURCES (by share of links and references)
Includes recently shared article headlines for context on narratives:
{domain_lines_str}

SOURCE TYPE BREAKDOWN:
{cat_lines}

MOST OVERLAPPING COMMUNITIES (shared news sources):
{sim_lines}

─── INSTRUCTIONS ─────────────────────────────────────────────────────────────

Write a highly specialized, analytical intelligence brief. Provide detailed, nuanced insights tailored to the specific ideological and informational characteristics of this community. You must mention and synthesize all the Top 20 news sources provided in your response. Do this all at once in a cohesive manner. Use Markdown headers for exactly these 4 sections:

### Community Profile
Identify the overarching theme or ideological slant of the Top 20 news sources in detail. Explicitly mention these news sources. Explain what this suggests about the community's information diet, epistemology, and political orientation.

### Media Ecosystem
Comment on the source type mix in depth, explicitly naming the major outlets among the 20 sources provided. Mention their journalistic approach (traditional news vs advocacy vs research), and what their presence implies about the community's trust in institutions.

### Narrative Signals
Based on the `Recent Shared Articles` listed under the active news sources, what are the primary topics, themes, or narratives this community focuses on? Give an elaborated answer and explicitly reference specific article headlines and the specific news sources broadcasting them as evidence to ground your analysis. When referencing an article, you MUST format it as a clickable Markdown link using the exact URL provided in the metrics (e.g., `[Article Title](https://...)`).

### Cross-Community Alignment
Note which other communities share overlapping media diets and what that indicates about their ideological clustering, potential for cross-pollination, or isolation. Provide a specialized perspective.

Tone: specialized, highly analytical, neutral, and professional. No bullet points under the headers (use paragraphs). Do not use the word "echo chamber". Do not make political value judgments. Do not invent information not provided in the metrics."""


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
