"""
Layer 2 — Fast Geo Filter (Cost Shield)
Lightweight NER via keyword matching + country list.
Drops posts with no physical geo reference BEFORE any LLM calls.
"""
import re
from typing import List

from app.database.models import RawPost, GeoCandidate
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Comprehensive country/territory list for fast matching
COUNTRY_KEYWORDS = {
    "afghanistan", "albania", "algeria", "angola", "argentina", "armenia",
    "australia", "austria", "azerbaijan", "bahrain", "bangladesh", "belarus",
    "belgium", "bolivia", "bosnia", "brazil", "bulgaria", "cambodia",
    "cameroon", "canada", "chad", "chile", "china", "colombia", "congo",
    "croatia", "cuba", "cyprus", "czechia", "denmark", "ecuador", "egypt",
    "ethiopia", "finland", "france", "georgia", "germany", "ghana", "greece",
    "guatemala", "haiti", "honduras", "hungary", "india", "indonesia", "iran",
    "iraq", "ireland", "israel", "italy", "japan", "jordan", "kazakhstan",
    "kenya", "kosovo", "kuwait", "kyrgyzstan", "laos", "latvia", "lebanon",
    "libya", "lithuania", "malaysia", "mali", "mexico", "moldova", "mongolia",
    "morocco", "mozambique", "myanmar", "namibia", "nepal", "netherlands",
    "nicaragua", "nigeria", "north korea", "norway", "oman", "pakistan",
    "palestine", "panama", "paraguay", "peru", "philippines", "poland",
    "portugal", "qatar", "romania", "russia", "rwanda", "saudi arabia",
    "senegal", "serbia", "sierra leone", "somalia", "south africa",
    "south korea", "south sudan", "spain", "sri lanka", "sudan", "sweden",
    "switzerland", "syria", "taiwan", "tajikistan", "tanzania", "thailand",
    "tunisia", "turkey", "turkmenistan", "uganda", "ukraine", "united kingdom",
    "united states", "uruguay", "uzbekistan", "venezuela", "vietnam",
    "yemen", "zambia", "zimbabwe",
    # Common city shortcuts
    "beijing", "moscow", "washington", "kyiv", "kiev", "tehran", "riyadh",
    "islamabad", "kabul", "baghdad", "damascus", "ankara", "tel aviv",
    "jerusalem", "cairo", "tripoli", "khartoum", "nairobi", "lagos",
    "london", "paris", "berlin", "brussels", "warsaw", "budapest", "bucharest",
    "istanbul", "dubai", "doha", "abu dhabi", "mumbai", "delhi", "karachi",
    "dhaka", "colombo", "kathmandu", "yangon", "hanoi", "phnom penh",
    "bangkok", "jakarta", "manila", "tokyo", "seoul", "pyongyang",
    "taipei", "hong kong", "singapore", "kuala lumpur",
    "caracas", "bogota", "lima", "santiago", "buenos aires", "brasilia",
    "havana", "mexico city", "ottawa",
}

# Abbreviations that refer to real countries
COUNTRY_ABBREVIATIONS = {
    "us", "usa", "uk", "uae", "eu", "nato", "un",
    "dprk", "prc", "roc", "ksa",
}

VAGUE_BLOCKLIST = {
    "europe", "middle east", "asia", "africa", "global", "world",
    "international", "western", "eastern", "region", "continent",
    "overseas", "abroad", "latin america", "southeast asia",
    "central asia", "north africa", "sub-saharan",
}


def is_vague(text: str) -> bool:
    """Returns True if the text contains any vague regional terms."""
    text_lower = text.lower()
    return any(v.lower() in text_lower for v in VAGUE_BLOCKLIST)


def _tokenize(text: str) -> List[str]:
    return re.findall(r"\b[\w\s'-]{2,}\b", text.lower())


def fast_geo_filter(posts: List[RawPost]) -> List[GeoCandidate]:
    """
    Returns only posts that contain at least one valid physical geo term.
    Rejects vague regional terms.
    """
    candidates: List[GeoCandidate] = []

    for post in posts:
        text_lower = post.title.lower()
        found_terms: List[str] = []

        # Check vague blocklist first
        vague_hit = any(v in text_lower for v in VAGUE_BLOCKLIST)

        # Check country keywords (multi-word aware)
        for country in COUNTRY_KEYWORDS:
            if country in text_lower:
                found_terms.append(country)

        # Check abbreviations (word boundary)
        words = set(re.findall(r"\b\w+\b", text_lower))
        for abbr in COUNTRY_ABBREVIATIONS:
            if abbr in words:
                found_terms.append(abbr.upper())

        # Remove vague terms from found list
        found_terms = [t for t in found_terms if t.lower() not in VAGUE_BLOCKLIST]

        if found_terms:
            candidates.append(GeoCandidate(
                post_id=post.id,
                title=post.title,
                detected_geo_terms=list(set(found_terms)),
                subreddit=post.subreddit,
            ))
            logger.debug(f"GEO PASS [{post.id}]: {found_terms}")
        else:
            logger.debug(f"GEO DROP [{post.id}]: {post.title[:60]}")

    logger.info(f"Geo filter: {len(candidates)}/{len(posts)} posts passed")
    return candidates
