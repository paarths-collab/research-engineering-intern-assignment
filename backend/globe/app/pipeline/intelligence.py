"""
Layer 6 — Contextual Intelligence (LLM Analysis)
Feeds Reddit post + NewsBundle into a single intelligence prompt.
Produces: executive summary, sentiment, risk level, strategic implications.
Pure LLM contextual reasoning.
"""
import json
import re
import asyncio
from typing import List, Optional

from app.config import get_settings
from app.database.models import StructuredEvent, NewsBundle, RawPost, NarrativeIntel
from app.llm.client import request_chat_completion
from app.utils.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()

_TOKEN_BUDGET = 80000   # Leave 20k buffer from 100k daily limit
_tokens_used = 0


def _format_news_context(bundle: NewsBundle) -> str:
    if not bundle.articles:
        return "No corroborating news found."
    lines = []
    for a in bundle.articles[:5]:
        trust = "✓" if a.is_trusted else "·"
        lines.append(f"  {trust} [{a.source}] {a.title}")
        if a.snippet:
            lines.append(f"    ↳ {a.snippet[:150]}")
    return "\n".join(lines)


def _build_intel_prompt(
    post: RawPost,
    event: StructuredEvent,
    bundle: NewsBundle,
) -> str:
    news_ctx = _format_news_context(bundle)

    context_block = f"""
EVENT HEADLINE: {post.title}
EVENT TYPE: {event.event_type}
PRIMARY LOCATION: {event.primary_location}
KEY ENTITIES: {', '.join(event.key_entities)}
REDDIT ENGAGEMENT: score={post.score}, comments={post.num_comments}
SUBREDDIT: r/{post.subreddit}

CORROBORATING NEWS ({bundle.news_count} articles, {bundle.trusted_source_count} trusted):
{news_ctx}
"""

    return f"""
Analyse this geopolitical event and produce a structured intelligence assessment.

{context_block}

Return STRICT JSON with exactly this structure (no markdown, no extra text):
{{
  "summary": "3-5 sentence executive summary grounded in available data",
  "sentiment_label": "positive|negative|neutral|mixed",
  "sentiment_confidence": 0.0-1.0,
  "risk_level": "Low|Medium|High",
  "strategic_implications": [
    "Implication 1",
    "Implication 2",
    "Implication 3"
  ]
}}
"""


def _parse_intel_response(content: str, event_id: str) -> NarrativeIntel:
    content = re.sub(r"```(?:json)?", "", content).strip().strip("`")

    defaults = NarrativeIntel(
        event_id=event_id,
        summary="Insufficient data for analysis.",
        risk_level="Low",
        sentiment_label="neutral",
        sentiment_confidence=0.5,
        strategic_implications=[],
    )

    try:
        match = re.search(r"\{[\s\S]*\}", content)
        if match:
            data = json.loads(match.group(0))
            return NarrativeIntel(
                event_id=event_id,
                summary=data.get("summary", defaults.summary),
                sentiment_label=data.get("sentiment_label", "neutral"),
                sentiment_confidence=float(data.get("sentiment_confidence", 0.5)),
                risk_level=data.get("risk_level", "Low"),
                strategic_implications=data.get("strategic_implications", [])[:5],
            )
    except Exception as e:
        logger.warning(f"Intel parse error: {e}")

    return defaults


async def analyse_event(
    post: RawPost,
    event: StructuredEvent,
    bundle: NewsBundle,
) -> NarrativeIntel:
    """Run intelligence analysis for a single event via shared Groq SDK client."""
    try:
        prompt = _build_intel_prompt(post, event, bundle)
        output = await request_chat_completion(
            messages=[
                {
                    "role": "system",
                    "content": "You are a geopolitical intelligence analyst. Return only valid JSON.",
                },
                {"role": "user", "content": prompt},
            ],
            model=settings.PRIMARY_MODEL,
            temperature=0.1,
            max_tokens=1200,
        )
        intel = _parse_intel_response(output, event.id)
        logger.debug(
            f"INTEL [{event.primary_location}]: risk={intel.risk_level} "
            f"sentiment={intel.sentiment_label}"
        )
        return intel

    except Exception as e:
        err = str(e)
        if "429" in err or "rate_limit" in err.lower() or "RateLimitError" in err:
            raise   # Let outer retry loop handle it
        logger.warning(f"Intelligence analysis error: {e}")
        return NarrativeIntel(
            event_id=event.id,
            summary="Analysis unavailable.",
            risk_level="Low",
            sentiment_label="neutral",
            sentiment_confidence=0.0,
            strategic_implications=[],
        )


async def analyse_all_events(
    posts_map: dict[str, RawPost],
    events: List[StructuredEvent],
    bundles_map: dict[str, NewsBundle],
) -> List[NarrativeIntel]:
    global _tokens_used
    results = []

    for event in events:
        # Rough token budget guard (~700 tokens per call)
        if _tokens_used > _TOKEN_BUDGET:
            logger.warning(f"Token budget exhausted ({_tokens_used} used), skipping remaining events")
            break

        post = posts_map.get(event.post_id)
        bundle = bundles_map.get(event.id, NewsBundle(event_id=event.id))
        if not post:
            continue

        for attempt in range(3):
            try:
                intel = await analyse_event(post, event, bundle)
                results.append(intel)
                _tokens_used += 700  # Approximate per-call usage
                await asyncio.sleep(6)  # TPM throttle
                break
            except Exception as e:
                match = re.search(r"try again in (\d+(?:\.\d+)?)s", str(e))
                wait = float(match.group(1)) + 2 if match else 20 * (attempt + 1)
                logger.warning(f"TPM limit, waiting {wait:.1f}s (attempt {attempt+1}/3)")
                await asyncio.sleep(wait)
                if attempt == 2:
                    results.append(NarrativeIntel(
                        event_id=event.id,
                        summary="Analysis unavailable.",
                        risk_level="Low",
                        sentiment_label="neutral",
                        sentiment_confidence=0.0,
                        strategic_implications=[],
                    ))

    logger.info(f"Intelligence analysis complete -- {len(results)} assessments")
    return results
