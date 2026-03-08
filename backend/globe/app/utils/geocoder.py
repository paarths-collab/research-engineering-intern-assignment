import asyncio
import time
from typing import Optional
from functools import lru_cache
import httpx

from app.utils.logger import get_logger

logger = get_logger(__name__)

_geo_cache: dict = {}

VAGUE_TERMS = {
    "europe", "middle east", "asia", "global", "world", "international",
    "western", "eastern", "southern", "northern", "africa", "latin america",
    "southeast asia", "central asia", "the west", "the east", "overseas",
    "abroad", "region", "continent",
}

NORMALIZE_MAP = {
    "US": "United States", "U.S.": "United States", "USA": "United States",
    "U.S.A.": "United States", "UK": "United Kingdom", "U.K.": "United Kingdom",
    "UAE": "United Arab Emirates", "Russian": "Russia", "Iranian": "Iran",
    "Israeli": "Israel", "Ukrainian": "Ukraine", "Qatari": "Qatar",
    "Chinese": "China", "North Korean": "North Korea", "South Korean": "South Korea",
    "Turkish": "Turkey", "Saudi": "Saudi Arabia", "Pakistani": "Pakistan",
    "Indian": "India", "Brazilian": "Brazil", "French": "France",
    "German": "Germany", "British": "United Kingdom", "American": "United States",
}


def normalize_location(name: str) -> str:
    return NORMALIZE_MAP.get(name, name)


def is_vague(name: str) -> bool:
    return name.strip().lower() in VAGUE_TERMS


async def geocode_location(name: str) -> Optional[dict]:
    """Geocode a location name using Nominatim. Cached."""
    normalized = normalize_location(name)

    if is_vague(normalized):
        logger.debug(f"Dropping vague location: {normalized}")
        return None

    if normalized in _geo_cache:
        return _geo_cache[normalized]

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": normalized, "format": "json", "limit": 1},
                headers={"User-Agent": "simppl-globe/1.0"},
            )
            await asyncio.sleep(1)  # Nominatim rate limit

            data = resp.json()
            if data:
                result = {
                    "name": normalized,
                    "lat": float(data[0]["lat"]),
                    "lon": float(data[0]["lon"]),
                    "display_name": data[0].get("display_name", normalized),
                    "type": data[0].get("type", "unknown"),
                }
                _geo_cache[normalized] = result
                return result

    except Exception as e:
        logger.warning(f"Geocode failed for '{normalized}': {e}")

    return None


def get_cache_size() -> int:
    return len(_geo_cache)
