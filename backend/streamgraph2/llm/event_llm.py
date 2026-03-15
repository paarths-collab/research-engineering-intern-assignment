"""
event_llm.py — Structured Event Intelligence brief generation.

The LLM receives ONLY a pre-processed payload (no raw posts).
It never touches the internet or guesses events.
"""

import asyncio
import logging
import json

from litellm import acompletion, RateLimitError # type: ignore
from streamgraph2.data.config import GROQ_API_KEY, LLM_MODEL

log = logging.getLogger(__name__)

_RATE_LIMIT_WAIT = 60   # seconds to wait when Groq TPM limit is hit
_MAX_RETRIES     = 3    # max retry attempts per call


async def _call_llm(messages: list[dict], max_tokens: int = 800, temperature: float = 0.3) -> str:
    """Wrapper around acompletion with automatic rate-limit retry (waits 60 s)."""
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            response = await acompletion(
                model=LLM_MODEL,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                api_key=GROQ_API_KEY,
            )
            return response.choices[0].message.content.strip()  # type: ignore
        except RateLimitError as e:
            if attempt < _MAX_RETRIES:
                log.warning(
                    "Groq rate limit hit (attempt %d/%d). Waiting %ds before retry. %s",
                    attempt, _MAX_RETRIES, _RATE_LIMIT_WAIT, e,
                )
                await asyncio.sleep(_RATE_LIMIT_WAIT)
            else:
                log.error("Groq rate limit exceeded after %d attempts.", _MAX_RETRIES)
                raise
    raise RuntimeError("LLM call failed without a response")


def _build_prompt(payload: dict) -> str:
    sub_lines      = "\n".join(
        f"  - r/{r[0]}: {r[1]} posts" for r in payload["top_subreddits"]
    )
    domain_lines   = "\n".join(
        f"  - {d[0]}: {d[1]} links" for d in payload["top_domains"]
    )
    headline_lines = "\n".join(f"  - {h}" for h in payload["headline_examples"])

    return f"""You are a concise OSINT intelligence analyst writing for an institutional dashboard.
Analyze this Reddit narrative spike using ONLY the structured data below.

EVENT CONTEXT:
- Date:        {payload["event_date"]}
- Theme:       {payload["cluster"]}
- Topic Focus: {payload["topic"]}
- Total Posts: {payload["total_posts"]}

TOP COMMUNITIES:
{sub_lines}

TOP NEWS SOURCES:
{domain_lines}

REPRESENTATIVE HEADLINES:
{headline_lines}

Write EXACTLY 4 sections with these bold headings. Be forensic and analytical. No filler.

**THE CATALYST**: What real-world event triggered this spike? Infer from headlines. (1-2 sentences)
**THE REACTION**: How are Reddit communities responding? What specific grievances or positions? (2 sentences)
**NARRATIVE FRAMING**: How does the Reddit framing differ from objective reporting? Partisan angle? (2 sentences)
**DATA SIGNAL**: State key metrics — volume, top communities, dominant sources — as hard evidence. (1-2 sentences)"""


async def generate_event_brief(payload: dict) -> str:
    """
    Call Groq LLM with the structured event payload.
    Returns the brief as a markdown string.
    """
    return await _call_llm(
        messages=[{"role": "user", "content": _build_prompt(payload)}],
        max_tokens=800,
    )


# ── Stage 1: Topic Bifurcation ────────────────────────────────

def _build_topic_extraction_prompt(headlines: list[dict]) -> str:
    # Up to 150 headlines; titles capped at 120 chars each
    sample = headlines[:150]
    lines = "\n".join(
        f"- [{h['subreddit']}] {h['title'][:120]}"
        for h in sample
    )
    return f"""You are a senior geopolitical narrative intelligence analyst.

Given the following Reddit headlines from a ±10-day window around a volume spike, identify the distinct narrative topics being discussed.

Rules:
- Produce 4–8 topics (more is better if the data supports it)
- Each topic must be a full descriptive sentence explaining WHAT is being discussed and WHY it matters
- Merge near-identical headlines but keep ideologically distinct framings as separate topics
- For each topic identify: which subreddits are driving it, the dominant emotional tone, and the core claim being made
- Provide 3–4 representative example headlines per topic

HEADLINES:
{lines}

Respond with valid JSON only (no markdown fences, no explanation):
[
  {{
    "topic": "<full descriptive sentence>",
    "subreddits": ["..."],
    "sentiment": "outrage | alarm | celebratory | skeptical | neutral",
    "key_claim": "<one sentence: the core assertion being made>",
    "example_headlines": ["...", "...", "..."]
  }}
]"""


