"""
hybrid/constants.py
--------------------
Single source of truth for all schema values, valid enums, and paths.
Every other file imports from here. Never hardcode values elsewhere.
"""

import os
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────────
BACKEND_DIR = Path(r"C:\Users\Paarth\Coding\simppl\research-engineering-intern-assignment\backend")
PROJECT_DIR = Path(r"C:\Users\Paarth\Coding\simppl\research-engineering-intern-assignment")

DATA_DIR = Path(
    os.getenv("DATA_DIR", r"C:\Users\Paarth\Coding\simppl\research-engineering-intern-assignment\data")
)

# ── Dataset bounds ─────────────────────────────────────────────────────────────
DATE_START = "2024-07-23"
DATE_END   = "2025-02-18"

# ── Valid subreddits (exact case as they appear in CSVs) ──────────────────────
VALID_SUBREDDITS: frozenset[str] = frozenset([
    "politics", "Conservative", "Anarchism", "Liberal", "Republican",
    "PoliticalDiscussion", "socialism", "worldpolitics", "democrats", "neoliberal"
])

# ── CSV filename -> DuckDB view name ──────────────────────────────────────────
CSV_TO_VIEW: dict[str, str] = {
    "author_amplification_summary.csv":    "author_amplification",
    "author_influence_profile.csv":        "author_influence",
    "bridge_authors_v2.csv":               "bridge_authors",
    "clean_posts.csv":                     "posts",
    "clean_top_distinctive_domains.csv":   "distinctive_domains",
    "clean_with_clusters_v2.csv":          "posts_with_clusters",
    "daily_volume_v2.csv":                 "daily_volume",
    "echo_chamber_scores.csv":             "echo_chamber_scores",
    "graph_edge_intelligence_table.csv":   "graph_edges",
    "ideological_distance_matrix.csv":     "ideological_distance",
    "narrative_diffusion_table.csv":       "narrative_diffusion",
    "narrative_intelligence_summary.csv":  "narrative_intelligence",
    "narrative_registry.csv":              "narrative_registry",
    "narrative_spread_chain_table.csv":    "narrative_spread_chains",
    "narrative_topic_mapping.csv":         "narrative_topic_mapping",
    "subreddit_domain_flow_v2.csv":        "subreddit_domain_flow",
    "subreddit_intelligence_summary.csv":  "subreddit_intelligence",
    "user_intelligence_summary.csv":       "user_intelligence",
    "amplification_event_table.csv":       "amplification_events",
}

# ── Table -> columns (authoritative) ─────────────────────────────────────────
TABLE_SCHEMA: dict[str, list[str]] = {
    "posts": [
        "id", "created_datetime", "subreddit", "author",
        "title", "domain", "score", "num_comments", "permalink", "url"
    ],
    "author_amplification": [
        "author", "total_relative_amplification", "amplification_events"
    ],
    "author_influence": [
        "author", "total_posts", "narratives_transported",
        "avg_ideological_distance_crossed", "total_amplification_generated",
        "final_influence_score"
    ],
    "bridge_authors": ["author", "subreddit", "post_count"],
    "posts_with_clusters": [
        "id", "created_datetime", "subreddit", "author", "title",
        "domain", "score", "num_comments", "permalink", "url", "duplicate_cluster_id"
    ],
    "daily_volume":        ["created_datetime", "post_count"],
    "echo_chamber_scores": ["subreddit", "lift"],
    "graph_edges": [
        "narrative_id", "cluster_id", "author", "subreddit", "title",
        "domain", "url", "permalink", "created_datetime", "score",
        "num_comments", "origin_subreddit", "hours_from_origin"
    ],
    "ideological_distance": ["subreddit_a", "subreddit_b", "ideological_distance"],
    "narrative_diffusion": [
        "narrative_id", "subreddit", "author",
        "order_of_appearance", "time_from_origin_hours"
    ],
    "narrative_intelligence": [
        "narrative_id", "total_posts_x", "unique_subreddits_x", "unique_authors",
        "first_seen_x", "last_seen", "cluster_id", "primary_domain",
        "representative_title", "spread_strength"
    ],
    "narrative_registry": [
        "narrative_id", "cluster_id", "primary_domain",
        "representative_title", "total_posts", "unique_subreddits", "first_seen"
    ],
    "narrative_spread_chains": ["narrative_id", "spread_sequence"],
    "narrative_topic_mapping": ["narrative_id", "topic_cluster", "topic_label"],
    "subreddit_domain_flow":   ["subreddit", "domain", "count"],
    "subreddit_intelligence": [
        "subreddit", "total_duplicate_posts", "unique_narratives",
        "unique_users", "avg_score", "domain", "lift"
    ],
    "user_intelligence": [
        "author", "total_duplicate_posts", "unique_narratives",
        "communities_active_in", "first_seen", "last_seen",
        "most_common_domain", "total_posts", "narratives_transported",
        "avg_ideological_distance_crossed", "total_relative_amplification",
        "final_influence_score"
    ],
    "amplification_events": [
        "author", "narrative_id", "from_sub", "to_sub",
        "time_delta_hours", "engagement_before", "engagement_after",
        "amplification_percentage"
    ],
    "distinctive_domains": [
        "subreddit", "domain", "count", "category", "sub_total",
        "domain_total", "p_domain_given_sub", "p_domain_global", "lift"
    ],
}

