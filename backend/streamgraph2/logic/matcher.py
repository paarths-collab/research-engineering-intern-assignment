"""
matcher.py — Pure vector math cosine similarity attribution.

No LLM involved. No guesswork.
Each topic centroid is matched against all news embeddings.
Top K results stored per topic.
"""

import math
from typing import List, Dict

from streamgraph2.data import db
from streamgraph2.data.config import SIMILARITY_TOP_K


def _cosine(a: List[float], b: List[float]) -> float:
    dot   = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


async def run_similarity_matching(
    job_id: str,
    topics: List[Dict],
    news_items: List[Dict],
) -> List[Dict]:
    """
    For each topic centroid, compute cosine similarity against all news embeddings.
    Store top SIMILARITY_TOP_K matches per topic.

    Returns list of match dicts for downstream use.
    """
    if not topics or not news_items:
        print("  [Match] Skipped — no topics or news items")
        return []

    all_matches = []

    for topic in topics:
        centroid  = topic["centroid"]
        topic_id  = topic["topic_id"]

        # Score all news items
        scored = []
        for item in news_items:
            sim = _cosine(centroid, item["embedding"])
            scored.append({
                "topic_id" : topic_id,
                "headline" : item["headline"],
                "source"   : item["source"],
                "url"      : item["url"],
                "similarity": round(sim, 4),
            })

        # Keep top K
        top_k = sorted(scored, key=lambda x: -x["similarity"])[:SIMILARITY_TOP_K]

        for match in top_k:
            await db.save_news_match(
                job_id     = job_id,
                topic_id   = match["topic_id"],
                headline   = match["headline"],
                source     = match["source"],
                url        = match["url"],
                similarity = match["similarity"],
            )
            all_matches.append(match)

        print(
            f"  [Match] Topic {topic_id} | top sim: "
            f"{top_k[0]['similarity']:.3f} → {top_k[0]['headline'][:60]}"
        )

    return all_matches
