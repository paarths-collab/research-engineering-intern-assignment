"""
compute.py — All statistical computation.

Functions:
    get_echo_scores()           → sorted list of {subreddit, lift}
    get_similarity_matrix()     → cosine similarity matrix across all subreddits
    get_category_breakdown()    → source type distribution for one subreddit
    get_top_domains()           → top n distinctive domains by lift
    get_treemap_payload()       → hierarchical dict for Treemap visualization
    get_subreddit_summary_payload() → structured dict for LLM prompt
"""

import math
from collections import defaultdict
from typing import Dict, List, Any

from polarize_1.data_loader import DataStore


# ── Panel 1: Echo Scores ──────────────────────────────────────────────────────

def get_echo_scores(store: DataStore) -> List[dict]:
    """Return echo scores sorted by lift descending."""
    return [
        {"subreddit": s, "lift": round(v, 4)}
        for s, v in sorted(store.echo_scores.items(), key=lambda x: -x[1])
    ]


# ── Panel 2: Cosine Similarity Matrix ────────────────────────────────────────

def _magnitude(vec: Dict[str, int]) -> float:
    return math.sqrt(sum(v * v for v in vec.values()))


def _cosine(a: Dict[str, int], b: Dict[str, int]) -> float:
    # Only iterate over the smaller set for speed
    if len(a) > len(b):
        a, b = b, a
    dot = sum(a[d] * b[d] for d in a if d in b)
    mag_a = _magnitude(a)
    mag_b = _magnitude(b)
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def get_similarity_matrix(store: DataStore) -> dict:
    """
    Compute pairwise cosine similarity across all subreddits.
    Returns: { subreddits: [...], matrix: [[float, ...], ...] }
    """
    subs = store.subreddits
    vecs = store.flow_vectors

    # Memoize magnitudes
    mags = {s: _magnitude(vecs[s]) for s in subs}

    matrix = []
    for s1 in subs:
        row = []
        for s2 in subs:
            if s1 == s2:
                row.append(1.0)
            else:
                sim = _cosine(vecs[s1], vecs[s2])
                row.append(round(sim, 4))
        matrix.append(row)

    return {"subreddits": subs, "matrix": matrix}


# ── Panel 3: Category Breakdown ───────────────────────────────────────────────

def get_category_breakdown(store: DataStore, subreddit: str) -> List[dict]:
    """
    Aggregate distinctive domain counts by category for one subreddit.
    Returns: [{ cat, count, pct }, ...] sorted by pct desc
    """
    rows = store.distinctive.get(subreddit, [])
    if not rows:
        return []

    totals: Dict[str, int] = defaultdict(int)
    for r in rows:
        totals[r.category] += r.count

    grand = sum(totals.values())
    return sorted(
        [
            {"cat": cat, "count": cnt, "pct": round((cnt / grand) * 100, 1)}
            for cat, cnt in totals.items()
        ],
        key=lambda x: -x["pct"],
    )


# ── Top Distinctive Domains ───────────────────────────────────────────────────

def get_top_domains(store: DataStore, subreddit: str, n: int = 5) -> List[dict]:
    """Return top n domains by lift for a subreddit."""
    rows = sorted(store.distinctive.get(subreddit, []), key=lambda r: -r.lift)
    return [
        {
            "domain": r.domain,
            "count": r.count,
            "category": r.category,
            "lift": round(r.lift, 3),
            "p_sub": round(r.p_domain_given_sub, 5),
            "p_global": round(r.p_domain_global, 5),
        }
        for r in rows[:n]
    ]


# ── Treemap Payload Builder ───────────────────────────────────────────────────

def get_treemap_payload(store: DataStore, subreddit: str) -> dict:
    """
    Build a hierarchical payload for D3/Nivo Treemaps.
    Structure: Root -> Category -> Domain.
    """
    rows = store.distinctive.get(subreddit, [])
    if not rows:
        return {"name": "Media Ecosystem", "children": []}

    categories = defaultdict(list)
    for r in rows:
        categories[r.category].append({
            "name": r.domain,
            "loc": r.count,
            "lift": round(r.lift, 3),
            "p_sub": round(r.p_domain_given_sub, 5),
            "p_global": round(r.p_domain_global, 5)
        })

    children = []
    for cat_name, domains in categories.items():
        children.append({
            "name": cat_name,
            "children": domains
        })

    return {
        "name": "Media Ecosystem",
        "children": children
    }


# ── LLM Payload Builder ───────────────────────────────────────────────────────

def get_subreddit_summary_payload(store: DataStore, subreddit: str) -> dict:
    """
    Build the structured payload sent to the LLM.
    Contains exactly: echo score, top domains, category breakdown, similar subs.
    """
    echo = round(store.echo_scores.get(subreddit, 0.0), 2)
    top_doms = get_top_domains(store, subreddit, n=5)
    cat_breakdown = get_category_breakdown(store, subreddit)

    # Find top 3 most similar subreddits (excluding self)
    subs = store.subreddits
    vecs = store.flow_vectors
    similarities = []
    for other in subs:
        if other == subreddit:
            continue
        sim = round(_cosine(vecs[subreddit], vecs[other]), 3)
        if sim > 0.05:
            similarities.append({"subreddit": other, "similarity": sim})
    similarities.sort(key=lambda x: -x["similarity"])
    closest = similarities[:3]

    return {
        "subreddit": subreddit,
        "echo_score": echo,
        "top_domains": top_doms,
        "category_breakdown": cat_breakdown,
        "similar_subreddits": closest,
    }