# ── Internal opaque keys (never quote as human-readable names) ────────────────
INTERNAL_KEY_COLUMNS: list[str] = [
    "narrative_id", "cluster_id", "duplicate_cluster_id", "internal_system_id"
]

# ── Valid influence metrics ───────────────────────────────────────────────────
VALID_INFLUENCE_METRICS: list[str] = [
    "final_influence_score", "total_relative_amplification",
    "narratives_transported", "avg_ideological_distance_crossed",
    "communities_active_in", "total_posts"
]

# ── Schema trimmer: keyword -> relevant tables ────────────────────────────────
TABLE_KEYWORDS: dict[str, list[str]] = {
    "influence":     ["author_influence", "user_intelligence"],
    "amplification": ["amplification_events", "author_amplification"],
    "bridge":        ["bridge_authors", "posts"],
    "narrative":     ["narrative_intelligence", "narrative_topic_mapping",
                      "narrative_registry", "narrative_diffusion"],
    "echo":          ["echo_chamber_scores", "subreddit_intelligence"],
    "ideological":   ["ideological_distance"],
    "spread":        ["narrative_spread_chains", "narrative_diffusion", "graph_edges"],
    "domain":        ["distinctive_domains", "subreddit_domain_flow"],
    "volume":        ["daily_volume"],
    "post":          ["posts", "posts_with_clusters"],
    "author":        ["user_intelligence", "author_influence", "author_amplification"],
    "subreddit":     ["subreddit_intelligence", "echo_chamber_scores"],
    "cluster":       ["posts_with_clusters", "narrative_intelligence"],
    "topic":         ["narrative_topic_mapping"],
    "score":         ["author_influence", "user_intelligence", "subreddit_intelligence"],
    "community":     ["user_intelligence", "bridge_authors", "ideological_distance"],
    "communities":   ["user_intelligence", "bridge_authors", "ideological_distance"],
}


def build_schema_string() -> str:
    return "\n".join(
        f"  {tbl}({', '.join(cols)})"
        for tbl, cols in TABLE_SCHEMA.items()
    )


def trim_schema(query: str) -> str:
    """Returns only the schema lines relevant to the query keywords."""
    q = query.lower()
    relevant: set[str] = {"posts"}
    for keyword, tables in TABLE_KEYWORDS.items():
        if keyword in q:
            relevant.update(tables)
    if len(relevant) <= 1:
        return build_schema_string()
    return "\n".join(
        f"  {tbl}({', '.join(cols)})"
        for tbl, cols in TABLE_SCHEMA.items()
        if tbl in relevant
    )


SCHEMA_STRING: str = build_schema_string()
VALID_SUBS_STR: str = ", ".join(sorted(VALID_SUBREDDITS))
