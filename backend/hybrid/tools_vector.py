"""
hybrid/tools_vector.py
-----------------------
Vector / semantic search tool for the Vector Agent.

The Vector Agent is ONLY allowed to use this tool.
It cannot compute numbers, run SQL, or produce analysis.
"""

import os
import time
import logging

from langchain.tools import tool

from hybrid.database import semantic_search

logger = logging.getLogger(__name__)
_SLEEP = float(os.getenv("TOOL_SLEEP_SECONDS", "4"))


@tool
def search_vectors(topic: str) -> str:
    """
    Semantic search over Reddit post titles using sentence embeddings.

    Use for qualitative questions about:
    - Narrative themes and framing
    - Ideology and political sentiment
    - Opinion patterns and rhetoric

    Do NOT use for counts, dates, or numeric metrics — use execute_sql for those.

    Input: a plain-English topic description (e.g. "election fraud claims", "immigration rhetoric")
    Returns: up to 5 matched posts with subreddit, date, title, similarity score.
    """
    time.sleep(_SLEEP)
    results = semantic_search(topic, top_k=5)

    if not results:
        return (
            f"Semantic search for '{topic}' returned no results. "
            "Try a broader or different keyword."
        )

    lines = [f"Semantic search results for: '{topic}'"]
    for r in results:
        sim = f" | sim={r['similarity']:.3f}" if "similarity" in r else ""
        lines.append(
            f"  - [r/{r.get('subreddit', '?')}] ({r.get('date', '?')})"
            f" score={r.get('score', '?')}{sim}: {r.get('title', '?')}"
        )
    return "\n".join(lines)
