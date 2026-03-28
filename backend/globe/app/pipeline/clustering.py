"""
Layer 8 — Event Clustering
Prevents duplicate pins for the same event.
Clusters deterministically by primary location.
"""
import uuid
import json
from collections import Counter
from typing import List

from app.database.models import (
    StructuredEvent, NarrativeIntel, ImpactScore, RawPost,
    NewsBundle, EventCluster, ResolvedLocation
)
from app.database.connection import get_connection
from app.utils.logger import get_logger

logger = get_logger(__name__)


def _location_key(loc_name: str) -> str:
    """Normalise location name for grouping."""
    parts = loc_name.lower().split(",")
    return parts[0].strip()


def _dominant_sentiment(sentiments: List[str]) -> str:
    if not sentiments:
        return "neutral"
    return Counter(sentiments).most_common(1)[0][0]


def _escalation_level(avg_impact: float, risk: str) -> str:
    if risk == "High" or avg_impact > 0.6:
        return "Escalating"
    if risk == "Medium" or avg_impact > 0.3:
        return "Active"
    return "Emerging"


def _build_cluster(
    group_events: List[StructuredEvent],
    geo_map: dict[str, ResolvedLocation],
    posts_map: dict[str, RawPost],
    intel_map: dict[str, NarrativeIntel],
    scores_map: dict[str, ImpactScore],
    bundles_map: dict[str, NewsBundle],
) -> EventCluster:
    post_ids = [e.post_id for e in group_events]
    primary_loc = group_events[0].primary_location

    # Coordinates — use first resolved location
    loc = geo_map.get(primary_loc)
    lat = loc.lat if loc else 0.0
    lon = loc.lon if loc else 0.0

    # Impact
    impact_vals = [
        scores_map[e.id].impact_value
        for e in group_events
        if e.id in scores_map
    ]
    avg_impact = round(sum(impact_vals) / len(impact_vals), 4) if impact_vals else 0.0

    # Sentiment
    sentiments = [
        intel_map[e.id].sentiment_label
        for e in group_events
        if e.id in intel_map
    ]
    dom_sentiment = _dominant_sentiment(sentiments)

    # Risk — take max
    risk_priority = {"Low": 0, "Medium": 1, "High": 2}
    risks = [intel_map[e.id].risk_level for e in group_events if e.id in intel_map]
    risk_level = max(risks, key=lambda r: risk_priority.get(r, 0)) if risks else "Low"

    # Summary — pick from highest impact intel
    best_event = max(group_events, key=lambda e: scores_map.get(e.id, ImpactScore(
        event_id=e.id, impact_value=0)).impact_value)
    best_intel = intel_map.get(best_event.id)
    summary = best_intel.summary if best_intel else ""
    strategic = best_intel.strategic_implications if best_intel else []

    # News count
    news_total = sum(
        bundles_map.get(e.id, NewsBundle(event_id=e.id)).news_count
        for e in group_events
    )
    trusted_total = sum(
        bundles_map.get(e.id, NewsBundle(event_id=e.id)).trusted_source_count
        for e in group_events
    )

    # Confidence
    if trusted_total >= 3:
        confidence = "High"
    elif news_total >= 1:
        confidence = "Medium"
    else:
        confidence = "Low"

    from datetime import date
    return EventCluster(
        cluster_id=str(uuid.uuid4()),
        post_ids=post_ids,
        primary_location=primary_loc,
        lat=lat,
        lon=lon,
        average_impact=avg_impact,
        dominant_sentiment=dom_sentiment,
        risk_level=risk_level,
        escalation_level=_escalation_level(avg_impact, risk_level),
        summary=summary,
        strategic_implications=strategic,
        news_count=news_total,
        confidence=confidence,
        run_date=str(date.today()),
    )


def cluster_events(
    events: List[StructuredEvent],
    geo_map: dict[str, ResolvedLocation],
    posts_map: dict[str, RawPost],
    intel_map: dict[str, NarrativeIntel],
    scores_map: dict[str, ImpactScore],
    bundles_map: dict[str, NewsBundle],
) -> List[EventCluster]:
    if not events:
        return []

    # Strategy 6: Location Level Intelligence
    # Group events deterministically by primary_location
    groups: dict[str, List[StructuredEvent]] = {}
    for e in events:
        loc = e.primary_location
        if not loc:
            loc = "Unknown Location"
        groups.setdefault(loc, []).append(e)

    clusters = []
    for loc, group_events in groups.items():
        cluster = _build_cluster(
            group_events, geo_map, posts_map, intel_map, scores_map, bundles_map
        )
        clusters.append(cluster)

    clusters.sort(key=lambda c: c.average_impact, reverse=True)
    logger.info(f"Clustering map complete — {len(clusters)} locations from {len(events)} events")

    _persist_clusters(clusters)
    return clusters




def _persist_clusters(clusters: List[EventCluster]) -> None:
    conn = get_connection()
    for c in clusters:
        conn.execute("""
            INSERT OR REPLACE INTO event_clusters
            (cluster_id, post_ids, primary_location, lat, lon,
             average_impact, dominant_sentiment, risk_level, escalation_level,
             summary, strategic_implications, news_count, confidence, run_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            c.cluster_id, json.dumps(c.post_ids), c.primary_location,
            c.lat, c.lon, c.average_impact, c.dominant_sentiment,
            c.risk_level, c.escalation_level, c.summary,
            json.dumps(c.strategic_implications),
            c.news_count, c.confidence, c.run_date,
        ])
