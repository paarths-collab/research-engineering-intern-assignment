"""
Layer 3 — LLM Geo Resolution
Turns raw geo terms into precise, geocoded coordinates.
Uses Groq (fast + cheap). Validates via Nominatim geocoding.
Caches results to avoid redundant calls.
"""
import json
import re
import asyncio
from typing import List, Optional
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage

from app.config import get_settings
from app.database.models import GeoCandidate, ResolvedLocation
from app.database.connection import get_connection
from app.utils.geocoder import geocode_location
from app.utils.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()

SYSTEM_PROMPT = """You are a precise geo-intelligence resolver for a geopolitical mapping system.
Return ONLY valid JSON. Never return markdown, explanations, or extra text."""

GEO_RESOLVE_PROMPT = """Given this news headline, identify the PRIMARY physical location where the event occurs.

Rules:
1. Prefer specific city over country if a city is mentioned.
2. Convert nationality adjectives (Iranian → Iran, Russian → Russia, Israeli → Israel).
3. Return ONLY ONE primary location as "City, Country" or just "Country".
4. Reject abstract regions (Middle East, Europe, Global) — return null.
5. Return null if no valid physical location found.

Headline: {title}

Return JSON:
{{"primary_location": "City, Country" or "Country" or null}}
"""


def _get_llm(model: str = None) -> ChatGroq:
    return ChatGroq(
        api_key=settings.GROQ_API_KEY,
        model=model or settings.FAST_MODEL,
        temperature=0,
        max_retries=3,
    )


def _parse_location_response(content: str) -> Optional[str]:
    content = re.sub(r"```(?:json)?", "", content).strip().strip("`")
    try:
        data = json.loads(content)
        loc = data.get("primary_location")
        if loc and loc != "null":
            return str(loc).strip()
    except Exception:
        # Fallback regex
        match = re.search(r'"primary_location"\s*:\s*"([^"]+)"', content)
        if match:
            return match.group(1).strip()
    return None


async def resolve_geo_for_candidate(
    candidate: GeoCandidate,
    llm: ChatGroq,
) -> Optional[ResolvedLocation]:
    """Resolve a single geo candidate to precise coordinates."""
    try:
        prompt = GEO_RESOLVE_PROMPT.format(title=candidate.title)
        response = await llm.ainvoke([
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ])

        location_name = _parse_location_response(response.content)
        if not location_name:
            logger.debug(f"GEO RESOLVE: null for '{candidate.title[:50]}'")
            return None

        # Validate via geocoding
        geo = await geocode_location(location_name)
        if not geo:
            # Try just the country part
            parts = location_name.split(",")
            if len(parts) > 1:
                geo = await geocode_location(parts[-1].strip())

        if not geo:
            logger.debug(f"GEO VALIDATE FAIL: '{location_name}'")
            return None

        resolved = ResolvedLocation(
            name=location_name,
            lat=geo["lat"],
            lon=geo["lon"],
            geo_type=geo.get("type", "unknown"),
            display_name=geo.get("display_name", location_name),
        )
        logger.debug(f"GEO RESOLVED: {resolved.name} ({resolved.lat:.2f},{resolved.lon:.2f})")
        return resolved

    except Exception as e:
        err = str(e)
        if "429" in err or "rate_limit" in err.lower():
            raise   # Let outer retry loop handle it
        logger.warning(f"Geo resolve error for '{candidate.title[:40]}': {e}")
        return None


def _get_cached_resolution(post_id: str) -> Optional[ResolvedLocation]:
    """Return a previously resolved location for this post_id, or None."""
    conn = get_connection()
    row = conn.execute(
        "SELECT resolved, lat, lon, geo_type FROM geo_resolutions WHERE post_id = ? LIMIT 1",
        [post_id]
    ).fetchone()
    if row:
        return ResolvedLocation(
            name=row[0], lat=row[1], lon=row[2],
            geo_type=row[3] or "unknown", display_name="",
        )
    return None


async def resolve_all_candidates(
    candidates: List[GeoCandidate],
) -> List[tuple[GeoCandidate, ResolvedLocation]]:
    llm = _get_llm(settings.FAST_MODEL)
    results = []
    skipped = 0

    for candidate in candidates:
        # ── Cache check: skip LLM if already resolved ─────────────────
        cached = _get_cached_resolution(candidate.post_id)
        if cached:
            results.append((candidate, cached))
            skipped += 1
            continue

        await asyncio.sleep(2.0)  # 2s gap = ~30 RPM at free tier limit
        for attempt in range(3):
            try:
                loc = await resolve_geo_for_candidate(candidate, llm)
                if loc is not None:
                    results.append((candidate, loc))
                break
            except Exception as e:
                if "429" in str(e) or "rate_limit" in str(e).lower():
                    match = re.search(r"try again in (\d+(?:\.\d+)?)s", str(e))
                    wait = float(match.group(1)) + 2 if match else 15 * (attempt + 1)
                    logger.warning(f"Rate limit on geo resolve, waiting {wait:.1f}s (attempt {attempt+1}/3)")
                    await asyncio.sleep(wait)
                else:
                    logger.warning(f"Resolve error for '{candidate.title[:40]}': {e}")
                    break

    logger.info(f"Geo resolution: {len(results)}/{len(candidates)} resolved ({skipped} from cache)")
    _persist_geo_resolutions(results)
    return results


def _persist_geo_resolutions(
    pairs: List[tuple[GeoCandidate, ResolvedLocation]],
) -> None:
    conn = get_connection()
    for candidate, loc in pairs:
        rid = f"{candidate.post_id}_{loc.name[:20].replace(' ', '_')}"
        conn.execute("""
            INSERT OR REPLACE INTO geo_resolutions
            (id, post_id, raw_term, resolved, lat, lon, geo_type)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, [rid, candidate.post_id, ", ".join(candidate.detected_geo_terms),
              loc.name, loc.lat, loc.lon, loc.geo_type])
