"""
agents/validator_agent.py — Structural correctness checker.

Checks:
  - Topics detected (count > 0)
  - All topic sizes > 0
  - News similarity scores reasonable
  - Sentiment percentages sum ≈ 100
  - Acceleration ratio computed
  - Minimum news count met

Returns: { status: 'pass'|'warn'|'fail', issues: [...] }
"""

from typing import Dict, List
from streamgraph2.data.config import AGENT_MIN_SIMILARITY, AGENT_WARN_SIMILARITY, AGENT_MIN_NEWS_COUNT


def validate(pipeline_result: Dict) -> Dict:
    issues  = []
    status  = "pass"

    topics    = pipeline_result.get("topics", [])
    matches   = pipeline_result.get("news_matches", [])
    sentiment = pipeline_result.get("sentiment", [])
    metrics   = pipeline_result.get("metrics", {})

    # ── Topic checks ─────────────────────────────────────────
    if not topics:
        issues.append("NO_TOPICS: BERTopic returned zero topics")
        status = "fail"
    else:
        zero_size = [t for t in topics if t.get("size", 0) == 0]
        if zero_size:
            issues.append(f"ZERO_SIZE_TOPICS: {len(zero_size)} topics have size=0")
            status = "warn"

    # ── News match checks ─────────────────────────────────────
    if not matches:
        issues.append("NO_MATCHES: No news matches were computed")
        status = "fail"
    else:
        unique_news = {m["headline"] for m in matches}
        if len(unique_news) < AGENT_MIN_NEWS_COUNT:
            issues.append(
                f"LOW_NEWS_COUNT: Only {len(unique_news)} unique news items "
                f"(minimum {AGENT_MIN_NEWS_COUNT})"
            )
            status = "warn" if status != "fail" else "fail"

        low_sim = [m for m in matches if m.get("similarity", 0) < AGENT_MIN_SIMILARITY]
        if len(low_sim) == len(matches):
            issues.append(
                f"ALL_LOW_SIMILARITY: All {len(matches)} matches below "
                f"threshold {AGENT_MIN_SIMILARITY}"
            )
            status = "fail"
        elif low_sim:
            issues.append(
                f"PARTIAL_LOW_SIMILARITY: {len(low_sim)}/{len(matches)} matches "
                f"below {AGENT_MIN_SIMILARITY}"
            )
            if status == "pass":
                status = "warn"

    # ── Sentiment checks ──────────────────────────────────────
    for day_sent in sentiment:
        total = (
            day_sent.get("negative", 0) +
            day_sent.get("neutral", 0) +
            day_sent.get("positive", 0)
        )
        if not (95 <= total <= 105):
            issues.append(
                f"SENTIMENT_SUM_ERROR: {day_sent.get('date')} sums to {total:.1f}% (expected ≈100)"
            )
            status = "warn" if status == "pass" else status

    if not sentiment:
        issues.append("NO_SENTIMENT: Sentiment evolution not computed")
        status = "warn" if status == "pass" else status

    # ── Acceleration check ────────────────────────────────────
    if not metrics or metrics.get("acceleration_ratio") is None:
        issues.append("NO_ACCELERATION: Volume acceleration not computed")
        status = "warn" if status == "pass" else status

    return {
        "agent"   : "validator",
        "status"  : status,
        "issues"  : issues,
        "passed"  : len(issues) == 0,
    }
