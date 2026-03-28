"""
agents/anomaly_agent.py — Statistical logic anomaly detector.

Looks for logical inconsistencies that pass structural validation
but indicate modeling problems:

  - All posts in noise topic → clustering failure
  - One topic dominating > threshold → low diversity signal
  - All similarity scores near-zero → embedding mismatch
  - No negative sentiment change during spike → unusual
  - Acceleration near 1.0 but spike was detected → data inconsistency
"""

from typing import Dict, List
from streamgraph2.data.config import AGENT_WARN_SIMILARITY, AGENT_MAX_DOMINANT_TOPIC


def detect_anomalies(pipeline_result: Dict) -> Dict:
    anomalies = []
    status    = "pass"

    topics    = pipeline_result.get("topics", [])
    matches   = pipeline_result.get("news_matches", [])
    sentiment = pipeline_result.get("sentiment", [])
    metrics   = pipeline_result.get("metrics", {})

    # ── Topic anomalies ───────────────────────────────────────
    if topics:
        dominant = max(topics, key=lambda t: t.get("size_percent", 0))
        dom_pct  = dominant.get("size_percent", 0)

        if dom_pct > AGENT_MAX_DOMINANT_TOPIC:
            anomalies.append({
                "code"   : "DOMINANT_TOPIC",
                "detail" : f"Topic {dominant['topic_id']} captures {dom_pct:.1f}% of posts — "
                           "clustering may be too coarse"
            })
            status = "warn"

        if len(topics) == 1:
            anomalies.append({
                "code"   : "SINGLE_TOPIC",
                "detail" : "Only one topic found — BERTopic may need lower min_topic_size"
            })
            status = "warn"

    # ── Similarity anomalies ──────────────────────────────────
    if matches:
        avg_sim = sum(m.get("similarity", 0) for m in matches) / len(matches)
        if avg_sim < AGENT_WARN_SIMILARITY:
            anomalies.append({
                "code"   : "LOW_AVERAGE_SIMILARITY",
                "detail" : f"Average similarity {avg_sim:.3f} below warn threshold "
                           f"{AGENT_WARN_SIMILARITY} — news corpus may be too narrow"
            })
            status = "warn"

        max_sim = max(m.get("similarity", 0) for m in matches)
        if max_sim < 0.35:
            anomalies.append({
                "code"   : "VERY_LOW_MAX_SIMILARITY",
                "detail" : f"Best match similarity only {max_sim:.3f} — "
                           "topic and news embeddings may be from different domains"
            })
            status = "fail"

    # ── Sentiment anomalies ───────────────────────────────────
    if len(sentiment) >= 2:
        baseline_neg = sentiment[0].get("negative", 0)
        spike_neg    = sentiment[1].get("negative", 0)

        if spike_neg < baseline_neg - 5:
            anomalies.append({
                "code"   : "NEGATIVE_SENTIMENT_DECREASED",
                "detail" : f"Negative sentiment dropped {baseline_neg:.1f}% → {spike_neg:.1f}% "
                           "during spike — unexpected pattern"
            })
            if status == "pass":
                status = "warn"

    # ── Acceleration anomalies ────────────────────────────────
    ratio = (metrics or {}).get("acceleration_ratio")
    if ratio is not None:
        if 0.9 <= ratio <= 1.1:
            anomalies.append({
                "code"   : "NEAR_ZERO_ACCELERATION",
                "detail" : f"Acceleration ratio {ratio:.3f} near 1.0 — "
                           "spike classification may be a false positive"
            })
            if status == "pass":
                status = "warn"

        if ratio > 10:
            anomalies.append({
                "code"   : "EXTREME_ACCELERATION",
                "detail" : f"Acceleration ratio {ratio:.1f}× — "
                           "verify baseline date has sufficient data"
            })
            if status == "pass":
                status = "warn"

    return {
        "agent"    : "anomaly_detector",
        "status"   : status,
        "anomalies": anomalies,
        "clean"    : len(anomalies) == 0,
    }
