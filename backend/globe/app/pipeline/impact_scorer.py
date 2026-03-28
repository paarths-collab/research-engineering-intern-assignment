"""
Layer 7 — Impact Scoring Engine
Pure deterministic math. No LLM calls.
Combines news presence + engagement + velocity + risk weight.
Produces normalised 0-1 impact score + confidence level.
"""
from typing import List

from app.database.models import (
    StructuredEvent, NewsBundle, NarrativeIntel, RawPost, ImpactScore
)
from app.utils.logger import get_logger

logger = get_logger(__name__)

RISK_WEIGHTS = {"Low": 0.2, "Medium": 0.5, "High": 1.0}

# Confidence thresholds
CONF_HIGH_NEWS = 3
CONF_MED_NEWS = 1
CONF_HIGH_ENGAGEMENT = 500
CONF_MED_ENGAGEMENT = 100


def compute_impact_score(
    event: StructuredEvent,
    post: RawPost,
    bundle: NewsBundle,
    intel: NarrativeIntel,
) -> ImpactScore:
    # ── News presence score (0–0.40) ────────────────────────
    news_score = min(bundle.news_count / 7, 1.0) * 0.30
    trusted_bonus = min(bundle.trusted_source_count / 3, 1.0) * 0.10

    # ── Engagement score (0–0.30) ────────────────────────────
    raw_engagement = post.score + post.num_comments
    engagement_score = min(raw_engagement / 2000, 1.0) * 0.25

    # ── Velocity score (0–0.10) ──────────────────────────────
    velocity_score = min(post.velocity_score / 500, 1.0) * 0.10

    # ── Risk weight (0–0.20) ─────────────────────────────────
    risk_w = RISK_WEIGHTS.get(intel.risk_level, 0.2)
    risk_score = risk_w * 0.20

    # ── Sentiment modifier ───────────────────────────────────
    sentiment_mod = 0.0
    if intel.sentiment_label in ("negative", "mixed"):
        sentiment_mod = 0.05

    raw_impact = (
        news_score + trusted_bonus + engagement_score
        + velocity_score + risk_score + sentiment_mod
    )
    impact_value = round(min(raw_impact, 1.0), 4)

    # ── Confidence level ─────────────────────────────────────
    if bundle.trusted_source_count >= CONF_HIGH_NEWS and raw_engagement >= CONF_HIGH_ENGAGEMENT:
        confidence = "High"
    elif bundle.news_count >= CONF_MED_NEWS and raw_engagement >= CONF_MED_ENGAGEMENT:
        confidence = "Medium"
    else:
        confidence = "Low"

    score = ImpactScore(
        event_id=event.id,
        impact_value=impact_value,
        confidence_level=confidence,
    )
    logger.debug(
        f"IMPACT [{event.primary_location}]: {impact_value:.3f} / {confidence}"
    )
    return score


def score_all_events(
    events: List[StructuredEvent],
    posts_map: dict[str, RawPost],
    bundles_map: dict[str, NewsBundle],
    intel_map: dict[str, NarrativeIntel],
) -> List[ImpactScore]:
    scores = []
    for event in events:
        post = posts_map.get(event.post_id)
        bundle = bundles_map.get(event.id, NewsBundle(event_id=event.id))
        intel = intel_map.get(event.id)

        if not post or not intel:
            continue

        score = compute_impact_score(event, post, bundle, intel)
        scores.append(score)

    logger.info(f"Impact scoring complete — {len(scores)} scores")
    return scores
