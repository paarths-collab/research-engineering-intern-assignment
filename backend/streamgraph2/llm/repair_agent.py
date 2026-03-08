"""
agents/repair_agent.py — Corrective action recommender.

Receives findings from validator and anomaly detector.
Outputs structured repair suggestions.

Agents do NOT directly modify database or rerun code.
They output: { issue_detected: bool, suggested_action: str, params: dict }
The pipeline interprets suggestions and optionally re-runs phases.
"""

from typing import Dict, List


# ── Action registry ───────────────────────────────────────────
# Maps issue codes → repair suggestions

REPAIR_MAP = {
    "NO_TOPICS": {
        "action": "rerun_topic_modeling",
        "params": {"reduce_min_topic_size_by": 2},
        "reason": "BERTopic returned no topics — lower min_topic_size and retry",
    },
    "SINGLE_TOPIC": {
        "action": "rerun_topic_modeling",
        "params": {"reduce_min_topic_size_by": 3},
        "reason": "Only one topic found — reduce cluster granularity threshold",
    },
    "DOMINANT_TOPIC": {
        "action": "rerun_topic_modeling",
        "params": {"reduce_min_topic_size_by": 2},
        "reason": "One topic dominates — loosen clustering to reveal sub-narratives",
    },
    "NO_MATCHES": {
        "action": "rerun_news_fetch",
        "params": {"expand_limit_by": 50},
        "reason": "No news matches — fetch more headlines",
    },
    "LOW_NEWS_COUNT": {
        "action": "rerun_news_fetch",
        "params": {"expand_limit_by": 30},
        "reason": "Too few news items — increase fetch limit",
    },
    "ALL_LOW_SIMILARITY": {
        "action": "lower_similarity_threshold",
        "params": {"new_threshold": 0.25},
        "reason": "All similarities low — lower threshold or expand news corpus",
    },
    "VERY_LOW_MAX_SIMILARITY": {
        "action": "rerun_news_fetch_with_broader_query",
        "params": {"expand_categories": True},
        "reason": "Best match still very low — try broader news query terms",
    },
    "NO_SENTIMENT": {
        "action": "expand_reddit_enrichment",
        "params": {"expand_window_days": 2},
        "reason": "No text for sentiment — expand enrichment window",
    },
    "NO_ACCELERATION": {
        "action": "check_baseline_data",
        "params": {},
        "reason": "Baseline missing — verify posts exist for day-before date",
    },
}


def suggest_repairs(
    validation_result: Dict,
    anomaly_result: Dict,
) -> Dict:
    """
    Takes output from validator and anomaly detector.
    Returns prioritized list of repair actions.
    """
    suggestions = []
    seen_actions = set()

    all_codes = (
        [issue for issue in validation_result.get("issues", [])]
        + [a["code"] for a in anomaly_result.get("anomalies", [])]
    )

    for code in all_codes:
        # Extract code prefix (strip detail text)
        clean_code = code.split(":")[0].strip()
        repair = REPAIR_MAP.get(clean_code)
        if repair and repair["action"] not in seen_actions:
            suggestions.append({
                "issue_code": clean_code,
                "action"    : repair["action"],
                "params"    : repair["params"],
                "reason"    : repair["reason"],
            })
            seen_actions.add(repair["action"])

    # Overall assessment
    has_failures = (
        validation_result.get("status") == "fail" or
        anomaly_result.get("status") == "fail"
    )
    has_warnings = (
        validation_result.get("status") == "warn" or
        anomaly_result.get("status") == "warn"
    )

    if has_failures:
        overall = "critical — output should not be finalized without repair"
    elif has_warnings:
        overall = "degraded — output is usable but confidence is reduced"
    else:
        overall = "healthy — proceed to brief generation"

    return {
        "agent"            : "repair",
        "issue_detected"   : len(suggestions) > 0,
        "repair_required"  : has_failures,
        "overall_assessment": overall,
        "suggestions"      : suggestions,
    }
