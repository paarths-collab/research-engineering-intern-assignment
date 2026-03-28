"""
Tests — Layer 7: Impact Scoring
"""
import pytest
from app.pipeline.impact_scorer import compute_impact_score, score_all_events, RISK_WEIGHTS
from app.database.models import StructuredEvent, RawPost, NewsBundle, NewsArticle, NarrativeIntel, ImpactScore
import time


def _make_post(post_id, score=1000, comments=300):
    return RawPost(
        id=post_id, title="Test", subreddit="worldnews",
        score=score, num_comments=comments,
        created_utc=time.time() - 3600,
        engagement_score=score * 0.6 + comments * 0.4,
        velocity_score=score / 1.0,
    )


def _make_event(event_id, post_id):
    return StructuredEvent(
        id=event_id, post_id=post_id, event_type="conflict",
        primary_location="Tehran, Iran",
    )


def _make_bundle(event_id, news_count=3, trusted=2):
    articles = [
        NewsArticle(
            id=f"a{i}", event_id=event_id,
            title=f"News {i}", url=f"https://reuters.com/news/{i}",
            is_trusted=(i < trusted),
        )
        for i in range(news_count)
    ]
    return NewsBundle(
        event_id=event_id,
        articles=articles,
        news_count=news_count,
        trusted_source_count=trusted,
    )


def _make_intel(event_id, risk="Medium", sentiment="negative"):
    return NarrativeIntel(
        event_id=event_id,
        summary="Test summary",
        risk_level=risk,
        sentiment_label=sentiment,
        sentiment_confidence=0.8,
    )


class TestRiskWeights:
    def test_high_risk_weight_is_greatest(self):
        assert RISK_WEIGHTS["High"] > RISK_WEIGHTS["Medium"] > RISK_WEIGHTS["Low"]


class TestComputeImpactScore:
    def test_high_news_high_engagement_high_score(self):
        event = _make_event("e1", "p1")
        post = _make_post("p1", score=5000, comments=1000)
        bundle = _make_bundle("e1", news_count=7, trusted=4)
        intel = _make_intel("e1", risk="High")
        score = compute_impact_score(event, post, bundle, intel)
        assert score.impact_value > 0.5
        assert score.confidence_level == "High"

    def test_no_news_low_score(self):
        event = _make_event("e1", "p1")
        post = _make_post("p1", score=100, comments=10)
        bundle = NewsBundle(event_id="e1", news_count=0, trusted_source_count=0)
        intel = _make_intel("e1", risk="Low", sentiment="neutral")
        score = compute_impact_score(event, post, bundle, intel)
        assert score.impact_value < 0.2
        assert score.confidence_level == "Low"

    def test_impact_value_in_range(self):
        event = _make_event("e1", "p1")
        post = _make_post("p1", score=99999, comments=99999)
        bundle = _make_bundle("e1", news_count=7, trusted=7)
        intel = _make_intel("e1", risk="High", sentiment="negative")
        score = compute_impact_score(event, post, bundle, intel)
        assert 0.0 <= score.impact_value <= 1.0

    def test_medium_confidence_threshold(self):
        event = _make_event("e1", "p1")
        post = _make_post("p1", score=200, comments=50)
        bundle = _make_bundle("e1", news_count=2, trusted=1)
        intel = _make_intel("e1", risk="Medium")
        score = compute_impact_score(event, post, bundle, intel)
        assert score.confidence_level in ("Medium", "High")


class TestScoreAllEvents:
    def test_score_all_returns_correct_count(self, sample_events, sample_posts, sample_bundles, sample_intel):
        posts_map = {p.id: p for p in sample_posts}
        bundles_map = {b.event_id: b for b in sample_bundles}
        intel_map = {i.event_id: i for i in sample_intel}
        scores = score_all_events(sample_events, posts_map, bundles_map, intel_map)
        assert len(scores) == len(sample_events)

    def test_all_scores_valid(self, sample_events, sample_posts, sample_bundles, sample_intel):
        posts_map = {p.id: p for p in sample_posts}
        bundles_map = {b.event_id: b for b in sample_bundles}
        intel_map = {i.event_id: i for i in sample_intel}
        scores = score_all_events(sample_events, posts_map, bundles_map, intel_map)
        for s in scores:
            assert 0.0 <= s.impact_value <= 1.0
            assert s.confidence_level in ("Low", "Medium", "High")
