"""
media_ecosystem.py — Dashboard analytics computed from Neon.

Replaces the old compute.py CSV-based approach.
All data comes from tables populated by ingest.py:
  - echo_chamber_scores
  - subreddit_domain_flow
  - top_distinctive_domains

Three analytical products:
  1. get_echo_scores()         → Panel 1 bar chart
  2. get_similarity_matrix()   → Panel 2 heatmap
  3. get_category_breakdown()  → Panel 3 source type composition
  4. get_top_domains()         → Panel 3 domain table
  5. build_llm_payload()       → Panel 4 AI brief input
"""

import math
from typing import Dict, List, Optional

from streamgraph2.data import db


# ── Panel 1: Echo Scores ──────────────────────────────────────

async def get_echo_scores() -> List[dict]:
    """Return all subreddit echo scores sorted by lift descending."""
    async with db.conn() as c:
        rows = await c.fetch(
            "SELECT subreddit, echo_score FROM echo_chamber_scores ORDER BY echo_score DESC"
        )
    return [{"subreddit": r["subreddit"], "lift": round(r["echo_score"], 4)} for r in rows]


# ── Panel 2: Cosine Similarity Matrix ────────────────────────

async def _load_flow_vectors() -> Dict[str, Dict[str, int]]:
    """Load all subreddit→domain counts from Neon into memory."""
    vectors: Dict[str, Dict[str, int]] = {}
    async with db.conn() as c:
        rows = await c.fetch("SELECT subreddit, domain, post_count FROM subreddit_domain_flow")
    for r in rows:
        sub = r["subreddit"]
        if sub not in vectors:
            vectors[sub] = {}
        vectors[sub][r["domain"]] = r["post_count"]
    return vectors


def _cosine(a: Dict[str, int], b: Dict[str, int]) -> float:
    if len(a) > len(b):
        a, b = b, a
    dot   = sum(a[d] * b[d] for d in a if d in b)
    mag_a = math.sqrt(sum(v * v for v in a.values()))
    mag_b = math.sqrt(sum(v * v for v in b.values()))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


async def get_similarity_matrix() -> dict:
    """
    Compute pairwise cosine similarity across all subreddits.
    Returns { subreddits: [...], matrix: [[float,...], ...] }
    """
    vecs = await _load_flow_vectors()
    subs = sorted(vecs.keys())

    matrix = []
    for s1 in subs:
        row = []
        for s2 in subs:
            sim = 1.0 if s1 == s2 else round(_cosine(vecs[s1], vecs[s2]), 4)
            row.append(sim)
        matrix.append(row)

    return {"subreddits": subs, "matrix": matrix}


# ── Panel 3a: Category Breakdown ─────────────────────────────

async def get_category_breakdown(subreddit: str) -> List[dict]:
    """Source type composition for one subreddit from Neon."""
    async with db.conn() as c:
        rows = await c.fetch("""
            SELECT category, SUM(count) AS total
            FROM top_distinctive_domains
            WHERE subreddit = $1
            GROUP BY category
            ORDER BY total DESC
        """, subreddit)

    if not rows:
        return []

    grand = sum(r["total"] for r in rows)
    return [
        {
            "cat"  : r["category"],
            "count": r["total"],
            "pct"  : round((r["total"] / grand) * 100, 1),
        }
        for r in rows
    ]


# ── Panel 3b: Top Distinctive Domains ────────────────────────

async def get_top_domains(subreddit: str, n: int = 5) -> List[dict]:
    """Top n domains by lift for a subreddit."""
    async with db.conn() as c:
        rows = await c.fetch("""
            SELECT domain, count, category, lift, p_domain_given_sub, p_domain_global
            FROM top_distinctive_domains
            WHERE subreddit = $1
            ORDER BY lift DESC
            LIMIT $2
        """, subreddit, n)

    return [
        {
            "domain"  : r["domain"],
            "count"   : r["count"],
            "category": r["category"],
            "lift"    : round(r["lift"], 3),
            "p_sub"   : round(r["p_domain_given_sub"], 5),
            "p_global": round(r["p_domain_global"], 5),
        }
        for r in rows
    ]


# ── All subreddits ────────────────────────────────────────────

async def get_all_subreddits() -> List[str]:
    """All subreddits present in the domain flow table."""
    async with db.conn() as c:
        rows = await c.fetch(
            "SELECT DISTINCT subreddit FROM subreddit_domain_flow ORDER BY subreddit"
        )
    return [r["subreddit"] for r in rows]


# ── LLM Payload Builder ───────────────────────────────────────

async def build_llm_payload(subreddit: str) -> dict:
    """
    Assemble structured metrics dict for the LLM intelligence brief.
    Sent to /media-brief endpoint.
    """
    vecs    = await _load_flow_vectors()
    echo_rows = await get_echo_scores()
    echo_score = next((e["lift"] for e in echo_rows if e["subreddit"] == subreddit), 0.0)

    top_domains   = await get_top_domains(subreddit, n=5)
    cat_breakdown = await get_category_breakdown(subreddit)

    # Nearest neighbors
    subs = [e["subreddit"] for e in echo_rows]
    sims = []
    for other in subs:
        if other == subreddit or other not in vecs or subreddit not in vecs:
            continue
        sim = round(_cosine(vecs[subreddit], vecs[other]), 3)
        if sim > 0.05:
            sims.append({"subreddit": other, "similarity": sim})
    sims.sort(key=lambda x: -x["similarity"])

    return {
        "subreddit"         : subreddit,
        "echo_score"        : round(echo_score, 2),
        "top_domains"       : top_domains,
        "category_breakdown": cat_breakdown,
        "similar_subreddits": sims[:3],
    }