async def extract_topics(headlines: list[dict]) -> list[dict]:
    """
    Stage 1 LLM call: extract 4-8 narrative topics from headlines.
    Returns list of {topic, subreddits, sentiment, key_claim, example_headlines}.
    """
    raw = await _call_llm(
        messages=[{"role": "user", "content": _build_topic_extraction_prompt(headlines)}],
        max_tokens=1200,
    )

    def _strip_fences(text: str) -> str:
        out = text.strip()
        if out.startswith("```"):
            parts = out.split("```")
            if len(parts) >= 2:
                out = parts[1].strip()
            if out.lower().startswith("json"):
                out = out[4:].strip()
        return out

    def _extract_json_array(text: str) -> str:
        s = _strip_fences(text)
        start = s.find("[")
        if start == -1:
            raise ValueError("No JSON array start token '[' found in LLM response")

        in_string = False
        escaped = False
        depth = 0
        end = -1

        for i, ch in enumerate(s[start:], start=start):
            if in_string:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_string = False
                continue

            if ch == '"':
                in_string = True
            elif ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    end = i
                    break

        if end == -1:
            raise ValueError("No complete JSON array found in LLM response")
        return s[start:end + 1]

    def _parse_topics(text: str) -> list[dict]:
        payload = json.loads(_extract_json_array(text))
        if not isinstance(payload, list):
            raise ValueError("Topic extraction payload is not a JSON array")
        return [p for p in payload if isinstance(p, dict)]

    try:
        return _parse_topics(raw)
    except Exception as first_exc:
        log.warning("Topic extraction JSON parse failed, attempting one-shot repair: %s", first_exc)
        repaired = await _call_llm(
            messages=[
                {
                    "role": "system",
                    "content": "Return only valid JSON. No markdown fences. Preserve meaning.",
                },
                {
                    "role": "user",
                    "content": (
                        "Convert the following malformed model output into a valid JSON array of objects "
                        "with keys: topic, subreddits, sentiment, key_claim, example_headlines.\n\n"
                        f"{raw}"
                    ),
                },
            ],
            max_tokens=1400,
            temperature=0,
        )
        return _parse_topics(repaired)


# ── Stage 2: Deep Narrative Analysis ─────────────────────────

def _build_narrative_analysis_prompt(topic: str, posts: list[dict]) -> str:
    # Up to 150 posts; titles capped at 120 chars each, sorted by date
    sample = sorted(posts[:150], key=lambda p: p.get('date', ''))
    post_lines = "\n".join(
        f"- [{p.get('date','?')}] [{p['subreddit']}] [{p.get('domain', '')}] {p['title'][:120]}"
        for p in sample
    )
    return f"""You are a senior OSINT narrative intelligence analyst writing a classified institutional brief.

Your task: produce a comprehensive, multi-perspective intelligence report on how the following narrative topic developed across Reddit communities over a 10-day window (5 days before the spike through 5 days after).

TOPIC: {topic}

POSTS (sorted chronologically — date, subreddit, domain, headline):
{post_lines}

---
Write the following sections in full. Be forensic, cite specific dates/subreddits/domains. No filler.

**EXECUTIVE SUMMARY**
Two or three sentences capturing the entire narrative arc — what happened, why it mattered, and what the data reveals.

**VOLUME SPIKE ANALYSIS**
Explain specifically why post volume increased during this window. Consider: Was there a breaking news event, a political development, a viral post, a policy announcement, or a real-world incident that caused a sudden surge? Did volume build gradually (slow burn) or explode overnight (flash event)? Which subreddits were the first movers and which joined later? Quantify the relative activity across the earliest vs. peak vs. post-peak days based on the post distribution you can see.

**TIMELINE & TREND ARC**
Trace the narrative day by day. What was the discussion 5 days before the spike? What triggered the peak? What happened in the 5 days after — did it sustain, fade, or mutate into a new narrative? Cite specific dates and subreddit activity.

**MULTI-PERSPECTIVE ANALYSIS**
Describe how at least 3 different ideological or community perspectives framed this topic differently. What did conservatives vs. liberals vs. moderates emphasise? Where did the framings diverge or align?

**AMPLIFICATION MECHANICS**
Which subreddits drove the most volume? Were there bridge communities sharing across ideological lines? Did any single domain dominate the sourcing? Identify any coordinated or organic amplification patterns.

**KEY CLAIMS & COUNTER-NARRATIVES**
List the 2–3 dominant claims made in these posts. For each, note if a counter-narrative existed and which communities pushed back.

**INTELLIGENCE ASSESSMENT**
What does this narrative event reveal about underlying social tensions or political dynamics? What is the most likely real-world trigger? Is this a one-off spike or part of a longer pattern?"""


async def generate_narrative_analysis(topic: str, posts: list[dict]) -> str:
    """
    Stage 2 LLM call: deep multi-perspective narrative analysis.
    Returns markdown-formatted brief.
    """
    return await _call_llm(
        messages=[{"role": "user", "content": _build_narrative_analysis_prompt(topic, posts)}],
        max_tokens=1600,
    )
