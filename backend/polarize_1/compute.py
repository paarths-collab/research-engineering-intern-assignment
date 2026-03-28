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
    """
    Return News Source Diversity (unique domains per subreddit).
    Calculated from flow_vectors: subreddit -> { domain: count, ... }
    """
    diversity = {}
    for sub, vector in store.flow_vectors.items():
        diversity[sub] = len(vector.keys())

    if not diversity:
        return []

    # Find max diversity for normalization (0-1 range for UI bars)
    max_div = max(diversity.values())
    norm_factor = max(max_div, 1)

    return [
        {
            "subreddit": s,
            "source_count": count,
            "score": round(count / norm_factor, 4)
        }
        for s, count in sorted(diversity.items(), key=lambda x: -x[1])
    ]


# ── Panel 2: Cosine Similarity Matrix ────────────────────────────────────────

def get_similarity_matrix(store: DataStore) -> dict:
    """
    Compute pairwise unique domain overlap across all subreddits.
    Returns: { subreddits: [...], matrix: [[int, ...], ...] }
    """
    subs = store.subreddits
    vecs = store.flow_vectors
    
    # Pre-calculate sets of domains for each subreddit
    sub_sets = {s: set(vecs[s].keys()) for s in subs}

    matrix = []
    for s1 in subs:
        row = []
        for s2 in subs:
            if s1 == s2:
                # Overlap with itself is the total count of unique domains
                row.append(len(sub_sets[s1]))
            else:
                # Count shared domains
                overlap = len(sub_sets[s1].intersection(sub_sets[s2]))
                row.append(overlap)
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

def get_top_domains(store: DataStore, subreddit: str, n: int = 20) -> List[dict]:
    """Return top n domains by raw reference count for a subreddit."""
    vector = store.flow_vectors.get(subreddit, {})
    if not vector:
        return []
        
    total_sub_links = sum(vector.values())
    sorted_domains = sorted(vector.items(), key=lambda x: -x[1])
    
    results = []
    for domain, count in sorted_domains[:n]:
        results.append({
            "domain": domain,
            "count": count,
            "category": store.domain_to_category.get(domain, "Uncategorized"),
            "p_sub": round(count / total_sub_links, 5) if total_sub_links > 0 else 0.0,
        })
    return results


# ── Treemap Payload Builder ───────────────────────────────────────────────────

from .analytics import build_treemap_payload, build_global_ecosystem_payload

def get_treemap_payload(store: DataStore, subreddit: str) -> dict:
    """
    Build a hierarchical payload for D3/Nivo Treemaps.
    Ensures ALL news channels are displayed, even with 0 mentions.
    """
    return build_treemap_payload(store, subreddit)


def get_global_ecosystem_payload(store: DataStore) -> dict:
    """
    Build a global hierarchy: Root -> Category -> Domain.
    Used for the "All Sources" global view with drill-down.
    """
    return build_global_ecosystem_payload(store)


# ── LLM Payload Builder ───────────────────────────────────────────────────────

def get_subreddit_summary_payload(store: DataStore, subreddit: str) -> dict:
    """
    Build the structured payload sent to the LLM.
    Contains exactly: echo score, top domains, category breakdown, similar subs.
    """
    echo = round(store.echo_scores.get(subreddit, 0.0), 2)
    top_doms = get_top_domains(store, subreddit, n=20)
    cat_breakdown = get_category_breakdown(store, subreddit)
    
    # Inject actual post data for the top 10 sources so the LLM has real context
    for d in top_doms:
        d["recent_titles"] = get_domain_posts(store, subreddit, d["domain"], limit=3)

    # Find top 3 most similar subreddits by domain overlap (excluding self)
    subs = store.subreddits
    vecs = store.flow_vectors
    sub_set = set(vecs[subreddit].keys())
    
    similarities = []
    for other in subs:
        if other == subreddit:
            continue
        other_set = set(vecs[other].keys())
        overlap = len(sub_set.intersection(other_set))
        if overlap > 0:
            similarities.append({"subreddit": other, "overlap": overlap})
    similarities.sort(key=lambda x: -x["overlap"])
    closest = similarities[:3]

    return {
        "subreddit": subreddit,
        "echo_score": echo,
        "top_domains": top_doms,
        "category_breakdown": cat_breakdown,
        "similar_subreddits": closest,
    }

def get_domain_posts(store: DataStore, subreddit: str, domain: str, limit: int = 50) -> List[dict]:
    """
    Retrieve up to `limit` post titles and urls for a specific subreddit and domain.
    Used for context-aware AI analysis.
    """
    if store.posts is None:
        return []
    
    # Filter by subreddit and domain
    mask = (store.posts["subreddit"] == subreddit) & (store.posts["domain"] == domain)
    subset = store.posts[mask].drop_duplicates(subset=["title"])
    
    # Return unique title and url pairs
    return subset[["title", "url"]].head(limit).to_dict("records")
