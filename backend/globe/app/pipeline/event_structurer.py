"""
Layer 4 — Event Structuring (LLM Assisted)
Extracts structured intelligence from a geo-validated post:
event_type, key_entities, search_queries, secondary locations.
Uses Groq llama-3.3-70b for higher quality extraction.
"""
import json
import re
import uuid
import asyncio
from typing import List, Optional

from app.config import get_settings
from app.database.models import GeoCandidate, ResolvedLocation, StructuredEvent
from app.database.connection import get_connection
from app.llm.client import request_chat_completion
from app.utils.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()
SYSTEM_PROMPT = """You are a geopolitical intelligence extraction engine.
Return ONLY valid JSON. No markdown, no explanation, no preamble."""

STRUCTURE_PROMPT = """Analyse this geopolitical news headline and extract structured intelligence.

Headline: {title}
Primary Location: {primary_location}

Extract:
1. event_type — one of: [conflict, diplomacy, election, protest, disaster, economic, terrorism, sanctions, military_movement, cyber, humanitarian, other]
2. secondary_locations — other countries/cities involved (max 3, empty list if none)
3. key_entities — organisations, governments, leaders, groups mentioned (max 5)
4. search_queries — 3 optimised news search queries to verify this event (short, specific)

Return JSON exactly:
{{
  "event_type": "...",
  "secondary_locations": ["...", "..."],
  "key_entities": ["...", "..."],
  "search_queries": ["query1", "query2", "query3"]
}}"""
def _parse_structure_response(content: str) -> Optional[dict]:
    content = re.sub(r"```(?:json)?", "", content).strip().strip("`")
    try:
        return json.loads(content)
    except Exception:
        match = re.search(r"\{[\s\S]*\}", content)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                pass
    return None


async def structure_event(
    candidate: GeoCandidate,
    location: ResolvedLocation,
    model: str,
) -> Optional[StructuredEvent]:
    try:
        prompt = STRUCTURE_PROMPT.format(
            title=candidate.title,
            primary_location=location.name,
        )
        content = await request_chat_completion(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            model=model,
            temperature=0,
        )
        data = _parse_structure_response(content)
        if not data:
            logger.warning(f"Structure parse fail for '{candidate.title[:50]}'")
            return None

        event = StructuredEvent(
            id=str(uuid.uuid4()),
            post_id=candidate.post_id,
            event_type=data.get("event_type", "other"),
            primary_location=location.name,
            secondary_locations=data.get("secondary_locations", [])[:3],
            key_entities=data.get("key_entities", [])[:5],
            search_queries=data.get("search_queries", [])[:3],
        )
        logger.debug(f"STRUCTURED [{event.event_type}]: {location.name}")
        return event

    except Exception as e:
        err = str(e)
        if "429" in err or "rate_limit" in err.lower() or "RateLimitError" in err:
            raise   # Let outer retry loop handle it
        logger.warning(f"Event structure error: {e}")
        return None


def _get_cached_event(post_id: str) -> Optional[StructuredEvent]:
    """Return an already-structured event for this post_id, or None."""
    conn = get_connection()
    row = conn.execute(
        """SELECT id, post_id, event_type, primary_location,
                  secondary_locations, key_entities, search_queries
           FROM structured_events WHERE post_id = ? LIMIT 1""",
        [post_id]
    ).fetchone()
    if row:
        return StructuredEvent(
            id=row[0], post_id=row[1], event_type=row[2],
            primary_location=row[3],
            secondary_locations=json.loads(row[4] or "[]"),
            key_entities=json.loads(row[5] or "[]"),
            search_queries=json.loads(row[6] or "[]"),
        )
    return None


async def structure_all_events(
    pairs: List[tuple[GeoCandidate, ResolvedLocation]],
) -> List[StructuredEvent]:
    model = settings.FAST_MODEL
    events = []
    skipped = 0

    for candidate, location in pairs:
        # ── Cache check: skip LLM if already structured ─────────
        cached = _get_cached_event(candidate.post_id)
        if cached:
            events.append(cached)
            skipped += 1
            continue

        await asyncio.sleep(3)  # ~20 RPM stay under limit
        for attempt in range(3):
            try:
                result = await structure_event(candidate, location, model)
                if result:
                    events.append(result)
                break
            except Exception as e:
                match = re.search(r"try again in (\d+(?:\.\d+)?)s", str(e))
                wait = float(match.group(1)) + 2 if match else 20 * (attempt + 1)
                logger.warning(f"Rate limit on structuring, waiting {wait:.1f}s (attempt {attempt+1}/3)")
                await asyncio.sleep(wait)

    logger.info(f"Event structuring: {len(events)}/{len(pairs)} events built ({skipped} from cache)")
    _persist_structured_events(events)
    return events


def _persist_structured_events(events: List[StructuredEvent]) -> None:
    conn = get_connection()
    for e in events:
        conn.execute("""
            INSERT OR REPLACE INTO structured_events
            (id, post_id, event_type, primary_location,
             secondary_locations, key_entities, search_queries)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, [
            e.id, e.post_id, e.event_type, e.primary_location,
            json.dumps(e.secondary_locations),
            json.dumps(e.key_entities),
            json.dumps(e.search_queries),
        ])
